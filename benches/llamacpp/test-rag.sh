#!/bin/bash
set -euo pipefail

# Run llama.cpp batched benchmark
# Emulates a RAG subagent scenario: 8 parallel queries with 2048-token context, 128-token output.
# npl=8 triggers MMQ kernels, making both prefill and generation compute-bound.
# Uses llama-batched-bench which supports parallel sequences (-npl).

echo "==> Running llama.cpp batched benchmark (npl=8, pp2048, tg128)..."
./build/bin/llama-batched-bench \
    -m models/Qwen3-8B-Q4_K_M.gguf \
    -c 32768 \
    -b 2048 \
    -ub 512 \
    -npp 2048 \
    -ntg 128 \
    -npl 8 \
    2>&1 | awk '
/^\|[[:space:]]+[0-9]/ {
    gsub(/\|/, " ")
    pp = $1
    tg = $2
    batch = $3
    pp_speed = $6
    tg_speed = $8
    total_speed = $10
}
END {
    print "Batch:  " batch " sequences"
    print "Input:  " pp " tokens @ " pp_speed " t/s"
    print "Output: " tg " tokens @ " tg_speed " t/s"
    print "Total:  " total_speed " t/s"
}'
