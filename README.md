# 🌀 Mandelbrot Multi-Language Hardware Evaluation & Benchmark Suite

[![CI Pipeline](https://github.com/maluve05/PC-Benchmarking-Tool/actions/workflows/ci.yml/badge.svg)](https://github.com/maluve05/PC-Benchmarking-Tool/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

A **100% automated, zero-touch** microarchitectural benchmark and hardware profiling suite that measures and analyzes Mandelbrot-set rendering performance across **C, C++, Java, and Python** (Pure CPython, NumPy vectorized, and Numba LLVM JIT).

The suite automates everything in a single command: host hardware telemetry extraction, compiler detection, optimized compilation, mathematical verification, matrix benchmarking, 300-DPI publication chart rendering, and full markdown report generation.

---

## 📑 Table of Contents

- [⚡ Quickstart](#-quickstart)
- [✨ Key Features](#-key-features)
- [🔄 6-Stage Benchmark Pipeline](#-6-stage-benchmark-pipeline)
- [📊 Supported Implementations](#-supported-implementations)
- [⚙️ Command-Line Interface (CLI)](#️-command-line-interface-cli)
- [📁 Project Layout](#-project-layout)
- [🧮 Mathematical & Algorithm Specification](#-mathematical--algorithm-specification)
- [📈 Generated Artifacts & Reports](#-generated-artifacts--reports)
- [🧪 Running Tests](#-running-tests)
- [🤝 Contributing & Architecture](#-contributing--architecture)
- [📄 License](#-license)

---

## ⚡ Quickstart

Clone the repository and run the single master runner using Python or your platform's native shell wrapper:

### 1. Master Python Entrypoint
```bash
python run_all.py
```

### 2. Native Shell Wrappers
| Platform / Shell | Command | Description |
|---|---|---|
| **PowerShell** | `.\run_all.ps1` | Native Windows PowerShell wrapper with parameter forwarding |
| **Command Prompt (CMD)** | `run_all.ps1` or `python run_all.py` | Windows CMD execution |
| **Bash / Linux / macOS** | `./run_all.sh` | POSIX compliant shell wrapper |

### 3. Fast Iteration (Quick Mode)
For a reduced workload that completes in seconds:
```bash
python run_all.py --quick
# or
.\run_all.ps1 -Quick
# or
./run_all.sh --quick
```

---

## ✨ Key Features

- **Zero-Touch Automation**: Automatically installs missing Python dependencies, locates native compilers (`gcc`, `clang`, `cl.exe`, `javac`), compiles optimized binaries, and runs benchmarks.
- **Graceful Toolchain Degradation**: If a compiler (such as GCC or JDK) is not installed on the system, the suite reports it and continues benchmarking available runtimes without failing.
- **Cryptographic Verification**: Renders a 1600×1200 image across all engines and validates mathematical parity using strided SHA-256 iteration-count fingerprints.
- **Hardware Telemetry Extraction**: Captures CPU model, physical core and logical thread counts, L1/L2/L3 cache sizes, vector ISA extensions (AVX-512, AVX2, FMA, SSE, NEON), and RAM bandwidth/frequency.
- **Publication-Ready Visualizations**: Automatically generates six 300-DPI charts illustrating runtime, speedups, Amdahl multicore scaling, throughput (MPix/s), memory footprint (RSS), and a 5-axis radar chart.

---

## 🔄 6-Stage Benchmark Pipeline

```
Stage 1: Preflight ───> Stage 2: Build ───> Stage 3: Verify ───> Stage 4: Bench ───> Stage 5: Charts ───> Stage 6: Report
 (Toolchain & Env)       (AOT & JIT)         (SHA-256 Parity)     (Res x Depths)      (6x 300-DPI)        (REPORT.md)
```

1. **Stage 1 · Preflight & Environment Setup**:
   Validates Python version ($\ge 3.8$), auto-installs requirements (`numpy`, `pillow`, `matplotlib`, `psutil`, `numba`), and probes available compilers.
2. **Stage 2 · Automated Compilation**:
   Compiles C (`-O3 -march=native -fopenmp -ffast-math -std=c11`), C++20 (`-O3 -march=native -ffast-math -pthread -std=c++20`), and Java (`javac`).
3. **Stage 3 · Correctness & Visual Verification**:
   Renders $1600 \times 1200$ @ $N=256$ with each engine; generates strided JSON fingerprints and cross-validates SHA-256 hashes and boundary variance.
4. **Stage 4 · Comprehensive Benchmark Suite**:
   Runs workload matrix across resolutions ($1600 \times 1200$, 4K UHD $3840 \times 2160$, 8K UHD $7680 \times 4320$) and iteration depths ($N \in \{256, 512, 1024\}$) with warmup cycles, statistical metrics (min, mean, median, $\sigma$), and memory polling.
5. **Stage 5 · Visual Asset & Chart Generation**:
   Produces six 300-DPI publication PNGs in `output/charts/`.
6. **Stage 6 · Automated Technical Report**:
   Generates `output/REPORT.md` containing hardware tables, benchmark matrices, speedup ratios, thread-scaling curves, and architectural commentary.

---

## 📊 Supported Implementations

| Implementation | Language | Paradigm | Concurrency Model | SIMD / Acceleration |
|---|---|---|---|---|
| `c_scalar` | C | AOT Compiled | Single-threaded | Auto-vectorized |
| `c_openmp` | C | AOT Compiled | OpenMP dynamic schedule | Auto-vectorized |
| `c_simd` | C | AOT Compiled | OpenMP dynamic schedule | Hand-tuned AVX2 (256-bit 4-lane `double`) |
| `cpp` | C++20 | AOT Compiled | `std::jthread` thread pool | Lock-free atomic work-stealing |
| `java` | Java | JVM HotSpot | ForkJoinPool (`IntStream.parallel`) | HotSpot C2 JIT Compiler |
| `python_numba` | Python | LLVM JIT | `@njit(parallel=True)` with `prange` | FastMath + LLVM Auto-SIMD |
| `python_numpy` | Python | Vectorized | C-extension vector operations | Dynamic chunking on active coordinate masks |
| `python_pure` | Python | Interpreted | Single-threaded | CPython bytecode baseline |

---

## ⚙️ Command-Line Interface (CLI)

```text
usage: run_all.py [-h] [--quick] [--skip-verify] [--skip-bench]
                  [--skip-thread-scaling] [--skip-charts] [--skip-report]

Mandelbrot multi-language benchmark suite

options:
  -h, --help             Show this help message and exit
  --quick                Run reduced workload (faster iteration for development)
  --skip-verify          Skip Stage 3 verification image rendering & fingerprinting
  --skip-bench           Skip Stage 4 matrix benchmarks
  --skip-thread-scaling  Skip thread-scaling study in Stage 4
  --skip-charts          Skip Stage 5 chart PNG generation
  --skip-report          Skip Stage 6 technical markdown report generation
```

---

## 📁 Project Layout

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml                 # Multi-OS GitHub Actions CI matrix
├── .vscode/
│   ├── launch.json                # VS Code debug configurations
│   ├── settings.json              # Workspace settings and paths
│   └── tasks.json                 # VS Code build and test tasks
├── dependencies/
│   ├── modules/
│   │   ├── benchmark_engine.py    # Benchmark execution & verification engine
│   │   ├── builder.py             # AOT compiler & build manager
│   │   ├── chart_generator.py     # Publication chart generation (300 DPI)
│   │   ├── hardware_info.py       # Hardware telemetry extractor
│   │   ├── preflight.py           # Dependency installer & toolchain discovery
│   │   └── report_generator.py    # Technical report generator
│   ├── requirements.txt           # Python package dependencies
│   └── src/
│       ├── c/                     # mandelbrot.c + stb_image_write.h
│       ├── cpp/                   # mandelbrot.cpp + stb_image_write.h
│       ├── java/                  # Mandelbrot.java
│       └── python/                # mandelbrot_pure.py, numpy.py, numba.py
├── tests/
│   ├── test_mandelbrot_math.py    # Mathematical parity & palette unit tests
│   ├── test_pipeline_stages.py    # Pipeline stages, engine & chart tests
│   └── test_preflight_and_hardware.py # Hardware & toolchain detection tests
├── .gitattributes                 # Line ending and binary attributes
├── .gitignore                     # Git ignore rules
├── ARCHITECTURE.md                # In-depth architectural documentation
├── CONTRIBUTING.md                # Guide for contributing new languages
├── LICENSE                        # MIT License
├── README.md                      # Project documentation
├── run_all.ps1                    # Windows PowerShell wrapper
├── run_all.py                     # Master runner script
└── run_all.sh                     # Linux / macOS Bash wrapper
```

---

## 🧮 Mathematical & Algorithm Specification

- **Continuous Domain**: $x \in [-2.0, 0.5]$, $y \in [-1.25, 1.25]$
- **Centered Sampling**: $x_0 = -2.0 + (i + 0.5)\frac{2.5}{W}, \quad y_0 = 1.25 - (j + 0.5)\frac{2.5}{H}$
- **Recurrence**: $z_0 = 0, \quad z_{n+1} = z_n^2 + c$
- **Escape Threshold**: $|z_n|^2 = x_n^2 + y_n^2 > 4.0$ ($R = 2.0$)
- **Color Palette**: Deterministic 256-index integer palette (interior points forced to black `(0, 0, 0)`).
- **Computational Workload**: 8 FLOPs per iteration model used for GFLOPS calculations.

For complete algorithmic proofs and hardware mapping, refer to [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 📈 Generated Artifacts & Reports

Every run generates the following artifacts in the `output/` directory:

- **`output/images/`**: Verification images (`mandelbrot_c.png`, `mandelbrot_cpp.png`, `mandelbrot_java.png`, `mandelbrot_py.png`) and fingerprint JSON files.
- **`output/charts/`**:
  - `01_execution_time_by_language.png`: Execution time across resolutions (log scale).
  - `02_speedup_relative_to_baseline.png`: Speedup multiples vs. Pure Python baseline.
  - `03_multicore_thread_scaling.png`: Amdahl multicore scaling curve vs. ideal linear scaling.
  - `04_throughput_vs_iterations.png`: Megapixels/second throughput across iteration depths.
  - `05_memory_consumption.png`: Peak Resident Set Size (RSS in MB) per implementation.
  - `06_hardware_saturation_radar.png`: 5-axis composite hardware saturation radar chart.
- **`output/raw_data/`**: `benchmark_results.json` and `benchmark_results.csv`.
- **`output/REPORT.md`**: Comprehensive publication report containing full hardware telemetry, data matrices, and architectural analysis.

---

## 🧪 Running Tests

Run the full automated test suite using Python's built-in `unittest`:

```bash
python -m unittest discover -s tests -v
```

Or execute via VS Code by opening the **Test Explorer** or running the `Run Unit Tests` task (`Ctrl+Shift+P` -> `Tasks: Run Task` -> `Run Unit Tests`).

---

## 🤝 Contributing & Architecture

Want to add support for a new language (such as **Rust, Go, Zig, Julia, C#, Swift**)?

- Read [CONTRIBUTING.md](CONTRIBUTING.md) for the standardized CLI contract and step-by-step instructions.
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for concurrency mechanics, cache alignment guidelines, and SIMD kernel design.

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
