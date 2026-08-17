# 🌀 Mandelbrot Multi-Language Hardware Evaluation & Benchmark Suite

A **100% automated, zero-touch** benchmark and analysis system that profiles the
host machine and compares Mandelbrot-set rendering performance across **C, C++,
Java and Python** (pure, NumPy and Numba variants) — from hardware detection and
compilation straight through to PNG charts and a full technical report.

## ▶️ Quickstart (VS Code)

Open the project root in VS Code, then run **one command** in any terminal
(PowerShell, CMD or Bash):

```bash
python run_all.py
```

or double-click the wrapper for your shell:

| Shell        | Command              |
|--------------|----------------------|
| PowerShell   | `.\run_all.ps1`      |
| CMD          | `run_all.ps1` or `python run_all.py` |
| Bash / Git   | `./run_all.sh`       |

That single invocation performs **everything**:

1. **Preflight** — checks Python, auto-installs missing packages from
   `dependencies/requirements.txt`, detects compilers (`gcc`, `clang`, `cl`,
   `javac`) and the JVM.
2. **Compilation** — builds C / C++ (`-O3 -march=native -ffast-math -fopenmp`)
   and Java (`javac`) with optimal flags. Missing compilers are reported and
   skipped gracefully — the suite continues with whatever is available.
3. **Verification** — renders a 1920×1080 @ N=1000 image with every available
   implementation and cross-validates iteration-count fingerprints for
   mathematical parity.
4. **Benchmarking** — 1080p / 4K / 8K × iteration depths 500 / 1000 / 5000,
   warmups + timed runs, throughput (MPix/s), GFLOPS estimate and peak RSS, plus
   a 1→max-thread scaling study.
5. **Charts** — six 300-DPI publication PNGs in `output/charts/`.
6. **Report** — a comprehensive `output/REPORT.md` with hardware profile,
   results matrices, speedup / Amdahl analysis and an architectural deep-dive.

### Options

```bash
python run_all.py --quick          # reduced workload for fast iteration
python run_all.py --skip-verify    # skip verification renders
python run_all.py --skip-bench     # skip benchmarks
python run_all.py --skip-charts    # skip chart generation
python run_all.py --skip-report    # skip report generation
```

## 📁 Project Layout

```text
.
├── run_all.py                 # single master entry-point script
├── run_all.ps1 / run_all.sh   # cross-platform wrappers
├── README.md
├── dependencies/
│   ├── src/
│   │   ├── c/        mandelbrot.c + stb_image_write.h (vendored)
│   │   ├── cpp/      mandelbrot.cpp + stb_image_write.h (vendored)
│   │   ├── java/     Mandelbrot.java
│   │   └── python/   mandelbrot_pure.py · mandelbrot_numpy.py · mandelbrot_numba.py
│   ├── modules/      preflight · hardware_info · builder · benchmark_engine
│   │                 chart_generator · report_generator
│   └── requirements.txt
└── output/            (generated at runtime)
    ├── images/        mandelbrot_*.png + fingerprints
    ├── charts/        01..06 *.png
    ├── raw_data/      benchmark_results.json / .csv
    └── REPORT.md
```

## 🧮 Algorithm (shared spec)

- Viewport: `x ∈ [-2.0, 0.5]`, `y ∈ [-1.25, 1.25]`
- Recurrence: `zₙ₊₁ = zₙ² + c` with `z₀ = 0`
- Escape radius: `|zₙ|² > 4` (R = 2)
- Iteration depths: 500 / 1000 / 5000
- Interior = black; exterior = deterministic integer palette (bit-identical
  across languages)

## 🔧 Requirements

- Python ≥ 3.8 (auto-installs `numpy`, `pillow`, `matplotlib`, `psutil`,
  `numba` on first run)
- Optional (auto-detected): GCC / Clang / MSVC for C & C++, JDK for Java

## 📊 Output

- `output/images/mandelbrot_{c,cpp,java,py}.png` — visual correctness proof
- `output/charts/01…06_*.png` — benchmark visualizations
- `output/raw_data/benchmark_results.{json,csv}` — full raw measurements
- `output/REPORT.md` — comprehensive technical report
