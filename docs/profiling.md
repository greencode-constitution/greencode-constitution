### Options

```
--json            JSON output
--gpu-poll-ms N   GPU poll interval (default: 100)
--plug-poll-s N   Smart plug poll interval in seconds (default: 10)
-o, --output F    Write to file
```

### Requirements

- Linux with `perf`
- Optional: `nvidia-smi` for GPU
- Optional: `tinytuya` + SmartLife/Tuya smart plug for wall power

### Measurement Methods

The tool tries CPU measurement methods in order: **perf** (hardware counters) → **rapl_sysfs** → **estimated** (lower accuracy, TDP-based). The output shows which was used as `cpu=<method>`. For accurate results, enable perf/RAPL access below.

### Enable Perf/RAPL Access

RUN THIS AT THE BEGINNING, NOT AFTER BENCHES. IF METHOD REMAINS ESTIMATED, DO NOT TRY TO IMPROVISE AND LET IT BE.
```bash
# Once per boot (enables perf and RAPL methods)
sudo sysctl kernel.perf_event_paranoid=-1
```

### Comparison Workflow

Pick a random suffix (e.g. 4 hex chars) and use it in all paths:

```bash
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) --json -o /tmp/energy-XXXX-before.json -- ./cmd
# ... apply fix ...
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) --json -o /tmp/energy-XXXX-after.json -- ./cmd
python3 -c "import json; b,a = [json.load(open(f))['total_energy_joules'] for f in ('/tmp/energy-XXXX-before.json','/tmp/energy-XXXX-after.json')]; print(f'Before: {b:.2f}J  After: {a:.2f}J  Reduction: {(b-a)/b*100:.1f}%')"
rm /tmp/energy-XXXX-*.json
```

**Note:** Always check the `measurement_method` field in the JSON output. **If `estimated` was used (i.e. `cpu=estimated`), warn the user** that CPU energy results are approximations with significantly lower accuracy than hardware-based measurements. For reliable comparisons, enable perf/RAPL access and ensure both measurements use the same method.

### Wall Power (Smart Plug)

Optional SmartLife/Tuya smart plug support measures total wall power (including PSU losses, RAM, fans). Configured via `SMARTPLUG_*` env vars — see the docstring at the top of `tools/energy-profile.py` for setup details. Only useful for benchmarks **> 1 minute** (firmware refreshes readings every ~15-30s). Do not look up or troubleshoot plug configuration unless the user specifically asks for help setting one up.

### Kernel-Level Profiling (GPU)

Energy profiling tells you *how much* energy is consumed. Kernel-level profiling tells you *where* it is consumed. **Always profile before optimizing** (Article IV).

When NVIDIA GPU is detected (`*.cu` / `*.cuh` files in project), use Nsight tools:

```bash
# Step 1: Identify which kernels dominate GPU time
nsys profile --stats=true ./your_program

# Step 2: Deep-dive into a specific hot kernel
ncu --set full -k "kernel_name" ./your_program
```

See the `code/cuda` skill for detailed usage, metric interpretation, and a decision tree for memory-bound vs compute-bound kernels.

For non-NVIDIA GPUs or CPU-only workloads, use `perf` flamegraphs (see `code/c-cpp` skill) or language-specific profilers (see matching language skill).
