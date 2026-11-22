"""模型の管理から取れることを確かめる。
検品の台本を先に読むと HF_HUB_OFFLINE が入り、模型の管理から取れなかった。
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
