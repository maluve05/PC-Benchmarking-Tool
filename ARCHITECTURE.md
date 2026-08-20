# Architecture of the Mandelbrot Benchmark Suite

The **Mandelbrot Multi-Language Hardware Evaluation & Benchmark Suite** is engineered as an automated, zero-touch profiling pipeline designed to benchmark host microarchitectures across multiple language runtimes, memory subsystems, and parallelism models.

---

## 🏛️ High-Level Architectural Principles

1. **Zero-Touch Execution**: A single command (`python run_all.py` or `./run_all.sh` / `.\run_all.ps1`) runs the entire pipeline from environment setup to publication-ready reports.
2. **Graceful Toolchain Degradation**: If native compilers (e.g. GCC, MSVC, JDK) are not present, missing languages are skipped gracefully while available runtimes continue execution.
3. **Mathematical & Visual Parity**: Every implementation shares identical viewport bounds, centered sampling math, and deterministic color palettes. Correctness is verified cryptographically via strided SHA-256 fingerprints before benchmarking begins.
4. **Microarchitectural Saturation**: Workloads systematically test single-thread instruction throughput, SIMD vector lane efficiency, multi-core scaling, and memory hierarchy behavior.

---

## 🔄 6-Stage Execution Pipeline

```
  ┌─────────────────────────────────────────────────────────────┐
  │  Stage 1: Preflight & Environment Setup                     │
  │  • Python version verification (>= 3.8)                     │
  │  • Automatic pip package installation                       │
  │  • Native toolchain detection (GCC, Clang, MSVC, JDK)       │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Stage 2: Automated Compilation                             │
  │  • C:   -O3 -march=native -fopenmp -ffast-math -std=c11    │
  │  • C++: -O3 -march=native -ffast-math -pthread -std=c++20   │
  │  • Java: javac (Mandelbrot.java)                            │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Stage 3: Mathematical Verification                         │
  │  • Render 1600x1200 @ N=256 on all available engines       │
  │  • Generate strided iteration-count fingerprint JSON files  │
  │  • Cryptographic SHA-256 cross-validation & pairwise diff   │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Stage 4: Comprehensive Benchmark Suite                     │
  │  • Resolution matrix: 1600x1200, 4K (2160p), 8K (4320p)     │
  │  • Iteration depths: N ∈ {256, 512, 1024}                  │
  │  • Warmup iterations + timed runs with wall-clock stats     │
  │  • Thread-scaling study (1 -> max logical threads)          │
  │  • Peak RSS memory polling via psutil daemon thread         │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Stage 5: Visual Asset & Chart Generation                   │
  │  • 01: Execution Time by Language & Resolution (log scale) │
  │  • 02: Speedup vs Pure-Python Baseline                      │
  │  • 03: Multicore Thread Scaling & Amdahl Efficiency         │
  │  • 04: Throughput vs Iteration Depth (Megapixels/sec)       │
  │  • 05: Peak Memory Consumption (RSS in MB)                  │
  │  • 06: Hardware Saturation 5-Axis Radar Chart               │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Stage 6: Automated Technical Report (output/REPORT.md)     │
  │  • Hardware telemetry profile (CPU, Caches, ISA, RAM)       │
  │  • Consolidated results matrices & speedup tables           │
  │  • Architectural deep-dive and saturation analysis          │
  └─────────────────────────────────────────────────────────────┘
```

---

## 🧮 Mathematical Model & Correctness

### 1. Viewport Specification
- Continuous complex domain:
  $$x \in [-2.0, 0.5], \quad y \in [-1.25, 1.25]$$
- Pixel resolution $W \times H$.
- Grid step sizes:
  $$\Delta x = \frac{2.5}{W}, \quad \Delta y = \frac{2.5}{H}$$
- Centered coordinate mapping for pixel $(i, j)$ with $0 \le i < W$ and $0 \le j < H$:
  $$c = \left(-2.0 + (i + 0.5)\Delta x\right) + \mathbf{i}\left(1.25 - (j + 0.5)\Delta y\right)$$

### 2. Recurrence & Escape Condition
For initial value $z_0 = 0$:
$$z_{n+1} = z_n^2 + c = (x_n^2 - y_n^2 + c_r) + \mathbf{i}(2 x_n y_n + c_i)$$

The escape threshold is $|z_n|^2 = x_n^2 + y_n^2 > 4.0$ (escape radius $R = 2$).

### 3. Floating-Point Complexity Model
Each iteration evaluates:
- 2 real multiplications ($x^2, y^2$)
- 1 real subtraction ($x^2 - y^2$)
- 1 real addition ($+ c_r$)
- 2 real multiplications ($2xy$)
- 1 real addition ($+ c_i$)
- 1 escape check ($x^2 + y^2 > 4.0$, utilizing precalculated $x^2, y^2$)

Total conservative floating-point workload: **8 FLOPs per iteration**.

$$\text{GFLOPS} = \frac{W \times H \times N_{\text{iter}} \times 8.0}{\text{Mean Time (seconds)} \times 10^9}$$

---

## ⚡ Concurrency & Parallelism Strategies

The Mandelbrot set exhibits severe non-uniform computational density:
- **Exterior points** escape within 1–10 iterations.
- **Interior points (Cardioid & Bulbs)** run through the full $N_{\text{iter}}$ budget.

Static row partitioning causes severe thread starvation. Each language implementation addresses load balancing accordingly:

| Language | Paradigm | Concurrency Mechanism | Load Balancing |
|---|---|---|---|
| **C** | OpenMP | `#pragma omp parallel for` | `schedule(dynamic)` |
| **C++20** | Native Threads | `std::jthread` pool + `std::atomic<size_t>` row index | Work-stealing dynamic queue |
| **Java** | ForkJoinPool | `IntStream.range(0, h).parallel()` | Fork-Join work stealing |
| **Python (Numba)** | LLVM OpenMP | `@njit(parallel=True)` with `prange` | Auto-scheduled chunk loops |
| **Python (NumPy)** | Vectorized SIMD | Chunked 2D boolean array masks | Shrinking active coordinate set |
| **Python (Pure)** | Bytecode Scalar | Single thread | Baseline reference |

---

## 🔍 SIMD Vectorization Architecture

In addition to compiler auto-vectorization, an explicit **AVX2 SIMD kernel** is implemented in C (`mandel_simd_row`):
- Operates on 256-bit registers (`__m256d`), computing **4 double-precision complex coordinates simultaneously**.
- Maintains an active lane bitmask (`__m256i active`) to track unescaped pixels.
- Increments per-lane iteration counters via masked vector additions (`_mm256_and_pd`, `_mm256_add_pd`).
- Early-exits when all 4 lanes in the vector have escaped (`_mm256_testz_si256`).

---

## 💾 Memory & Cache Subsystem Design

1. **Streaming Writes**: Output frames are written sequentially in row-major order to maximize L1/L2 cache line hits and hardware prefetching.
2. **False Sharing Prevention**: Parallel worker threads own distinct row buffers; no two threads write to adjacent bytes within the same 64-byte cache line.
3. **Chunked NumPy Memory Bounding**: NumPy vectorization dynamically chunks rows to ensure array intermediates never exceed ~2 million elements, preventing memory spikes at 4K and 8K resolutions.
4. **Real-time Memory Profiling**: Peak resident set size (RSS) is measured during benchmark execution via a dedicated background polling thread running `psutil.Process().memory_info().rss` at 100ms intervals.
