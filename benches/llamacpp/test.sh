#!/bin/bash
set -euo pipefail

# Run llama.cpp batch benchmark
# Emulates a RAG subagent scenario: large prompt (8x2048 concatenated contexts), short output.
# Prefill is compute-bound (MMQ/GEMM on large token batch); generation is kept short.

echo "==> Running llama.cpp batch benchmark (pp16384, tg128)..."
./build/bin/llama-bench -m models/Qwen3-8B-Q4_K_M.gguf -p 16384 -n 128 -r 1 2>&1 | awk '
/pp[0-9]+/ {
    match($0, /pp([0-9]+)/, arr);
    prompt_tokens=arr[1];
    match($0, /([0-9]+\.[0-9]+) ±/, speed);
    prompt_speed=speed[1]
}
/tg[0-9]+/ {
    match($0, /tg([0-9]+)/, arr);
    gen_tokens=arr[1];
    match($0, /([0-9]+\.[0-9]+) ±/, speed);
    gen_speed=speed[1]
}
END {
    print "Input:  " prompt_tokens " tokens @ " prompt_speed " t/s"
    print "Output: " gen_tokens " tokens @ " gen_speed " t/s"
}'
