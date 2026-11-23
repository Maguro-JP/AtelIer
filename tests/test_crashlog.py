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

    def test_old_or_warning_records_are_not_shown(self):
        """落ちていない回・古い記録・見せた記録では知らせない（前は起動のたびに出た）"""
        from atelier.app import crash_log as crashlog
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "crash.log"
            # 前の版が積み上げた記録: 捕まえて続けた例外と、昔落ちたときの記録
            log.write_text("==== 起動 ====\n裏の糸 描く糸\nTraceback (most recent call last):\nZeroDivisionError\n"
                           "Windows fatal exception: access violation\n", encoding="utf-8")
            old = log.stat().st_size
            with mock.patch.object(crashlog, "path", return_value=log):
                self.assertEqual(crashlog.last_crash(None), "")   # 前に見た位置が無い（初めての起動・引き継いだ置き場）
                with open(log, "a", encoding="utf-8") as f:
                    f.write("==== 起動 ====\n裏の糸 描く糸\nTraceback (most recent call last):\nValueError\n")
                self.assertEqual(crashlog.last_crash(old), "")   # 例外の記録だけ（落ちていない）
                mid = log.stat().st_size
                with open(log, "a", encoding="utf-8") as f:
                    f.write("==== 起動 ====\nWindows fatal exception: code 0xe06d7363\n")
                self.assertEqual(crashlog.last_crash(mid, crashed=False), "")   # 正しく閉じた回の faulthandler の出力
                self.assertIn("fatal", crashlog.last_crash(mid, crashed=True))
                self.assertEqual(crashlog.last_crash(log.stat().st_size), "")   # 一度見せた記録は二度と出さない
                self.assertEqual(crashlog.last_crash(log.stat().st_size + 100), "")   # 記録が消されて短くなった


if __name__ == "__main__":
    unittest.main()
