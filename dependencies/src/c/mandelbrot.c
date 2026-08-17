/*
 * mandelbrot.c — C implementation of the Mandelbrot benchmark suite.
 *
 * Provides:
 *   - Scalar single-threaded escape-time kernel.
 *   - AVX2 SIMD kernel (8 doubles/lane) when compiled with -mavx2 / -march=native.
 *   - OpenMP parallel row rendering with dynamic scheduling.
 *   - PNG export via the vendored stb_image_write.h header.
 *   - A deterministic integer palette so colors are bit-identical across languages.
 *   - A compact iteration-count fingerprint (JSON) used for cross-language validation.
 *
 * CLI contract (kept identical across all languages):
 *   mandelbrot_c render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>] [--simd]
 *   mandelbrot_c bench  <w> <h> <max_iter> <threads> <runs> [--simd]
 *
 * bench mode prints a single JSON line to stdout with timing statistics.
 */
#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

#ifdef _OPENMP
#include <omp.h>
#endif

#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif

/* ---- complex coordinate viewport (shared spec) ---- */
#define XMIN (-2.0)
#define XMAX (0.5)
#define YMIN (-1.25)
#define YMAX (1.25)

/* ---- portable wall-clock timer ---- */
static double now_sec(void) {
#ifdef _WIN32
    static LARGE_INTEGER freq = {0, 0};
    if (freq.QuadPart == 0) QueryPerformanceFrequency(&freq);
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)freq.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

/* ---- scalar escape-time kernel for one row ---- */
static void mandel_scalar_row(int w, double y0, int max_iter, int *it_row) {
    const double dx = (XMAX - XMIN) / (double)w;
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

/* ---- AVX2 SIMD kernel (8 pixels / iteration) ---- */
#ifdef __AVX2__
#include <immintrin.h>
static void mandel_simd_row(int w, double y0, int max_iter, int *it_row) {
    const double dx = (XMAX - XMIN) / (double)w;
    __m256d four = _mm256_set1_pd(4.0);
    __m256d one = _mm256_set1_pd(1.0);
    __m256d y0v = _mm256_set1_pd(y0);
    int i = 0;
    for (; i + 8 <= w; i += 8) {
        double x0[8];
        for (int k = 0; k < 8; k++) x0[k] = XMIN + (i + k + 0.5) * dx;
        __m256d x0v = _mm256_loadu_pd(x0);
        __m256d x = _mm256_setzero_pd();
        __m256d y = _mm256_setzero_pd();
        __m256d itd = _mm256_setzero_pd();
        __m256i active = _mm256_set1_epi64x(-1); /* all lanes active */
        for (int n = 0; n < max_iter; n++) {
            __m256d x2 = _mm256_mul_pd(x, x);
            __m256d y2 = _mm256_mul_pd(y, y);
            __m256d xy = _mm256_mul_pd(x, y);
            __m256d nx = _mm256_add_pd(_mm256_sub_pd(x2, y2), x0v);
            __m256d ny = _mm256_add_pd(_mm256_add_pd(xy, xy), y0v);
            x = nx;
            y = ny;
            __m256d mag2 = _mm256_add_pd(x2, y2);
            __m256i newactive = _mm256_castpd_si256(_mm256_cmp_pd(mag2, four, _CMP_LE_OQ));
            /* increment per-lane iteration count for lanes still active */
            __m256d inc = _mm256_and_pd(_mm256_castsi256_pd(newactive), one);
            itd = _mm256_add_pd(itd, inc);
            if (_mm256_testz_si256(newactive, newactive)) break;
            active = newactive;
        }
        double itf[8];
        _mm256_storeu_pd(itf, itd);
        long long actf[4];
        _mm256_storeu_si256((__m256i *)actf, active);
        for (int k = 0; k < 8; k++) {
            it_row[i + k] = (actf[k] != 0) ? max_iter : (int)(itf[k] + 1.0);
        }
    }
    /* tail pixels (scalar) */
    for (; i < w; i++) {
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
#else
static void mandel_simd_row(int w, double y0, int max_iter, int *it_row) {
    mandel_scalar_row(w, y0, max_iter, it_row);
}
#endif

/* ---- deterministic integer palette (identical in every language) ---- */
static void it_to_rgb(int it, int max_iter, uint8_t out[3]) {
    if (it >= max_iter) {
        out[0] = 0; out[1] = 0; out[2] = 0;
        return;
    }
    int idx = (int)(((long long)it * 255) / max_iter);
    uint8_t r, g, b;
    if (idx < 64)      { r = 0;             g = (uint8_t)(idx * 4);      b = 255; }
    else if (idx < 128){ r = 0;             g = 255;                     b = (uint8_t)(255 - (idx - 64) * 4); }
    else if (idx < 192){ r = (uint8_t)((idx - 128) * 4); g = 255;        b = 0; }
    else               { r = 255;           g = (uint8_t)(255 - (idx - 192) * 4); b = 0; }
    out[0] = r; out[1] = g; out[2] = b;
}

/* ---- compute the full frame (no image output), used by bench mode ---- */
static void compute_frame(int w, int h, int max_iter, int threads, int use_simd) {
    const double dy = (YMAX - YMIN) / (double)h;
    int nt = threads > 0 ? threads : 1;
#ifdef _OPENMP
    omp_set_num_threads(nt);
#endif
#pragma omp parallel
    {
        int *it_row = (int *)malloc((size_t)w * sizeof(int));
        if (!it_row) continue; /* cannot happen inside omp region; guard */
#pragma omp for schedule(dynamic)
        for (int j = 0; j < h; j++) {
            const double y0 = YMAX - (j + 0.5) * dy;
            if (use_simd) mandel_simd_row(w, y0, max_iter, it_row);
            else mandel_scalar_row(w, y0, max_iter, it_row);
        }
        free(it_row);
    }
}

/* ---- render + PNG + fingerprint ---- */
static int render_frame(int w, int h, int max_iter, int threads, int use_simd,
                        const char *png_path, const char *fp_path) {
    const double dy = (YMAX - YMIN) / (double)h;
    int nt = threads > 0 ? threads : 1;
    int stride = (int)((double)((size_t)w * (size_t)h) / 300000.0);
    if (stride < 1) stride = 1;
    const int sample_cols = (w - 1) / stride + 1;
    const int sample_rows = (h - 1) / stride + 1;
    const size_t n_samples = (size_t)sample_cols * (size_t)sample_rows;

    uint8_t *img = (uint8_t *)malloc((size_t)w * (size_t)h * 3);
    int *samples = (int *)malloc(n_samples * sizeof(int));
    if (!img || !samples) { free(img); free(samples); return 1; }

#ifdef _OPENMP
    omp_set_num_threads(nt);
#endif
#pragma omp parallel
    {
        int *it_row = (int *)malloc((size_t)w * sizeof(int));
        if (!it_row) continue;
#pragma omp for schedule(dynamic)
        for (int j = 0; j < h; j++) {
            const double y0 = YMAX - (j + 0.5) * dy;
            if (use_simd) mandel_simd_row(w, y0, max_iter, it_row);
            else mandel_scalar_row(w, y0, max_iter, it_row);
            uint8_t *row = img + (size_t)j * (size_t)w * 3;
            for (int i = 0; i < w; i++) it_to_rgb(it_row[i], max_iter, row + i * 3);
            if (j % stride == 0) {
                int r = j / stride;
                int *base = samples + (size_t)r * (size_t)sample_cols;
                for (int i = 0; i < w; i += stride) base[i / stride] = it_row[i];
            }
        }
        free(it_row);
    }

    int ok = 0;
    if (png_path && *png_path) {
        ok = stbi_write_png(png_path, w, h, 3, img, (int)((size_t)w * 3));
    }
    if (fp_path && *fp_path) {
        FILE *f = fopen(fp_path, "w");
        if (f) {
            fprintf(f, "{\"w\":%d,\"h\":%d,\"max_iter\":%d,\"stride\":%d,\"samples\":[", w, h, max_iter, stride);
            for (size_t i = 0; i < n_samples; i++) {
                if (i) fputc(',', f);
                fprintf(f, "%d", samples[i]);
            }
            fprintf(f, "]}");
            fclose(f);
        }
    }
    free(img);
    free(samples);
    return ok ? 0 : 1;
}

/* ---- simple statistics ---- */
static int cmp_int(const void *a, const void *b) {
    double da = *(const double *)a, db = *(const double *)b;
    return (da > db) - (da < db);
}

static void bench(int w, int h, int max_iter, int threads, int use_simd, int runs) {
    if (runs < 1) runs = 1;
    /* warmup (critical for caches / frequency ramp) */
    compute_frame(w, h, max_iter, threads, use_simd);
    double *times = (double *)malloc((size_t)runs * sizeof(double));
    if (!times) return;
    for (int r = 0; r < runs; r++) {
        double t0 = now_sec();
        compute_frame(w, h, max_iter, threads, use_simd);
        times[r] = (now_sec() - t0) * 1000.0;
    }
    /* stats */
    double sum = 0.0, min = times[0], max = times[0];
    for (int r = 0; r < runs; r++) { sum += times[r]; if (times[r] < min) min = times[r]; if (times[r] > max) max = times[r]; }
    double mean = sum / runs;
    qsort(times, (size_t)runs, sizeof(double), cmp_int);
    double median = (runs % 2) ? times[runs / 2] : 0.5 * (times[runs / 2 - 1] + times[runs / 2]);
    double var = 0.0;
    for (int r = 0; r < runs; r++) { double d = times[r] - mean; var += d * d; }
    double stddev = sqrt(var / runs);

    const char *variant = use_simd ? "simd" : (threads > 1 ? "openmp" : "scalar");
    printf("{\"language\":\"c\",\"variant\":\"%s\",\"width\":%d,\"height\":%d,\"max_iter\":%d,"
           "\"threads\":%d,\"runs\":%d,\"min_ms\":%.3f,\"mean_ms\":%.3f,\"median_ms\":%.3f,"
           "\"stddev_ms\":%.3f,\"pixel_iterations\":%lld}\n",
           variant, w, h, max_iter, threads, runs, min, mean, median, stddev,
           (long long)w * (long long)h * (long long)max_iter);
    free(times);
}

static void usage(const char *prog) {
    fprintf(stderr, "usage:\n  %s render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>] [--simd]\n"
                    "  %s bench  <w> <h> <max_iter> <threads> <runs> [--simd]\n", prog, prog);
}

int main(int argc, char **argv) {
    if (argc < 6) { usage(argv[0]); return 2; }
    const char *mode = argv[1];
    int w = atoi(argv[2]), h = atoi(argv[3]), max_iter = atoi(argv[4]), threads = atoi(argv[5]);
    int use_simd = 0;

    if (strcmp(mode, "render") == 0) {
        if (argc < 7) { usage(argv[0]); return 2; }
        const char *png_path = argv[6];
        const char *fp_path = (argc > 7) ? argv[7] : NULL;
        for (int i = 8; i < argc; i++) if (!strcmp(argv[i], "--simd")) use_simd = 1;
#ifndef __AVX2__
        if (use_simd) { fprintf(stderr, "warning: --simd requested but binary not compiled with AVX2; using scalar.\n"); use_simd = 0; }
#endif
        return render_frame(w, h, max_iter, threads, use_simd, png_path, fp_path) ? 1 : 0;
    } else if (strcmp(mode, "bench") == 0) {
        if (argc < 7) { usage(argv[0]); return 2; }
        int runs = atoi(argv[6]);
        for (int i = 7; i < argc; i++) if (!strcmp(argv[i], "--simd")) use_simd = 1;
#ifndef __AVX2__
        if (use_simd) { fprintf(stderr, "warning: --simd requested but binary not compiled with AVX2; using scalar.\n"); use_simd = 0; }
#endif
        bench(w, h, max_iter, threads, use_simd, runs);
        return 0;
    }
    usage(argv[0]);
    return 2;
}
