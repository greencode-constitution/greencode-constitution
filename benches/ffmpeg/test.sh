#!/bin/bash
set -euo pipefail

# Run FFmpeg benchmark
# Uses GPU-accelerated pipeline if NVENC is available, otherwise CPU-only.
# Both pipelines produce comparable workloads with complex filter graphs.

OUTPUT="/tmp/ffmpeg_bench_output.mp4"

# Detect NVENC support in the built binary
ENCODERS=$(./ffmpeg -hide_banner -encoders 2>/dev/null || true)
HAS_NVENC=0
if echo "$ENCODERS" | grep -q h264_nvenc; then
    HAS_NVENC=1
fi

if [ "$HAS_NVENC" -eq 1 ]; then
    echo "==> Running FFmpeg benchmark (CPU+GPU pipeline)..."
    echo "    Input:   4K 60fps synthetic (testsrc2), 60s"
    echo "    Filters: scale_cuda, bilateral_cuda, overlay_cuda + CPU unsharp/noise/drawtext"
    echo "    Encoder: h264_nvenc"

    ./ffmpeg -y \
        -f lavfi -i testsrc2=duration=60:size=3840x2160:rate=60 \
        -f lavfi -i sine=frequency=440:duration=60:sample_rate=48000 \
        -filter_complex "\
            [0:v]split=2[cpu_path][gpu_path];\
            [cpu_path]scale=1920x1080,unsharp=5:5:1.0,\
                noise=alls=20:allf=t,\
                drawtext=text='Benchmark':fontsize=36:fontcolor=white:x=10:y=10[cpu_out];\
            [gpu_path]hwupload_cuda,scale_cuda=1280:720,\
                bilateral_cuda=sigmaS=10:sigmaR=0.1[gpu_scaled];\
            [cpu_out]hwupload_cuda[cpu_uploaded];\
            [cpu_uploaded][gpu_scaled]overlay_cuda=x=640:y=360[composited];\
            [composited]scale_cuda=1920:1080[vout];\
            [1:a]highpass=f=200,lowpass=f=8000,dynaudnorm[aout]" \
        -map "[vout]" -map "[aout]" \
        -c:v h264_nvenc -preset p5 -rc vbr -cq 23 -profile:v high \
        -c:a aac -b:a 192k \
        -movflags +faststart \
        "$OUTPUT" 2>&1
else
    echo "==> Running FFmpeg benchmark (CPU-only pipeline)..."
    echo "    Input:   1080p 30fps synthetic (testsrc2), 60s"
    echo "    Filters: scale, unsharp, edgedetect, colorbalance, overlay, drawtext, noise, eq"
    echo "    Encoder: libx264"

    ./ffmpeg -y \
        -f lavfi -i testsrc2=duration=60:size=1920x1080:rate=30 \
        -f lavfi -i sine=frequency=440:duration=60:sample_rate=48000 \
        -f lavfi -i sine=frequency=880:duration=60:sample_rate=48000 \
        -filter_complex "\
            [0:v]split=3[v1][v2][v3];\
            [v1]scale=1280x720,unsharp=5:5:1.0,hue=s=0.8[scaled];\
            [v2]scale=640x360,edgedetect=low=0.1:high=0.4[edges];\
            [v3]scale=640x360,colorbalance=rs=0.3:gs=-0.2:bs=0.1[color];\
            [edges][color]hstack[bottom];\
            [scaled]pad=1280:1080:0:0[top_padded];\
            [top_padded][bottom]overlay=0:720[composited];\
            [composited]drawtext=text='Benchmark':fontsize=36:fontcolor=white:x=10:y=10,\
                eq=brightness=0.06:contrast=1.1,\
                noise=alls=20:allf=t,\
                deflicker,\
                fps=24[vout];\
            [1:a][2:a]amerge=inputs=2,\
                aresample=44100,\
                highpass=f=200,\
                lowpass=f=8000,\
                dynaudnorm,\
                aecho=0.8:0.88:60:0.4[aout]" \
        -map "[vout]" -map "[aout]" \
        -c:v libx264 -preset medium -crf 23 -profile:v high -level 4.1 \
        -c:a aac -b:a 192k -ac 2 \
        -movflags +faststart \
        -threads 0 \
        "$OUTPUT" 2>&1
fi

echo "==> Benchmark complete!"
echo "    Output: $OUTPUT"
