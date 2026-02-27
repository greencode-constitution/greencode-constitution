// SPDX-License-Identifier: GPL-2.0
/*
 * SCMI Shared Memory Probe Module (v2 - with doorbell)
 *
 * Directly maps the SCMI shared memory transport on NVIDIA DGX Spark (GB10)
 * and sends SCMI Base Protocol + Sensor Protocol discovery messages.
 *
 * Now includes SMC-based doorbell support: after writing to shmem, issues
 * an ARM SMC call to notify the firmware.
 *
 * SCMI Spec: ARM DEN0056E
 * Shared Memory Transport layout (per channel):
 *   +0x00: Reserved (4 bytes)
 *   +0x04: Channel Status (4 bytes) - bit0=CHANNEL_FREE, bit1=CHANNEL_ERROR
 *   +0x08: Reserved (8 bytes)
 *   +0x10: Flags (4 bytes) - bit0=INTR_ENABLED
 *   +0x14: Length (4 bytes) - header + payload length
 *   +0x18: Message Header (4 bytes)
 *   +0x1C: Message Payload (variable)
 *
 * Message Header encoding:
 *   [7:0]   = Message ID
 *   [9:8]   = Message Type (0=Command, 1=DelayedResponse, 2=Notification)
 *   [17:10] = Protocol ID
 *   [27:18] = Token
 *   [31:28] = Reserved
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/delay.h>
#include <linux/arm-smccc.h>

#define SCMI_NAME_MAX	16

/* SCMI shared memory channel addresses from ACPI DSDT (NVDA8200 / SCP0) */
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

/* Channel Status bits */
#define SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE	BIT(0)
#define SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR	BIT(1)

/* Message Header encoding */
#define MSG_ID_MASK		GENMASK(7, 0)
#define MSG_TYPE_MASK		GENMASK(9, 8)
#define MSG_PROTO_ID_MASK	GENMASK(17, 10)
#define MSG_TOKEN_MASK		GENMASK(27, 18)

#define PACK_MSG_HDR(id, type, proto, token) \
	(FIELD_PREP(MSG_ID_MASK, (id)) | \
	 FIELD_PREP(MSG_TYPE_MASK, (type)) | \
	 FIELD_PREP(MSG_PROTO_ID_MASK, (proto)) | \
	 FIELD_PREP(MSG_TOKEN_MASK, (token)))

/* SCMI Protocol IDs */
#define SCMI_PROTO_BASE		0x10
#define SCMI_PROTO_POWER	0x11
#define SCMI_PROTO_PERF		0x13
#define SCMI_PROTO_CLOCK	0x14
#define SCMI_PROTO_SENSOR	0x15
#define SCMI_PROTO_RESET	0x16
#define SCMI_PROTO_VOLTAGE	0x17
#define SCMI_PROTO_POWERCAP	0x18

/* Base Protocol commands */
#define BASE_DISCOVER_VENDOR		0x3
#define BASE_DISCOVER_SUB_VENDOR	0x4
#define BASE_DISCOVER_IMPL_VER		0x5
#define BASE_DISCOVER_LIST_PROTOCOLS	0x6

/* Sensor Protocol commands */
#define SENSOR_DESCRIPTION_GET		0x3
#define SENSOR_READING_GET		0x6

/*
 * Candidate SMC function IDs to try as doorbell.
 * ARM SMCCC convention: bits [31:24] define call type.
 *   0xC2xxxxxx = Fast Call, SMC64, SiP Service
 *   0x82xxxxxx = Fast Call, SMC32, SiP Service
 *   0xC3xxxxxx = Fast Call, SMC64, OEM Service
 *   0x83xxxxxx = Fast Call, SMC32, OEM Service
 *
 * MediaTek uses SiP service with function IDs like:
 *   0xC200053C = MTK_SIP_TINYSYS_SSPM_CONTROL
 *
 * NVIDIA Tegra typically uses:
 *   0xC2FFFE00-FF range for BPMP/SCP
 *
 * Standard SCMI examples use:
 *   0xC3000001 (OEM service, function 1)
 */
static const u32 smc_candidates[] = {
	/* MediaTek TinySYS SSPM control */
	0xC200053C,
	/* Standard SCMI SMC function IDs */
	0xC3000001,
	0x83000001,
	/* NVIDIA-style function IDs */
	0xC2FFFE00,
	0xC2FFFE01,
	0xC2FFFE02,
	0xC2FFFE03,
	0xC2FFFE10,
	0xC2FFFE20,
	/* More common function IDs used in various DTs */
	0xC2000001,
	0xC2000002,
	0xC2000003,
	0xC2000004,
	0xC2000010,
	0xC2000100,
	/* 32-bit variants */
	0x8200053C,
	0x82000001,
	0x82000002,
	0x82000010,
};

/* Currently active SMC function ID (0 = no doorbell / polling only) */
static u32 active_smc_id;

/* Module parameters - allow specifying SMC ID directly */
static u32 smc_id;
module_param(smc_id, uint, 0444);
MODULE_PARM_DESC(smc_id, "SMC function ID to use as doorbell (0=scan)");

static int channel_idx;
module_param(channel_idx, int, 0444);
MODULE_PARM_DESC(channel_idx, "Channel to use: 0=shmem_base, 1=ch_a, 2=ch_b, 3=ch_c");

static const char *sensor_type_name(unsigned int type)
{
	switch (type) {
	case 0x02: return "Temperature_C";
	case 0x05: return "Voltage";
	case 0x06: return "Current";
	case 0x07: return "Power";
	case 0x08: return "Energy";
	case 0x13: return "RPM";
	case 0x41: return "Percentage";
	default:   return "Other";
	}
}

static void dump_region(void __iomem *base, phys_addr_t phys, size_t len,
			const char *name)
{
	int i;
	u32 val;

	pr_info("scmi_probe: === %s @ 0x%llx ===\n", name, (u64)phys);
	for (i = 0; i < len && i < 64; i += 4) {
		val = ioread32(base + i);
		if (val != 0)
			pr_info("scmi_probe:   +0x%02x: 0x%08x\n", i, val);
	}

	val = ioread32(base + SHMEM_CHAN_STAT);
	pr_info("scmi_probe:   Channel Status: 0x%08x (FREE=%d, ERROR=%d)\n",
		val, !!(val & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE),
		!!(val & SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR));
}

static void ring_doorbell(void __iomem *shmem)
{
	struct arm_smccc_res res;

	if (active_smc_id == 0)
		return;

	/*
	 * Issue SMC call. Different platforms pass different args:
	 * - Some pass 0 as all args (just signal)
	 * - Some pass channel physical address as a1
	 * - Some pass message header as a1
	 * We try with 0 args first; if a specific pattern is needed,
	 * the module can be reloaded with different parameters.
	 */
	arm_smccc_smc(active_smc_id, 0, 0, 0, 0, 0, 0, 0, &res);
}

/*
 * Send an SCMI command via shared memory with optional SMC doorbell.
 */
static int scmi_send_msg(void __iomem *shmem, u8 proto_id, u8 msg_id,
			 const void *tx_buf, size_t tx_len,
			 void *rx_buf, size_t rx_max, size_t *rx_len,
			 u16 token)
{
	u32 status, hdr;
	int timeout;

	/* Check channel is free */
	status = ioread32(shmem + SHMEM_CHAN_STAT);
	if (!(status & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE)) {
		/* Try to reset channel - write CHANNEL_FREE */
		iowrite32(SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE,
			  shmem + SHMEM_CHAN_STAT);
		wmb();
		udelay(100);
		status = ioread32(shmem + SHMEM_CHAN_STAT);
		if (!(status & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE)) {
			pr_warn("scmi_probe: channel not free (status=0x%08x), "
				"proceeding anyway\n", status);
		}
	}

	/* Build message header */
	hdr = PACK_MSG_HDR(msg_id, 0 /* CMD */, proto_id, token);

	/* Write payload first */
	if (tx_buf && tx_len > 0) {
		int i;
		const u32 *src = tx_buf;

		for (i = 0; i < tx_len / 4; i++)
			iowrite32(src[i], shmem + SHMEM_MSG_PAYLOAD + i * 4);
	}

	/* Write length (header size 4 + payload) */
	iowrite32(4 + tx_len, shmem + SHMEM_LENGTH);

	/* Write header */
	iowrite32(hdr, shmem + SHMEM_MSG_HDR);

	/* Set flags: enable interrupt notification */
	iowrite32(0, shmem + SHMEM_FLAGS);

	/* Clear CHANNEL_FREE to signal firmware */
	iowrite32(0, shmem + SHMEM_CHAN_STAT);

	/* Memory barrier to ensure all writes are visible before doorbell */
	wmb();

	/* Ring the doorbell (SMC call) */
	ring_doorbell(shmem);

	/* Poll for response (CHANNEL_FREE set again by firmware) */
	timeout = 2000; /* 2 seconds total */
	while (timeout > 0) {
		udelay(1000); /* 1ms */
		status = ioread32(shmem + SHMEM_CHAN_STAT);
		if (status & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE)
			break;
		timeout--;
	}

	if (timeout == 0) {
		pr_warn("scmi_probe: timeout (proto=0x%02x, msg=0x%02x, "
			"smc=0x%08x)\n", proto_id, msg_id, active_smc_id);
		return -ETIMEDOUT;
	}

	if (status & SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR) {
		pr_warn("scmi_probe: channel error "
			"(proto=0x%02x, msg=0x%02x)\n", proto_id, msg_id);
		return -EIO;
	}

	/* Read response */
	{
		u32 resp_len = ioread32(shmem + SHMEM_LENGTH);
		u32 resp_hdr = ioread32(shmem + SHMEM_MSG_HDR);
		size_t payload_len;

		pr_info("scmi_probe: Response: len=%u, hdr=0x%08x\n",
			resp_len, resp_hdr);

		if (resp_len < 4) {
			pr_warn("scmi_probe: invalid response length %u\n",
				resp_len);
			return -EINVAL;
		}

		payload_len = resp_len - 4; /* subtract header */
		if (payload_len > rx_max)
			payload_len = rx_max;

		if (rx_buf && payload_len > 0) {
			int i;
			u32 *dst = rx_buf;

			for (i = 0; i < (payload_len + 3) / 4; i++)
				dst[i] = ioread32(shmem + SHMEM_MSG_PAYLOAD +
						  i * 4);
		}

		if (rx_len)
			*rx_len = payload_len;
	}

	return 0;
}

/*
 * Try a single SMC ID: write a simple SCMI Base PROTOCOL_VERSION
 * command and see if firmware responds.
 */
static int try_smc_doorbell(void __iomem *shmem, u32 func_id)
{
	struct arm_smccc_res res;
	u32 status, hdr;
	int timeout;

	/* First, try the raw SMC call to see if it returns NOT_SUPPORTED */
	arm_smccc_smc(func_id, 0, 0, 0, 0, 0, 0, 0, &res);
	if (res.a0 == SMCCC_RET_NOT_SUPPORTED) {
		return -ENOENT;
	}

	pr_info("scmi_probe: SMC 0x%08x returned: a0=0x%lx a1=0x%lx "
		"a2=0x%lx a3=0x%lx\n",
		func_id, res.a0, res.a1, res.a2, res.a3);

	/* Reset the channel */
	iowrite32(SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE, shmem + SHMEM_CHAN_STAT);
	wmb();
	udelay(100);

	/* Prepare a PROTOCOL_VERSION command for Base protocol */
	hdr = PACK_MSG_HDR(0x0, 0, SCMI_PROTO_BASE, 0xAA);
	iowrite32(4, shmem + SHMEM_LENGTH);
	iowrite32(hdr, shmem + SHMEM_MSG_HDR);
	iowrite32(0, shmem + SHMEM_FLAGS);
	iowrite32(0, shmem + SHMEM_CHAN_STAT);
	wmb();

	/* Ring doorbell */
	arm_smccc_smc(func_id, 0, 0, 0, 0, 0, 0, 0, &res);

	/* Quick poll - 200ms */
	timeout = 200;
	while (timeout > 0) {
		udelay(1000);
		status = ioread32(shmem + SHMEM_CHAN_STAT);
		if (status & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE)
			break;
		timeout--;
	}

	if (timeout > 0 && !(status & SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR)) {
		u32 resp_len = ioread32(shmem + SHMEM_LENGTH);
		u32 resp_hdr = ioread32(shmem + SHMEM_MSG_HDR);

		pr_info("scmi_probe: *** SMC 0x%08x GOT RESPONSE! ***\n",
			func_id);
		pr_info("scmi_probe:   resp_len=%u resp_hdr=0x%08x\n",
			resp_len, resp_hdr);
		return 0;
	}

	if (timeout == 0) {
		pr_info("scmi_probe: SMC 0x%08x: no response (timeout)\n",
			func_id);
	} else {
		pr_info("scmi_probe: SMC 0x%08x: channel error\n", func_id);
	}

	return -ETIMEDOUT;
}

/*
 * Scan SMC function IDs to find one that works as doorbell.
 * Also tries passing the channel physical address as arg.
 */
static u32 scan_smc_doorbells(void __iomem *shmem, phys_addr_t shmem_phys)
{
	int i;
	int ret;
	struct arm_smccc_res res;

	pr_info("scmi_probe: === Scanning SMC function IDs for doorbell ===\n");

	for (i = 0; i < ARRAY_SIZE(smc_candidates); i++) {
		ret = try_smc_doorbell(shmem, smc_candidates[i]);
		if (ret == 0)
			return smc_candidates[i];
	}

	/*
	 * Also try with channel physical address as a1 argument.
	 * Some implementations pass the shmem address to identify
	 * which channel to process.
	 */
	pr_info("scmi_probe: === Retrying with shmem addr as arg ===\n");
	for (i = 0; i < ARRAY_SIZE(smc_candidates); i++) {
		u32 func_id = smc_candidates[i];
		u32 status, hdr;
		int timeout;

		/* Skip already-tested NOT_SUPPORTED ones */
		arm_smccc_smc(func_id, 0, 0, 0, 0, 0, 0, 0, &res);
		if (res.a0 == SMCCC_RET_NOT_SUPPORTED)
			continue;

		/* Reset and prepare message */
		iowrite32(SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE,
			  shmem + SHMEM_CHAN_STAT);
		wmb();
		udelay(100);

		hdr = PACK_MSG_HDR(0x0, 0, SCMI_PROTO_BASE, 0xBB);
		iowrite32(4, shmem + SHMEM_LENGTH);
		iowrite32(hdr, shmem + SHMEM_MSG_HDR);
		iowrite32(0, shmem + SHMEM_FLAGS);
		iowrite32(0, shmem + SHMEM_CHAN_STAT);
		wmb();

		/* Ring doorbell with shmem phys addr as a1 */
		arm_smccc_smc(func_id, shmem_phys, 0, 0, 0, 0, 0, 0, &res);

		timeout = 200;
		while (timeout > 0) {
			udelay(1000);
			status = ioread32(shmem + SHMEM_CHAN_STAT);
			if (status & SCMI_SHMEM_CHAN_STAT_CHANNEL_FREE)
				break;
			timeout--;
		}

		if (timeout > 0 &&
		    !(status & SCMI_SHMEM_CHAN_STAT_CHANNEL_ERROR)) {
			pr_info("scmi_probe: *** SMC 0x%08x + addr GOT RESPONSE! ***\n",
				func_id);
			return func_id;
		}
	}

	pr_info("scmi_probe: No working SMC doorbell found\n");
	return 0;
}

static void probe_base_protocol(void __iomem *shmem)
{
	u32 rx_buf[64];
	size_t rx_len;
	int ret;

	pr_info("scmi_probe: === Probing SCMI Base Protocol (0x10) ===\n");

	/* PROTOCOL_VERSION (msg 0x0) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_BASE, 0x0,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 1);
	if (ret == 0 && rx_len >= 8) {
		pr_info("scmi_probe: Base Protocol Version: status=%d, "
			"version=0x%08x\n",
			(int)(s32)rx_buf[0], rx_buf[1]);
	} else {
		pr_info("scmi_probe: Base PROTOCOL_VERSION failed: "
			"ret=%d, rx_len=%zu\n", ret, rx_len);
		return;
	}

	/* PROTOCOL_ATTRIBUTES (msg 0x1) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_BASE, 0x1,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 2);
	if (ret == 0 && rx_len >= 8) {
		u32 attrs = rx_buf[1];

		pr_info("scmi_probe: Base Attributes: status=%d, "
			"num_agents=%u, num_protocols=%u\n",
			(int)(s32)rx_buf[0],
			(attrs >> 8) & 0xFF, attrs & 0xFF);
	}

	/* DISCOVER_VENDOR (msg 0x3) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_BASE, BASE_DISCOVER_VENDOR,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 3);
	if (ret == 0 && rx_len >= 8) {
		char *vendor = (char *)&rx_buf[1];

		vendor[SCMI_NAME_MAX - 1] = '\0';
		pr_info("scmi_probe: Vendor: status=%d, name='%s'\n",
			(int)(s32)rx_buf[0], vendor);
	}

	/* DISCOVER_SUB_VENDOR (msg 0x4) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_BASE, BASE_DISCOVER_SUB_VENDOR,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 4);
	if (ret == 0 && rx_len >= 8) {
		char *vendor = (char *)&rx_buf[1];

		vendor[SCMI_NAME_MAX - 1] = '\0';
		pr_info("scmi_probe: Sub-Vendor: status=%d, name='%s'\n",
			(int)(s32)rx_buf[0], vendor);
	}

	/* DISCOVER_IMPL_VERSION (msg 0x5) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_BASE, BASE_DISCOVER_IMPL_VER,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 5);
	if (ret == 0 && rx_len >= 8) {
		pr_info("scmi_probe: Impl Version: status=%d, "
			"version=0x%08x\n",
			(int)(s32)rx_buf[0], rx_buf[1]);
	}

	/* DISCOVER_LIST_PROTOCOLS (msg 0x6) */
	{
		u32 skip = 0;

		ret = scmi_send_msg(shmem, SCMI_PROTO_BASE,
				    BASE_DISCOVER_LIST_PROTOCOLS,
				    &skip, 4, rx_buf, sizeof(rx_buf),
				    &rx_len, 6);
		if (ret == 0 && rx_len >= 8) {
			u32 num_protos = rx_buf[1];
			int i;
			u8 *proto_list = (u8 *)&rx_buf[2];

			pr_info("scmi_probe: Protocol List: status=%d, "
				"num=%u\n",
				(int)(s32)rx_buf[0], num_protos);

			for (i = 0; i < num_protos && i < (rx_len - 8); i++) {
				pr_info("scmi_probe:   Protocol 0x%02x%s\n",
					proto_list[i],
					proto_list[i] == 0x15 ?
						" (SENSOR!)" :
					proto_list[i] == 0x18 ?
						" (POWERCAP)" :
					proto_list[i] == 0x17 ?
						" (VOLTAGE)" :
					proto_list[i] == 0x11 ?
						" (POWER)" :
					proto_list[i] == 0x13 ?
						" (PERF)" :
					proto_list[i] == 0x14 ?
						" (CLOCK)" :
					proto_list[i] == 0x16 ?
						" (RESET)" :
					"");
			}
		}
	}
}

static void probe_sensor_protocol(void __iomem *shmem)
{
	u32 rx_buf[128];
	size_t rx_len;
	int ret;

	pr_info("scmi_probe: === Probing SCMI Sensor Protocol (0x15) ===\n");

	/* SENSOR PROTOCOL_VERSION (msg 0x0) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_SENSOR, 0x0,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 10);
	if (ret == 0 && rx_len >= 8) {
		pr_info("scmi_probe: Sensor Protocol Version: status=%d, "
			"version=0x%08x\n",
			(int)(s32)rx_buf[0], rx_buf[1]);
	} else {
		pr_info("scmi_probe: Sensor protocol not available "
			"or no response\n");
		return;
	}

	/* SENSOR PROTOCOL_ATTRIBUTES (msg 0x1) */
	ret = scmi_send_msg(shmem, SCMI_PROTO_SENSOR, 0x1,
			    NULL, 0, rx_buf, sizeof(rx_buf), &rx_len, 11);
	if (ret == 0 && rx_len >= 12) {
		u32 attrs = rx_buf[1];
		u32 num_sensors = attrs & 0xFFFF;
		u32 max_pending = (attrs >> 16) & 0xFF;
		u32 reg_addr_low = rx_buf[2];
		u32 reg_addr_high = (rx_len >= 16) ? rx_buf[3] : 0;
		u32 reg_len = (rx_len >= 20) ? rx_buf[4] : 0;

		pr_info("scmi_probe: Sensor Attributes: status=%d, "
			"num_sensors=%u, max_pending=%u\n",
			(int)(s32)rx_buf[0], num_sensors, max_pending);
		pr_info("scmi_probe:   Sensor reg addr: 0x%08x%08x, "
			"len=%u\n",
			reg_addr_high, reg_addr_low, reg_len);

		/* Enumerate sensors */
		if (num_sensors > 0) {
			u32 desc_idx = 0;
			int total = 0;

			while (total < num_sensors && total < 64) {
				ret = scmi_send_msg(shmem,
						   SCMI_PROTO_SENSOR,
						   SENSOR_DESCRIPTION_GET,
						   &desc_idx, 4,
						   rx_buf, sizeof(rx_buf),
						   &rx_len,
						   12 + total);
				if (ret != 0 || rx_len < 8)
					break;

				{
					u32 nrf = rx_buf[1];
					u32 num_returned = nrf & 0xFFF;
					u32 num_remaining;
					int s;
					u32 *desc;

					num_remaining = (nrf >> 16) & 0xFFFF;
					pr_info("scmi_probe: Sensor desc: "
						"returned=%u, remaining=%u\n",
						num_returned, num_remaining);

					desc = &rx_buf[2];
					for (s = 0; s < num_returned; s++) {
						u32 sid = desc[0];
						u32 ah = desc[2];
						char *name;
						unsigned int stype;
						int scale;

						stype = ah & 0xFF;
						scale = (ah >> 11) & 0x1F;
						if (scale & 0x10)
							scale |= ~0x1F;

						name = (char *)&desc[3];
						name[SCMI_NAME_MAX - 1] = '\0';

						pr_info("scmi_probe:   "
							"Sensor[%u]: id=%u, "
							"type=%s(0x%02x), "
							"scale=%d, "
							"name='%s'\n",
							total + s, sid,
							sensor_type_name(stype),
							stype, scale, name);

						desc += 4;
					}

					total += num_returned;
					desc_idx = total;

					if (num_remaining == 0)
						break;
				}
			}

			/* Try reading first sensors */
			{
				int s;

				for (s = 0; s < total && s < 16; s++) {
					u32 sensor_id = s;

					ret = scmi_send_msg(shmem,
							   SCMI_PROTO_SENSOR,
							   SENSOR_READING_GET,
							   &sensor_id, 4,
							   rx_buf,
							   sizeof(rx_buf),
							   &rx_len,
							   20 + s);
					if (ret == 0 && rx_len >= 12) {
						s32 sc;
						u64 value;

						sc = (s32)rx_buf[0];
						value = (u64)rx_buf[1] |
							((u64)rx_buf[2] << 32);
						pr_info("scmi_probe:   "
							"Reading[%d]: "
							"status=%d, "
							"value=%lld "
							"(0x%llx)\n",
							s, sc,
							(long long)(s64)value,
							value);
					}
				}
			}
		}
	}
}

static int __init scmi_probe_init(void)
{
	void __iomem *shmem_base;
	void __iomem *ch_a, *ch_b, *ch_c;
	void __iomem *active_ch;
	phys_addr_t active_phys;
	const char *ch_name;

	pr_info("scmi_probe: Loading SCMI probe module v2 (with doorbell)\n");
	pr_info("scmi_probe: Target: NVIDIA DGX Spark (GB10 SoC)\n");

	/* Map all regions */
	shmem_base = ioremap(SCMI_SHMEM_BASE, SCMI_SHMEM_SIZE);
	if (!shmem_base) {
		pr_err("scmi_probe: Failed to map SCMI SHMEM\n");
		return -ENOMEM;
	}

	ch_a = ioremap(SCMI_CH_A_BASE, SCMI_CH_A_SIZE);
	ch_b = ioremap(SCMI_CH_B_BASE, SCMI_CH_B_SIZE);
	ch_c = ioremap(SCMI_CH_C_BASE, SCMI_CH_C_SIZE);

	/* Dump all regions first */
	dump_region(shmem_base, SCMI_SHMEM_BASE, 64, "SHMEM Base");
	if (ch_a)
		dump_region(ch_a, SCMI_CH_A_BASE, 64, "Channel A");
	if (ch_b)
		dump_region(ch_b, SCMI_CH_B_BASE, 64, "Channel B");
	if (ch_c)
		dump_region(ch_c, SCMI_CH_C_BASE, 64, "Channel C");

	/* Select active channel */
	switch (channel_idx) {
	case 1:
		active_ch = ch_a;
		active_phys = SCMI_CH_A_BASE;
		ch_name = "Channel A";
		break;
	case 2:
		active_ch = ch_b;
		active_phys = SCMI_CH_B_BASE;
		ch_name = "Channel B";
		break;
	case 3:
		active_ch = ch_c;
		active_phys = SCMI_CH_C_BASE;
		ch_name = "Channel C";
		break;
	default:
		active_ch = shmem_base;
		active_phys = SCMI_SHMEM_BASE;
		ch_name = "SHMEM Base";
		break;
	}

	if (!active_ch) {
		pr_err("scmi_probe: Selected channel not mapped\n");
		goto out;
	}

	pr_info("scmi_probe: Using %s for communication\n", ch_name);

	/* Step 1: Find doorbell SMC function ID */
	if (smc_id != 0) {
		pr_info("scmi_probe: Using user-specified SMC ID: 0x%08x\n",
			smc_id);
		active_smc_id = smc_id;
	} else {
		/* Scan for working SMC doorbell on this channel */
		active_smc_id = scan_smc_doorbells(active_ch, active_phys);

		if (active_smc_id == 0) {
			pr_info("scmi_probe: No SMC doorbell found, "
				"trying polling only...\n");
		}
	}

	/* Step 2: Probe protocols */
	probe_base_protocol(active_ch);
	probe_sensor_protocol(active_ch);

out:
	if (ch_c)
		iounmap(ch_c);
	if (ch_b)
		iounmap(ch_b);
	if (ch_a)
		iounmap(ch_a);
	iounmap(shmem_base);

	pr_info("scmi_probe: Probe complete.\n");
	return -ENODEV;
}

static void __exit scmi_probe_exit(void)
{
	pr_info("scmi_probe: Module unloaded\n");
}

module_init(scmi_probe_init);
module_exit(scmi_probe_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("DGX Spark Power Probe");
MODULE_DESCRIPTION("SCMI shared memory probe with SMC doorbell for NVIDIA DGX Spark");
