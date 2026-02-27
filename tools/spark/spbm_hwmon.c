// SPDX-License-Identifier: GPL-2.0
/*
 * NVIDIA DGX Spark (GB10) SPBM Power Telemetry hwmon driver
 *
 * Exposes the System Power Budget Manager (SPBM) shared memory as
 * standard Linux hwmon sensors. The SPBM region is at physical address
 * 0x1C238000 (4KB), the second memory resource of the MTEL (NVDA8800)
 * ACPI device.
 *
 * The SPBM firmware (running on MediaTek SSPM) continuously updates
 * these registers with live power telemetry in milliwatts and
 * cumulative energy counters in millijoules.
 *
 * Since the NVDA8800 ACPI device is stuck in waiting_for_supplier
 * (no Linux driver for its dependencies), this module directly
 * ioremaps the known physical address.
 *
 * Usage:
 *   sudo insmod spbm_hwmon.ko
 *   sensors spbm-*
 *   cat /sys/class/hwmon/hwmonN/power1_input   # microwatts
 *
 * Discovered by reverse-engineering the DSDT _DSM for NVDA8800.
 * No upstream driver exists as of kernel 6.14.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/platform_device.h>
#include <linux/hwmon.h>
#include <linux/io.h>

#define DRIVER_NAME	"spbm"

/* SPBM physical address (MTEL region 2) */
static unsigned long spbm_phys = 0x1C238000;
module_param(spbm_phys, ulong, 0444);
MODULE_PARM_DESC(spbm_phys, "SPBM physical address (default: 0x1C238000)");

#define SPBM_SIZE	0x1000

/*
 * Register offsets. Firmware writes milliwatts for power,
 * millijoules (cumulative) for energy.
 * hwmon expects microwatts and microjoules respectively.
 */

/* Instantaneous power telemetry */
#define TE_SYS_TOTAL	0x300
#define TE_SOC_PKG	0x304
#define TE_C_AND_G	0x308
#define TE_CPU_P	0x30C
#define TE_CPU_E	0x310
#define TE_VCORE	0x314
#define TE_VDDQ	0x318
#define TE_CHR		0x31C
#define TE_GPC_OUT	0x320
#define TE_GPU_OUT	0x324
#define TE_GPC_IN	0x328
#define TE_GPU_IN	0x32C
#define TE_SYS_IN	0x330
#define TE_DLA_IN	0x334
#define TE_PREREG_IN	0x338
#define TE_DLA_OUT	0x33C

/* Energy accumulators */
#define EN_PKG		0x344
#define EN_CPU_E	0x350
#define EN_CPU_P	0x35C
#define EN_GPC		0x368
#define EN_GPM		0x374

/* Power limits (effective, milliwatts) */
#define PL1_EFF		0x160
#define PL2_EFF		0x164
#define SYSPL1_EFF	0x170

/* Power budgets */
#define BUD_CPU		0x600
#define BUD_GPU		0x604
#define BUD_CPU_E	0x680
#define BUD_CPU_P	0x684

struct spbm_chan {
	u32 offset;
	const char *label;
};

static const struct spbm_chan pwr_chans[] = {
	{ TE_SYS_TOTAL, "sys_total" },
	{ TE_SOC_PKG,   "soc_pkg" },
	{ TE_C_AND_G,   "cpu_gpu" },
	{ TE_CPU_P,     "cpu_p" },
	{ TE_CPU_E,     "cpu_e" },
	{ TE_VCORE,     "vcore" },
	{ TE_VDDQ,      "vddq" },
	{ TE_CHR,       "dc_input" },
	{ TE_GPU_OUT,   "gpu_out" },
	{ TE_GPC_OUT,   "gpc_out" },
	{ TE_GPU_IN,    "gpu_in" },
	{ TE_GPC_IN,    "gpc_in" },
	{ TE_SYS_IN,    "sys_in" },
	{ TE_PREREG_IN, "prereg_in" },
	{ TE_DLA_IN,    "dla_in" },
	{ TE_DLA_OUT,   "dla_out" },
	{ PL1_EFF,      "pl1" },
	{ PL2_EFF,      "pl2" },
	{ SYSPL1_EFF,   "syspl1" },
	{ BUD_CPU,      "budget_cpu" },
	{ BUD_GPU,      "budget_gpu" },
	{ BUD_CPU_E,    "budget_cpu_e" },
	{ BUD_CPU_P,    "budget_cpu_p" },
};
#define N_PWR ARRAY_SIZE(pwr_chans)

static const struct spbm_chan nrg_chans[] = {
	{ EN_PKG,   "pkg" },
	{ EN_CPU_E, "cpu_e" },
	{ EN_CPU_P, "cpu_p" },
	{ EN_GPC,   "gpc" },
	{ EN_GPM,   "gpm" },
};
#define N_NRG ARRAY_SIZE(nrg_chans)

struct spbm_priv {
	void __iomem *base;
	struct platform_device *pdev;
};

static struct spbm_priv *spbm_inst;

/* hwmon callbacks */

static umode_t spbm_visible(const void *data, enum hwmon_sensor_types type,
			     u32 attr, int ch)
{
	if (type == hwmon_power && ch < N_PWR &&
	    (attr == hwmon_power_input || attr == hwmon_power_label))
		return 0444;
	if (type == hwmon_energy && ch < N_NRG &&
	    (attr == hwmon_energy_input || attr == hwmon_energy_label))
		return 0444;
	return 0;
}

static int spbm_read(struct device *dev, enum hwmon_sensor_types type,
		     u32 attr, int ch, long *val)
{
	struct spbm_priv *p = dev_get_drvdata(dev);
	u32 raw;

	if (type == hwmon_power && attr == hwmon_power_input && ch < N_PWR) {
		raw = ioread32(p->base + pwr_chans[ch].offset);
		*val = (long)raw * 1000; /* mW → uW */
		return 0;
	}
	if (type == hwmon_energy && attr == hwmon_energy_input && ch < N_NRG) {
		raw = ioread32(p->base + nrg_chans[ch].offset);
		*val = (long)raw * 1000; /* mJ → uJ */
		return 0;
	}
	return -EOPNOTSUPP;
}

static int spbm_read_string(struct device *dev, enum hwmon_sensor_types type,
			    u32 attr, int ch, const char **str)
{
	if (type == hwmon_power && ch < N_PWR) {
		*str = pwr_chans[ch].label;
		return 0;
	}
	if (type == hwmon_energy && ch < N_NRG) {
		*str = nrg_chans[ch].label;
		return 0;
	}
	return -EOPNOTSUPP;
}

static const struct hwmon_ops spbm_ops = {
	.is_visible = spbm_visible,
	.read = spbm_read,
	.read_string = spbm_read_string,
};

/* Build config arrays with a trailing 0 sentinel */

static const u32 pwr_cfg[N_PWR + 1] = {
	[0 ... N_PWR - 1] = HWMON_P_INPUT | HWMON_P_LABEL,
	[N_PWR] = 0,
};

static const u32 nrg_cfg[N_NRG + 1] = {
	[0 ... N_NRG - 1] = HWMON_E_INPUT | HWMON_E_LABEL,
	[N_NRG] = 0,
};

static const struct hwmon_channel_info pwr_info = {
	.type = hwmon_power,
	.config = pwr_cfg,
};

static const struct hwmon_channel_info nrg_info = {
	.type = hwmon_energy,
	.config = nrg_cfg,
};

static const struct hwmon_channel_info * const spbm_info[] = {
	&pwr_info, &nrg_info, NULL,
};

static const struct hwmon_chip_info spbm_chip = {
	.ops = &spbm_ops,
	.info = spbm_info,
};

/* Module init/exit */

static int __init spbm_init(void)
{
	struct spbm_priv *p;
	struct device *hwdev;
	u32 test;

	p = kzalloc(sizeof(*p), GFP_KERNEL);
	if (!p)
		return -ENOMEM;

	p->pdev = platform_device_register_simple(DRIVER_NAME, -1, NULL, 0);
	if (IS_ERR(p->pdev)) {
		kfree(p);
		return PTR_ERR(p->pdev);
	}

	p->base = ioremap(spbm_phys, SPBM_SIZE);
	if (!p->base) {
		pr_err("spbm: ioremap 0x%lx failed\n", spbm_phys);
		platform_device_unregister(p->pdev);
		kfree(p);
		return -ENOMEM;
	}

	/* Sanity check */
	test = ioread32(p->base + TE_SYS_TOTAL);
	if (test == 0 || test == 0xFFFFFFFF)
		pr_warn("spbm: SYS_TOTAL=%u — telemetry may be inactive\n",
			test);
	else
		pr_info("spbm: live — SYS=%u mW, SOC=%u mW, CPU_P=%u mW, "
			"GPU=%u mW\n", test,
			ioread32(p->base + TE_SOC_PKG),
			ioread32(p->base + TE_CPU_P),
			ioread32(p->base + TE_GPU_OUT));

	platform_set_drvdata(p->pdev, p);

	hwdev = devm_hwmon_device_register_with_info(&p->pdev->dev,
						     DRIVER_NAME, p,
						     &spbm_chip, NULL);
	if (IS_ERR(hwdev)) {
		pr_err("spbm: hwmon registration failed: %ld\n",
		       PTR_ERR(hwdev));
		iounmap(p->base);
		platform_device_unregister(p->pdev);
		kfree(p);
		return PTR_ERR(hwdev);
	}

	pr_info("spbm: registered %zu power + %zu energy hwmon channels\n",
		N_PWR, N_NRG);

	spbm_inst = p;
	return 0;
}

static void __exit spbm_exit(void)
{
	if (spbm_inst) {
		iounmap(spbm_inst->base);
		platform_device_unregister(spbm_inst->pdev);
		kfree(spbm_inst);
		spbm_inst = NULL;
	}
	pr_info("spbm: unloaded\n");
}

module_init(spbm_init);
module_exit(spbm_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("DGX Spark Power Telemetry");
MODULE_DESCRIPTION("NVIDIA DGX Spark (GB10) SPBM power hwmon driver");
