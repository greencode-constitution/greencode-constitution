#!/bin/bash
set -euo pipefail

# Run llama.cpp batch benchmark
# Emulates a RAG subagent scenario: 8 parallel queries with long context, short output.
# npl=8 triggers MMQ kernels, making both prefill and generation compute-bound.

echo "==> Running llama.cpp batch benchmark (npl=8, pp2048, tg128)..."
./build/bin/llama-bench -m models/Qwen3-8B-Q4_K_M.gguf -npl 8 -p 2048 -n 128 -r 1 2>&1 | awk '
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
