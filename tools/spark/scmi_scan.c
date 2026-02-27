// SPDX-License-Identifier: GPL-2.0
/*
 * SCMI Doorbell Scanner v3 - Targeted
 *
 * Tests only the known-accepted SMC function IDs discovered by the
 * previous wide scan. Uses msleep() to avoid soft lockups.
 *
 * Known accepted SiP SMC IDs (returned a0=0, not NOT_SUPPORTED):
 *   0x121, 0x202, 0x205, 0x273, 0x506, 0x514,
 *   0x515 (a0=3), 0x517, 0x51E, 0x523, 0x5F0
 *
 * Tests each ID as SCMI doorbell on all 4 channels with various args.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/delay.h>
#include <linux/arm-smccc.h>

/* SCMI channel addresses from ACPI DSDT (NVDA8200 / SCP0) */
#define SCMI_SHMEM_BASE		0x1A800000
#define SCMI_SHMEM_SIZE		0x80000
#define SCMI_CH_A_BASE		0x1AB20000
#define SCMI_CH_A_SIZE		0x1000
#define SCMI_CH_B_BASE		0x1AAA0000
#define SCMI_CH_B_SIZE		0x1000
#define SCMI_CH_C_BASE		0x1AAB0000
#define SCMI_CH_C_SIZE		0x1000

/* SCMI Shared Memory offsets */
#define SHMEM_CHAN_STAT		0x04
#define SHMEM_FLAGS		0x10
#define SHMEM_LENGTH		0x14
#define SHMEM_MSG_HDR		0x18
#define SHMEM_MSG_PAYLOAD	0x1C

#define SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE	BIT(0)
#define SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR	BIT(1)

#define MSG_ID_MASK		GENMASK(7, 0)
#define MSG_TYPE_MASK		GENMASK(9, 8)
#define MSG_PROTO_ID_MASK	GENMASK(17, 10)
#define MSG_TOKEN_MASK		GENMASK(27, 18)

#define PACK_MSG_HDR(id, type, proto, token) \
	(FIELD_PREP(MSG_ID_MASK, (id)) | \
	 FIELD_PREP(MSG_TYPE_MASK, (type)) | \
	 FIELD_PREP(MSG_PROTO_ID_MASK, (proto)) | \
	 FIELD_PREP(MSG_TOKEN_MASK, (token)))

/* Known-accepted SMC function IDs from the wide scan */
static const u16 accepted_ids[] = {
	0x121, 0x202, 0x205, 0x273,
	0x506, 0x514, 0x515, 0x517,
	0x51E, 0x523, 0x5F0,
};

struct channel_info {
	phys_addr_t phys;
	u32 size;
	const char *name;
};

static const struct channel_info channels[] = {
	{ SCMI_SHMEM_BASE, SCMI_SHMEM_SIZE, "SHMEM_BASE" },
	{ SCMI_CH_A_BASE,  SCMI_CH_A_SIZE,  "CH_A" },
	{ SCMI_CH_B_BASE,  SCMI_CH_B_SIZE,  "CH_B" },
	{ SCMI_CH_C_BASE,  SCMI_CH_C_SIZE,  "CH_C" },
};

/*
 * Prepare SCMI Base Protocol VERSION message in shmem.
 */
static void prepare_msg(void __iomem *shmem, u16 token)
{
	/* Reset channel */
	iowrite32(SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE,
		  shmem + SHMEM_CHAN_STAT);
	wmb();
	msleep(5);

	/* Base Protocol VERSION (proto=0x10, msg=0x0) */
	iowrite32(4, shmem + SHMEM_LENGTH);
	iowrite32(PACK_MSG_HDR(0x0, 0, 0x10, token), shmem + SHMEM_MSG_HDR);
	iowrite32(0, shmem + SHMEM_FLAGS);
	iowrite32(0, shmem + SHMEM_CHAN_STAT);
	wmb();
}

/*
 * Check for response. Uses msleep() to be scheduler-friendly.
 */
static int check_resp(void __iomem *shmem, int wait_ms)
{
	u32 status;
	int elapsed = 0;

	while (elapsed < wait_ms) {
		msleep(5);
		elapsed += 5;
		status = ioread32(shmem + SHMEM_CHAN_STAT);
		if (status & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE)
			return (status & SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR)
				? -EIO : 0;
	}
	return -ETIMEDOUT;
}

static void report_hit(void __iomem *shmem, u32 func_id,
		       const char *ch_name, const char *desc)
{
	u32 rlen = ioread32(shmem + SHMEM_LENGTH);
	u32 rhdr = ioread32(shmem + SHMEM_MSG_HDR);
	u32 pay0 = ioread32(shmem + SHMEM_MSG_PAYLOAD);
	u32 pay1 = ioread32(shmem + SHMEM_MSG_PAYLOAD + 4);

	pr_info("scmi_scan: *** HIT on %s! SMC 0x%08x %s ***\n",
		ch_name, func_id, desc);
	pr_info("scmi_scan:   len=%u hdr=0x%08x payload=[0x%08x, 0x%08x]\n",
		rlen, rhdr, pay0, pay1);
}

static int __init scmi_scan_init(void)
{
	void __iomem *ch_map[4] = {};
	int ci, si;
	int ret;
	struct arm_smccc_res res;

	pr_info("scmi_scan: Targeted SCMI doorbell test (v3)\n");
	pr_info("scmi_scan: Testing %zu known SMC IDs x %d channels\n",
		ARRAY_SIZE(accepted_ids), (int)ARRAY_SIZE(channels));

	/* Map all channels */
	for (ci = 0; ci < ARRAY_SIZE(channels); ci++) {
		ch_map[ci] = ioremap(channels[ci].phys, channels[ci].size);
		if (!ch_map[ci])
			pr_warn("scmi_scan: Failed to map %s\n",
				channels[ci].name);
	}

	/*
	 * For each channel, try each accepted SMC ID with several
	 * argument patterns. Use msleep between tests.
	 */
	for (ci = 0; ci < ARRAY_SIZE(channels); ci++) {
		if (!ch_map[ci])
			continue;

		pr_info("scmi_scan: --- Testing %s @ 0x%llx ---\n",
			channels[ci].name, (u64)channels[ci].phys);

		for (si = 0; si < ARRAY_SIZE(accepted_ids); si++) {
			u32 fid64 = 0xC2000000 | accepted_ids[si];

			/* Test 1: SMC64 with no args */
			prepare_msg(ch_map[ci], (ci << 8) | (si << 4) | 1);
			arm_smccc_smc(fid64, 0, 0, 0, 0, 0, 0, 0, &res);
			ret = check_resp(ch_map[ci], 100);
			if (ret == 0) {
				report_hit(ch_map[ci], fid64,
					   channels[ci].name, "args(0,0,0)");
				goto done;
			}
			msleep(10);

			/* Test 2: SMC64 with channel phys addr as a1 */
			prepare_msg(ch_map[ci], (ci << 8) | (si << 4) | 2);
			arm_smccc_smc(fid64, channels[ci].phys, 0, 0,
				      0, 0, 0, 0, &res);
			ret = check_resp(ch_map[ci], 100);
			if (ret == 0) {
				report_hit(ch_map[ci], fid64,
					   channels[ci].name, "args(phys,0,0)");
				goto done;
			}
			msleep(10);

			/* Test 3: SMC64 with channel index as a1 */
			prepare_msg(ch_map[ci], (ci << 8) | (si << 4) | 3);
			arm_smccc_smc(fid64, ci, 0, 0, 0, 0, 0, 0, &res);
			ret = check_resp(ch_map[ci], 100);
			if (ret == 0) {
				report_hit(ch_map[ci], fid64,
					   channels[ci].name, "args(idx,0,0)");
				goto done;
			}
			msleep(10);

			pr_info("scmi_scan: %s SMC 0x%08x: no response "
				"(smc_ret=0x%lx)\n",
				channels[ci].name, fid64, res.a0);
		}
	}

	pr_info("scmi_scan: No working doorbell found across all channels.\n");

done:
	for (ci = 0; ci < ARRAY_SIZE(channels); ci++) {
		if (ch_map[ci])
			iounmap(ch_map[ci]);
	}

	pr_info("scmi_scan: Scan complete.\n");
	return -ENODEV;
}

static void __exit scmi_scan_exit(void) {}

module_init(scmi_scan_init);
module_exit(scmi_scan_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("DGX Spark Doorbell Scanner");
MODULE_DESCRIPTION("Targeted SCMI doorbell scan for NVIDIA DGX Spark");
