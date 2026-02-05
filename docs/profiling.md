# Energy Profiling Reference

## Options

```
--json          JSON output
--gpu-poll-ms N GPU poll interval (default: 100)
-o, --output F  Write to file
```

## Requirements

- Linux with `perf`
- Optional: `nvidia-smi` for GPU

## Enable RAPL Access

```bash
# Once per boot
sudo sysctl kernel.perf_event_paranoid=-1
```

## Comparison Workflow

```bash
bash <(curl -sL $BASE_URL/profile.sh) --json -o before.json -- ./cmd
# ... apply fix ...
bash <(curl -sL $BASE_URL/profile.sh) --json -o after.json -- ./cmd
jq -s '{before: .[0].total_energy_joules, after: .[1].total_energy_joules,
        reduction_pct: ((.[0].total_energy_joules - .[1].total_energy_joules) / .[0].total_energy_joules * 100)}' \
  before.json after.json
```
