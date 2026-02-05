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
    """Monitor NVIDIA GPU power consumption via nvidia-smi."""

    def __init__(self, poll_interval_ms: int = 100):
        self.available = self._check_available()
        self.poll_interval = poll_interval_ms / 1000.0
        self._samples: List[float] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _check_available(self) -> bool:
        if not shutil.which("nvidia-smi"):
            return False
        # Check if we can query power
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and result.stdout.strip()

    def _poll_loop(self):
        """Background thread that polls GPU power."""
        while self._running:
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
                if result.returncode == 0:
                    # Sum power across all GPUs
                    total_power = sum(
                        float(line.strip())
                        for line in result.stdout.strip().split("\n")
                        if line.strip()
                    )
                    self._samples.append(total_power)
            except (subprocess.TimeoutExpired, ValueError):
                pass
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

    wall_start = time.perf_counter()

    if perf_reader.available:
        # Use perf stat for measurement
        method = "perf"
        exit_code, cpu_time, cpu_energy = perf_reader.measure(command)
        wall_time = time.perf_counter() - wall_start
    elif rapl_reader.available:
        # Use RAPL sysfs
        method = "rapl_sysfs"
        energy_start = rapl_reader.read_energy_uj()
        proc_start = time.process_time()

        result = subprocess.run(command)
        exit_code = result.returncode

        wall_time = time.perf_counter() - wall_start
        cpu_time = time.process_time() - proc_start
        energy_end = rapl_reader.read_energy_uj()

        # Handle counter wraparound
        if energy_end >= energy_start:
            cpu_energy = (energy_end - energy_start) / 1_000_000  # uJ to J
        else:
            cpu_energy = None  # Counter wrapped
    else:
        # No energy measurement available
        method = "time_only"
        proc_start = time.process_time()
        result = subprocess.run(command)
        exit_code = result.returncode
        wall_time = time.perf_counter() - wall_start
        cpu_time = time.process_time() - proc_start

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
            total_energy += gpu_energy

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
        command=command
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

    lines.extend([
        "",
        f"Measurement method: {result.measurement_method}",
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
