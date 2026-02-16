# llama.cpp Benchmark

Standardized energy efficiency benchmark for llama.cpp inference.

## Setup

If `llama.cpp [bench]` detected in project, run these scripts in order:

### 1. Prepare environment

Downloads model and sets up dependencies:

```bash
bash <(curl -sfL $BASE_URL/benches/llamacpp/prepare.sh)
```

Creates:
- Python venv at `./venv`
- Downloads Qwen3-8B-Q4_K_M model to `./models/`

### 2. Build with optimizations

Compiles llama.cpp with CUDA support:

```bash
bash <(curl -sfL $BASE_URL/benches/llamacpp/build.sh)
```

Produces:
- `./build/bin/llama-bench` executable
- Full parallel build using all CPU cores

### 3. Run benchmark with profiler

Executes standardized inference workload:

```bash
bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) -- bash <(curl -sfL $BASE_URL/benches/llamacpp/test.sh)
```

## Output

**Token throughput:**
- Input: 488 tokens @ X.X t/s (prompt processing)
- Output: 512 tokens @ X.X t/s (text generation)

**Energy consumption:**
- CPU: X.X joules (RAPL/perf)
- GPU: X.X joules (nvidia-smi/rocm-smi)
- Wall time: X.Xs

## Workflow

1. Run baseline benchmark to measure initial performance
2. Apply optimizations from constitution and skills
3. Rebuild: `bash <(curl -sfL $BASE_URL/benches/llamacpp/build.sh)`
4. Re-run benchmark with profiler
5. Compare results: lower joules and/or higher throughput = improvement

## Benchmark Details

- **Prompt:** 488 tokens (AI ethics discussion with question)
- **Generation:** 512 tokens (forced via `--ignore-eos`)
- **Model:** Qwen3-8B-Q4_K_M (4.68 GiB quantized)
- **Backend:** CUDA with 99 GPU layers
- **Consistency:** Single run, deterministic workload
