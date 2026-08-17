#!/usr/bin/env python3
"""
mandelbrot_numba.py — Numba JIT-compiled implementation of the Mandelbrot
benchmark suite. Uses @numba.njit(parallel=True, fastmath=True) with prange
row-parallelism; thread count controlled via numba.set_num_threads().

CLI contract:
  python mandelbrot_numba.py render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]
  python mandelbrot_numba.py bench  <w> <h> <max_iter> <threads> <runs>
"""
import json
import statistics
import sys
import time

import numpy as np

XMIN, XMAX, YMIN, YMAX = -2.0, 0.5, -1.25, 1.25

try:
    from numba import njit, prange
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False


@njit(parallel=True, fastmath=True, cache=True)
def compute_nb(w, h, max_iter):
    dx = (XMAX - XMIN) / w
    dy = (YMAX - YMIN) / h
    it = np.empty((h, w), dtype=np.int32)
    for j in prange(h):
        y0 = YMAX - (j + 0.5) * dy
        for i in range(w):
            x0 = XMIN + (i + 0.5) * dx
            x = 0.0
            y = 0.0
            x2 = 0.0
            y2 = 0.0
            itc = 0
            while x2 + y2 <= 4.0 and itc < max_iter:
                y = 2.0 * x * y + y0
                x = x2 - y2 + x0
                x2 = x * x
                y2 = y * y
                itc += 1
            it[j, i] = itc
    return it


def compute(w, h, max_iter, threads):
    if not HAVE_NUMBA:
        raise RuntimeError("numba is not available")
    from numba import set_num_threads
    set_num_threads(max(1, threads))
    return compute_nb(w, h, max_iter)


def it_to_rgb(it, max_iter):
    if it >= max_iter:
        return (0, 0, 0)
    idx = (it * 255) // max_iter
    if idx < 64:
        return (0, idx * 4, 255)
    if idx < 128:
        return (0, 255, 255 - (idx - 64) * 4)
    if idx < 192:
        return ((idx - 128) * 4, 255, 0)
    return (255, 255 - (idx - 192) * 4, 0)


def render_frame(w, h, max_iter, threads, png_path, fp_path):
    it = compute(w, h, max_iter, threads)
    idx = np.minimum((it.astype(np.int64) * 255) // max_iter, 255)
    pal = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        pal[i] = (0, 0, 0) if i >= 255 else it_to_rgb(i, max_iter)
    rgb = pal[idx]
    from PIL import Image
    Image.fromarray(rgb, "RGB").save(png_path)

    if fp_path:
        stride = max(1, int((w * h) / 300000.0))
        samples = it[::stride, ::stride].ravel().tolist()
        with open(fp_path, "w") as f:
            json.dump({"w": w, "h": h, "max_iter": max_iter, "stride": stride,
                       "samples": samples}, f)
    return 0


def bench(w, h, max_iter, threads, runs):
    compute(w, h, max_iter, threads)  # warmup (LLVM compile + JIT)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        compute(w, h, max_iter, threads)
        times.append((time.perf_counter() - t0) * 1000.0)
    mean = statistics.fmean(times)
    median = statistics.median(times)
    stddev = statistics.pstdev(times) if len(times) > 1 else 0.0
    print(json.dumps({
        "language": "python", "variant": "numba", "width": w, "height": h,
        "max_iter": max_iter, "threads": threads, "runs": runs,
        "min_ms": min(times), "mean_ms": round(mean, 3), "median_ms": round(median, 3),
        "stddev_ms": round(stddev, 3),
        "pixel_iterations": w * h * max_iter,
    }))


def main(argv):
    if len(argv) < 6:
        print(__doc__)
        return 2
    mode = argv[1]
    w, h, max_iter = int(argv[2]), int(argv[3]), int(argv[4])
    threads = int(argv[5])
    if mode == "render":
        if len(argv) < 7:
            return 2
        png = argv[6]
        fp = argv[7] if len(argv) > 7 else None
        return render_frame(w, h, max_iter, threads, png, fp)
    if mode == "bench":
        runs = int(argv[6]) if len(argv) > 6 else 5
        bench(w, h, max_iter, threads, runs)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
