### Options

```
--json          JSON output
--gpu-poll-ms N GPU poll interval (default: 100)
-o, --output F  Write to file
```

### Requirements

- Linux with `perf`
- Optional: `nvidia-smi` for GPU

### Measurement Methods

The tool tries methods in order: **perf** (hardware counters) → **rapl_sysfs** → **estimated** (lower accuracy, TDP-based). The output shows which method was used. For accurate results, enable perf/RAPL access below.

### Enable RAPL Access

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

**Note:** Always check the `measurement_method` field in the JSON output. **If `estimated` was used, warn the user** that results are approximations with significantly lower accuracy than hardware-based measurements. For reliable comparisons, enable perf/RAPL access and ensure both measurements use the same method.
