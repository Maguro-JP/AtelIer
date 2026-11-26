"""新規キャンバスのあとに元に戻すで前の絵へ戻ること、前の作業ファイルを白い絵で上書きしないこと、
保存が終わったら「保存しています…」を残さないこと"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("ATELIER_CHECK", "off")


class NewCanvasUndoTest(unittest.TestCase):
    def test_new_canvas_is_undoable_and_forgets_project(self):
        from PySide6.QtWidgets import QApplication
        from atelier.app.main_window import Window
        from atelier.ai.engine import Studio
        from tests.test_draw import FakePainter, FakeWords
        from tests.test_editing import app
        from tests.test_brushtools import drag
        app()
        with TemporaryDirectory() as tmp:
            w = Window(Studio(FakeWords(), FakePainter(), Path(tmp)))
            w.resize(1200, 800); w.show(); QApplication.processEvents()
            c = w.canvas
            c.tool = "pen"
            drag(c, [(300 + i * 20, 400 + i * 10) for i in range(15)])
            QApplication.processEvents()
            drawn = c.layers[c.current].image.copy()
            w.project_path = str(Path(tmp) / "a.atelier")
            w.shared["new"].trigger() if hasattr(w, "shared") and "new" in w.shared else w.new_blank()
            QApplication.processEvents()
            self.assertIsNone(w.project_path)
            self.assertNotEqual(c.layers[c.current].image, drawn)
            c.undo(); QApplication.processEvents()
            self.assertEqual(c.layers[c.current].image, drawn)

            w.project_path = str(Path(tmp) / "b.atelier")
            w.save_project(); w.wait_io(10)
            for _ in range(5):
                QApplication.processEvents()
            self.assertTrue(Path(w.project_path).is_file())
            self.assertNotIn("保存しています", w.statusBar().currentMessage())
            w.dirty = False
            w.close()


if __name__ == "__main__":
    unittest.main()
