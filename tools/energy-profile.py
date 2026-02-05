#!/usr/bin/env python3
"""
energy-profile.py - Measure energy consumption of a command.

Usage:
    ./energy-profile.py [options] -- <command> [args...]

Options:
    --json          Output results as JSON
    --gpu-poll-ms   GPU polling interval in milliseconds (default: 100)
    -o, --output    Write results to file instead of stdout

Requirements:
    - Linux with RAPL support (Intel CPUs) or perf access
    - nvidia-smi for GPU measurements (optional)

Example:
    ./energy-profile.py -- python train_model.py
    ./energy-profile.py --json -- ./benchmark
"""

import argparse
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


def run_with_rusage(command: List[str]) -> tuple:
    """Run command and return (exit_code, wall_time, cpu_time) using os.wait4 for accurate rusage."""
    wall_start = time.perf_counter()
    proc = subprocess.Popen(command)
    _, status, rusage = os.wait4(proc.pid, 0)
    wall_time = time.perf_counter() - wall_start
    exit_code = os.waitstatus_to_exitcode(status)
    cpu_time = rusage.ru_utime + rusage.ru_stime
    return exit_code, wall_time, cpu_time


def measure_energy(command: List[str], gpu_poll_ms: int = 100) -> EnergyResult:
    """Measure energy consumption of a command."""
    perf_reader = PerfEnergyReader()
    rapl_reader = RAPLReader()
    gpu_monitor = GPUPowerMonitor(gpu_poll_ms)

    cpu_energy = None
    cpu_time = 0.0
    method = "none"

    # Start GPU monitoring
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
        # No energy measurement available
        method = "time_only"
        exit_code, wall_time, cpu_time = run_with_rusage(command)

    # Stop GPU monitoring
    gpu_energy, gpu_avg_power = gpu_monitor.stop()
    if not gpu_monitor.available:
        gpu_energy = None
        gpu_avg_power = None

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
        is_apu=gpu_monitor.is_apu
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
        lines.extend([
            "Energy:",
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

    if result.cpu_energy_joules is None and result.gpu_energy_joules is None:
        lines.append("Energy: (not available - no RAPL/perf access)")

    method_info = result.measurement_method
    if result.gpu_type:
        method_info += f", gpu={result.gpu_type}"
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

    result = measure_energy(command, args.gpu_poll_ms)

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
