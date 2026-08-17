#!/usr/bin/env python3
"""
mandelbrot_pure.py — Pure Python (CPython) implementation of the Mandelbrot
benchmark suite. No numpy / numba: a hand-optimized scalar escape-time loop.

CLI contract (identical across languages):
  python mandelbrot_pure.py render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]
  python mandelbrot_pure.py bench  <w> <h> <max_iter> <threads> <runs>
"""
import json
import statistics
import sys
import time

XMIN, XMAX, YMIN, YMAX = -2.0, 0.5, -1.25, 1.25


def compute(w, h, max_iter):
    """Return a 2D list (rows) of escape iteration counts (row-major)."""
    dx = (XMAX - XMIN) / w
    dy = (YMAX - YMIN) / h
    xs = [XMIN + (i + 0.5) * dx for i in range(w)]
    grid = []
    for j in range(h):
        y0 = YMAX - (j + 0.5) * dy
        row = [0] * w
        for i in range(w):
            x0 = xs[i]
            x = y = x2 = y2 = 0.0
            it = 0
            while x2 + y2 <= 4.0 and it < max_iter:
                y = 2.0 * x * y + y0
                x = x2 - y2 + x0
                x2 = x * x
                y2 = y * y
                it += 1
            row[i] = it
        grid.append(row)
    return grid


def it_to_rgb(it, max_iter):
    """Deterministic integer palette — bit-identical across languages."""
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


def render_frame(w, h, max_iter, png_path, fp_path):
    grid = compute(w, h, max_iter)

    from PIL import Image
    data = bytearray(w * h * 3)
    pos = 0
    for row in grid:
        for it in row:
            r, g, b = it_to_rgb(it, max_iter)
            data[pos] = r
            data[pos + 1] = g
            data[pos + 2] = b
            pos += 3
    img = Image.frombuffer("RGB", (w, h), bytes(data), "raw", "RGB", 0, 1)
    img.save(png_path)

    if fp_path:
        stride = max(1, int((w * h) / 300000.0))
        samples = []
        for j in range(0, h, stride):
            row = grid[j]
            for i in range(0, w, stride):
                samples.append(row[i])
        with open(fp_path, "w") as f:
            json.dump({"w": w, "h": h, "max_iter": max_iter, "stride": stride,
                       "samples": samples}, f)
    return 0


def bench(w, h, max_iter, runs):
    compute(w, h, max_iter)  # warmup
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        compute(w, h, max_iter)
        times.append((time.perf_counter() - t0) * 1000.0)
    mean = statistics.fmean(times)
    median = statistics.median(times)
    stddev = statistics.pstdev(times) if len(times) > 1 else 0.0
    print(json.dumps({
        "language": "python", "variant": "pure", "width": w, "height": h,
        "max_iter": max_iter, "threads": 1, "runs": runs,
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
    threads = int(argv[5])  # accepted for CLI parity; pure Python is single-threaded
    if mode == "render":
        if len(argv) < 7:
            return 2
        png = argv[6]
        fp = argv[7] if len(argv) > 7 else None
        return render_frame(w, h, max_iter, png, fp)
    if mode == "bench":
        runs = int(argv[6]) if len(argv) > 6 else 5
        bench(w, h, max_iter, runs)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
