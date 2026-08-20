import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dependencies" / "modules"))

import preflight
import hardware_info


class TestPreflightAndHardware(unittest.TestCase):
    def test_python_version_check(self):
        info = preflight.python_version_check()
        self.assertIn("version", info)
        self.assertIn("executable", info)
        self.assertTrue(info["ok"])

    def test_detect_compilers(self):
        tc = preflight.detect_compilers()
        self.assertIsInstance(tc, dict)
        for key in ("gcc", "g++", "clang", "clang++", "javac", "java", "c_compiler", "cpp_compiler"):
            self.assertIn(key, tc)

    def test_collect_hardware(self):
        tc = preflight.detect_compilers()
        hw = hardware_info.collect_hardware(tc)
        self.assertIsInstance(hw, dict)
        self.assertIn("cpu_model", hw)
        self.assertIn("logical_threads", hw)
        self.assertIn("ram", hw)
        self.assertIn("vector_isa", hw)
        self.assertIn("os_full", hw)
        self.assertGreaterEqual(hw["logical_threads"], 1)

    def test_format_hardware_table(self):
        tc = preflight.detect_compilers()
        hw = hardware_info.collect_hardware(tc)
        tbl = hardware_info.format_hardware_table(hw)
        self.assertIsInstance(tbl, str)
        self.assertIn("| Metric | Value |", tbl)
        self.assertIn("CPU Model", tbl)
        self.assertIn("Logical Threads", tbl)


if __name__ == "__main__":
    unittest.main()
