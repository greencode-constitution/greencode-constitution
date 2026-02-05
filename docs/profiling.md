# Energy Profiling Reference

## Options

```
--json          JSON output
--gpu-poll-ms N GPU poll interval (default: 100)
-o, --output F  Write to file
```

## Requirements

- Linux with `perf` or readable `/sys/class/powercap/intel-rapl/`
- Optional: `nvidia-smi` for GPU

## RAPL Access

```bash
# Temporary (until reboot)
sudo chmod -R a+r /sys/class/powercap/intel-rapl/
# Or
sudo sysctl kernel.perf_event_paranoid=1
```

## Comparison Workflow

```bash
# BASE_URL is where you fetched this doc from
curl -sL $BASE_URL/profile.sh | bash -s -- --json -o before.json -- ./cmd
# ... apply fix ...
curl -sL $BASE_URL/profile.sh | bash -s -- --json -o after.json -- ./cmd
jq -s '{before: .[0].total_energy_joules, after: .[1].total_energy_joules,
        reduction_pct: ((.[0].total_energy_joules - .[1].total_energy_joules) / .[0].total_energy_joules * 100)}' \
  before.json after.json
```
