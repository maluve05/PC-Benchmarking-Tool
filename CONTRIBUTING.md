# Contributing to the Mandelbrot Benchmark Suite

Thank you for your interest in contributing to the **Mandelbrot Multi-Language Hardware Evaluation & Benchmark Suite**! We welcome contributions ranging from new language implementations (e.g. Rust, Go, Zig, Julia, C#, Swift) to optimizations, bug fixes, and documentation improvements.

---

## 🎯 Adding a New Language Implementation

Every language implementation in this suite adheres to an exact mathematical specification, deterministic color palette, and standardized Command-Line Interface (CLI) contract. This ensures fair, apples-to-apples performance comparisons across all compilers and runtimes.

### 1. Mathematical Specification

All implementations compute the classic Mandelbrot set escape-time algorithm:

- **Complex Viewport**:
  - Real axis: $x \in [-2.0, 0.5]$ (width = 2.5)
  - Imaginary axis: $y \in [-1.25, 1.25]$ (height = 2.5)
- **Pixel Coordinate Mapping** (pixel-centered sampling):
  $$x_0 = -2.0 + (i + 0.5) \times \frac{2.5}{W}$$
  $$y_0 = 1.25 - (j + 0.5) \times \frac{2.5}{H}$$
  *(where $i \in [0, W-1]$ is column index from left, and $j \in [0, H-1]$ is row index from top)*
- **Recurrence**:
  $$z_0 = 0, \quad z_{n+1} = z_n^2 + c$$
  Escape condition: $|z_n|^2 = x_n^2 + y_n^2 > 4.0$ or $n \ge \text{max\_iter}$.

---

### 2. Standardized Color Palette

To ensure visual and binary consistency across languages, the integer palette mapping must be exact:

- **Interior points** ($it \ge \text{max\_iter}$): Black `(RGB 0, 0, 0)`
- **Exterior points** ($it < \text{max\_iter}$):
  $$\text{idx} = \left\lfloor \frac{it \times 255}{\text{max\_iter}} \right\rfloor$$
  $$\begin{cases}
    \text{idx} < 64: & R = 0, \quad G = \text{idx} \times 4, \quad B = 255 \\
    \text{idx} < 128: & R = 0, \quad G = 255, \quad B = 255 - (\text{idx} - 64) \times 4 \\
    \text{idx} < 192: & R = (\text{idx} - 128) \times 4, \quad G = 255, \quad B = 0 \\
    \text{idx} \ge 192: & R = 255, \quad G = 255 - (\text{idx} - 192) \times 4, \quad B = 0
  \end{cases}$$

---

### 3. CLI Contract

Your executable or script must accept the following command-line interface:

#### Mode 1: Render (`render`)
```bash
<binary_or_script> render <width> <height> <max_iter> <threads> <out.png> [<fingerprint.json>]
```
- **Arguments**:
  - `<width>`: Integer image width (e.g. `1600`)
  - `<height>`: Integer image height (e.g. `1200`)
  - `<max_iter>`: Maximum iteration depth (e.g. `256`)
  - `<threads>`: Thread count requested (1 for single-threaded, $>1$ for parallel)
  - `<out.png>`: Output path to save the rendered PNG image
  - `[<fingerprint.json>]` *(optional)*: Strided iteration-count fingerprint JSON file

- **Fingerprint format**:
  $$\text{stride} = \max\left(1, \left\lfloor \frac{W \times H}{300000} \right\rfloor\right)$$
  Sample pixels at grid $(j, i)$ where $j \pmod{\text{stride}} == 0$ and $i \pmod{\text{stride}} == 0$.
  ```json
  {
    "w": 1600,
    "h": 1200,
    "max_iter": 256,
    "stride": 6,
    "samples": [0, 5, 256, 12, ...]
  }
  ```

#### Mode 2: Benchmark (`bench`)
```bash
<binary_or_script> bench <width> <height> <max_iter> <threads> <runs>
```
- **Behavior**:
  1. Perform 1 warmup iteration (not timed).
  2. Execute `<runs>` timed iterations.
  3. Calculate min, mean, median, and sample standard deviation in milliseconds.
  4. Print exactly **one line of JSON** to standard output:
     ```json
     {
       "language": "rust",
       "variant": "rayon",
       "width": 1600,
       "height": 1200,
       "max_iter": 256,
       "threads": 16,
       "runs": 5,
       "min_ms": 12.345,
       "mean_ms": 12.567,
       "median_ms": 12.510,
       "stddev_ms": 0.120,
       "pixel_iterations": 491520000
     }
     ```

---

## 🛠️ Step-by-Step Integration Guide

1. **Place source code**:
   Create `dependencies/src/<language>/` (e.g. `dependencies/src/rust/`).
2. **Add compilation logic in `builder.py`** *(if compiled)*:
   Add a `build_<language>()` function in `dependencies/modules/builder.py` that checks for compiler availability in `toolchain` and builds with maximal optimization (e.g. `cargo build --release`, `go build`, `-O3`).
3. **Register in `benchmark_engine.py`**:
   Add the implementation definition to `make_implementations()` in `dependencies/modules/benchmark_engine.py`.
4. **Register in `chart_generator.py` & `report_generator.py`**:
   Add display name and color palette mapping in `DISPLAY`, `SHORT`, and `COLORS`.
5. **Run tests & verification**:
   ```bash
   python -m unittest discover -s tests -v
   python run_all.py --quick
   ```

---

## 🧪 Testing Guidelines

Before opening a pull request:
- Ensure all automated unit tests pass:
  ```bash
  python -m unittest discover -s tests -v
  ```
- Run a quick benchmark to verify fingerprint validation passes:
  ```bash
  python run_all.py --quick
  ```
- Verify that `output/REPORT.md` generates without errors or warnings.

---

## 📝 Pull Request Checklist

- [ ] New implementation conforms to mathematical viewport and coordinate sampling spec.
- [ ] Render output matches deterministic integer palette.
- [ ] Fingerprint matches cross-validation with existing languages.
- [ ] Unit tests added / updated in `tests/`.
- [ ] Graceful fallback when compiler/runtime is not installed on the host.
