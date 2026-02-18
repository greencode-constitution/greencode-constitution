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
- Python venv at `./.venv`
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
curl -sfL $BASE_URL/benches/llamacpp/{fn}.sh > /tmp/llamacpp-test.sh && chmod +x /tmp/llamacpp-test.sh && bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) -- /tmp/llamacpp-test.sh
```

Where `{fn}` is the filename for the benchmark script: `test-simple.sh` for one agent, and `test-rag.sh` for multi-agent RAG scenario (focuses on input token processing and total throughput).

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
2. **Profile kernel-level hotspots** to identify optimization targets:
   ```bash
   nsys profile --stats=true ./build/bin/llama-bench -m models/Qwen3-8B-Q4_K_M.gguf -p 488 -n 128 -r 1 2>&1 | tail -40
   ```
   Focus on the "CUDA Kernel Statistics" table. Only optimize kernels that account for >5% of total GPU time (per Article IV). Use a shorter `-n` value here for faster profiling — kernel proportions are stable across generation lengths.
3. For each hot kernel, use `ncu` to determine if it is memory-bound or compute-bound:
   ```bash
   ncu --set full -k "kernel_name" ./build/bin/llama-bench -m models/Qwen3-8B-Q4_K_M.gguf -p 488 -n 32 -r 1
   ```
4. Apply targeted optimizations from constitution and skills
5. Rebuild: `curl -sfL $BASE_URL/benches/llamacpp/build.sh | bash`
   - Append `| tail -5` to see final build summary
6. Re-run benchmark with profiler
7. Compare results: lower joules and/or higher throughput = improvement

## Benchmark Details

- **Model:** Qwen3-8B-Q4_K_M (4.68 GiB quantized)
- **Backend:** CUDA with 99 GPU layers
- **Consistency:** Single run, deterministic workload
