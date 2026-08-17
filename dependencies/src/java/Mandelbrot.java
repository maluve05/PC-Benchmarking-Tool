import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;

/**
 * Mandelbrot.java — Java implementation of the Mandelbrot benchmark suite.
 *
 * - threads == 1 : scalar single-threaded loop.
 * - threads  > 1 : parallel row rendering via IntStream.parallel() inside a
 *                  ForkJoinPool sized to the requested thread count.
 * - PNG export via native javax.imageio.ImageIO.
 *
 * CLI contract:
 *   java Mandelbrot render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]
 *   java Mandelbrot bench  <w> <h> <max_iter> <threads> <runs>
 */
public class Mandelbrot {
    static final double XMIN = -2.0, XMAX = 0.5, YMIN = -1.25, YMAX = 1.25;

    static int escape(double x0, double y0, int maxIter) {
        double x = 0.0, y = 0.0, x2 = 0.0, y2 = 0.0;
        int it = 0;
        while (x2 + y2 <= 4.0 && it < maxIter) {
            y = 2.0 * x * y + y0;
            x = x2 - y2 + x0;
            x2 = x * x;
            y2 = y * y;
            it++;
        }
        return it;
    }

    /** Deterministic integer palette — bit-identical to C/C++/Python. */
    static int itToRgb(int it, int maxIter) {
        if (it >= maxIter) return 0xFF000000; // black (alpha ignored in TYPE_INT_RGB)
        int idx = (int) (((long) it * 255) / maxIter);
        int r, g, b;
        if (idx < 64)      { r = 0;             g = idx * 4;                     b = 255; }
        else if (idx < 128){ r = 0;             g = 255;                         b = 255 - (idx - 64) * 4; }
        else if (idx < 192){ r = (idx - 128) * 4; g = 255;                       b = 0; }
        else               { r = 255;           g = 255 - (idx - 192) * 4;       b = 0; }
        return (r << 16) | (g << 8) | b;
    }

    /**
     * Compute the frame. If rgb != null, pixel colors are written.
     * If samples != null, the strided iteration-count fingerprint is written.
     */
    static void compute(final int w, final int h, final int maxIter, final int threads,
                        final int[] rgb, final int[] samples, final int stride) {
        final double dy = (YMAX - YMIN) / (double) h;
        final double dx = (XMAX - XMIN) / (double) w;
        final int sampleCols = (w - 1) / stride + 1;

        final ThreadLocal<int[]> tl = ThreadLocal.withInitial(() -> new int[w]);

        Runnable body = () -> IntStream.range(0, h).parallel().forEach(j -> {
            int[] itRow = tl.get();
            double y0 = YMAX - (j + 0.5) * dy;
            for (int i = 0; i < w; i++) {
                itRow[i] = escape(XMIN + (i + 0.5) * dx, y0, maxIter);
            }
            if (rgb != null) {
                for (int i = 0; i < w; i++) rgb[j * w + i] = itToRgb(itRow[i], maxIter);
            }
            if (samples != null && j % stride == 0) {
                int r = j / stride;
                for (int i = 0; i < w; i += stride) samples[r * sampleCols + i / stride] = itRow[i];
            }
        });

        if (threads <= 1) {
            body.run();
        } else {
            ForkJoinPool pool = new ForkJoinPool(threads);
            try {
                pool.submit(body).get();
            } catch (Exception e) {
                throw new RuntimeException(e);
            } finally {
                pool.shutdown();
            }
        }
    }

    static int renderFrame(int w, int h, int maxIter, int threads, String pngPath, String fpPath) throws Exception {
        int stride = (int) (((double) w * h) / 300000.0);
        if (stride < 1) stride = 1;
        int sampleCols = (w - 1) / stride + 1;
        int sampleRows = (h - 1) / stride + 1;
        int[] rgb = new int[w * h];
        int[] samples = new int[sampleCols * sampleRows];
        compute(w, h, maxIter, threads, rgb, samples, stride);

        BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
        img.setRGB(0, 0, w, h, rgb, 0, w);
        boolean ok = pngPath != null && !pngPath.isEmpty() && ImageIO.write(img, "png", new File(pngPath));

        if (fpPath != null && !fpPath.isEmpty()) {
            StringBuilder sb = new StringBuilder();
            sb.append("{\"w\":").append(w).append(",\"h\":").append(h)
              .append(",\"max_iter\":").append(maxIter)
              .append(",\"stride\":").append(stride)
              .append(",\"samples\":[");
            for (int i = 0; i < samples.length; i++) {
                if (i > 0) sb.append(',');
                sb.append(samples[i]);
            }
            sb.append("]}");
            java.nio.file.Files.write(new File(fpPath).toPath(), sb.toString().getBytes("UTF-8"));
        }
        return ok ? 0 : 1;
    }

    static void bench(int w, int h, int maxIter, int threads, int runs) {
        if (runs < 1) runs = 1;
        compute(w, h, maxIter, threads, null, null, 1); // warmup (HotSpot C2 JIT)
        double[] times = new double[runs];
        for (int r = 0; r < runs; r++) {
            long t0 = System.nanoTime();
            compute(w, h, maxIter, threads, null, null, 1);
            times[r] = (System.nanoTime() - t0) / 1e6;
        }
        double sum = 0, min = Double.MAX_VALUE;
        for (double t : times) { sum += t; if (t < min) min = t; }
        double mean = sum / runs;
        double[] sorted = times.clone();
        Arrays.sort(sorted);
        double median = (runs % 2 == 1) ? sorted[runs / 2] : 0.5 * (sorted[runs / 2 - 1] + sorted[runs / 2]);
        double var = 0;
        for (double t : times) { double d = t - mean; var += d * d; }
        double stddev = Math.sqrt(var / runs);

        System.out.printf("{\"language\":\"java\",\"variant\":\"parallel\",\"width\":%d,\"height\":%d,\"max_iter\":%d,"
                + "\"threads\":%d,\"runs\":%d,\"min_ms\":%.3f,\"mean_ms\":%.3f,\"median_ms\":%.3f,"
                + "\"stddev_ms\":%.3f,\"pixel_iterations\":%d}%n",
                w, h, maxIter, threads, runs, min, mean, median, stddev, (long) w * h * maxIter);
    }

    static void usage(String prog) {
        System.err.println("usage:\n  " + prog + " render <w> <h> <max_iter> <threads> <out.png> [<fingerprint.json>]\n"
                + "  " + prog + " bench  <w> <h> <max_iter> <threads> <runs>");
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 5) { usage("java Mandelbrot"); System.exit(2); }
        String mode = args[0];
        int w = Integer.parseInt(args[1]), h = Integer.parseInt(args[2]);
        int maxIter = Integer.parseInt(args[3]), threads = Integer.parseInt(args[4]);

        if (mode.equals("render")) {
            if (args.length < 6) { usage("java Mandelbrot"); System.exit(2); }
            String png = args[5];
            String fp = args.length > 6 ? args[6] : null;
            System.exit(renderFrame(w, h, maxIter, threads, png, fp));
        } else if (mode.equals("bench")) {
            if (args.length < 6) { usage("java Mandelbrot"); System.exit(2); }
            bench(w, h, maxIter, threads, Integer.parseInt(args[5]));
        } else {
            usage("java Mandelbrot");
            System.exit(2);
        }
    }
}
