/*
 * mandelbrot.cpp — C++20 implementation of the Mandelbrot benchmark suite.
 *
 * Uses std::jthread with an atomic work-stealing-style row scheduler for
 * dynamic parallel workload distribution. PNG export via vendored
 * stb_image_write.h. Identical CLI contract to the C / Java / Python builds.
 *
 *   mandelbrot_cpp render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]
 *   mandelbrot_cpp bench  <w> <h> <max_iter> <threads> <runs>
 */
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#include <atomic>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <numeric>
#include <thread>
#include <vector>

static constexpr double XMIN = -2.0, XMAX = 0.5, YMIN = -1.25, YMAX = 1.25;

static inline double now_sec() {
    using namespace std::chrono;
    return duration_cast<duration<double>>(steady_clock::now().time_since_epoch()).count();
}

/* ---- scalar escape-time kernel (one row) ---- */
static void mandel_row(int w, double y0, int max_iter, int *it_row) {
    const double dx = (XMAX - XMIN) / static_cast<double>(w);
#pragma GCC unroll 4
    for (int i = 0; i < w; i++) {
        const double x0 = XMIN + (i + 0.5) * dx;
        double x = 0.0, y = 0.0, x2 = 0.0, y2 = 0.0;
        int it = 0;
        while (x2 + y2 <= 4.0 && it < max_iter) {
            y = 2.0 * x * y + y0;
            x = x2 - y2 + x0;
            x2 = x * x;
            y2 = y * y;
            it++;
        }
        it_row[i] = it;
    }
}

/* ---- deterministic integer palette (identical across languages) ---- */
static void it_to_rgb(int it, int max_iter, uint8_t out[3]) {
    if (it >= max_iter) {
        out[0] = 0; out[1] = 0; out[2] = 0;
        return;
    }
    int idx = static_cast<int>((static_cast<long long>(it) * 255) / max_iter);
    uint8_t r, g, b;
    if (idx < 64)       { r = 0; g = static_cast<uint8_t>(idx * 4); b = 255; }
    else if (idx < 128) { r = 0; g = 255; b = static_cast<uint8_t>(255 - (idx - 64) * 4); }
    else if (idx < 192) { r = static_cast<uint8_t>((idx - 128) * 4); g = 255; b = 0; }
    else                { r = 255; g = static_cast<uint8_t>(255 - (idx - 192) * 4); b = 0; }
    out[0] = r; out[1] = g; out[2] = b;
}

/*
 * Compute the frame. If img != nullptr the RGB pixels are written there,
 * otherwise the work is discarded (bench mode). If samples != nullptr the
 * strided iteration-count fingerprint is accumulated into it.
 */
static void compute(int w, int h, int max_iter, int threads,
                    uint8_t *img, int *samples, int stride) {
    const double dy = (YMAX - YMIN) / static_cast<double>(h);
    const int sample_cols = (w - 1) / stride + 1;
    const double dx = (XMAX - XMIN) / static_cast<double>(w);

    std::atomic<std::size_t> next{0};
    auto worker = [&]() {
        std::vector<int> it_row(static_cast<std::size_t>(w));
        for (;;) {
            const std::size_t j = next.fetch_add(1);
            if (j >= static_cast<std::size_t>(h)) break;
            mandel_row(w, YMAX - (j + 0.5) * dy, max_iter, it_row.data());
            if (img) {
                uint8_t *row = img + j * static_cast<std::size_t>(w) * 3;
                for (int i = 0; i < w; i++) it_to_rgb(it_row[i], max_iter, row + i * 3);
            }
            if (samples && j % static_cast<std::size_t>(stride) == 0) {
                const int r = static_cast<int>(j / stride);
                int *base = samples + static_cast<std::size_t>(r) * sample_cols;
                for (int i = 0; i < w; i += stride) base[i / stride] = it_row[i];
            }
        }
    };

    if (threads <= 1) {
        worker();
    } else {
        std::vector<std::jthread> pool;
        pool.reserve(threads);
        for (int t = 0; t < threads; t++) pool.emplace_back(worker);
        /* jthreads join on destruction */
    }
    (void)dx;
}

static int render_frame(int w, int h, int max_iter, int threads,
                        const char *png_path, const char *fp_path) {
    int stride = static_cast<int>(static_cast<double>(static_cast<std::size_t>(w) * h) / 300000.0);
    if (stride < 1) stride = 1;
    const int sample_cols = (w - 1) / stride + 1;
    const int sample_rows = (h - 1) / stride + 1;
    const std::size_t n_samples = static_cast<std::size_t>(sample_cols) * sample_rows;

    std::vector<uint8_t> img(static_cast<std::size_t>(w) * h * 3);
    std::vector<int> samples(n_samples, 0);
    compute(w, h, max_iter, threads, img.data(), samples.data(), stride);

    int ok = 0;
    if (png_path && *png_path)
        ok = stbi_write_png(png_path, w, h, 3, img.data(), w * 3);
    if (fp_path && *fp_path) {
        FILE *f = fopen(fp_path, "w");
        if (f) {
            fprintf(f, "{\"w\":%d,\"h\":%d,\"max_iter\":%d,\"stride\":%d,\"samples\":[", w, h, max_iter, stride);
            for (std::size_t i = 0; i < n_samples; i++) {
                if (i) fputc(',', f);
                fprintf(f, "%d", samples[i]);
            }
            fprintf(f, "]}");
            fclose(f);
        }
    }
    return ok ? 0 : 1;
}

static void bench(int w, int h, int max_iter, int threads, int runs) {
    if (runs < 1) runs = 1;
    compute(w, h, max_iter, threads, nullptr, nullptr, 1); /* warmup */
    std::vector<double> times;
    times.reserve(runs);
    for (int r = 0; r < runs; r++) {
        const double t0 = now_sec();
        compute(w, h, max_iter, threads, nullptr, nullptr, 1);
        times.push_back((now_sec() - t0) * 1000.0);
    }
    const double sum = std::accumulate(times.begin(), times.end(), 0.0);
    const double mean = sum / runs;
    const double min = *std::min_element(times.begin(), times.end());
    std::vector<double> sorted = times;
    std::sort(sorted.begin(), sorted.end());
    const double median = (runs % 2) ? sorted[runs / 2]
                                     : 0.5 * (sorted[runs / 2 - 1] + sorted[runs / 2]);
    double var = 0.0;
    for (double t : times) { double d = t - mean; var += d * d; }
    const double stddev = std::sqrt(var / runs);

    printf("{\"language\":\"cpp\",\"variant\":\"threads\",\"width\":%d,\"height\":%d,\"max_iter\":%d,"
           "\"threads\":%d,\"runs\":%d,\"min_ms\":%.3f,\"mean_ms\":%.3f,\"median_ms\":%.3f,"
           "\"stddev_ms\":%.3f,\"pixel_iterations\":%lld}\n",
           w, h, max_iter, threads, runs, min, mean, median, stddev,
           static_cast<long long>(w) * h * max_iter);
}

static void usage(const char *prog) {
    fprintf(stderr, "usage:\n  %s render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]\n"
                    "  %s bench  <w> <h> <max_iter> <threads> <runs>\n", prog, prog);
}

int main(int argc, char **argv) {
    if (argc < 6) { usage(argv[0]); return 2; }
    const char *mode = argv[1];
    const int w = atoi(argv[2]), h = atoi(argv[3]), max_iter = atoi(argv[4]), threads = atoi(argv[5]);

    if (strcmp(mode, "render") == 0) {
        if (argc < 7) { usage(argv[0]); return 2; }
        const char *png_path = argv[6];
        const char *fp_path = (argc > 7) ? argv[7] : nullptr;
        return render_frame(w, h, max_iter, threads, png_path, fp_path) ? 1 : 0;
    } else if (strcmp(mode, "bench") == 0) {
        if (argc < 7) { usage(argv[0]); return 2; }
        bench(w, h, max_iter, threads, atoi(argv[6]));
        return 0;
    }
    usage(argv[0]);
    return 2;
}
