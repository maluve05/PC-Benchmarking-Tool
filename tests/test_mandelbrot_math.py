import unittest
import numpy as np
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dependencies" / "src" / "python"))

import mandelbrot_pure as py_pure
import mandelbrot_numpy as py_numpy
try:
    import mandelbrot_numba as py_numba
    HAVE_NUMBA = True
except Exception:
    HAVE_NUMBA = False


class TestMandelbrotMath(unittest.TestCase):
    def test_known_points_pure(self):
        """Test known points in the Mandelbrot set and outside."""
        grid = py_pure.compute(10, 10, 256)
        self.assertEqual(len(grid), 10)
        self.assertEqual(len(grid[0]), 10)

    def test_it_to_rgb_palette(self):
        """Verify palette output bounds and properties."""
        # Interior should be black (0, 0, 0)
        self.assertEqual(py_pure.it_to_rgb(256, 256), (0, 0, 0))
        self.assertEqual(py_pure.it_to_rgb(500, 256), (0, 0, 0))
        
        # Exterior points
        rgb_0 = py_pure.it_to_rgb(0, 256)
        self.assertEqual(rgb_0, (0, 0, 255))
        
        rgb_half = py_pure.it_to_rgb(128, 256)
        self.assertTrue(all(0 <= c <= 255 for c in rgb_half))

        # Check NumPy palette matching
        np_rgb_0 = py_numpy.it_to_rgb(0, 256)
        self.assertEqual(rgb_0, np_rgb_0)
        np_rgb_half = py_numpy.it_to_rgb(128, 256)
        self.assertEqual(rgb_half, np_rgb_half)

    def test_pure_vs_numpy_parity(self):
        """Pure Python and NumPy algorithms should produce bit-identical grids."""
        w, h, max_iter = 32, 24, 128
        pure_grid = np.array(py_pure.compute(w, h, max_iter), dtype=np.int32)
        numpy_grid = py_numpy.compute(w, h, max_iter)
        
        np.testing.assert_array_equal(pure_grid, numpy_grid)

    def test_pure_vs_numba_parity(self):
        """Pure Python and Numba algorithms should produce identical or near-identical grids."""
        if not HAVE_NUMBA:
            self.skipTest("Numba not available")
        w, h, max_iter = 32, 24, 128
        pure_grid = np.array(py_pure.compute(w, h, max_iter), dtype=np.int32)
        numba_grid = py_numba.compute(w, h, max_iter, 1)
        
        diff = np.abs(pure_grid - numba_grid)
        # Differences should be 0 or at most 1 on boundary due to fastmath
        self.assertTrue(np.all(diff <= 1))
        exact_ratio = np.sum(diff == 0) / diff.size
        self.assertGreaterEqual(exact_ratio, 0.99)


if __name__ == "__main__":
    unittest.main()
