"""落ちた記録: 捕まえられなかった例外が crash.log に残り、次の起動で前の回の分だけを見つける"""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


class CrashLogTest(unittest.TestCase):
    def test_thread_exception_is_written_and_found(self):
        from atelier.app import crash_log as crashlog
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "crash.log"
            with mock.patch.object(crashlog, "path", return_value=log):
                old_hook, old_thread = sys.excepthook, threading.excepthook
                try:
                    crashlog.install()
                    start = log.stat().st_size
                    self.assertEqual(crashlog.last_crash(start), "")
                    t = threading.Thread(target=lambda: 1 / 0, name="描く糸")
                    t.start()
                    t.join()
                    text = log.read_text(encoding="utf-8")
                    self.assertIn("ZeroDivisionError", text)   # 裏の糸の例外は記録に残す
                    self.assertIn("描く糸", text)
                    # 捕まえて続けた例外では、次の起動で知らせない（前は起動のたびに知らせが出た）
                    self.assertEqual(crashlog.last_crash(start), "")
                    with open(log, "a", encoding="utf-8") as f:
                        f.write("Windows fatal exception: access violation\n")
                    self.assertIn("fatal", crashlog.last_crash(start))   # アプリごと落ちたときだけ知らせる
                    self.assertEqual(crashlog.last_crash(log.stat().st_size), "")   # 見たあとの分は空
                finally:
                    import faulthandler
                    faulthandler.disable()
                    sys.excepthook, threading.excepthook = old_hook, old_thread
                    if crashlog._FILE:
                        crashlog._FILE.close()


if __name__ == "__main__":
    unittest.main()
