"""
benchmark_engine.py — Stages 3 & 4 of the pipeline.

* Stage 3: correctness & visual verification — renders a 1600x1200@256
  image with every available implementation, then cross-validates the
  iteration-count fingerprints for mathematical parity.
* Stage 4: comprehensive benchmark suite — resolution x iteration-depth
  matrix plus a thread-scaling study, with warmup, >= 1 timed runs,
  wall-clock statistics, throughput/GFLOPS estimates and peak RSS (psutil).

Results are written to output/raw_data/benchmark_results.json and .csv.
"""
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
PYTHON_DIR = SRC / "python"
OUTPUT_DIR = PROJECT_ROOT.parent / "output"
RAW_DIR = OUTPUT_DIR / "raw_data"
IMG_DIR = OUTPUT_DIR / "images"

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:  # noqa: BLE001
    HAVE_PSUTIL = False

# Primary workload (user-specified): 1600 x 1200 @ 256 iterations.
BASE_W, BASE_H = 1600, 1200
VERIFY_W, VERIFY_H, VERIFY_ITER = BASE_W, BASE_H, 256
DEPTHS = [256, 512, 1024]

# (width, height, max_iter, runs, timeout_seconds)
FULL_CASES = [
    (BASE_W, BASE_H, 256, 5, 120),
    (BASE_W, BASE_H, 512, 5, 120),
    (BASE_W, BASE_H, 1024, 3, 180),
    (3840, 2160, 256, 3, 180),
    (3840, 2160, 512, 3, 180),
    (7680, 4320, 256, 1, 300),
    (7680, 4320, 512, 1, 300),
]
QUICK_CASES = [
    (BASE_W, BASE_H, 256, 3, 120),
    (BASE_W, BASE_H, 512, 3, 120),
    (3840, 2160, 256, 1, 180),
]
PURE_PYTHON_CASES = [
    (800, 600, 256, 1, 180),
    (BASE_W, BASE_H, 256, 1, 300),
]
PURE_PYTHON_QUICK_CASES = [
    (800, 600, 256, 1, 180),
]
# NumPy is vectorized but pays per-iteration array overhead; a full 4K/8K or
# deep-iteration matrix would take tens of minutes, so it runs the base
# resolution depth sweep plus one 4K@256 datapoint. Larger cases are skipped.
NUMPY_CASES = [
    (BASE_W, BASE_H, 256, 3, 180),
    (BASE_W, BASE_H, 512, 3, 180),
    (3840, 2160, 256, 1, 240),
]
NUMPY_QUICK_CASES = [
    (BASE_W, BASE_H, 256, 3, 180),
    (BASE_W, BASE_H, 512, 3, 180),
]

FLOPS_PER_ITER = 8.0  # conservative estimate: 2 mul + 2 add (real), 2 mul + 1 add (imag), 2 mul + 1 add (escape check)


class Impl:
    def __init__(self, impl_id, language, variant, display, threads, needs_build,
                 build_key, cmd_builder, requires_avx2=False):
        self.id = impl_id
        self.language = language
        self.variant = variant
        self.display = display
        self.threads = threads  # int or "max"
        self.needs_build = needs_build
        self.build_key = build_key  # "c" | "cpp" | "java" | None
        self.cmd_builder = cmd_builder
        self.requires_avx2 = requires_avx2
        self.available = False
        self.skip_reason = ""


def _resolve_threads(threads, max_threads):
    return max_threads if threads == "max" else int(threads)


def make_implementations(ctx):
    """ctx: dict with builds, python exe, max_threads, has_avx2."""
    impls = []
    builds = ctx["builds"]
    py = ctx["python"]
    max_threads = ctx["max_threads"]

    def c_cmd(impl, mode, w, h, mi, threads, runs, png, fp):
        cmd = [builds["c"]["exe"], mode, str(w), str(h), str(mi), str(threads)]
        if mode == "render":
            cmd += [png, fp]
        else:
            cmd += [str(runs)]
        if impl.variant == "simd":
            cmd += ["--simd"]
        return cmd

    def cpp_cmd(impl, mode, w, h, mi, threads, runs, png, fp):
        cmd = [builds["cpp"]["exe"], mode, str(w), str(h), str(mi), str(threads)]
        if mode == "render":
            cmd += [png, fp]
        else:
            cmd += [str(runs)]
        return cmd

    def java_cmd(impl, mode, w, h, mi, threads, runs, png, fp):
        cmd = [builds["java"]["java"], "-cp", builds["java"]["class_dir"],
               "Mandelbrot", mode, str(w), str(h), str(mi), str(threads)]
        if mode == "render":
            cmd += [png, fp]
        else:
            cmd += [str(runs)]
        return cmd

    def py_cmd(script):
        def builder(impl, mode, w, h, mi, threads, runs, png, fp):
            cmd = [py, str(PYTHON_DIR / script), mode, str(w), str(h), str(mi), str(threads)]
            if mode == "render":
                cmd += [png, fp]
            else:
                cmd += [str(runs)]
            return cmd
        return builder

    spec = [
        ("c_scalar", "c", "scalar", "C (scalar, 1T)", 1, True, "c", c_cmd),
        ("c_openmp", "c", "openmp", "C (OpenMP)", "max", True, "c", c_cmd),
        ("c_simd", "c", "simd", "C (AVX2+OpenMP)", "max", True, "c", c_cmd, True),
        ("cpp", "cpp", "threads", "C++20 (jthread pool)", "max", True, "cpp", cpp_cmd),
        ("java", "java", "parallel", "Java (ForkJoinPool)", "max", True, "java", java_cmd),
        ("python_pure", "python", "pure", "Python (pure)", 1, False, None, py_cmd("mandelbrot_pure.py")),
        ("python_numpy", "python", "numpy", "Python (NumPy)", 1, False, None, py_cmd("mandelbrot_numpy.py")),
        ("python_numba", "python", "numba", "Python (Numba JIT)", "max", False, None, py_cmd("mandelbrot_numba.py")),
    ]
    for s in spec:
        impl = Impl(*s)
        if s[5] and builds.get(s[6], {}).get("ok"):
            impl.available = True
        elif not s[5]:
            impl.available = True
        impls.append(impl)
    # Mark language availability cleanly.
    for impl in impls:
        if impl.needs_build and not builds.get(impl.build_key, {}).get("ok"):
            impl.available = False
            impl.skip_reason = builds.get(impl.build_key, {}).get("reason", "build failed")
    return impls


def _run_subprocess(cmd, timeout, measure_rss=True):
    """Run cmd, poll RSS, return (rc, stdout, stderr, peak_rss_mb, wall_s)."""
    peak = 0.0
    start = time.perf_counter()

    def _bump(new_peak):
        nonlocal peak
        if new_peak > peak:
            peak = new_peak
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except Exception as e:  # noqa: BLE001
        return -1, "", f"spawn failed: {e}", 0.0, 0.0

    stop = threading.Event()

    def poll():
        if not (HAVE_PSUTIL and measure_rss):
            return
        try:
            p = psutil.Process(proc.pid)
            while not stop.is_set():
                try:
                    _bump(p.memory_info().rss)
                except Exception:  # noqa: BLE001
                    break
                stop.wait(0.1)
        except Exception:  # noqa: BLE001
            pass

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        wall = time.perf_counter() - start
        return proc.returncode, stdout or "", stderr or "", peak / (1024 * 1024), wall
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        wall = time.perf_counter() - start
        return "TIMEOUT", "", f"timed out after {timeout}s", peak / (1024 * 1024), wall
    finally:
        stop.set()


def _parse_bench_json(stdout):
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:  # noqa: BLE001
                continue
    return None


def run_impl_bench(impl, ctx, w, h, max_iter, runs, timeout):
    """Run one benchmark case for one implementation."""
    threads = _resolve_threads(impl.threads, ctx["max_threads"])
    cmd = impl.cmd_builder(impl, "bench", w, h, max_iter, threads, runs, None, None)
    rc, out, err, peak, wall = _run_subprocess(cmd, timeout)
    result = {
        "impl": impl.id, "language": impl.language, "variant": impl.variant,
        "display": impl.display, "width": w, "height": h, "max_iter": max_iter,
        "threads": threads, "runs": runs,
        "pixel_iterations": w * h * max_iter,
        "peak_rss_mb": round(peak, 1), "engine_wall_s": round(wall, 3),
        "status": "ok",
    }
    if rc == "TIMEOUT":
        result["status"] = "timeout"
        result["error"] = err.strip()
        return result
    if rc != 0:
        result["status"] = "error"
        result["error"] = (err or out).strip()[-400:]
        return result
    j = _parse_bench_json(out)
    if not j:
        result["status"] = "error"
        result["error"] = "no JSON output from program: " + (err or out).strip()[-300:]
        return result
    result.update({
        "min_ms": j.get("min_ms"), "mean_ms": j.get("mean_ms"),
        "median_ms": j.get("median_ms"), "stddev_ms": j.get("stddev_ms"),
        "mpix_s": round(w * h / (j["mean_ms"] * 1000.0), 3) if j.get("mean_ms") else None,
        "gflops": round(w * h * max_iter * FLOPS_PER_ITER / (j["mean_ms"] / 1000.0) / 1e9, 3) if j.get("mean_ms") else None,
    })
    return result


# Canonical implementation per language (owns the mandelbrot_<lang>.png name).
CANONICAL_IMPL = {"c": "c_openmp", "cpp": "cpp", "java": "java", "python": "python_numpy"}
# Language -> image short name (mission spec: mandelbrot_c/cpp/java/py.png).
LANG_SHORT = {"c": "c", "cpp": "cpp", "java": "java", "python": "py"}


def run_verify(impl, ctx, out_dir=IMG_DIR):
    """Render the verification image + fingerprint for one implementation."""
    threads = _resolve_threads(impl.threads, ctx["max_threads"])
    if impl.id == CANONICAL_IMPL.get(impl.language):
        png = out_dir / f"mandelbrot_{LANG_SHORT.get(impl.language, impl.language)}.png"
    else:
        png = out_dir / f"mandelbrot_{impl.id}.png"
    fp = out_dir / f"{impl.id}_fingerprint.json"
    cmd = impl.cmd_builder(impl, "render", VERIFY_W, VERIFY_H, VERIFY_ITER,
                           threads, 1, str(png), str(fp))
    rc, out, err, peak, wall = _run_subprocess(cmd, timeout=900)
    info = {"impl": impl.id, "png": str(png), "fingerprint": str(fp),
            "peak_rss_mb": round(peak, 1), "wall_s": round(wall, 3), "status": "ok"}
    if rc == "TIMEOUT":
        info["status"] = "timeout"
    elif rc != 0:
        info["status"] = "error"
        info["error"] = (err or out).strip()[-300:]
    if fp.exists():
        try:
            data = json.loads(fp.read_text())
            samples = data.get("samples", [])
            interior = sum(1 for s in samples if s >= data.get("max_iter", 0))
            h = hashlib.sha256(json.dumps(samples, separators=(",", ":")).encode()).hexdigest()
            info["sha256"] = h
            info["interior_fraction"] = round(interior / len(samples), 5) if samples else None
            info["n_samples"] = len(samples)
        except Exception as e:  # noqa: BLE001
            info["fingerprint_error"] = str(e)
    return info


def cross_validate(fingerprints):
    """Compare fingerprints pairwise; return validation summary + per-impl diffs."""
    fps = {f["impl"]: f for f in fingerprints if f.get("sha256")}
    summary = {"method": "strided iteration-count fingerprint (SHA-256 + pairwise diff)",
               "pairs": [], "all_match": True}
    ids = list(fps.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = fps[ids[i]], fps[ids[j]]
            pair = {"a": ids[i], "b": ids[j],
                    "identical": a["sha256"] == b["sha256"],
                    "interior_a": a.get("interior_fraction"), "interior_b": b.get("interior_fraction")}
            if not pair["identical"]:
                summary["all_match"] = False
                # (Fingerprint files were already written; diff via stored samples.)
                try:
                    sa = json.loads(Path(a["fingerprint"]).read_text())["samples"]
                    sb = json.loads(Path(b["fingerprint"]).read_text())["samples"]
                    n = min(len(sa), len(sb))
                    exact = sum(1 for k in range(n) if sa[k] == sb[k])
                    diff1 = sum(1 for k in range(n) if abs(sa[k] - sb[k]) > 1)
                    pair["exact_fraction"] = round(exact / n, 5)
                    pair["diff_gt1_fraction"] = round(diff1 / n, 6)
                    pair["max_abs_diff"] = max((abs(sa[k] - sb[k]) for k in range(n)), default=0)
                    pair["pass"] = pair["exact_fraction"] > 0.999 and pair["diff_gt1_fraction"] < 1e-4
                    if not pair["pass"]:
                        summary["all_match"] = False
                except Exception:  # noqa: BLE001
                    pair["pass"] = False
            else:
                pair["pass"] = True
            summary["pairs"].append(pair)
    return summary


def run_thread_scaling(impls, ctx, timeout=180):
    """Thread-scaling study at the base resolution for parallel implementations."""
    w, h, mi, runs = VERIFY_W, VERIFY_H, VERIFY_ITER, 3
    max_threads = ctx["max_threads"]
    thread_list = []
    t = 1
    while t <= max_threads:
        thread_list.append(t)
        t *= 2
    if thread_list[-1] != max_threads:
        thread_list.append(max_threads)
    results = []
    for impl in impls:
        if not impl.available or impl.threads == 1:
            continue
        for threads in thread_list:
            cmd = impl.cmd_builder(impl, "bench", w, h, mi, threads, runs, None, None)
            rc, out, err, peak, wall = _run_subprocess(cmd, timeout)
            row = {"impl": impl.id, "language": impl.language, "variant": impl.variant,
                   "width": w, "height": h, "max_iter": mi, "threads": threads,
                   "runs": runs, "pixel_iterations": w * h * mi,
                   "peak_rss_mb": round(peak, 1), "status": "ok"}
            j = _parse_bench_json(out)
            if rc == "TIMEOUT":
                row["status"] = "timeout"
            elif rc != 0 or not j:
                row["status"] = "error"
                row["error"] = (err or out).strip()[-200:]
            else:
                row.update({"min_ms": j.get("min_ms"), "mean_ms": j.get("mean_ms"),
                            "median_ms": j.get("median_ms"), "stddev_ms": j.get("stddev_ms")})
            results.append(row)
    return results


def run_benchmarks(impls, ctx, quick=False):
    results = []
    cases = FULL_CASES if not quick else QUICK_CASES
    pure_cases = PURE_PYTHON_CASES if not quick else PURE_PYTHON_QUICK_CASES
    for impl in impls:
        if not impl.available:
            continue
        if impl.id == "python_pure":
            case_list = pure_cases
        elif impl.id == "python_numpy":
            case_list = NUMPY_CASES if not quick else NUMPY_QUICK_CASES
        else:
            case_list = cases
        for (w, h, mi, runs, timeout) in case_list:
            r = run_impl_bench(impl, ctx, w, h, mi, runs, timeout)
            results.append(r)
            _print_result(r)
    return results


def _print_result(r):
    if r["status"] == "ok":
        print(f"    [{r['language']}/{r['variant']:7s}] {r['width']}x{r['height']} @ {r['max_iter']:>4d} "
              f"T={r['threads']:>2d}  mean {r['mean_ms']:>10.1f} ms  "
              f"({r.get('mpix_s', 0):>6.1f} MPix/s, {r.get('gflops', 0):>5.1f} GFLOPS, RSS {r['peak_rss_mb']:>6.1f} MB)")
    else:
        print(f"    [{r['language']}/{r['variant']:7s}] {r['width']}x{r['height']} @ {r['max_iter']:>4d} "
              f"T={r['threads']:>2d}  {r['status'].upper()}: {r.get('error', '')[:80]}")


def save_results(results, thread_scaling, validation, filename="benchmark_results.json"):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verification": {"width": VERIFY_W, "height": VERIFY_H, "max_iter": VERIFY_ITER},
        "cross_validation": validation,
        "thread_scaling": thread_scaling,
        "results": results,
    }
    json_path = RAW_DIR / filename
    json_path.write_text(json.dumps(payload, indent=2))

    csv_path = RAW_DIR / "benchmark_results.csv"
    fieldnames = ["impl", "language", "variant", "display", "width", "height", "max_iter",
                  "threads", "runs", "pixel_iterations", "min_ms", "mean_ms", "median_ms",
                  "stddev_ms", "mpix_s", "gflops", "peak_rss_mb", "engine_wall_s", "status", "error"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    return json_path, csv_path
