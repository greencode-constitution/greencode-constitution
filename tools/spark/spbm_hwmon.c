// SPDX-License-Identifier: GPL-2.0
/*
 * NVIDIA DGX Spark (GB10) SPBM Power Telemetry hwmon driver
 *
 * Exposes the System Power Budget Manager (SPBM) shared memory as
 * standard Linux hwmon sensors. The SPBM region is the second memory
 * resource of the MTEL (NVDA8800) ACPI device.
 *
 * The SPBM firmware (running on MediaTek SSPM) continuously updates
 * these registers with live power telemetry in milliwatts and
 * cumulative energy counters in millijoules.
 *
 * This driver binds as an acpi_driver to the NVDA8800 device on the
 * ACPI bus. The device has no platform_device (missing _UID/_STA in
 * DSDT), so a platform_driver cannot be used.
 *
 * Usage:
 *   sudo modprobe spbm_hwmon   (or auto-loaded via DKMS + udev)
 *   sensors spbm-*
 *   cat /sys/class/hwmon/hwmonN/power1_input   # microwatts
 *
 * Discovered by reverse-engineering the DSDT _DSM for NVDA8800.
 * No upstream driver exists as of kernel 6.14.
 */

#include <linux/module.h>
#include <linux/hwmon.h>
#include <linux/io.h>
#include <linux/acpi.h>
#include <linux/list.h>

#define DRIVER_NAME	"spbm"
#define SPBM_SIZE	0x1000

/* SPBM _CRS memory resource index (0-based) */
#define SPBM_RES_IDX	1

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
};

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
		*val = (long)raw * 1000; /* mW -> uW */
		return 0;
	}
	if (type == hwmon_energy && attr == hwmon_energy_input && ch < N_NRG) {
		raw = ioread32(p->base + nrg_chans[ch].offset);
		*val = (long)raw * 1000; /* mJ -> uJ */
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

/* ACPI driver */

static int spbm_add(struct acpi_device *adev)
{
	struct device *dev = &adev->dev;
	struct list_head res_list;
	struct resource_entry *re;
	resource_size_t phys = 0;
	struct spbm_priv *p;
	struct device *hwdev;
	int idx = 0, ret;
	u32 test;

	p = devm_kzalloc(dev, sizeof(*p), GFP_KERNEL);
	if (!p)
		return -ENOMEM;

	/* Find SPBM memory resource from _CRS (resource index SPBM_RES_IDX) */
	INIT_LIST_HEAD(&res_list);
	ret = acpi_dev_get_resources(adev, &res_list, NULL, NULL);
	if (ret < 0)
		return ret;

	list_for_each_entry(re, &res_list, node) {
		if (resource_type(re->res) == IORESOURCE_MEM) {
			if (idx == SPBM_RES_IDX) {
				phys = re->res->start;
				break;
			}
			idx++;
		}
	}
	acpi_dev_free_resource_list(&res_list);

	if (!phys) {
		dev_err(dev, "SPBM memory resource not found in _CRS\n");
		return -ENODEV;
	}

	p->base = devm_ioremap(dev, phys, SPBM_SIZE);
	if (!p->base)
		return -ENOMEM;

	/* Sanity check */
	test = ioread32(p->base + TE_SYS_TOTAL);
	if (test == 0 || test == 0xFFFFFFFF)
		dev_warn(dev, "SYS_TOTAL=%u, telemetry may be inactive\n",
			 test);
	else
		dev_info(dev, "live at 0x%llx: SYS=%u mW, SOC=%u mW, "
			 "CPU_P=%u mW, GPU=%u mW\n", (u64)phys, test,
			 ioread32(p->base + TE_SOC_PKG),
			 ioread32(p->base + TE_CPU_P),
			 ioread32(p->base + TE_GPU_OUT));

	hwdev = devm_hwmon_device_register_with_info(dev, DRIVER_NAME, p,
						     &spbm_chip, NULL);
	if (IS_ERR(hwdev))
		return PTR_ERR(hwdev);

	dev_info(dev, "registered %zu power + %zu energy hwmon channels\n",
		 N_PWR, N_NRG);

	return 0;
}

static const struct acpi_device_id spbm_acpi_ids[] = {
	{ "NVDA8800", 0 },
	{ }
};
MODULE_DEVICE_TABLE(acpi, spbm_acpi_ids);

static struct acpi_driver spbm_driver = {
	.name = DRIVER_NAME,
	.ids = spbm_acpi_ids,
	.ops = {
		.add = spbm_add,
	},
};
module_acpi_driver(spbm_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("DGX Spark Power Telemetry");
MODULE_DESCRIPTION("NVIDIA DGX Spark (GB10) SPBM power hwmon driver");
