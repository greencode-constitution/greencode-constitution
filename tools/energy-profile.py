#!/usr/bin/env python3
"""
energy-profile.py - Measure energy consumption of a command.

Usage:
    ./energy-profile.py [options] -- <command> [args...]

Options:
    --json          Output results as JSON
    --gpu-poll-ms   GPU polling interval in milliseconds (default: 100)
    --plug-poll-s   Smart plug polling interval in seconds (default: 10)
    -o, --output    Write results to file instead of stdout

Requirements:
    - Linux with RAPL support (Intel CPUs) or perf access
    - nvidia-smi for GPU measurements (optional)
    - tinytuya for SmartLife/Tuya plug wall power measurement (optional)

SmartLife/Tuya Plug (wall power measurement):
    Set these environment variables in your bashrc to enable.
    SMARTPLUG_ID is always required. Then configure either local or cloud mode:

    Common:
        SMARTPLUG_ID         Device ID (required)
        SMARTPLUG_DPS_POWER  DPS index/code for power reading (auto-detected)
        SMARTPLUG_DPS_SCALE  Scale divisor for raw value to watts (auto-detected)

    Local LAN mode (preferred):
        SMARTPLUG_IP         Device LAN IP address
        SMARTPLUG_KEY        Local key
        SMARTPLUG_VERSION    Protocol version (default: 3.3)

    Note: Tuya breakers/energy meters update power readings every ~15-30s
    in firmware. The plug poll interval (--plug-poll-s, default 10s) controls
    how often we query the device. Shorter intervals won't improve resolution.

    Cloud API mode (works remotely, rate-limited):
        SMARTPLUG_API_KEY    Tuya IoT Platform API/Client ID
        SMARTPLUG_API_SECRET Tuya IoT Platform API/Client Secret
        SMARTPLUG_API_REGION Data center region (default: eu)
                             Options: cn, us, us-e, eu, eu-w, sg, in

    To obtain credentials, install tinytuya and run:
        python -m tinytuya wizard

Example:
    ./energy-profile.py -- python train_model.py
    ./energy-profile.py --json -- ./benchmark
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List


@dataclass
class EnergyResult:
    """Energy measurement results."""
    wall_time_seconds: float
    cpu_time_seconds: float
    cpu_energy_joules: Optional[float]
    gpu_energy_joules: Optional[float]
    total_energy_joules: Optional[float]
    cpu_avg_power_watts: Optional[float]
    gpu_avg_power_watts: Optional[float]
    measurement_method: str
    exit_code: int
    command: List[str]
    gpu_type: Optional[str] = None
    is_apu: bool = False
    plug_energy_joules: Optional[float] = None
    plug_avg_power_watts: Optional[float] = None
    plug_mode: Optional[str] = None
    plug_samples: Optional[int] = None


class RAPLReader:
    """Read CPU energy from RAPL sysfs interface."""

    # Try both intel-rapl (common) and amd-rapl paths
    RAPL_PATHS = [
        Path("/sys/class/powercap/intel-rapl"),
        Path("/sys/class/powercap/amd-rapl"),
    ]

    def __init__(self):
        self.rapl_path = self._find_rapl_path()
        self.available = self.rapl_path is not None
        self.domains = self._find_domains() if self.available else []

    def _find_rapl_path(self) -> Optional[Path]:
        """Find available RAPL sysfs path."""
        for path in self.RAPL_PATHS:
            if path.exists() and os.access(path, os.R_OK):
                return path
        return None

    def _find_domains(self) -> List[Path]:
        """Find RAPL energy counter files (package-level)."""
        domains = []
        if not self.rapl_path:
            return domains
        for entry in self.rapl_path.iterdir():
            # Match both intel-rapl:N and amd-rapl:N patterns
            if entry.name.startswith(("intel-rapl:", "amd-rapl:")):
                energy_file = entry / "energy_uj"
                if energy_file.exists() and os.access(energy_file, os.R_OK):
                    domains.append(energy_file)
        return domains

    def read_energy_uj(self) -> int:
        """Read total energy in microjoules across all packages."""
        total = 0
        for domain in self.domains:
            try:
                with open(domain) as f:
                    total += int(f.read().strip())
            except (IOError, ValueError):
                pass
        return total


class PerfEnergyReader:
    """Read CPU energy using perf stat."""

    # Events to try (in order of preference)
    ENERGY_EVENTS = ["power/energy-pkg/", "power/energy-ram/", "power/energy-cores/"]

    def __init__(self):
        self.available_events = self._find_available_events()
        self.available = len(self.available_events) > 0

    def _find_available_events(self) -> List[str]:
        """Find which energy events are available on this system."""
        if not shutil.which("perf"):
            return []

        available = []
        for event in self.ENERGY_EVENTS:
            try:
                result = subprocess.run(
                    ["perf", "stat", "-e", event, "--", "true"],
                    capture_output=True,
                    text=True,
                    timeout=5.0
                )
                # Must succeed and show actual Joules reading
                if result.returncode == 0 and re.search(r"[\d.]+\s+Joules", result.stderr):
                    available.append(event)
            except (subprocess.TimeoutExpired, OSError):
                pass
        return available

    def measure(self, command: List[str]) -> tuple:
        """Run command under perf stat and return (exit_code, cpu_time, energy_joules)."""
        events = ",".join(self.available_events)
        result = subprocess.run(
            ["perf", "stat", "-e", events, "--"] + command,
            capture_output=True,
            text=True
        )

        # Parse perf output for energy values
        energy_joules = 0.0
        for line in result.stderr.split("\n"):
            # Match lines like "    42.31 Joules power/energy-pkg/"
            match = re.search(r"([\d.]+)\s+Joules\s+power/energy", line)
            if match:
                energy_joules += float(match.group(1))

        # Parse CPU time
        cpu_time = 0.0
        for line in result.stderr.split("\n"):
            if "task-clock" in line:
                match = re.search(r"([\d.,]+)\s+msec\s+task-clock", line)
                if match:
                    cpu_time = float(match.group(1).replace(",", "")) / 1000.0

        return result.returncode, cpu_time, energy_joules if energy_joules > 0 else None


class CPUPowerEstimator:
    """Estimate CPU power consumption using frequency and utilization when hardware measurement unavailable."""

    # TDP estimates for common CPU types (watts)
    TDP_ESTIMATES = {
        "arm_high_perf": 15.0,  # Cortex-X series, Apple M-series performance cores
        "arm_efficiency": 5.0,   # Cortex-A series efficiency cores
        "x86_desktop": 65.0,     # Typical desktop CPU
        "x86_laptop": 15.0,      # Typical laptop CPU
        "default": 25.0,         # Conservative default
    }

    def __init__(self):
        self.cpu_type = self._detect_cpu_type()
        self.base_tdp = self._get_base_tdp()
        self.cpu_count = os.cpu_count() or 1

    def _detect_cpu_type(self) -> str:
        """Detect CPU architecture and type."""
        try:
            with open("/proc/cpuinfo") as f:
                cpuinfo = f.read().lower()
                if "cortex-x" in cpuinfo or "apple" in cpuinfo:
                    return "arm_high_perf"
                elif "cortex-a" in cpuinfo or "aarch64" in cpuinfo or "arm" in cpuinfo:
                    return "arm_efficiency"
                elif "intel" in cpuinfo or "amd" in cpuinfo:
                    # Check if laptop (harder to detect, use conservative estimate)
                    return "x86_laptop"
        except IOError:
            pass
        return "default"

    def _get_base_tdp(self) -> float:
        """Get base TDP estimate for this CPU type."""
        return self.TDP_ESTIMATES.get(self.cpu_type, self.TDP_ESTIMATES["default"])

    def _read_cpu_frequencies(self) -> List[float]:
        """Read current frequencies for all CPUs in MHz."""
        frequencies = []
        for cpu_id in range(self.cpu_count):
            freq_file = Path(f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_cur_freq")
            try:
                if freq_file.exists():
                    with open(freq_file) as f:
                        # Value is in kHz, convert to MHz
                        frequencies.append(int(f.read().strip()) / 1000.0)
            except (IOError, ValueError):
                pass
        return frequencies

    def _read_max_frequencies(self) -> List[float]:
        """Read maximum frequencies for all CPUs in MHz."""
        frequencies = []
        for cpu_id in range(self.cpu_count):
            freq_file = Path(f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/cpuinfo_max_freq")
            try:
                if freq_file.exists():
                    with open(freq_file) as f:
                        frequencies.append(int(f.read().strip()) / 1000.0)
            except (IOError, ValueError):
                pass
        return frequencies

    def estimate_energy(self, wall_time: float, cpu_time: float) -> Optional[float]:
        """
        Estimate CPU energy consumption in joules.

        Power modeling:
        - Dynamic power scales approximately as f³ (P ∝ V² × f, V ∝ f for DVFS)
        - Use average frequency ratio during execution
        - Scale by CPU utilization (cpu_time / wall_time)
        - Idle power is minimal with modern power management (~2-5% TDP per active core)
        """
        if wall_time <= 0:
            return None

        # Read current and max frequencies
        cur_freqs = self._read_cpu_frequencies()
        max_freqs = self._read_max_frequencies()

        # CPU utilization (clamped to number of cores)
        utilization = min(cpu_time / wall_time, self.cpu_count)
        util_ratio = utilization / self.cpu_count

        if not cur_freqs or not max_freqs:
            # Fallback: use CPU utilization only
            # Idle power is ~3% TDP, active power scales linearly with utilization
            idle_power = 0.03 * self.base_tdp
            active_power = 0.97 * self.base_tdp * util_ratio
            avg_power = idle_power + active_power
            return avg_power * wall_time

        # Calculate frequency scaling factor (average across cores)
        freq_ratios = [cur / max_val for cur, max_val in zip(cur_freqs, max_freqs)]
        avg_freq_ratio = sum(freq_ratios) / len(freq_ratios) if freq_ratios else 1.0

        # Power scales as f³ for dynamic component (P ∝ V² × f, V ∝ f)
        freq_scale = avg_freq_ratio ** 3

        # Modern CPUs with good power gating: minimal idle, most power is dynamic
        # Idle: ~3% of TDP (package + IO)
        # Active: scales with frequency³ and utilization
        idle_power = 0.03 * self.base_tdp
        active_power = 0.97 * self.base_tdp * freq_scale * util_ratio
        avg_power = idle_power + active_power

        energy_joules = avg_power * wall_time
        return energy_joules


class GPUPowerMonitor:
    """Monitor GPU power consumption via nvidia-smi, rocm-smi, or sysfs."""

    def __init__(self, poll_interval_ms: int = 100):
        self.poll_interval = poll_interval_ms / 1000.0
        self._samples: List[float] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._amd_power_files: List[Path] = []  # Must be before _detect_gpu()
        self.gpu_type, self.available = self._detect_gpu()
        self.is_apu = self._detect_apu()

    def _detect_apu(self) -> bool:
        """Detect if running on an APU (integrated CPU+GPU)."""
        if self.gpu_type not in ("amd_sysfs", "amd_rocm"):
            return False
        # Check if GPU is on same PCI root as CPU (APU indicator)
        # APUs typically have PCI device class 0x0380xx (display controller)
        # and share power domain with CPU
        try:
            for card in Path("/sys/class/drm").iterdir():
                if not card.name.startswith("card") or "-" in card.name:
                    continue
                pci_class = card / "device" / "class"
                if pci_class.exists():
                    cls = pci_class.read_text().strip()
                    # 0x038000 = Display controller (APU GPU)
                    # 0x030000 = VGA controller (discrete GPU)
                    if cls.startswith("0x0380"):
                        return True
        except (IOError, OSError):
            pass
        return False

    def _detect_gpu(self) -> tuple:
        """Detect available GPU and return (type, available)."""
        # Try NVIDIA first
        if shutil.which("nvidia-smi"):
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return "nvidia", True

        # Try AMD ROCm CLI
        if shutil.which("rocm-smi"):
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--json"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    if data:
                        return "amd_rocm", True
                except (json.JSONDecodeError, KeyError):
                    pass

        # Try AMD sysfs (hwmon interface)
        self._amd_power_files = self._find_amd_sysfs_power()
        if self._amd_power_files:
            return "amd_sysfs", True

        return None, False

    def _find_amd_sysfs_power(self) -> List[Path]:
        """Find AMD GPU power files in sysfs."""
        power_files = []
        drm_path = Path("/sys/class/drm")
        if not drm_path.exists():
            return []

        for card in drm_path.iterdir():
            if not card.name.startswith("card") or "-" in card.name:
                continue
            hwmon_path = card / "device" / "hwmon"
            if not hwmon_path.exists():
                continue
            for hwmon in hwmon_path.iterdir():
                power_file = hwmon / "power1_average"
                if power_file.exists() and os.access(power_file, os.R_OK):
                    power_files.append(power_file)
        return power_files

    def _read_nvidia_power(self) -> Optional[float]:
        """Read power from NVIDIA GPU."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                return sum(
                    float(line.strip())
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                )
        except (subprocess.TimeoutExpired, ValueError):
            pass
        return None

    def _read_amd_rocm_power(self) -> Optional[float]:
        """Read power from AMD GPU via rocm-smi."""
        try:
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--json"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                total_power = 0.0
                # rocm-smi JSON format: {"card0": {"Power (Avg)": "45.0 W"}, ...}
                for card, info in data.items():
                    if card.startswith("card"):
                        for key, value in info.items():
                            if "power" in key.lower() and "avg" in key.lower():
                                # Parse "45.0 W" -> 45.0
                                match = re.search(r"([\d.]+)", str(value))
                                if match:
                                    total_power += float(match.group(1))
                                break
                return total_power if total_power > 0 else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
            pass
        return None

    def _read_amd_sysfs_power(self) -> Optional[float]:
        """Read power from AMD GPU via sysfs hwmon (microwatts -> watts)."""
        total_power = 0.0
        for power_file in self._amd_power_files:
            try:
                with open(power_file) as f:
                    # Value is in microwatts
                    total_power += int(f.read().strip()) / 1_000_000
            except (IOError, ValueError):
                pass
        return total_power if total_power > 0 else None

    def _poll_loop(self):
        """Background thread that polls GPU power."""
        if self.gpu_type == "nvidia":
            read_fn = self._read_nvidia_power
        elif self.gpu_type == "amd_rocm":
            read_fn = self._read_amd_rocm_power
        else:
            read_fn = self._read_amd_sysfs_power
        while self._running:
            power = read_fn()
            if power is not None:
                self._samples.append(power)
            time.sleep(self.poll_interval)

    def start(self):
        """Start background power monitoring."""
        if not self.available:
            return
        self._samples = []
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> tuple:
        """Stop monitoring and return (total_joules, avg_watts)."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

        if not self._samples:
            return 0.0, 0.0

        avg_watts = sum(self._samples) / len(self._samples)
        # Energy = average power * time (time = samples * interval)
        total_time = len(self._samples) * self.poll_interval
        total_joules = avg_watts * total_time

        return total_joules, avg_watts


try:
    import tinytuya
except ImportError:
    tinytuya = None


class SmartPlugMonitor:
    """Monitor wall power consumption via SmartLife/Tuya smart plug.

    Supports two modes:
    - Local LAN: direct device connection (fast polling, no rate limits)
    - Cloud API: via Tuya IoT Platform (works remotely, rate-limited)

    Local is preferred when both are configured.
    """

    # Common DPS indices for power on Tuya smart plugs
    # 19/5/4: standard plugs (deciwatts typically)
    # 118: Tuya breakers/energy meters (watts)
    POWER_DPS_CANDIDATES = ["19", "5", "4", "118"]
    # Common cloud API code names for power
    POWER_CODE_CANDIDATES = ["cur_power", "power", "Power"]
    # Tuya energy meters encode V/I/P in phase_a as base64 struct
    PHASE_CODES = ["phase_a", "phase_b", "phase_c"]

    def __init__(self, poll_interval_s: float = 10.0):
        self.poll_interval = poll_interval_s
        self._samples: List[float] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0
        self._stop_time: float = 0.0
        self._device = None  # local OutletDevice
        self._cloud = None   # Cloud API client
        self._cloud_device_id: Optional[str] = None
        self._power_dps: Optional[str] = None
        self._power_code: Optional[str] = None
        self._dps_scale: float = 1.0
        self._mode: Optional[str] = None  # "local" or "cloud"
        self.available = False
        self._setup()

    def _setup(self):
        """Configure plug from environment variables. Try local first, then cloud."""
        if tinytuya is None:
            return

        plug_id = os.environ.get("SMARTPLUG_ID")
        if not plug_id:
            return

        user_dps = os.environ.get("SMARTPLUG_DPS_POWER")
        user_scale = os.environ.get("SMARTPLUG_DPS_SCALE")

        # Try local LAN first (faster, no rate limits)
        plug_ip = os.environ.get("SMARTPLUG_IP")
        plug_key = os.environ.get("SMARTPLUG_KEY")
        if plug_ip and plug_key:
            if self._setup_local(plug_id, plug_ip, plug_key, user_dps, user_scale):
                return

        # Try cloud API
        api_key = os.environ.get("SMARTPLUG_API_KEY")
        api_secret = os.environ.get("SMARTPLUG_API_SECRET")
        if api_key and api_secret:
            self._setup_cloud(plug_id, api_key, api_secret, user_dps, user_scale)

    def _setup_local(self, plug_id, plug_ip, plug_key, user_dps, user_scale) -> bool:
        """Set up local LAN connection. Returns True on success."""
        version = float(os.environ.get("SMARTPLUG_VERSION", "3.3"))
        try:
            self._device = tinytuya.OutletDevice(plug_id, plug_ip, plug_key)
            self._device.set_version(version)
        except Exception:
            self._device = None
            return False

        try:
            status = self._device.status()
        except Exception:
            self._device = None
            return False

        dps = status.get("dps", {})
        if not dps:
            self._device = None
            return False

        if user_dps:
            self._power_dps = user_dps
            self._dps_scale = float(user_scale) if user_scale else 10.0
        else:
            for candidate in self.POWER_DPS_CANDIDATES:
                if candidate in dps:
                    raw = dps[candidate]
                    if isinstance(raw, (int, float)) and raw > 0:
                        # Heuristic: if value > 500, likely deciwatts (divide by 10)
                        self._dps_scale = 10.0 if raw > 500 else 1.0
                        self._power_dps = candidate
                        break
            if user_scale:
                self._dps_scale = float(user_scale)

        if self._power_dps is None:
            self._device = None
            return False

        self._mode = "local"
        self.available = True
        return True

    def _setup_cloud(self, plug_id, api_key, api_secret, user_dps, user_scale):
        """Set up Tuya Cloud API connection."""
        api_region = os.environ.get("SMARTPLUG_API_REGION", "eu")
        try:
            self._cloud = tinytuya.Cloud(
                apiRegion=api_region,
                apiKey=api_key,
                apiSecret=api_secret,
                apiDeviceID=plug_id,
            )
            self._cloud_device_id = plug_id
        except Exception:
            self._cloud = None
            return

        # Test connection and detect power code
        try:
            result = self._cloud.getstatus(plug_id)
        except Exception:
            self._cloud = None
            return

        if not result or not result.get("success"):
            self._cloud = None
            return

        status_list = result.get("result", [])

        if user_dps:
            # User specified a code name to use
            self._power_code = user_dps
            self._dps_scale = float(user_scale) if user_scale else 10.0
        else:
            # Auto-detect from cloud status response
            # First try direct power codes
            for item in status_list:
                code = item.get("code", "")
                value = item.get("value")
                if code in self.POWER_CODE_CANDIDATES:
                    if isinstance(value, (int, float)) and value >= 0:
                        self._dps_scale = 10.0 if value > 500 else 1.0
                        self._power_code = code
                        break
            # Then try phase_a encoded format (Tuya energy meters)
            if self._power_code is None:
                for item in status_list:
                    if item.get("code") in self.PHASE_CODES:
                        power = self._parse_phase_power(item.get("value", ""))
                        if power is not None:
                            self._power_code = item["code"]
                            self._dps_scale = 1.0  # _parse_phase_power returns watts
                            break
            if user_scale:
                self._dps_scale = float(user_scale)

        if self._power_code is None:
            self._cloud = None
            return

        self._mode = "cloud"
        self.available = True

    def _read_power_local(self) -> Optional[float]:
        """Read power from local LAN device.

        Sends updatedps() to request a firmware DPS refresh, waits briefly,
        then reads status(). Non-persistent connection ensures fresh data
        (persistent sockets return stale cached values on these breakers).
        Each poll cycle takes ~1-2s due to connection overhead.
        """
        try:
            self._device.updatedps([int(self._power_dps)])
        except Exception:
            pass
        time.sleep(0.5)
        try:
            status = self._device.status()
            dps = status.get("dps", {})
            raw = dps.get(self._power_dps)
            if raw is not None and isinstance(raw, (int, float)):
                return float(raw) / self._dps_scale
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_phase_power(value: str) -> Optional[float]:
        """Parse Tuya phase_a/b/c base64 struct: 2B voltage(0.1V) + 3B current(mA) + 3B power(W)."""
        try:
            data = base64.b64decode(value)
            if len(data) < 8:
                return None
            power = int.from_bytes(data[5:8], "big")
            return float(power)
        except Exception:
            return None

    def _read_power_cloud(self) -> Optional[float]:
        """Read power from Tuya Cloud API."""
        try:
            result = self._cloud.getstatus(self._cloud_device_id)
            if not result or not result.get("success"):
                return None
            for item in result.get("result", []):
                if item.get("code") == self._power_code:
                    value = item.get("value")
                    # Handle phase_a encoded format
                    if self._power_code in self.PHASE_CODES:
                        power = self._parse_phase_power(value)
                        if power is not None:
                            return power / self._dps_scale
                        return None
                    if isinstance(value, (int, float)):
                        return float(value) / self._dps_scale
        except Exception:
            pass
        return None

    def _poll_loop(self):
        """Background thread that polls plug power."""
        read_fn = self._read_power_local if self._mode == "local" else self._read_power_cloud
        while self._running:
            power = read_fn()
            if power is not None:
                self._samples.append(power)
            time.sleep(self.poll_interval)

    def start(self):
        """Start background power monitoring."""
        if not self.available:
            return
        self._samples = []
        self._running = True
        self._start_time = time.perf_counter()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> tuple:
        """Stop monitoring and return (total_joules, avg_watts, sample_count)."""
        self._running = False
        self._stop_time = time.perf_counter()
        if self._thread:
            self._thread.join(timeout=5.0)

        if not self._samples:
            return 0.0, 0.0, 0

        avg_watts = sum(self._samples) / len(self._samples)
        # Use actual wall time (not sample count * interval) since
        # each poll cycle takes ~1-2s and firmware only refreshes
        # power readings every ~15-30s
        total_time = self._stop_time - self._start_time
        total_joules = avg_watts * total_time

        return total_joules, avg_watts, len(self._samples)


def run_with_rusage(command: List[str]) -> tuple:
    """Run command and return (exit_code, wall_time, cpu_time) using os.wait4 for accurate rusage."""
    wall_start = time.perf_counter()
    proc = subprocess.Popen(command)
    _, status, rusage = os.wait4(proc.pid, 0)
    wall_time = time.perf_counter() - wall_start
    exit_code = os.waitstatus_to_exitcode(status)
    cpu_time = rusage.ru_utime + rusage.ru_stime
    return exit_code, wall_time, cpu_time


def measure_energy(command: List[str], gpu_poll_ms: int = 100, plug_poll_s: float = 10.0) -> EnergyResult:
    """Measure energy consumption of a command."""
    perf_reader = PerfEnergyReader()
    rapl_reader = RAPLReader()
    cpu_estimator = CPUPowerEstimator()
    gpu_monitor = GPUPowerMonitor(gpu_poll_ms)
    plug_monitor = SmartPlugMonitor(plug_poll_s)

    cpu_energy = None
    cpu_time = 0.0
    method = "none"

    # Start monitoring
    plug_monitor.start()
    gpu_monitor.start()

    if perf_reader.available:
        # Use perf stat for measurement
        method = "perf"
        wall_start = time.perf_counter()
        exit_code, cpu_time, cpu_energy = perf_reader.measure(command)
        wall_time = time.perf_counter() - wall_start
    elif rapl_reader.available:
        # Use RAPL sysfs
        method = "rapl_sysfs"
        energy_start = rapl_reader.read_energy_uj()

        exit_code, wall_time, cpu_time = run_with_rusage(command)

        energy_end = rapl_reader.read_energy_uj()

        # Handle counter wraparound
        if energy_end >= energy_start:
            cpu_energy = (energy_end - energy_start) / 1_000_000  # uJ to J
        else:
            cpu_energy = None  # Counter wrapped
    else:
        # Use software-based power estimation
        method = "estimated"
        exit_code, wall_time, cpu_time = run_with_rusage(command)
        cpu_energy = cpu_estimator.estimate_energy(wall_time, cpu_time)

    # Stop monitoring
    gpu_energy, gpu_avg_power = gpu_monitor.stop()
    plug_energy, plug_avg_power, plug_samples = plug_monitor.stop()
    if not gpu_monitor.available:
        gpu_energy = None
        gpu_avg_power = None
    if not plug_monitor.available:
        plug_energy = None
        plug_avg_power = None
        plug_samples = None

    # Calculate totals and averages
    total_energy = None
    cpu_avg_power = None

    if cpu_energy is not None:
        cpu_avg_power = cpu_energy / wall_time if wall_time > 0 else None
        total_energy = cpu_energy
        if gpu_energy is not None:
            if gpu_monitor.is_apu and cpu_energy is not None:
                # APU: GPU sensor (PPT) includes package power, subtract CPU to isolate GPU
                gpu_energy = max(0, gpu_energy - cpu_energy)
                gpu_avg_power = gpu_energy / wall_time if wall_time > 0 else 0
            total_energy = cpu_energy + gpu_energy

    return EnergyResult(
        wall_time_seconds=wall_time,
        cpu_time_seconds=cpu_time,
        cpu_energy_joules=cpu_energy,
        gpu_energy_joules=gpu_energy,
        total_energy_joules=total_energy,
        cpu_avg_power_watts=cpu_avg_power,
        gpu_avg_power_watts=gpu_avg_power,
        measurement_method=method,
        exit_code=exit_code,
        command=command,
        gpu_type=gpu_monitor.gpu_type,
        is_apu=gpu_monitor.is_apu,
        plug_energy_joules=plug_energy,
        plug_avg_power_watts=plug_avg_power,
        plug_mode=plug_monitor._mode if plug_monitor.available else None,
        plug_samples=plug_samples,
    )


def format_human(result: EnergyResult) -> str:
    """Format results for human consumption."""
    lines = [
        "=" * 60,
        "Energy Profile Results",
        "=" * 60,
        f"Command: {' '.join(result.command)}",
        f"Exit code: {result.exit_code}",
        "",
        "Timing:",
        f"  Wall time:  {result.wall_time_seconds:>10.3f} s",
        f"  CPU time:   {result.cpu_time_seconds:>10.3f} s",
        "",
    ]

    if result.cpu_energy_joules is not None:
        energy_label = "Energy (estimated):" if result.measurement_method == "estimated" else "Energy:"
        lines.extend([
            energy_label,
            f"  CPU energy: {result.cpu_energy_joules:>10.2f} J",
        ])
        if result.cpu_avg_power_watts:
            lines.append(f"  CPU power:  {result.cpu_avg_power_watts:>10.2f} W (avg)")

    if result.gpu_energy_joules is not None:
        lines.extend([
            f"  GPU energy: {result.gpu_energy_joules:>10.2f} J",
        ])
        if result.gpu_avg_power_watts:
            lines.append(f"  GPU power:  {result.gpu_avg_power_watts:>10.2f} W (avg)")

    if result.total_energy_joules is not None:
        lines.extend([
            "",
            f"  TOTAL:      {result.total_energy_joules:>10.2f} J",
        ])

    if result.plug_energy_joules is not None:
        lines.extend([
            "",
            "Wall Power (Smart Plug):",
            f"  Energy:     {result.plug_energy_joules:>10.2f} J",
        ])
        if result.plug_avg_power_watts:
            lines.append(f"  Power:      {result.plug_avg_power_watts:>10.2f} W (avg)")
        if result.plug_samples:
            lines.append(f"  Samples:    {result.plug_samples:>10d}")

    if result.cpu_energy_joules is None and result.gpu_energy_joules is None and result.plug_energy_joules is None:
        lines.append("Energy: (not available - no RAPL/perf access or smart plug)")

    method_info = result.measurement_method
    if result.gpu_type:
        method_info += f", gpu={result.gpu_type}"
    if result.plug_mode:
        method_info += f", plug={result.plug_mode}"
    lines.extend([
        "",
        f"Measurement method: {method_info}",
        "=" * 60,
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Measure energy consumption of a command",
        usage="%(prog)s [options] -- <command> [args...]"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--gpu-poll-ms", type=int, default=100,
                        help="GPU polling interval in milliseconds (default: 100)")
    parser.add_argument("--plug-poll-s", type=float, default=10.0,
                        help="Smart plug polling interval in seconds (default: 10)")
    parser.add_argument("-o", "--output", type=str, help="Write output to file")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to profile")

    args = parser.parse_args()

    # Handle the -- separator
    command = args.command
    if command and command[0] == "--":
        command = command[1:]

    if not command:
        parser.print_help()
        sys.exit(1)

    result = measure_energy(command, args.gpu_poll_ms, args.plug_poll_s)

    if args.json:
        output = json.dumps(asdict(result), indent=2)
    else:
        output = format_human(result)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
            f.write("\n")
    else:
        print(output)

    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
