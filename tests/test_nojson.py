"""保存先に絵だけを置く試験。頼み・種は PNG に埋め、大きな記録はアプリのデータの置き場（records）に置く。
保存先に絵の数だけ .json が並ぶと、利用者には中身の分からないゴミに見えた"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock


class NoJsonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.out, self.home = root / "out", root / "home"
        self.env = mock.patch.dict(os.environ, {"ATELIER_HOME": str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _draw(self) -> Path:
        """描いた後と同じ道（Studio._save と _inspect）で絵を残す"""
        from PIL import Image
        from atelier.ai.engine import Studio
        fake = SimpleNamespace(out=self.out, last_check=None)
        meta = {"text": "赤い髪の魔法使い", "prompt": "1girl, red hair", "seed": 1234, "model": "m"}
        path = Studio._save(fake, Image.new("RGB", (16, 16), "white"), 1234, meta)
        with mock.patch("atelier.qc.hand_check.check", return_value={"readable": True, "bad": [], "hands": []}):
            Studio._inspect(fake, path, lambda _s: None)
        return path

    def test_no_json_in_output(self):
        path = self._draw()
        self.assertEqual([p.name for p in self.out.iterdir()], [path.parent.name])   # 保存先には日付のフォルダだけ
        self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])      # その中は絵だけ
        from atelier.ai import finishers
        self.assertTrue((finishers.record_dir(path) / "check.json").exists())
        self.assertTrue(str(finishers.record_dir(path)).startswith(str(self.home)))
        self.assertEqual(finishers.read_record(path, "check.json")["readable"], True)

    def test_prompt_and_seed_from_png(self):
        from atelier.ai import finishers
        from atelier.files.library import Library
        path = self._draw()
        meta = finishers.sidecar(path)
        self.assertEqual((meta["text"], meta["seed"]), ("赤い髪の魔法使い", 1234))
        lib = Library(self.home / "library")
        item = lib.add_work(str(path))
        self.assertEqual((item["text"], item["seed"]), ("赤い髪の魔法使い", 1234))

    def test_old_json_still_read(self):
        from PIL import Image
        from atelier.ai import finishers
        self.out.mkdir(parents=True)
        p = self.out / "old.png"
        Image.new("RGB", (8, 8)).save(p)
        p.with_suffix(".json").write_text(json.dumps({"text": "前の版", "seed": 7}), encoding="utf-8")
        p.with_suffix(".check.json").write_text(json.dumps({"readable": False}), encoding="utf-8")
        self.assertEqual(finishers.sidecar(p)["seed"], 7)
        self.assertEqual(finishers.read_record(p, "check.json"), {"readable": False})
        self.assertTrue(p.with_suffix(".json").exists())   # 利用者のデータなので消さない

    def test_trash_moves_records(self):
        from atelier.ai import finishers
        from atelier.files.trash import Trash
        path = self._draw()
        rd = finishers.record_dir(path)
        t = Trash(self.home / "trash")
        key = t.put([str(path)])
        self.assertFalse(path.exists() or rd.exists())
        t.restore(key)
        self.assertTrue(path.exists() and (rd / "check.json").exists())
        self.assertEqual(finishers.sidecar(path)["seed"], 1234)
        key = t.put([str(path)])
        t.purge(key)
        self.assertFalse(rd.exists())


if __name__ == "__main__":
    unittest.main()


class CharacterDesignerLibraryTest(unittest.TestCase):
    """CharacterDesigner から引き継いだライブラリーが「ファイルが無い」にならないことの試験。
    前は一覧（index.json）だけを写し、道は CharacterDesigner の置き場を指したままだった。CharacterDesigner を
    「部品も消す」で外すと、AtelIer に写してあった資料まで「ファイルが無い」になった"""

    def setUp(self):
        from PIL import Image
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cd, self.home = root / "ProgramData" / "CharacterDesigner", root / "ProgramData" / "AtelIer"
        self.pics = root / "Pictures" / "CharacterDesigner"
        self.env = mock.patch.dict(os.environ, {"CD_HOME": str(self.cd), "ATELIER_HOME": str(self.home)})
        self.env.start()
        for p in (self.pics / "a.png", self.cd / "library" / "docs" / "1a-ref.png", self.cd / "cd" / "library" / "docs" / "2b-old.png"):
            p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 8), "red").save(p)
        self.rows = [
            {"id": "w1", "kind": "work", "path": str(self.pics / "a.png"), "added": "2026-11-01", "seen": True},
            {"id": "d1", "kind": "doc", "path": str(self.cd / "library" / "docs" / "1a-ref.png"), "added": "2026-11-02"},
            {"id": "d2", "kind": "doc", "path": str(self.cd / "cd" / "library" / "docs" / "2b-old.png"), "added": "2026-10-01"},
            {"id": "gone", "kind": "work", "path": str(self.pics / "deleted.png"), "added": "2026-10-02", "seen": True}]
        (self.cd / "library" / "index.json").write_text(json.dumps(self.rows), encoding="utf-8")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _missing(self):
        from atelier.files.library import Library
        return sorted(i["id"] for i in Library(self.home / "library").missing())

    def test_import_copies_pictures_and_fixes_paths(self):
        from atelier.app import migrate
        migrate.integrate_files(self.cd, self.home, self.home / "gguf", ("library",))
        import shutil
        shutil.rmtree(self.cd)
        (self.pics / "a.png").unlink()
        self.assertEqual(self._missing(), ["gone"])
        from atelier.files.library import Library
        paths = {i["id"]: i["path"] for i in Library(self.home / "library").items}
        self.assertEqual(Path(paths["d2"]), self.home / "library" / "docs" / "2b-old.png")
        self.assertTrue(Path(paths["w1"]).is_relative_to(self.home))

    def test_import_adds_to_an_existing_index(self):
        from atelier.app import migrate
        from atelier.files.library import Library
        mine = Library(self.home / "library")
        mine.items = [{"id": "own", "kind": "work", "path": str(self.home / "own.png"), "added": "2026-11-20", "seen": True,
                       "rating": 0, "tags": []}]
        mine.save()
        migrate.integrate_files(self.cd, self.home, self.home / "gguf", ("library",))
        self.assertEqual(sorted(i["id"] for i in Library(self.home / "library").items), ["d1", "d2", "gone", "own", "w1"])

    def test_startup_repairs_index_copied_by_old_version(self):
        """前の版の引き継ぎ（一覧と docs をそのまま写した形）のあとで CharacterDesigner を外した利用者"""
        import shutil
        from atelier.app import migrate
        from atelier.files.library import Library
        shutil.copytree(self.cd / "library", self.home / "library")
        lib = Library(self.home / "library")
        os.remove(self.cd / "library" / "docs" / "1a-ref.png")   # 外したあと: AtelIer の写しだけが残る
        self.assertEqual(sorted(i["id"] for i in lib.missing()), ["d1", "gone"])
        self.assertEqual(migrate.repair_library(lib, self.home), 2)   # d1 は写しを指し、d2 は写して直す
        self.assertEqual(self._missing(), ["gone"])
        self.assertTrue((self.home / "library" / "docs" / "2b-old.png").is_file())
        self.assertTrue((self.cd / "cd" / "library" / "docs" / "2b-old.png").is_file())   # 元は消さない
        self.assertEqual(len(Library(self.home / "library").items), 4)   # 無い絵も一覧から黙って消さない
