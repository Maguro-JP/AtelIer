"""CharacterDesigner と模型を使い回し、模型の管理から取れることを確かめる。

AtelIer に移したとき、データの置き場の名前が変わり（C:\\ProgramData\\CharacterDesigner → AtelIer）、
CharacterDesigner で選んだ模型の置き場と取った言葉の模型が見えなくなった。
また、検品の台本を先に読むと HF_HUB_OFFLINE が入り、模型の管理から取れなかった。
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from atelier.files import paths


class CharacterDesignerShare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.mine, self.cd, self.models = root / "atelier", root / "cd", root / "D-LLM"
        for d in (self.mine, self.cd, self.models):
            d.mkdir()
        env = {"ATELIER_HOME": str(self.mine), "CD_HOME": str(self.cd)}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_uses_model_dir_chosen_in_character_designer(self):
        (self.cd / "places.json").write_text(json.dumps({"model_dir": str(self.models)}), encoding="utf-8")
        self.assertEqual(paths.chosen_model_dir(), str(self.models))
        self.assertEqual(paths.llm_home(), self.models)

    def test_own_choice_comes_first(self):
        own = Path(self.tmp.name) / "own"
        own.mkdir()
        (self.cd / "places.json").write_text(json.dumps({"model_dir": str(self.models)}), encoding="utf-8")
        paths.set_model_dir(str(own))
        self.assertEqual(paths.chosen_model_dir(), str(own))

    def test_missing_chosen_dir_is_ignored(self):
        (self.cd / "places.json").write_text(json.dumps({"model_dir": str(self.models / "gone")}), encoding="utf-8")
        self.assertEqual(paths.chosen_model_dir(), "")

    def test_reads_character_designer_gguf(self):
        self.assertIn(self.cd / "llm", paths.legacy_gguf_dirs())
        (self.cd / "llm").mkdir()
        (self.cd / "llm" / "w.gguf").write_bytes(b"x")
        with mock.patch.object(paths, "GGUF", self.models / "gguf"):
            self.assertEqual(paths.find_gguf("w.gguf"), self.cd / "llm" / "w.gguf")

    def test_manager_lists_character_designer_gguf(self):
        from atelier.models import manager
        (self.cd / "llm").mkdir()
        (self.cd / "llm" / "w.gguf").write_bytes(b"x")
        with mock.patch.object(manager, "HUB", self.models / "hub"), mock.patch.object(manager, "GGUF", self.models / "gguf"), \
                mock.patch.object(manager, "OWN_LLM", self.mine / "llm"), \
                mock.patch.object(paths, "GGUF", self.models / "gguf"), mock.patch.object(paths, "OWN_LLM", self.mine / "llm"):
            items = [i for i in manager.installed() if i.kind == "words"]
        self.assertEqual([i.path for i in items], [self.cd / "llm" / "w.gguf"])

    def test_import_does_not_copy_gguf(self):
        from atelier.app import migrate
        (self.cd / "llm").mkdir()
        (self.cd / "llm" / "w.gguf").write_bytes(b"x")
        (self.cd / "llm" / "w.gguf.part").write_bytes(b"x")
        (self.cd / "model_prefs.json").write_text("{}", encoding="utf-8")
        migrate.import_character_designer(self.cd, self.mine)
        self.assertTrue((self.mine / "model_prefs.json").exists())
        self.assertFalse((self.mine / "llm" / "w.gguf").exists())
        self.assertFalse((self.mine / "llm" / "w.gguf.part").exists())

    def test_migrate_finds_character_designer_home(self):
        from atelier.app import migrate
        self.assertEqual(migrate.character_designer_home(), self.cd)


class FetchWhileOffline(unittest.TestCase):
    def test_fetch_turns_offline_off(self):
        import huggingface_hub.constants as c
        from atelier.models import first_setup
        from atelier.models.catalog import ImageModel
        seen = []
        m = ImageModel(repo="o/tiny", name="tiny", good="", speed="", gb=0.01, steps=1, guidance=1.0, family="sd15x")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(c, "HF_HUB_OFFLINE", True), \
                mock.patch.object(first_setup, "HUB", Path(d)), mock.patch.object(first_setup, "engine_ready", lambda: True), \
                mock.patch.object(first_setup, "ensure_shared", lambda: None), \
                mock.patch("huggingface_hub.snapshot_download", lambda *a, **k: seen.append(c.HF_HUB_OFFLINE) or d):
            out = []
            f = first_setup.Fetcher()
            f.finished.connect(out.append)
            f.run(m, None, qc=False)
            self.assertTrue(c.HF_HUB_OFFLINE)   # 取り終えたら元に戻す
        self.assertEqual(out, [""])
        self.assertEqual(seen, [False])


if __name__ == "__main__":
    unittest.main()
