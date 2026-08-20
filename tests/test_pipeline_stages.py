import unittest
import sys
import tempfile
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dependencies" / "modules"))

import builder
import benchmark_engine as be
import chart_generator
import report_generator


class TestPipelineStages(unittest.TestCase):
    def test_builder_graceful_handling(self):
        empty_tc = {"c_compiler": None, "cpp_compiler": None, "javac": None, "java": None}
        builds = builder.build_all(empty_tc)
        self.assertFalse(builds["c"]["ok"])
        self.assertFalse(builds["cpp"]["ok"])
        self.assertFalse(builds["java"]["ok"])

    def test_implementation_generation(self):
        ctx = {
            "builds": {"c": {"ok": False}, "cpp": {"ok": False}, "java": {"ok": False}},
            "python": sys.executable,
            "max_threads": 4,
            "has_avx2": True,
        }
        impls = be.make_implementations(ctx)
        self.assertTrue(len(impls) >= 3)
        python_impls = [i for i in impls if i.language == "python"]
        self.assertTrue(all(i.available for i in python_impls))

    def test_cross_validation_logic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            samples = [0, 50, 100, 256, 256, 12, 8]
            fp1 = tmp_path / "fp1.json"
            fp2 = tmp_path / "fp2.json"
            fp1.write_text(json.dumps({"w": 10, "h": 10, "max_iter": 256, "stride": 1, "samples": samples}))
            fp2.write_text(json.dumps({"w": 10, "h": 10, "max_iter": 256, "stride": 1, "samples": samples}))

            fingerprints = [
                {"impl": "impl_a", "sha256": "mockhash1", "fingerprint": str(fp1), "interior_fraction": 0.28},
                {"impl": "impl_b", "sha256": "mockhash1", "fingerprint": str(fp2), "interior_fraction": 0.28},
            ]
            val = be.cross_validate(fingerprints)
            self.assertTrue(val["all_match"])
            self.assertEqual(len(val["pairs"]), 1)
            self.assertTrue(val["pairs"][0]["identical"])

    def test_chart_and_report_generation(self):
        mock_results = [
            {
                "impl": "python_pure", "language": "python", "variant": "pure", "display": "Python (pure)",
                "width": 1600, "height": 1200, "max_iter": 256, "threads": 1, "runs": 1,
                "pixel_iterations": 1600 * 1200 * 256, "peak_rss_mb": 45.0, "engine_wall_s": 2.5,
                "status": "ok", "min_ms": 2500.0, "mean_ms": 2500.0, "median_ms": 2500.0, "stddev_ms": 0.0,
                "mpix_s": 0.768, "gflops": 1.57,
            },
            {
                "impl": "python_numpy", "language": "python", "variant": "numpy", "display": "Python (NumPy)",
                "width": 1600, "height": 1200, "max_iter": 256, "threads": 1, "runs": 1,
                "pixel_iterations": 1600 * 1200 * 256, "peak_rss_mb": 65.0, "engine_wall_s": 0.25,
                "status": "ok", "min_ms": 250.0, "mean_ms": 250.0, "median_ms": 250.0, "stddev_ms": 0.0,
                "mpix_s": 7.68, "gflops": 15.7,
            },
            {
                "impl": "python_numba", "language": "python", "variant": "numba", "display": "Python (Numba JIT)",
                "width": 1600, "height": 1200, "max_iter": 256, "threads": 4, "runs": 1,
                "pixel_iterations": 1600 * 1200 * 256, "peak_rss_mb": 75.0, "engine_wall_s": 0.05,
                "status": "ok", "min_ms": 50.0, "mean_ms": 50.0, "median_ms": 50.0, "stddev_ms": 0.0,
                "mpix_s": 38.4, "gflops": 78.6,
            }
        ]
        mock_thread_scaling = [
            {"impl": "python_numba", "language": "python", "variant": "numba", "threads": 1, "mean_ms": 150.0, "status": "ok"},
            {"impl": "python_numba", "language": "python", "variant": "numba", "threads": 2, "mean_ms": 80.0, "status": "ok"},
            {"impl": "python_numba", "language": "python", "variant": "numba", "threads": 4, "mean_ms": 50.0, "status": "ok"},
        ]
        mock_validation = {"method": "mock", "pairs": [], "all_match": True}
        mock_hw = {"cpu_model": "Mock CPU", "logical_threads": 4, "_table": "| Metric | Value |\n|---|---|\n| Host | Mock |"}

        # Test chart generation
        charts = chart_generator.generate_all(mock_results, mock_thread_scaling)
        self.assertTrue(len(charts) > 0)
        for c in charts:
            self.assertTrue(c.exists())

        # Test report generation
        report_path = report_generator.generate_report(mock_results, mock_thread_scaling, mock_validation, mock_hw, {"quick": True})
        self.assertTrue(report_path.exists())
        content = report_path.read_text(encoding="utf-8")
        self.assertIn("Mandelbrot Multi-Language Hardware Evaluation & Benchmark Report", content)
        self.assertIn("Speedup Analysis", content)


if __name__ == "__main__":
    unittest.main()
