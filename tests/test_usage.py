"""デバッグモードの使用率表示: CPU とメモリを標準ライブラリだけで測る"""
import unittest

from atelier.app import usage


class CpuMeterTest(unittest.TestCase):
    def test_first_sample_is_none_then_percent(self):
        m = usage.CpuMeter()
        self.assertIsNone(m.sample(wall=100.0, proc=10.0))
        # 2 秒の間にプロセスが 1 秒分の CPU を使った。コア数で割るので、
        # 4 コアなら 12.5%（タスクマネージャーの表示と同じ物差し）
        import os
        pct = m.sample(wall=102.0, proc=11.0)
        self.assertAlmostEqual(pct, 1.0 / 2.0 / (os.cpu_count() or 1) * 100, places=6)

    def test_clamped_to_100(self):
        m = usage.CpuMeter()
        m.sample(wall=0.0, proc=0.0)
        self.assertLessEqual(m.sample(wall=0.001, proc=100.0), 100.0)


class SampleTest(unittest.TestCase):
    def test_sample_has_all_three(self):
        s = usage.sample(usage.CpuMeter())
        self.assertGreater(s["proc_mb"], 0)          # このプロセス自身のメモリ
        self.assertGreaterEqual(s["sys_mem_pct"], 0) # システム全体のメモリ使用率
        self.assertLessEqual(s["sys_mem_pct"], 100)

    def test_format_line_shows_numbers(self):
        line = usage.format_line({"cpu_pct": 12.34, "proc_mb": 3200.0, "sys_mem_pct": 68.0})
        self.assertIn("CPU 12%", line)
        self.assertIn("3.2 GB", line)
        self.assertIn("68%", line)

    def test_format_line_before_first_cpu_sample(self):
        line = usage.format_line({"cpu_pct": None, "proc_mb": 100.0, "sys_mem_pct": 50.0})
        self.assertIn("使用率", line)


if __name__ == "__main__":
    unittest.main()
