# CUDA / GPU Kernel Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: profile GPU workloads, identify kernel-level hotspots, and apply targeted optimizations.

---

## How to Use This Skill

1. **Profile first.** Run `nsys` or `ncu` against the target workload to identify which kernels dominate GPU time.
2. Only optimize kernels that account for **>5% of total GPU time** (per Article IV Scope Guards).
3. For each hot kernel, use `ncu` to determine whether it is memory-bandwidth-bound or compute-bound, then apply the appropriate fix pattern.

---

## Profiling Tools

### Nsight Systems (`nsys`) — Timeline & Kernel Breakdown

Identifies *which* kernels take the most time. Always start here.

```bash
# Full profile with stats summary
nsys profile --stats=true ./your_program

# Save to file for GUI analysis
nsys profile -o profile_output ./your_program

# Filter to CUDA API and kernel activity only
nsys profile --trace=cuda,nvtx --stats=true ./your_program
```

**Reading the output:** Look at the "CUDA Kernel Statistics" table. Sort by total time. Kernels below 5% of total GPU time are unlikely to yield meaningful energy savings.

Example output:
```
 Time (%)  Total Time (ns)  Instances  Avg (ns)   Kernel Name
 --------  ---------------  ---------  ---------  -----------
    72.3       1,245,000        128     9,726      mul_mat_vec_q4_K_cuda
    12.1         208,500         64     3,258      flash_attn_ext_f16
     4.2          72,300         64     1,130      rms_norm_f32
     ...
```

In this example, only `mul_mat_vec_q4_K_cuda` and `flash_attn_ext_f16` are worth optimizing (~84% combined).

### Nsight Compute (`ncu`) — Per-Kernel Deep Analysis

Identifies *why* a specific kernel is slow: memory-bound, compute-bound, or latency-bound.

```bash
# Profile a specific kernel by name substring
ncu --set full -k "mul_mat_vec" ./your_program

# Roofline analysis (shows how close to hardware limits)
ncu --set roofline -k "kernel_name" ./your_program

# Collect specific metrics only (lighter weight)
ncu --metrics sm__throughput.avg.pct_of_peak_sustained_elapsed,dram__throughput.avg.pct_of_peak_sustained_elapsed -k "kernel_name" ./your_program
```

**Key metrics to check:**

| Metric | What it tells you |
|--------|-------------------|
| `sm__throughput` | Compute utilization (% of peak) |
| `dram__throughput` | Memory bandwidth utilization (% of peak) |
| `sm__warps_active.avg.pct_of_peak_sustained_elapsed` | Occupancy |
| `l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum` | Global load transactions |

**Decision tree:**
- **dram throughput > 60%**: Memory-bandwidth-bound. Reduce memory traffic (vectorized loads, fusion, data reuse).
- **sm throughput > 60%**: Compute-bound. Reduce arithmetic (fast math, algorithmic changes).
- **Both low**: Latency-bound. Increase occupancy (reduce registers/shared memory, increase block size).

---

## 1. Unfused Kernel Chains (Redundant Global Memory Round-Trips)

**Why it wastes energy**: Each kernel reads from and writes to global memory. A chain of elementwise kernels (e.g., scale -> tanh -> scale) moves the same data through global memory multiple times. Fusing them into one kernel reduces memory traffic proportionally to the chain length.

### Detect

```bash
# Look for sequences of simple elementwise kernel launches
nsys profile --stats=true ./your_program 2>&1 | grep -E 'scale|norm|unary|softcap|silu|gelu|add_f32'
```

If multiple small kernels appear consecutively in the timeline with the same tensor dimensions, they are fusion candidates.

### Bad

```cpp
// Three separate kernels, three global memory round-trips
scale_f32<<<grid, block>>>(x, tmp1, s);
tanh_f32<<<grid, block>>>(tmp1, tmp2);
scale_f32<<<grid, block>>>(tmp2, dst, softcap);
```

### Fix

```cpp
// One kernel, one read + one write
__global__ void softcap_fused(const float *x, float *dst, float scale, float softcap, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) {
        dst[i] = tanhf(scale * x[i]) * softcap;
    }
}
```

**Energy impact**: Proportional to chain length. A 3-kernel chain fused to 1 kernel reduces memory traffic by ~3x for that operation.

---

## 2. Unvectorized Global Memory Access

**Why it wastes energy**: GPUs issue memory transactions in 32-byte or 128-byte sectors. Loading one `float` (4 bytes) per thread wastes 75-87% of each transaction. Using `float4` (16 bytes) ensures full utilization of each memory transaction.

### Detect

```bash
# In ncu output, check load/store efficiency
ncu --metrics l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum,l1tex__t_requests_pipe_lsu_mem_global_op_ld.sum -k "kernel_name" ./your_program
```

If `sectors / requests > 4` for 4-byte types, loads are not fully coalesced or vectorized.

Also grep for scalar access patterns in bandwidth-bound kernels:
```bash
grep -rEn 'dst\[i\] *=' --include="*.cu" ./src | grep -v float4
```

### Bad

```cuda
__global__ void scale_f32(const float *x, float *dst, float scale, int n) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i < n) {
        dst[i] = scale * x[i];  // 4 bytes per transaction
    }
}
```

### Fix

```cuda
__global__ void scale_f32_vec4(const float *x, float *dst, float scale, int n) {
    int i = (blockDim.x * blockIdx.x + threadIdx.x) * 4;
    if (i + 3 < n) {
        float4 v = ((const float4 *)x)[i / 4];
        v.x *= scale; v.y *= scale; v.z *= scale; v.w *= scale;
        ((float4 *)dst)[i / 4] = v;
    } else {
        for (int j = 0; j < 4 && i + j < n; j++)
            dst[i + j] = scale * x[i + j];
    }
}
```

**When to apply**: Only for kernels that `ncu` shows are memory-bandwidth-bound (dram throughput > 60%). For compute-bound kernels, vectorization won't help.

**Caveat**: Only safe when input/output pointers are 16-byte aligned and the access pattern is contiguous. Strided or indirect access patterns (e.g., gather/scatter for embedding lookups) cannot use `float4`.

---

## 3. Low Occupancy from Excessive Register or Shared Memory Usage

**Why it wastes energy**: Low occupancy means fewer warps are available to hide memory latency, leaving the GPU idle during memory stalls.

### Detect

```bash
ncu --metrics sm__warps_active.avg.pct_of_peak_sustained_elapsed -k "kernel_name" ./your_program
```

Occupancy below 25% in a memory-bound kernel is a problem.

```bash
# Check register usage per kernel at compile time
nvcc --ptxas-options=-v your_kernel.cu 2>&1 | grep "registers"
```

### Fix

- Reduce register pressure: use `__launch_bounds__(maxThreadsPerBlock, minBlocksPerMultiprocessor)`
- Reduce shared memory: reuse or reduce shared memory allocations
- Increase block size: more threads per block can improve scheduling (but test — too large can also hurt)

```cuda
// Hint to compiler to limit register usage for better occupancy
__global__ __launch_bounds__(256, 4)
void my_kernel(...) { ... }
```

---

## 4. Uncoalesced Memory Access

**Why it wastes energy**: When threads in a warp access non-contiguous memory addresses, the GPU issues multiple memory transactions instead of one. This multiplies memory bandwidth consumption.

### Detect

```bash
ncu --metrics l1tex__average_t_sectors_per_request_pipe_lsu_mem_global_op_ld.ratio -k "kernel_name" ./your_program
```

Ideal ratio is 4 (for 4-byte types with 128-byte cache lines / 32 threads). Higher means uncoalesced access.

### Bad

```cuda
// Column-major access in a row-major layout — threads stride by ncols
__global__ void sum_cols(const float *x, float *dst, int nrows, int ncols) {
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    float sum = 0;
    for (int row = 0; row < nrows; row++) {
        sum += x[row * ncols + col];  // stride = ncols between threads
    }
    dst[col] = sum;
}
```

### Fix

Transpose the access pattern so adjacent threads access adjacent memory, or use shared memory as a staging area:

```cuda
// Row-major access — adjacent threads read adjacent elements
__global__ void sum_rows(const float *x, float *dst, int ncols) {
    int row = blockIdx.x;
    float sum = 0;
    for (int col = threadIdx.x; col < ncols; col += blockDim.x) {
        sum += x[row * ncols + col];  // stride = 1 between threads
    }
    // warp reduction...
}
```

---

## 5. Redundant Math Operations

**Why it wastes energy**: Separate `sinf()` + `cosf()` calls on the same argument compute the same internal reduction twice. Combined intrinsics and fast-math variants reduce instruction count.

### Detect

```bash
# Separate sin/cos on same variable
grep -rEn 'sinf\(.*\)' --include="*.cu" --include="*.cuh" ./src
grep -rEn 'cosf\(.*\)' --include="*.cu" --include="*.cuh" ./src
# Check if --use_fast_math is already enabled in build
grep -rEn 'use_fast_math|fmad=true' CMakeLists.txt Makefile
```

### Bad

```cuda
float s = sinf(theta);
float c = cosf(theta);  // recomputes range reduction from sinf
```

### Fix

```cuda
float s, c;
sincosf(theta, &s, &c);  // single range reduction, both results
```

**Note**: If `--use_fast_math` is already enabled, the compiler may already emit `sincosf` automatically. Check with `nvdisasm` or `cuobjdump --dump-sass` before applying.

---

## 6. Kernel Launch Overhead (Too Many Small Kernels)

**Why it wastes energy**: Each kernel launch has 5-15us of overhead. Hundreds of small kernels per inference step can accumulate significant idle time.

### Detect

```bash
# Count kernel launches per second
nsys profile --stats=true ./your_program 2>&1 | grep "CUDA Kernel Statistics" -A 100 | head -50
```

If you see kernels with average duration < 10us and hundreds of instances, launch overhead is significant.

### Fix

- **Fuse adjacent kernels** operating on the same data (see pattern 1)
- **Use CUDA graphs** to batch kernel launches into a single submission
- **Increase work per kernel** — process multiple rows/elements per thread

```cuda
// Before: one kernel per small operation
for (int layer = 0; layer < n_layers; layer++) {
    rms_norm<<<grid, block, 0, stream>>>(...);
    scale<<<grid, block, 0, stream>>>(...);
}

// After: CUDA graph captures and replays the whole sequence
cudaGraph_t graph;
cudaStreamBeginCapture(stream, cudaStreamCaptureModeGlobal);
for (int layer = 0; layer < n_layers; layer++) {
    rms_norm<<<grid, block, 0, stream>>>(...);
    scale<<<grid, block, 0, stream>>>(...);
}
cudaStreamEndCapture(stream, &graph);
cudaGraphExec_t instance;
cudaGraphInstantiate(&instance, graph, NULL, NULL, 0);
cudaGraphLaunch(instance, stream);
```
