"""CharacterDesigner の作業ファイル（.cdproj）を開けて、上書きはしない。ほかのアプリのファイルは開かない。"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from atelier.files import project_file  # noqa: E402


class LegacyProjectTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from atelier.paint.canvas import Canvas
        self.canvas = Canvas()
        self.canvas.new_canvas(64, 48)
        self.canvas.draw_stroke([(5, 5), (60, 40)], color="#e02030", size=5)

    def test_writes_own_name_and_reads_legacy(self):
        snap = project_file.snapshot(self.canvas)
        self.assertEqual(snap["manifest"]["app"], "AtelIer")
        self.assertEqual(project_file.SUFFIX, ".atelier")
        before = self.canvas.flatten()
        with TemporaryDirectory() as d:
            snap["manifest"]["app"] = project_file.LEGACY_APPS[0]
            old = Path(d) / ("old" + project_file.LEGACY_SUFFIXES[0])
            project_file.write(snap, old)
            self.canvas.new_canvas(8, 8)
            project_file.load(self.canvas, old)
            self.assertEqual(self.canvas.flatten(), before)
            snap["manifest"]["app"] = "Other"
            bad = Path(d) / "bad.atelier"
            project_file.write(snap, bad)
            with self.assertRaises(ValueError):
                project_file.read(bad)

    def test_window_does_not_overwrite_legacy_file(self):
        """窓で前のアプリの作業ファイルを開くと、絵は読めるが、保存先はそのファイルにしない（上書きで前のアプリの物を壊さない）。
        自分の作業ファイルを開いたときは、そのファイルに保存する"""
        from atelier.ai.engine import Studio
        from atelier.app.main_window import Window
        from tests.test_chatdraw import FakePainter, FakeWords, wait_bg
        from PySide6.QtWidgets import QApplication
        qapp = QApplication.instance()
        snap = project_file.snapshot(self.canvas)
        before = self.canvas.flatten()
        with TemporaryDirectory() as d:
            w = Window(Studio(FakeWords(), FakePainter(), Path(d)))
            try:
                snap["manifest"]["app"] = project_file.LEGACY_APPS[0]
                old = Path(d) / ("old" + project_file.LEGACY_SUFFIXES[0])
                project_file.write(snap, old)
                w.open_path(str(old))
                wait_bg(qapp, w)
                self.assertEqual(w.canvas.flatten(), before)          # 前のアプリの絵が読める
                self.assertIsNone(w.project_path)                     # 上書きの保存先にしない
                snap["manifest"]["app"] = "AtelIer"
                own = Path(d) / ("own" + project_file.SUFFIX)
                project_file.write(snap, own)
                w.open_path(str(own))
                wait_bg(qapp, w)
                self.assertEqual(w.project_path, str(own))
            finally:
                w.dirty = False
                w.closing_checked = True
                w.close()


if __name__ == "__main__":
    unittest.main()


class UpdateSourceTest(unittest.TestCase):
    def test_updates_come_from_this_repository(self):
        """更新の確かめ先が流用元のままだと、AtelIer が CharacterDesigner の Setup.exe を入れてしまう"""
        from atelier.app import updater
        self.assertEqual(updater.REPO, "maguro-jp/atelier")
        nsi = (Path(__file__).resolve().parents[1] / "packaging" / "installer.nsi").read_text(encoding="utf-8")
        self.assertIn('!define APP "AtelIer"', nsi)
        self.assertNotIn("chatdraw", nsi)
