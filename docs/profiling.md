### Options

```
--json          JSON output
--gpu-poll-ms N GPU poll interval (default: 100)
-o, --output F  Write to file
```

### Requirements

- Linux with `perf`
- Optional: `nvidia-smi` for GPU

### Enable RAPL Access

```bash
# Once per boot
sudo sysctl kernel.perf_event_paranoid=-1
```

### Comparison Workflow

```bash
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) --json -o before.json -- ./cmd
# ... apply fix ...
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) --json -o after.json -- ./cmd
jq -s '{before: .[0].total_energy_joules, after: .[1].total_energy_joules,
        reduction_pct: ((.[0].total_energy_joules - .[1].total_energy_joules) / .[0].total_energy_joules * 100)}' \
  before.json after.json
```
