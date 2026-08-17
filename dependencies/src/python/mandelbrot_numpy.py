#!/usr/bin/env python3
"""
mandelbrot_numpy.py — NumPy vectorized implementation of the Mandelbrot
benchmark suite. Rows are processed in chunks to bound peak memory at 4K/8K.

CLI contract:
  python mandelbrot_numpy.py render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]
  python mandelbrot_numpy.py bench  <w> <h> <max_iter> <threads> <runs>
"""
import json
import statistics
import sys
import time

import numpy as np

XMIN, XMAX, YMIN, YMAX = -2.0, 0.5, -1.25, 1.25
CHUNK_PIXELS = 2_000_000  # target pixels per row-chunk (bounds memory at 8K)


def compute(w, h, max_iter):
    """Return int32 array (h, w) of escape iteration counts."""
    dx = (XMAX - XMIN) / w
    dy = (YMAX - YMIN) / h
    xs = XMIN + (np.arange(w, dtype=np.float64) + 0.5) * dx
    ys = YMAX - (np.arange(h, dtype=np.float64) + 0.5) * dy
    chunk_rows = max(1, CHUNK_PIXELS // w)
    it_full = np.zeros((h, w), dtype=np.int32)
    for j0 in range(0, h, chunk_rows):
        j1 = min(j0 + chunk_rows, h)
        Y = ys[j0:j1, None]
        C = xs[None, :] + 1j * Y
        Z = np.zeros_like(C)
        it = np.zeros((j1 - j0, w), dtype=np.int32)
        active = np.ones((j1 - j0, w), dtype=bool)
        with np.errstate(over="ignore", invalid="ignore"):
            for n in range(max_iter):
                Z = Z * Z + C
                escaped = (Z.real * Z.real + Z.imag * Z.imag) > 4.0
                newly = escaped & active
                it[newly] = n + 1
                active &= ~escaped
                if not active.any():
                    break
        it[it == 0] = max_iter  # never escaped -> interior
        it_full[j0:j1] = it
    return it_full


def colorize(it, max_iter):
    """Map iteration counts to RGB using the shared integer palette."""
    idx = np.minimum((it.astype(np.int64) * 255) // max_iter, 255)
    pal = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        pal[i] = it_to_rgb(i, max_iter)
    return pal[idx]  # (h, w, 3)


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


def render_frame(w, h, max_iter, png_path, fp_path):
    it = compute(w, h, max_iter)
    rgb = colorize(it, max_iter)
    from PIL import Image
    Image.fromarray(rgb, "RGB").save(png_path)

    if fp_path:
        stride = max(1, int((w * h) / 300000.0))
        samples = it[::stride, ::stride].ravel().tolist()
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
        "language": "python", "variant": "numpy", "width": w, "height": h,
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
