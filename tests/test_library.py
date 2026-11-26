"""ライブラリーの中身を確かめる（Library.check）の試験。何百件でも一気に見る。

絵は読まず、あるかないかだけ見る。CharacterDesigner の置き場を指す道で、
AtelIer の置き場に絵がある物は「直せる物」として数える（起動時の直しで直るはずの物）。
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atelier.files.library import Library, format_check  # noqa: E402


def _row(path, kind="work", rating=0, added="2026-11-20 10:00"):
    return {"id": "x", "kind": kind, "path": str(path), "added": added,
            "text": "", "prompt": "", "style": "", "model": "", "seed": None,
            "rating": rating, "tags": [], "note": "", "seen": True}


class CheckLibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.home = self.d / "home"
        self.cd = self.d / "cd"
        self.lib = self.home / "library"
        self.lib.mkdir(parents=True)
        (self.lib / "works").mkdir()
        (self.lib / "docs").mkdir()
        self.env = mock.patch.dict(os.environ, {"CD_HOME": str(self.cd)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _write(self, rows):
        (self.lib / "index.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return Library(self.lib)

    def test_counts_groups_and_fixable(self):
        exists = self.lib / "works" / "exists.png"
        exists.write_bytes(b"fake")
        # CharacterDesigner の置き場の道で、AtelIer の置き場に絵がある物（直せる）
        fixed = self.lib / "works" / "old1.png"
        fixed.write_bytes(b"fake")
        rows = [
            _row(exists, rating=1),
            _row(self.cd / "library" / "works" / "old1.png"),
            _row(self.cd / "library" / "works" / "old3.png"),
            _row(self.d / "pics" / "CharacterDesigner" / "old2.png", rating=-1),
            _row(self.lib / "works" / "gone.png"),
            _row(self.lib / "docs" / "ref.png", kind="doc"),
            {"id": "x", "kind": "work", "path": "", "seen": True},   # 道の無い行
            "not-a-dict",                                             # 辞書でない行
        ]
        lib = self._write(rows)
        rep = lib.check()
        self.assertEqual(rep["rows"], 8)
        self.assertEqual(rep["dropped"], 2)
        self.assertEqual(rep["works"], 5)
        self.assertEqual(rep["docs"], 1)
        self.assertEqual(rep["exist"], 1)
        self.assertEqual(rep["missing"], 5)
        self.assertEqual(rep["groups"].get("CharacterDesigner の置き場"), 2)
        self.assertEqual(rep["groups"].get("CharacterDesigner の保存先など"), 1)
        self.assertEqual(rep["groups"].get("AtelIer の置き場"), 2)
        self.assertEqual(rep["fixable"], 1)
        by_path = {m["path"]: m for m in rep["missing_items"]}
        self.assertTrue(by_path[str(self.cd / "library" / "works" / "old1.png")]["fixable"])
        self.assertFalse(by_path[str(self.cd / "library" / "works" / "old3.png")]["fixable"])
        self.assertEqual(len(rep["missing_items"]), 5)
        text = format_check(rep)
        self.assertIn("絵のファイルがある: 1 件", text)
        self.assertIn("絵のファイルが無い: 5 件", text)
        self.assertIn("old1.png", text)
        self.assertIn("old2.png", text)

    def test_not_a_list(self):
        (self.lib / "index.json").write_text('{"foo": 1}', encoding="utf-8")
        rep = Library(self.lib).check()
        self.assertTrue(rep["shape_error"])
        self.assertEqual(rep["rows"], 0)
        self.assertEqual(rep["exist"], 0)
        self.assertEqual(rep["missing"], 0)

    def test_missing_index(self):
        rep = Library(self.lib).check()
        self.assertFalse(rep["index_exists"])
        self.assertEqual(rep["rows"], 0)
        self.assertEqual(rep["exist"], 0)
        self.assertEqual(rep["missing"], 0)


class CheckLibraryPanelTest(unittest.TestCase):
    """「ライブラリーを確かめる」ボタンが、確かめの結果を窓に渡すこと（本物の窓、offscreen）。窓は出さない"""

    def setUp(self):
        from tests.test_editing import app
        self.qapp = app()
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.home = mock.patch("atelier.files.paths.HOME", self.d / "home")
        self.home.start()
        self.env = mock.patch.dict(os.environ, {"CD_HOME": str(self.d / "cd")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.home.stop()
        self.tmp.cleanup()

    def test_button_opens_check_dialog_with_report(self):
        from PySide6.QtWidgets import QPushButton
        from tests.test_draw import FakeWords
        from tests.test_phases import Painter
        from atelier.ai.engine import Studio
        from atelier.app.main_window import Window
        lib_dir = self.d / "lib"
        (lib_dir / "works").mkdir(parents=True)
        exists = lib_dir / "works" / "exists.png"
        exists.write_bytes(b"fake")
        rows = [_row(exists, rating=1),
                _row(lib_dir / "works" / "gone.png")]
        (lib_dir / "index.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        s = Studio(FakeWords(), Painter(), self.d / "out")
        s.way = "phases"
        w = Window(s)
        w.library = Library(lib_dir)
        w.library_panel.refresh()
        buttons = [b for b in w.library_panel.findChildren(QPushButton)
                   if b.text() == "ライブラリーを確かめる"]
        self.assertEqual(len(buttons), 1)
        with mock.patch("atelier.panels.library_panel.LibraryCheckDialog") as dlg:
            buttons[0].click()
            self.assertEqual(dlg.call_count, 1)
            rep = dlg.call_args[0][1]
            self.assertEqual(rep["exist"], 1)
            self.assertEqual(rep["missing"], 1)
            self.assertEqual(rep["rows"], 2)
        w.hide()
        w.deleteLater()


if __name__ == "__main__":
    unittest.main()


class PicturesPlaceTest(unittest.TestCase):
    """保存先の既定は、利用者が Windows で設定したピクチャの場所（移動していても追う）。
    ホームの下の Pictures と決めつけない"""

    def test_default_output_follows_the_known_pictures_folder(self):
        from atelier.files import paths
        with mock.patch.object(paths, "_known_pictures", return_value=Path("/mnt/d/Pictures")):
            self.assertEqual(paths.pictures_dir(), Path("/mnt/d/Pictures"))
            self.assertEqual(paths.default_output_dir(), Path("/mnt/d/Pictures") / "AtelIer")

    def test_pictures_falls_back_to_home_pictures(self):
        from atelier.files import paths
        with mock.patch.object(paths, "_known_pictures", return_value=None):
            self.assertEqual(paths.pictures_dir(), Path.home() / "Pictures")


class FindMissingTest(unittest.TestCase):
    """起動時の自動探索: 登録の道に絵が無いとき、同名の絵を探して道を付け替える。
    候補が複数あったら当てずっぽうに付け替えない"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.lib = self.d / "library"
        self.lib.mkdir(parents=True)
        self.pics = self.d / "pictures"
        self.pics.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rows):
        (self.lib / "index.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return Library(self.lib)

    def test_found_file_repoints_the_registration(self):
        gone = self.d / "old-drive" / "pic.png"   # 登録の道には無い
        (self.pics / "sub").mkdir()
        real = self.pics / "sub" / "pic.png"      # 探す場所の下にある
        real.write_bytes(b"x")
        lib = self._write([_row(gone)])
        self.assertEqual(lib.find_missing(search_roots=[self.pics]), 1)
        self.assertEqual(lib.items[0]["path"], str(real))
        again = Library(self.lib)                 # 一覧に保存されている
        self.assertEqual(again.items[0]["path"], str(real))

    def test_ambiguous_match_is_not_guessed(self):
        gone = self.d / "old" / "pic.png"
        other = self.d / "other"
        other.mkdir()
        (self.pics / "pic.png").write_bytes(b"x")
        (other / "pic.png").write_bytes(b"y")
        lib = self._write([_row(gone)])
        self.assertEqual(lib.find_missing(search_roots=[self.pics, other]), 0)
        self.assertEqual(lib.items[0]["path"], str(gone))

    def test_existing_files_are_not_touched(self):
        real = self.pics / "pic.png"
        real.write_bytes(b"x")
        lib = self._write([_row(real)])
        self.assertEqual(lib.find_missing(search_roots=[self.pics]), 0)
        self.assertEqual(lib.items[0]["path"], str(real))
