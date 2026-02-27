// SPDX-License-Identifier: GPL-2.0
/*
 * SPBM Telemetry Reader v4 - Confirmed live power readings
 *
 * The SPBM shared memory lives at MTEL region 2: 0x1C238000 (4KB).
 * This is the second memory region of the MTEL (NVDA8800) ACPI device.
 *
 * Reads twice with a 1-second delay to prove telemetry is live.
 *
 * Units: milliwatts (mW) based on analysis (e.g., GPU_OUT=4784
 * matches nvidia-smi 4.28W, PL1=140000 = 140W Spark TDP).
 *
 * ALL READS ONLY. No writes, no doorbells, no SMC calls.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/delay.h>

#define SPBM_PHYS	0x1C238000
#define SPBM_SIZE	0x1000

#define R(b, o) ioread32((b) + (o))

struct te_entry {
	u32 off;
	const char *name;
};

static const struct te_entry telemetry[] = {
	{ 0x300, "SYS_TOTAL" },
	{ 0x304, "SOC_PKG" },
	{ 0x308, "C_AND_G" },
	{ 0x30C, "CPU_P" },
	{ 0x310, "CPU_E" },
	{ 0x314, "VCORE" },
	{ 0x318, "VDDQ" },
	{ 0x31C, "CHR" },
	{ 0x320, "GPC_OUT" },
	{ 0x324, "TOTAL_GPU_OUT" },
	{ 0x328, "GPC_IN" },
	{ 0x32C, "TOTAL_GPU_IN" },
	{ 0x330, "TOTAL_SYS_IN" },
	{ 0x334, "DLA_IN" },
	{ 0x338, "PREREG_IN" },
	{ 0x33C, "DLA_OUT" },
};

static const struct te_entry energy[] = {
	{ 0x344, "PKG_ENERGY" },
	{ 0x350, "CPU_E_ENERGY" },
	{ 0x35C, "CPU_P_ENERGY" },
	{ 0x368, "GPC_ENERGY" },
	{ 0x374, "GPM_ENERGY" },
};

static void read_snapshot(void __iomem *base, u32 *te_vals, u32 *en_vals)
{
	int i;
	for (i = 0; i < ARRAY_SIZE(telemetry); i++)
		te_vals[i] = R(base, telemetry[i].off);
	for (i = 0; i < ARRAY_SIZE(energy); i++)
		en_vals[i] = R(base, energy[i].off);
}

static int __init spbm_read_init(void)
{
	void __iomem *base;
	u32 te1[16], te2[16], en1[5], en2[5];
	int i;

	pr_info("spbm_read: SPBM Live Telemetry v4 @ 0x%08x\n", SPBM_PHYS);

	base = ioremap(SPBM_PHYS, SPBM_SIZE);
	if (!base) {
		pr_err("spbm_read: ioremap failed\n");
		return -ENODEV;
	}

	/* === Power Limits === */
	pr_info("spbm_read: === Power Limits (mW) ===\n");
	pr_info("spbm_read: PL (EC):   PL1=%u PL2=%u PL3=%u PL4=%u\n",
		R(base, 0x120), R(base, 0x124), R(base, 0x128), R(base, 0x12C));
	pr_info("spbm_read: PL (UEFI): PL1=%u PL2=%u PL3=%u PL4=%u\n",
		R(base, 0x140), R(base, 0x144), R(base, 0x148), R(base, 0x14C));
	pr_info("spbm_read: PL (OS):   PL1=%u PL2=%u PL3=%u PL4=%u\n",
		R(base, 0x100), R(base, 0x104), R(base, 0x108), R(base, 0x10C));
	pr_info("spbm_read: PL (eff):  PL1=%u PL2=%u PL3=%u PL4=%u\n",
		R(base, 0x160), R(base, 0x164), R(base, 0x168), R(base, 0x16C));
	pr_info("spbm_read: SYSPL:     1=%u 2=%u 3=%u 4=%u\n",
		R(base, 0x170), R(base, 0x174), R(base, 0x178), R(base, 0x17C));

	/* === Status === */
	pr_info("spbm_read: Status: winner=%u lock=%u level=0x%x prochot=0x%x\n",
		R(base, 0x08), R(base, 0x0C), R(base, 0x48), R(base, 0x4C));

	/* === Budget === */
	pr_info("spbm_read: Budget: CPU=%u GPU=%u CPU_E=%u CPU_P=%u\n",
		R(base, 0x600), R(base, 0x604), R(base, 0x680), R(base, 0x684));
	pr_info("spbm_read: Budgeter: loop=%u w1=%u w2=%u\n",
		R(base, 0x500), R(base, 0x504), R(base, 0x508));

	/* === Snapshot 1 === */
	read_snapshot(base, te1, en1);
	pr_info("spbm_read: === Telemetry Snapshot 1 ===\n");
	for (i = 0; i < ARRAY_SIZE(telemetry); i++)
		pr_info("spbm_read:   %-16s %6u mW  (%u.%03u W)\n",
			telemetry[i].name, te1[i],
			te1[i] / 1000, te1[i] % 1000);
	pr_info("spbm_read: Energy counters:\n");
	for (i = 0; i < ARRAY_SIZE(energy); i++)
		pr_info("spbm_read:   %-16s %u\n", energy[i].name, en1[i]);

	/* === Wait 1 second === */
	msleep(1000);

	/* === Snapshot 2 === */
	read_snapshot(base, te2, en2);
	pr_info("spbm_read: === Telemetry Snapshot 2 (after 1s) ===\n");
	for (i = 0; i < ARRAY_SIZE(telemetry); i++) {
		s32 diff = (s32)te2[i] - (s32)te1[i];
		pr_info("spbm_read:   %-16s %6u mW  (delta=%+d)\n",
			telemetry[i].name, te2[i], diff);
	}
	pr_info("spbm_read: Energy deltas (≈ mJ over 1s ≈ mW avg):\n");
	for (i = 0; i < ARRAY_SIZE(energy); i++) {
		u32 diff = en2[i] - en1[i];
		pr_info("spbm_read:   %-16s delta=%u (was %u, now %u)\n",
			energy[i].name, diff, en1[i], en2[i]);
	}

	iounmap(base);
	pr_info("spbm_read: Done.\n");
	return -ENODEV;
}

static void __exit spbm_read_exit(void) {}

module_init(spbm_read_init);
module_exit(spbm_read_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("DGX Spark Power Telemetry");
MODULE_DESCRIPTION("Live SPBM telemetry reader for NVIDIA DGX Spark (GB10)");
