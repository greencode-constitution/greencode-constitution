# DGX Spark (GB10) Power Telemetry Investigation

## Goal

Determine whether CPU and GPU power, voltage, and current sensors can be
read on the NVIDIA DGX Spark (GB10 SoC).

## TL;DR

**Full system power telemetry is available** via the SPBM (System Power
Budget Manager) shared memory at physical address `0x1C238000`. This is the
second memory region of the MTEL (`NVDA8800`) ACPI device. A kernel module
is required to read it (kernel lockdown blocks `/dev/mem`).

**Available readings** (all in milliwatts, updated by firmware in real-time):

| Metric | Idle Value | Description |
|--------|-----------|-------------|
| SYS_TOTAL | ~36W | Total system power |
| SOC_PKG | ~22W | SoC package power |
| C_AND_G | ~10W | CPU + GPU combined |
| CPU_P | ~4.5W | P-core cluster |
| CPU_E | ~0.1W | E-core cluster |
| VCORE | ~4W | Core voltage domain |
| TOTAL_GPU_OUT | ~4.8W | GPU output (matches nvidia-smi) |
| CHR | ~36W | DC input / charger rail |
| PREREG_IN | ~8W | Pre-regulator input |
| + energy accumulators | cumulative | PKG, CPU_E, CPU_P, GPC, GPM |

**GPU power**: Also available via `nvidia-smi` / NVML (~4.5W idle).

## Platform Overview

- **SoC**: NVIDIA GB10 — ARM CPU + Blackwell GPU
  - 10x Cortex-X925 (P-cores, cpu0-9, cluster 56, up to 3.9 GHz)
  - 10x Cortex-A725 (E-cores, cpu10-19, cluster 1144, up to 4.0 GHz)
  - big.LITTLE configuration, **not** Neoverse V2
- **CPU chiplet (S-die)**: Designed by MediaTek (SMCCC SOC_ID: `jep106:0426:8901`)
- **Boot firmware**: AMI UEFI `5.36_0ACUM023` (Dec 2025), ACPI-only (no device tree)
- **Kernel**: `6.11.0-1016-nvidia` (Ubuntu, ARM64)
- **Secure Boot**: Enabled (modules require MOK signing)
- **Kernel Lockdown**: Active (`/dev/mem` blocked)

## SPBM Telemetry (CONFIRMED WORKING)

### Discovery

The MTEL device (`NVDA8800`) in the ACPI DSDT has a `_DSM` method (UUID
`12345678-1234-1234-1234-123456789abc`) that returns subsystem names and
register offset tables for the System Power Budget Manager (SPBM). The SPBM
data lives in the MTEL device's **second** memory region at `0x1C238000` (4KB).

The DSDT `_DSM` subfunction 2 returns named offset tables for:
- **CPUEB** (CPU Event Bus) — DVFS logs, performance counters, CPPC, power limits
- **SPBM** — Power limit management, telemetry, energy counters, budgeting
- **SSPM** — System Service Processor Manager
- **HFRP** — High-Frequency Rail Protection

### SPBM Register Map

All offsets relative to `0x1C238000`. Values in milliwatts unless noted.

#### Status (offsets 0x00–0x4F)

| Offset | Name | Description |
|--------|------|-------------|
| 0x08 | PID_MIN_WINNER | PID controller minimum winner |
| 0x0C | PID_MIN_WINNER_LOCK | Lock for above |
| 0x48 | PL_CUR_LEVEL_STATUS | Current power limit level |
| 0x4C | PROCHOT_STATUS | PROCHOT assertion status |

#### Power Limits (offsets 0x100–0x17F)

| Offset | Name | Observed Value |
|--------|------|---------------|
| 0x100–0x10C | PL1–PL4 (OS) | 0 (not set by OS) |
| 0x110–0x11C | SYSPL1–SYSPL4 (OS) | 0 (not set by OS) |
| 0x120–0x12C | PL1–PL4 (EC) | PL1=140000, PL2=142000 |
| 0x130–0x13C | SYSPL1–SYSPL4 (EC) | — |
| 0x140–0x14C | PL1–PL4 (UEFI) | 0 |
| 0x150–0x15C | SYSPL1–SYSPL4 (UEFI) | — |
| 0x160–0x16C | PL1–PL4 (effective) | PL1=140000, PL2=142000 |
| 0x170–0x17C | SYSPL1–SYSPL4 (effective) | 231000, 244000, 257000, 265000 |

#### PID Controller Tuning (offsets 0x200–0x27F)

KP, KI, KD, TAU parameters for each PL level and EDPC.

#### Telemetry — Instantaneous Power (offsets 0x300–0x33F)

| Offset | Name | Idle ~Value | Description |
|--------|------|-------------|-------------|
| 0x300 | SYS_TOTAL | ~36000 | Total system power |
| 0x304 | SOC_PKG | ~22000 | SoC package |
| 0x308 | C_AND_G | ~10000 | CPU + GPU combined |
| 0x30C | CPU_P | ~4500 | P-core cluster |
| 0x310 | CPU_E | ~100 | E-core cluster |
| 0x314 | VCORE | ~4000 | Core voltage domain |
| 0x318 | VDDQ | 0 | Memory VDDQ |
| 0x31C | CHR | ~36000 | DC input / charger |
| 0x320 | GPC_OUT | 0 | GPU GPC output |
| 0x324 | TOTAL_GPU_OUT | ~4800 | Total GPU output |
| 0x328 | GPC_IN | 0 | GPU GPC input |
| 0x32C | TOTAL_GPU_IN | 0 | Total GPU input |
| 0x330 | TOTAL_SYS_IN | 0 | Total system input |
| 0x334 | DLA_IN | ~9 | DLA input |
| 0x338 | PREREG_IN | ~8000 | Pre-regulator input |
| 0x33C | DLA_OUT | 0 | DLA output |

#### Energy Accumulators (offsets 0x344–0x37F)

| Offset | Name | Description |
|--------|------|-------------|
| 0x344 | PKG_ENERGY_ACC | Package energy (cumulative) |
| 0x348 | PKG_ENERGY_OVF | Overflow counter |
| 0x350 | CPU_E_ENERGY_ACC | E-core energy |
| 0x35C | CPU_P_ENERGY_ACC | P-core energy |
| 0x368 | GPC_ENERGY_ACC | GPC energy |
| 0x374 | GPM_ENERGY_ACC | GPU memory energy |

Energy units: delta ≈ millijoules per second (confirmed: PKG delta=18378
over 1s matches ~18W average idle, CPU_P delta=1599 ≈ 1.6W settling).

#### Budget (offsets 0x500–0x6FF)

| Offset | Name | Observed Value |
|--------|------|---------------|
| 0x500 | BUDGETER_LOOP_TIME | 100 |
| 0x504 | BUDGETER_W1 | 500 |
| 0x508 | BUDGETER_W2 | 500 |
| 0x600 | BUDGET_CPU_INST | 79999 |
| 0x604 | BUDGET_GPU_INST | 195000 |
| 0x680 | BUDGET_CPU_E_INST | 18399 |
| 0x684 | BUDGET_CPU_P_INST | 69599 |

#### PID Outputs and Limits (offsets 0x620–0x70F)

Detailed PID output and power limit clamping registers.

### Liveness Verification

Two snapshots 1 second apart confirm all readings are live:
- Instantaneous power varies between reads (normal for bursty workloads)
- Energy accumulators monotonically increase
- GPU_OUT tracks nvidia-smi within ~0.5W

### CPUEB Interface (MTEL region 1)

The CPUEB shared memory at `0x05170000 + offsets` contains:

| Offset (from MTEL base) | Name | Description |
|--------------------------|------|-------------|
| 0x5A400 | PERFCNT_LOG | Performance counter log |
| 0x5AC00 | FASTDVFS_LOG | Fast DVFS log |
| 0x5B400 | PL_INTERFACE | Power limit interface (stale copy?) |
| 0x5C404 | CPPC_INTERFACE | CPPC shared memory (active) |

The CPPC interface at `0x051CC404` is active with per-CPU CPPC data.

### NVPCF (NVDA0820) — GPU Power Config

The NPCF device implements DSM UUID `36b49710-2483-11e7-9598-0800200c9a66`
(NVIDIA Platform Configuration Framework). Returns GPU power limit tables.

### PMU0 (NVDA8900) — Performance Management Unit

Returns CPUEB SRAM mapping (`0x05160000`, 320KB), mailbox address
(`0x051CF600`), and extra region (`0x1C900000`, 4KB) via DSM UUID
`98196e9f-5625-43db-81fb-48bb73abb17e`.

## Standard Linux Interfaces Checked

| Interface | Result |
|-----------|--------|
| nvidia-smi | GPU power only (~4.5W idle) |
| hwmon / thermal | Temperature only (acpitz, NVMe, MLX5, WiFi) |
| RAPL / perf energy | Not available (ARM, not x86) |
| ARM AMU | Detected on all 20 CPUs, but no energy counters |
| tegrastats | Not installed / not available |
| SCMI powercap | Module loaded, but zero power zones |
| IPMI / BMC | No BMC on Spark |
| ACPI Power Meter | No ACPI power meter device exposed |
| I2C power monitors | No INA2xx or similar on any I2C bus |

## SCMI Investigation

### Hardware Present

The ACPI DSDT defines device `SCP0` (`NVDA8200`) with:

| Region | Address | Size | Contents |
|--------|---------|------|----------|
| SHMEM Base | `0x1A800000` | 512KB | All zeros |
| Channel A | `0x1AB20000` | 4KB | Stale data from boot |
| Channel B | `0x1AAA0000` | 4KB | All zeros |
| Channel C | `0x1AAB0000` | 4KB | All zeros |

Plus 4 interrupts: `0x2EA`, `0x2EB`, `0x2ED`, `0x2EE`.

### Why the Kernel Driver Doesn't Bind

The built-in `arm-scmi` driver supports both SMC and Mailbox transports
(`CONFIG_ARM_SCMI_TRANSPORT_SMC=y`, `CONFIG_ARM_SCMI_TRANSPORT_MAILBOX=y`),
but **`NVDA8200` has no `_DSD` ACPI property** (unchanged in Dec 2025 BIOS).
The driver requires `_DSD` to determine the transport type and parameters.

### Conclusion

The SCMI interface is non-functional and was a dead end. Power telemetry
is available through a completely different mechanism (SPBM via MTEL device).

## NVIDIA's Official Position

On **February 20, 2026**, NVIDIA moderator *aniculescu* stated on the
developer forums:

> "The Spark power management is different than the 72 core Grace CPU.
> There is no method to monitor CPU power and currently no plans to expose
> CPU rail information."

Source: https://forums.developer.nvidia.com/t/help-needed-how-to-enable-grace-cpu-power-telemetry-on-dgx-spark-gb10/360631

**Note:** This statement is technically incorrect — CPU power telemetry IS
available through the SPBM shared memory, just not through standard Linux
interfaces. NVIDIA likely meant there is no *supported* userspace API.

## Available Telemetry Summary

| Metric | Source | Access Method |
|--------|--------|---------------|
| System total power | SPBM +0x300 | Kernel module (ioremap 0x1C238000) |
| SoC package power | SPBM +0x304 | Kernel module |
| CPU+GPU combined | SPBM +0x308 | Kernel module |
| CPU P-core power | SPBM +0x30C | Kernel module |
| CPU E-core power | SPBM +0x310 | Kernel module |
| VCORE power | SPBM +0x314 | Kernel module |
| GPU output power | SPBM +0x324 | Kernel module (or nvidia-smi) |
| DC input power | SPBM +0x31C | Kernel module |
| Energy accumulators | SPBM +0x344ff | Kernel module |
| GPU power draw | nvidia-smi / NVML | `nvidia-smi --query-gpu=power.draw` |
| CPU temperature | hwmon (acpitz) | `/sys/class/thermal/thermal_zone*/temp` |
| NVMe temperature | hwmon | `/sys/class/hwmon/hwmon*/temp1_input` |
| Network temperature | hwmon (mlx5) | `/sys/class/hwmon/hwmon*/temp1_input` |

## Module Infrastructure

The `tools/spark/` directory contains kernel modules:

- `spbm_hwmon.c` — **hwmon driver** exposing SPBM as standard Linux sensors
  (23 power + 5 energy channels)
- `spbm_read.c` — **SPBM telemetry reader** (diagnostic dump of MTEL region 2
  at `0x1C238000` with liveness verification)
- `scmi_probe.c` — Full SCMI protocol prober with configurable SMC doorbell
  and channel selection (`insmod scmi_probe.ko smc_id=0xNNN channel_idx=N`)
- `scmi_scan.c` — Targeted doorbell scanner testing known-accepted SMC IDs
- `Makefile` — Build + MOK signing (`make all` builds and signs all modules)

Usage:
```bash
cd tools/spark
make hwmon   # Build, sign, load spbm_hwmon.ko, show sensors
make hwmon-unload  # Unload hwmon module
make spbm    # Build, sign, load spbm_read.ko, show diagnostic output
make probe   # SCMI probe (historical)
make scan    # SCMI doorbell scan (historical)
```

MOK signing key: `/var/lib/shim-signed/mok/MOK.{priv,der}` (enrolled).

## hwmon Driver

`spbm_hwmon.c` is a standalone kernel module that exposes all SPBM telemetry
as standard Linux hwmon sensors. It registers as a platform device with
direct `ioremap()` (ACPI binding to `NVDA8800` fails — device is stuck in
`waiting_for_supplier` due to missing supplier drivers).

```bash
cd tools/spark
make hwmon    # Build, sign, load, show sensors output
make hwmon-unload  # Unload module
```

Exposes 23 power channels + 5 energy accumulators via `/sys/class/hwmon/`.
Compatible with `lm-sensors` (`sensors` command).

**No upstream driver exists.** Searched mainline kernel (up to 6.14-rc4),
linux-next, NVIDIA grace-kernel, open-gpu-kernel-modules, and all NVIDIA
kernel repos. No driver for NVDA8800, NVDA8900, or NVPCF (NVDA0820) exists.
NVPCF is Windows-only (`nvpcf.sys`).

## Load Testing Validation

Per-cluster stress tests (Python tight loops with `taskset`):

| Scenario | PKG (W) | CPU_P (W) | CPU_E (W) | Notes |
|----------|---------|-----------|-----------|-------|
| Idle | ~22 | ~4.5 | ~0.1 | Baseline |
| E-cores only (cpu10-19) | ~55 | ~33 | ~5.3 | CPU_E confirmed working |
| P-cores only (cpu0-9) | ~60 | ~36 | ~5.4 | Cross-talk suggests shared domain |
| All 20 cores | ~92 | ~64 | ~10.5 | Full load |

Energy accumulators are more accurate than instantaneous readings (which
oscillate due to the 100ms PID control loop). PKG energy delta of ~18 kJ/s
at idle matches instantaneous SOC_PKG readings.

**Note:** CPU_E reports ~5W even when only P-cores are stressed, suggesting
some shared power domain or cross-cluster leakage in the measurement.

## Next Steps

1. ~~Write a proper hwmon driver~~ — **DONE** (`spbm_hwmon.c`)
2. ~~Test under load~~ — **DONE** (per-cluster validation above)
3. **Determine exact energy counter units** — verify mJ/tick calibration
   under known load with external measurement
4. **Investigate VDDQ=0** — memory power may need a different interface
5. **Explore OS-settable power limits** — the PL_OS registers at +0x100
   could allow software power capping (needs UPDATE_SPBM doorbell)
6. **Investigate CPU_E cross-talk** — E-core power ~5W even with only
   P-cores loaded; may be shared domain or measurement artifact
7. **Upstream the hwmon driver** — resolve ACPI supplier dependency to
   enable proper NVDA8800 binding instead of standalone ioremap
