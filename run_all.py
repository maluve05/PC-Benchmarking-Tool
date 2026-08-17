#!/usr/bin/env python3
"""
run_all.py — THE SINGLE MASTER ENTRY-POINT SCRIPT.

Running `python run_all.py` from the project root executes the entire
Mandelbrot multi-language hardware evaluation & benchmark suite with zero
manual steps:

    Stage 1  Preflight & environment setup (pip auto-install, toolchain detect)
    Stage 2  Automated compilation (C / C++ / Java, optimal flags)
    Stage 3  Correctness & visual verification (1080p PNGs + fingerprint parity)
    Stage 4  Comprehensive benchmark suite (resolutions x depths + thread scaling)
    Stage 5  Chart generation (6 publication PNGs, 300 DPI)
    Stage 6  Automated technical report (output/REPORT.md)

Usage:
    python run_all.py             full run (default)
    python run_all.py --quick     reduced workload for fast iteration
    python run_all.py --skip-verify --skip-bench   selective stages
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies"))
sys.path.insert(0, str(ROOT / "dependencies" / "modules"))

OUTPUT_DIR = ROOT / "output"
IMG_DIR = OUTPUT_DIR / "images"
RAW_DIR = OUTPUT_DIR / "raw_data"
CHART_DIR = OUTPUT_DIR / "charts"

# Windows consoles may default to cp1252; force UTF-8 so box-drawing and
# non-ASCII output never crashes the pipeline.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

START = time.time()


def section(title):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def banner():
    print(r"""
   __  ___            __     __  ___          __  __            __
  /  |/  /___  ____  / /_   /  |/  /___  ____/ /_/ /_  ___  ___/ /__
 / /|_/ / __ \/ __ \/ __/  / /|_/ / __ \/ __ \ __/ __ \/ _ \/ _  / _ \
/ /  / / /_/ / / / / /_   / /  / / /_/ / / / / /_/ / / /  __/ /_/ / // /
/_/  /_/\____/_/ /_/\__/  /_/  /_/\____/_/ /_/\__/_/ /_/\___/\__,_/\___/
   Multi-Language Hardware Evaluation & Mandelbrot Benchmark Suite
""")


def log(msg):
    print(msg, flush=True)
    with open(OUTPUT_DIR / "run.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    parser = argparse.ArgumentParser(description="Mandelbrot multi-language benchmark suite")
    parser.add_argument("--quick", action="store_true", help="reduced workload for fast iteration")
    parser.add_argument("--skip-verify", action="store_true", help="skip Stage 3 verification renders")
    parser.add_argument("--skip-bench", action="store_true", help="skip Stage 4 benchmarks")
    parser.add_argument("--skip-thread-scaling", action="store_true", help="skip thread-scaling study")
    parser.add_argument("--skip-charts", action="store_true", help="skip Stage 5 charts")
    parser.add_argument("--skip-report", action="store_true", help="skip Stage 6 report")
    args = parser.parse_args()

    for d in (OUTPUT_DIR, IMG_DIR, RAW_DIR, CHART_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if (OUTPUT_DIR / "run.log").exists():
        (OUTPUT_DIR / "run.log").unlink()

    banner()
    print(f"  Started at {time.strftime('%Y-%m-%d %H:%M:%S')}  |  "
          f"mode={'quick' if args.quick else 'full'}")
    log(f"run_all.py started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Stage 1 · Preflight ────────────────────────────────────────────────
    section("Stage 1 · Preflight & Environment Setup")
    import preflight
    pre = preflight.run_preflight()
    toolchain = pre["toolchain"]

    # ── Stage 2 · Build ────────────────────────────────────────────────────
    section("Stage 2 · Automated Compilation")
    import builder
    builds = builder.build_all(toolchain)
    # Add Java runtime path if available
    if builds.get("java", {}).get("ok") and toolchain.get("java"):
        builds["java"]["java"] = toolchain["java"]["path"]
    
    for lang, b in builds.items():
        if b.get("ok"):
            log(f"  [OK] {lang}: {b.get('exe') or b.get('class_dir')}  ({b.get('compiler')})")
        else:
            log(f"  [SKIP] {lang}: {b.get('reason', 'compiler missing')}")

    # ── Hardware profile (used by stages 4–6) ─────────────────────────────
    import hardware_info
    hw = hardware_info.collect_hardware(toolchain)
    hw["_table"] = hardware_info.format_hardware_table(hw)
    max_threads = hw.get("logical_threads") or os.cpu_count() or 4
    has_avx2 = "AVX2" in hw.get("vector_isa", {}).get("summary", "")

    import benchmark_engine as be
    ctx = {
        "builds": builds,
        "python": sys.executable,
        "max_threads": max_threads,
        "has_avx2": has_avx2,
    }
    impls = be.make_implementations(ctx)
    available = [i.id for i in impls if i.available]
    log(f"  Host: {hw.get('cpu_model')} · {max_threads} logical threads · "
        f"{hw.get('vector_isa', {}).get('summary', 'ISA unknown')}")
    log(f"  Available implementations: {', '.join(available) or 'NONE'}")

    results, thread_scaling, validation = [], [], {"pairs": [], "all_match": None}

    # ── Stage 3 · Verification ─────────────────────────────────────────────
    if not args.skip_verify:
        section("Stage 3 · Correctness & Visual Verification (1600x1200 @ N=256)")
        fps = []
        for impl in impls:
            if not impl.available:
                log(f"  [SKIP] {impl.id}: unavailable")
                continue
            log(f"  Rendering {impl.display} ...")
            info = be.run_verify(impl, ctx)
            status = info["status"]
            if status == "ok":
                log(f"    -> {info['png']}  (RSS {info['peak_rss_mb']:.1f} MB, "
                    f"sha256={info.get('sha256', 'n/a')[:12]}…)")
                fps.append(info)
            else:
                log(f"    [WARN] verification {status}: {info.get('error', '')[:120]}")
        validation = be.cross_validate(fps)
        n_pairs = len(validation.get("pairs", []))
        log(f"  Cross-validation: {n_pairs} pairwise comparisons, "
            f"all_match={validation.get('all_match')}")
        for p in validation.get("pairs", []):
            log(f"    {p['a']:>14s} vs {p['b']:<14s} identical={p.get('identical')} "
                f"pass={p.get('pass')}")

    # ── Stage 4 · Benchmarks ───────────────────────────────────────────────
    if not args.skip_bench:
        section("Stage 4 · Comprehensive Benchmark Suite")
        log("  Running resolution × iteration-depth matrix ...")
        results = be.run_benchmarks(impls, ctx, quick=args.quick)
        if not args.skip_thread_scaling:
            log("  Running thread-scaling study (1600x1200 @ N=256, 1→max threads) ...")
            thread_scaling = be.run_thread_scaling([i for i in impls if i.available], ctx)
        json_path, csv_path = be.save_results(results, thread_scaling, validation)
        log(f"  Results -> {json_path}")
        log(f"          -> {csv_path}")

    # ── Stage 5 · Charts ───────────────────────────────────────────────────
    if not args.skip_charts and results:
        section("Stage 5 · Chart & Visual Asset Generation")
        import chart_generator
        made = chart_generator.generate_all(results, thread_scaling)
        for p in made:
            log(f"  [OK] {p.name}")
        if not made:
            log("  [WARN] no charts generated (insufficient data)")

    # ── Stage 6 · Report ───────────────────────────────────────────────────
    if not args.skip_report:
        section("Stage 6 · Automated Technical Report Generation")
        import report_generator
        meta = {"quick": args.quick}
        report_path = report_generator.generate_report(results, thread_scaling, validation, hw, meta)
        log(f"  [OK] {report_path}")

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed = time.time() - START
    section("Run Complete")
    print(f"  Elapsed: {elapsed:.1f}s\n")
    print("  Artifacts:")
    print(f"    Images : {IMG_DIR}")
    print(f"    Charts : {CHART_DIR}")
    print(f"    Raw    : {RAW_DIR}")
    print(f"    Report : {OUTPUT_DIR / 'REPORT.md'}")
    if not available:
        print("\n  [ERROR] No implementations could run — nothing was benchmarked.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
