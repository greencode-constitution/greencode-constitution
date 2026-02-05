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

Pick a random suffix (e.g. 4 hex chars) and use it in all paths:

```bash
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) --json -o /tmp/energy-XXXX-before.json -- ./cmd
# ... apply fix ...
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) --json -o /tmp/energy-XXXX-after.json -- ./cmd
python3 -c "import json; b,a = [json.load(open(f))['total_energy_joules'] for f in ('/tmp/energy-XXXX-before.json','/tmp/energy-XXXX-after.json')]; print(f'Before: {b:.2f}J  After: {a:.2f}J  Reduction: {(b-a)/b*100:.1f}%')"
rm /tmp/energy-XXXX-*.json
```
