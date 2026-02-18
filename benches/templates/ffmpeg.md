# FFmpeg Benchmark

Standardized energy efficiency benchmark for FFmpeg transcoding pipelines.

## Setup

If `ffmpeg [bench]` detected in project, run these scripts in order:

### 1. Prepare environment

Installs build dependencies:

```bash
bash <(curl -sfL $BASE_URL/benches/ffmpeg/prepare.sh)
```

Installs:
- Build tools (nasm, yasm)
- Codec libraries (libx264, libx265)
- Text/font libraries (libfreetype, libfontconfig, libass)

### 2. Build with optimizations

Compiles FFmpeg, auto-detecting NVIDIA GPU for CUDA/NVENC support:

```bash
bash <(curl -sfL $BASE_URL/benches/ffmpeg/build.sh)
```

Produces:
- `./ffmpeg` and `./ffprobe` binaries
- CUDA/NVENC enabled if NVIDIA GPU + nvcc detected
- Full parallel build using all CPU cores

### 3. Run benchmark with profiler

Executes standardized transcoding workload:

```bash
curl -sfL $BASE_URL/benches/ffmpeg/test.sh > /tmp/ffmpeg-test.sh && chmod +x /tmp/ffmpeg-test.sh && bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) -- /tmp/ffmpeg-test.sh
```

The test script auto-detects NVENC support in the built binary and selects the appropriate pipeline.

## Output

**Transcoding throughput:**
- Frames: XXXX @ XX fps
- Speed: X.Xx realtime

**Energy consumption:**
- CPU: X.X joules (RAPL/perf)
- GPU: X.X joules (nvidia-smi, if GPU pipeline)
- Wall time: X.Xs

## Workflow

1. Run baseline benchmark to measure initial performance
2. **Profile hotspots** to identify optimization targets:
   - For CPU-only builds:
     ```bash
     perf record -g ./ffmpeg -y -f lavfi -i testsrc2=duration=10:size=1920x1080:rate=30 -f null - 2>/dev/null && perf report --stdio | head -60
     ```
   - For GPU builds:
     ```bash
     nsys profile --stats=true ./ffmpeg -y -f lavfi -i testsrc2=duration=10:size=3840x2160:rate=60 -f null - 2>&1 | tail -40
     ```
   Focus on filters/codecs that account for >5% of total time (per Article IV).
3. Apply targeted optimizations from constitution and skills
4. Rebuild: `bash <(curl -sfL $BASE_URL/benches/ffmpeg/build.sh)`
5. Re-run benchmark with profiler
6. Compare results: lower joules and/or higher throughput = improvement

## Benchmark Details

- **GPU pipeline:** 4K 60fps input, split CPU+GPU filter graph, h264_nvenc encoding
- **CPU pipeline:** 1080p 30fps input, complex multi-branch filter graph, libx264 encoding
- **Filters (GPU):** scale_cuda, bilateral_cuda, overlay_cuda + CPU unsharp/noise/drawtext
- **Filters (CPU):** scale, unsharp, edgedetect, colorbalance, hstack, overlay, drawtext, eq, noise, deflicker
- **Audio:** highpass, lowpass, dynaudnorm (GPU) / amerge, aresample, aecho (CPU)
- **Duration:** 60 seconds of synthetic content (testsrc2 + sine generators)
- **Consistency:** Deterministic synthetic input, single run
