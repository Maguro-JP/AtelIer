"""作業ファイル（.atelier）の保存と読み込み、前の形（.cdproj）の読み込み、PSD の書き出し、開く・保存・自動保存。"""
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from atelier.files import project_file
from tests.helpers import close, window


def painted_window():
    w = window(64, 48)
    c = w.canvas
    c.draw_stroke([(5, 5), (60, 40)], color="#e02030", size=5)
    c.add_layer()
    c.rename_layer(c.current, "線")
    c.set_opacity(0.5)
    return w


class ProjectFileTest(unittest.TestCase):
    def test_save_and_load_keep_layers(self):
        w = painted_window()
        c = w.canvas
        before = c.flatten()
        names = [layer.name for layer in c.layers]
        with TemporaryDirectory() as d:
            path = Path(d) / "a.atelier"
            project_file.save(c, path)
            self.assertFalse(path.with_name(path.name + ".part").exists())   # 書きかけを残さない
            with zipfile.ZipFile(path) as z:
                self.assertEqual(json.loads(z.read("manifest.json"))["app"], "AtelIer")
            c.new_canvas(10, 10)
            project_file.load(c, path)
        self.assertEqual(c.size_px(), (64, 48))
        self.assertEqual([layer.name for layer in c.layers], names)
        self.assertAlmostEqual(c.layers[-1].opacity, 0.5)
        self.assertEqual(c.flatten(), before)
        close(w)

    def test_reads_character_designer_file_and_rejects_others(self):
        w = painted_window()
        c = w.canvas
        with TemporaryDirectory() as d:
            snap = project_file.snapshot(c)
            snap["manifest"]["app"] = "CharacterDesigner"
            old = Path(d) / "old.cdproj"
            project_file.write(snap, old)
            c.new_canvas(10, 10)
            self.assertTrue(w.open_path(str(old)))
            self.assertEqual(c.size_px(), (64, 48))
            self.assertIsNone(w.project_path)   # 前の形には上書きしない（保存のときに置き場を聞く）
            snap["manifest"]["app"] = "Other"
            bad = Path(d) / "bad.atelier"
            project_file.write(snap, bad)
            with self.assertRaises(ValueError):
                project_file.read(bad)
        close(w)

    def test_psd_has_header_and_size(self):
        w = painted_window()
        with TemporaryDirectory() as d:
            path = Path(d) / "a.psd"
            project_file.export_psd(w.canvas, path)
            data = path.read_bytes()
        self.assertEqual(data[:4], b"8BPS")
        self.assertEqual(int.from_bytes(data[14:18], "big"), 48)   # 高さ
        self.assertEqual(int.from_bytes(data[18:22], "big"), 64)   # 幅
        close(w)


class FileCommandsTest(unittest.TestCase):
    def test_save_clears_dirty_and_reopens(self):
        w = window(40, 40)
        w.canvas.draw_stroke([(5, 5), (30, 30)], size=4)
        self.assertTrue(w.dirty)
        with TemporaryDirectory() as d:
            path = str(Path(d) / "work")
            with mock.patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(path, "")):
                self.assertTrue(w.save_project())
            self.assertEqual(w.project_path, path + ".atelier")   # 拡張子を付ける
            self.assertFalse(w.dirty)
            before = w.canvas.flatten()
            w.canvas.new_canvas(8, 8)
            self.assertTrue(w.open_path(w.project_path))
            self.assertEqual(w.canvas.flatten(), before)
            self.assertFalse(w.dirty)
        close(w)

    def test_unreadable_file_keeps_canvas(self):
        w = window(40, 40)
        with TemporaryDirectory() as d, mock.patch("PySide6.QtWidgets.QMessageBox.warning") as warned:
            broken = Path(d) / "broken.png"
            broken.write_bytes(b"not a picture")
            self.assertFalse(w.open_path(str(broken)))
            self.assertFalse(w.open_path(str(Path(d) / "missing.atelier")))
            self.assertEqual(warned.call_count, 2)   # 失敗は窓で知らせる
        self.assertEqual(w.canvas.size_px(), (40, 40))   # 0×0 のキャンバスにしない
        close(w)

    def test_export_png_and_layers(self):
        from PySide6.QtGui import QImage
        w = window(40, 40)
        w.canvas.draw_stroke([(5, 5), (30, 30)], size=4)
        with TemporaryDirectory() as d:
            png = str(Path(d) / "out.png")
            with mock.patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(png, "")):
                self.assertTrue(w.export_png())
            self.assertEqual(QImage(png).size(), w.canvas.flatten().size())
            files = w.export_layers_png(d)
            self.assertEqual(len(files), len(w.canvas.layers))
            self.assertTrue(all(Path(f).exists() for f in files))
        close(w)

    def test_autosave_only_when_dirty_and_restore_after_crash(self):
        w = window(40, 40)
        path = project_file.autosave_path()
        path.unlink(missing_ok=True)
        self.assertFalse(w.autosave())   # 変わっていなければ書かない
        w.canvas.draw_stroke([(5, 5), (30, 30)], size=4)
        self.assertTrue(w.autosave())
        self.assertTrue(path.exists())
        before = w.canvas.flatten()
        w.canvas.new_canvas(8, 8)
        w.store.setValue("running", 0)
        self.assertFalse(w.offer_restore())   # 正しく閉じたあとは聞かない
        w.store.setValue("running", 2 ** 22 + 12345)   # もう動いていない番号（前の回が落ちた形）
        with mock.patch.object(w, "ask_choice", return_value="open"):
            self.assertTrue(w.offer_restore())
        self.assertEqual(w.canvas.flatten(), before)
        self.assertIsNone(w.project_path)   # 自動保存の場所に上書き保存させない
        self.assertTrue(w.dirty)
        close(w)

    def test_close_asks_when_dirty(self):
        w = window(40, 40)
        w.canvas.draw_stroke([(5, 5), (30, 30)], size=4)
        with mock.patch.object(w, "ask_choice", return_value="cancel"):
            w.close()
        self.assertTrue(w.isVisible())   # 「やめる」なら閉じない
        close(w)
        self.assertFalse(w.isVisible())


if __name__ == "__main__":
    unittest.main()
