# Pasteur Benchmark

Standardized energy efficiency benchmark for Pasteur data synthesis pipelines.

## Setup

If `pasteur [bench]` detected in project, run these scripts in order:

### 1. Prepare environment

Installs Pasteur and ingests the mimic_core dataset:

```bash
bash <(curl -sfL $BASE_URL/benches/pasteur/prepare.sh)
```

Creates:
- Python venv at `./venv`
- Ingested mimic_core dataset

### 2. Run benchmark with profiler

Executes the mimic_core.mare synthesis pipeline:

```bash
curl -sfL $BASE_URL/benches/pasteur/test.sh > /tmp/pasteur-test.sh && chmod +x /tmp/pasteur-test.sh && bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) -- /tmp/pasteur-test.sh
```

## Output

**Energy consumption:**
- CPU: X.X joules (RAPL/perf)
- Wall time: X.Xs
- CPU time: X.Xs

## Workflow

1. Run baseline benchmark to measure initial performance
2. **Profile hotspots** to identify optimization targets:
   ```bash
   python -m cProfile -s cumulative -c "from pasteur.__main__ import main; main()" -- p mimic_core.mare 2>&1 | head -40
   ```
   Focus on functions that account for >5% of total runtime (per Article IV).
3. Apply targeted optimizations from constitution and skills
4. Re-run benchmark with profiler
5. Compare results: lower joules and/or shorter wall time = improvement

## Benchmark Details

- **Pipeline:** mimic_core.mare (data synthesis with MARE module)
- **Framework:** Kedro-based pipeline with Pasteur extensions
- **Workload:** CPU-bound data synthesis and transformation
