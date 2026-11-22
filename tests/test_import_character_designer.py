"""CharacterDesigner の部品・設定・記録を、AtelIer へ 1 回だけ写す（移さずに写す）ことを確かめる"""
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from atelier.app import migrate


class ImportCharacterDesignerTest(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        self.tmp = Path(tempfile.mkdtemp())
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(self.tmp / "settings"))
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(self.tmp / "settings"))
        self.src, self.dst = self.tmp / "CharacterDesigner", self.tmp / "AtelIer"
        (self.src / "gen" / "lib" / "torch").mkdir(parents=True)
        (self.src / "gen" / "lib" / "torch" / "version.py").write_text("__version__ = '2.5.0'\n")
        (self.src / "places.json").write_text('{"model_dir": "D:/LLM"}')
        (self.dst / "places.json").parent.mkdir(parents=True)
        (self.dst / "places.json").write_text('{"model_dir": "E:/LLM"}')

    def test_copies_parts_keeps_existing_and_source(self):
        self.assertTrue(migrate.import_once(self.dst, src=self.src))
        self.assertTrue((self.dst / "gen" / "lib" / "torch" / "version.py").exists())   # 部品が届き、取り直さずに描ける
        self.assertIn("E:/LLM", (self.dst / "places.json").read_text())                 # AtelIer で選んだ値は上書きしない
        self.assertTrue((self.src / "gen" / "lib" / "torch" / "version.py").exists())   # CharacterDesigner は元のまま
        self.assertFalse(migrate.import_once(self.dst, src=self.src))                  # 2 回目は何もしない

    def test_settings_copied_once_without_overwrite(self):
        QSettings("CharacterDesigner", "chatdraw-settings").setValue("model", "flux")
        QSettings("CharacterDesigner", "chatdraw").setValue("theme", "dark")
        QSettings("AtelIer", "atelier").setValue("theme", "light")
        self.assertTrue(migrate.import_once(self.dst, QSettings, src=self.src))
        self.assertEqual(QSettings("AtelIer", "atelier-settings").value("model"), "flux")
        self.assertEqual(QSettings("AtelIer", "atelier").value("theme"), "light")
        QSettings("CharacterDesigner", "chatdraw-settings").setValue("model", "sdxl")
        self.assertFalse(migrate.import_once(self.dst, QSettings, src=self.src))
        self.assertEqual(QSettings("AtelIer", "atelier-settings").value("model"), "flux")


if __name__ == "__main__":
    unittest.main()
