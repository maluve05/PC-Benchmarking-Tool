"""
chart_generator.py — Stage 5 of the pipeline.

Produces six publication-ready (300 DPI) PNG charts in output/charts/:
  01_execution_time_by_language.png
  02_speedup_relative_to_baseline.png
  03_multicore_thread_scaling.png
  04_throughput_vs_iterations.png
  05_memory_consumption.png
  06_hardware_saturation_radar.png
"""
import math
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHART_DIR = PROJECT_ROOT.parent / "output" / "charts"

# Canonical implementations used for per-language charts.
DISPLAY = ["c_openmp", "cpp", "java", "python_numba", "python_numpy", "python_pure"]
SHORT = {
    "c_openmp": "C (OpenMP)", "cpp": "C++20", "java": "Java",
    "python_numba": "Py Numba", "python_numpy": "Py NumPy", "python_pure": "Py Pure",
}
COLORS = {
    "c_openmp": "#1f77b4", "c_scalar": "#7f7f7f", "c_simd": "#17becf",
    "cpp": "#ff7f0e", "java": "#d62728",
    "python_numba": "#2ca02c", "python_numpy": "#9467bd", "python_pure": "#8c564b",
}


def _res(results, impl, w, h, mi):
    for r in results:
        if (r["impl"] == impl and r["width"] == w and r["height"] == h
                and r["max_iter"] == mi and r["status"] == "ok"):
            return r
    return None


def _best_res(results, impl, mi=256):
    for (w, h) in [(1600, 1200), (3840, 2160), (7680, 4320)]:
        r = _res(results, impl, w, h, mi)
        if r:
            return r
    return None


def _fmt_ms(v):
    if v is None:
        return "n/a"
    if v >= 1000:
        return f"{v / 1000:.2f} s"
    return f"{v:.0f} ms"


def chart_01(results):
    """Execution time by language across resolutions (log scale)."""
    resolutions = [(1600, 1200, "1600×1200"), (3840, 2160, "4K"), (7680, 4320, "8K")]
    labels = [d for d in DISPLAY if any(_res(results, d, w, h, 256) for w, h, _ in resolutions)]
    if not labels:
        return None
    x = np.arange(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(10, 6))
    for k, (w, h, name) in enumerate(resolutions):
        vals = []
        for d in labels:
            r = _res(results, d, w, h, 256)
            vals.append(r["mean_ms"] if r else np.nan)
        ax.bar(x + (k - 1) * width, vals, width, label=name,
               color=["#1f77b4", "#ff7f0e", "#d62728"][k])
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT.get(d, d) for d in labels], rotation=15)
    ax.set_ylabel("Mean wall-clock time (ms, log scale)")
    ax.set_title("Mandelbrot Rendering Time by Language & Resolution (N=256)")
    ax.legend(title="Resolution")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    return _save(fig, "01_execution_time_by_language.png")


def _extrapolate_pure_python(results, w, h, mi):
    """Linear extrapolation of pure Python runtime (pixels x iterations)."""
    base = None
    for r in results:
        if r["impl"] == "python_pure" and r["status"] == "ok":
            work = r["width"] * r["height"] * r["max_iter"]
            if base is None or work < base["work"]:
                base = {**r, "work": work}
    if not base or not base["work"]:
        return None
    target_work = w * h * mi
    return base["mean_ms"] * target_work / base["work"]


def chart_02(results):
    """Speedup relative to pure-Python baseline at 1600x1200@256."""
    w, h, mi = 1600, 1200, 256
    pure = _res(results, "python_pure", w, h, mi)
    if not pure or not pure.get("mean_ms"):
        return None
    baseline = pure["mean_ms"]
    impls = [d for d in DISPLAY if _res(results, d, w, h, mi)]
    speedups = []
    for d in impls:
        r = _res(results, d, w, h, mi)
        speedups.append(baseline / r["mean_ms"] if r and r.get("mean_ms") else None)
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(range(len(impls)), [s or 0 for s in speedups],
                  color=[COLORS.get(d, "#555") for d in impls])
    ax.axhline(1.0, color="black", ls="--", lw=1)
    for i, (d, s) in enumerate(zip(impls, speedups)):
        if s is not None:
            ax.text(i, s * 1.02, f"{s:.1f}x", ha="center", fontsize=9)
    ax.set_xticks(range(len(impls)))
    ax.set_xticklabels([SHORT.get(d, d) for d in impls], rotation=15)
    ax.set_ylabel(f"Speedup vs Pure Python ({_fmt_ms(baseline)} baseline)")
    ax.set_title("Speedup Relative to Pure-Python Baseline (1600x1200 @ 256 iter)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return _save(fig, "02_speedup_relative_to_baseline.png")


def chart_03(thread_scaling):
    """Multicore thread scaling (Amdahl efficiency) at the base resolution."""
    data = {}
    for r in thread_scaling:
        if r["status"] == "ok" and r.get("mean_ms"):
            data.setdefault(r["impl"], []).append(r)
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    for impl, rows in data.items():
        rows = sorted(rows, key=lambda r: r["threads"])
        ts = [r["threads"] for r in rows]
        ms = [r["mean_ms"] for r in rows]
        ax.plot(ts, ms, marker="o", label=SHORT.get(impl, impl), color=COLORS.get(impl))
        t1 = next((r["mean_ms"] for r in rows if r["threads"] == 1), None)
        if t1:
            ideal = [t1 / t for t in ts]
            ax.plot(ts, ideal, ls=":", color="gray", lw=1)
            ax.text(ts[-1], ideal[-1] * 1.05, "ideal", color="gray", fontsize=8)
    ax.set_xscale("log", base=2)
    ax.set_xticks(sorted({r["threads"] for rows in data.values() for r in rows}))
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Thread count (log2)")
    ax.set_ylabel("Mean wall-clock time (ms)")
    ax.set_title("Multicore Thread Scaling — 1600x1200 @ 256 iter")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _save(fig, "03_multicore_thread_scaling.png")


def chart_04(results):
    """Throughput (MPix/s) vs iteration depth at the base resolution."""
    depths = [256, 512, 1024]
    impls = [d for d in DISPLAY if any(_res(results, d, 1600, 1200, mi) for mi in depths)]
    if not impls:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    for d in impls:
        xs, ys = [], []
        for mi in depths:
            r = _res(results, d, 1600, 1200, mi)
            if r and r.get("mpix_s"):
                xs.append(mi)
                ys.append(r["mpix_s"])
        if xs:
            ax.plot(xs, ys, marker="o", label=SHORT.get(d, d), color=COLORS.get(d))
    ax.set_xscale("log", base=2)
    ax.set_xticks(depths)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Max iterations (N)")
    ax.set_ylabel("Throughput (Megapixels / s)")
    ax.set_title("Rendering Throughput vs Iteration Depth (1600x1200)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _save(fig, "04_throughput_vs_iterations.png")


def chart_05(results):
    """Peak memory consumption per implementation (base res @ 256)."""
    rows = []
    for d in DISPLAY:
        r = _res(results, d, 1600, 1200, 256) or _res(results, d, 1600, 1200, 512)
        if r and r.get("peak_rss_mb"):
            rows.append((d, r["peak_rss_mb"]))
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = [SHORT.get(d, d) for d, _ in rows]
    vals = [v for _, v in rows]
    ax.bar(range(len(rows)), vals, color=[COLORS.get(d, "#555") for d, _ in rows])
    for i, v in enumerate(vals):
        ax.text(i, v * 1.01, f"{v:.0f} MB", ha="center", fontsize=9)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(labels, rotation=15)
    ax.set_ylabel("Peak RSS (MB)")
    ax.set_title("Peak Memory Footprint per Implementation (1600x1200 @ 256 iter)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return _save(fig, "05_memory_consumption.png")


def _norm(values):
    """Normalize a list of floats to 0..1 (max = 1). Returns dict keyed by original index."""
    vals = [(i, v) for i, v in enumerate(values) if v is not None and v > 0]
    if not vals:
        return {}
    mx = max(v for _, v in vals)
    return {i: v / mx for i, v in vals}


def chart_06(results, thread_scaling):
    """Hardware saturation radar: normalized composite per language (data-driven)."""
    canon = {"c": "c_openmp", "cpp": "cpp", "java": "java", "python": "python_numba"}

    def _scaling(impl):
        rows = [x for x in thread_scaling if x["impl"] == impl and x.get("mean_ms")]
        if not rows:
            return None
        t1 = next((x["mean_ms"] for x in rows if x["threads"] == 1), None)
        tmax = max((x["mean_ms"] for x in rows), default=None)
        return (t1 / tmax) if t1 and tmax else None

    axes = ["Throughput", "Single-core", "Multicore", "Vectorized", "Mem-efficiency"]
    radar = {}
    for lang, impl in canon.items():
        r = _best_res(results, impl, 256)
        if not r:
            continue
        csc = _res(results, "c_scalar", 1600, 1200, 256)
        vals = [
            1.0 / r["mean_ms"] if r.get("mean_ms") else None,                     # throughput
            _scaling(impl),                                                          # single-core (t1 from scaling)
            _scaling(impl),                                                          # multicore (speedup)
            None,                                                                    # vectorized (filled below)
            1.0 / r["peak_rss_mb"] if r.get("peak_rss_mb") else None,              # mem efficiency
        ]
        # Vectorized: vectorized vs scalar throughput within the language.
        if lang == "c":
            rv = _res(results, "c_simd", 1600, 1200, 256)
            if rv and csc and rv.get("mpix_s") and csc.get("mpix_s"):
                vals[3] = rv["mpix_s"] / csc["mpix_s"]
        elif lang == "python":
            rn = _res(results, "python_numba", 1600, 1200, 256)
            rp = _res(results, "python_pure", 1600, 1200, 256)
            if rn and rp and rn.get("mpix_s") and rp.get("mpix_s"):
                vals[3] = rn["mpix_s"] / rp["mpix_s"]
        else:
            # No explicit vectorized variant: single-core throughput vs C scalar.
            if csc and csc.get("mean_ms"):
                vals[3] = csc["mean_ms"] / r["mean_ms"]
        radar[lang] = vals

    if not radar:
        return None
    langs = list(radar.keys())
    normed = {lang: [None] * len(axes) for lang in langs}
    for a in range(len(axes)):
        mapping = _norm([radar[lang][a] for lang in langs])
        for lang in langs:
            if lang in mapping:
                normed[lang][a] = mapping[lang]

    angles = np.linspace(0, 2 * np.pi, len(axes), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
    palette = {"c": "#1f77b4", "cpp": "#ff7f0e", "java": "#d62728", "python": "#2ca02c"}
    for lang in langs:
        values = normed[lang] + normed[lang][:1]
        ax.plot(angles, values, marker="o", label=lang.upper(), color=palette.get(lang, "#555"))
        ax.fill(angles, values, alpha=0.08, color=palette.get(lang, "#555"))
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axes)
    ax.set_ylim(0, 1.05)
    ax.set_title("Hardware Saturation Radar (normalized composite)", pad=24)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1))
    fig.tight_layout()
    return _save(fig, "06_hardware_saturation_radar.png")


def _save(fig, name):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / name
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_all(results, thread_scaling):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for fn in (chart_01, chart_02, chart_04, chart_05):
        p = fn(results)
        if p:
            made.append(p)
    p = chart_03(thread_scaling)
    if p:
        made.append(p)
    p = chart_06(results, thread_scaling)
    if p:
        made.append(p)
    return made
