"""デバッグモードの土台の重ね表示: 土台の絵を薄くする処理と、土台の受け渡しの試験"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atelier.app.window.settings_and_debug import SettingsAndDebugMixin, faded_base   # noqa: E402


class FadedBaseTest(unittest.TestCase):
    def test_alpha_is_scaled(self):
        img = Image.new("RGB", (4, 4), (200, 100, 50))
        out = faded_base(img, 0.35)
        self.assertEqual(out.mode, "RGBA")
        self.assertEqual(out.getpixel((0, 0)), (200, 100, 50, int(255 * 0.35)))

    def test_alpha_clamps(self):
        img = Image.new("RGB", (2, 2), (10, 10, 10))
        self.assertEqual(faded_base(img, 2.0).getpixel((0, 0))[3], 255)
        self.assertEqual(faded_base(img, 0.0).getpixel((0, 0))[3], 0)


class BaseHandoverTest(unittest.TestCase):
    """土台の絵は preview（見せる絵の通り道）とは別の通り道で窓へ渡る:
    Job の on_base → base_thumb シグナル → 窓の _stash_base。
    preview に混ぜると、受け側の見落としで土台が画面に出る（0.1.28 で起きた）"""

    def test_job_hands_base_over_on_base_not_preview(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from atelier.app.window.jobs import Job

        with TemporaryDirectory() as d:
            path = Path(d) / "p.png"
            Image.new("RGB", (2, 2), "white").save(path)

            class Studio:
                painter = None

                def draw(self, text, seed, **kw):
                    kw["on_base"](Image.new("RGB", (2, 2), (255, 0, 255)))
                    return "x", str(path)

            job = Job(Studio(), "x", [1])
            bases, previews = [], []
            job.base_thumb.connect(bases.append)
            job.preview.connect(previews.append)
            job._draw_one(1)
        self.assertEqual(len(bases), 1)
        self.assertEqual(bases[0].getpixel((0, 0)), (255, 0, 255))
        self.assertEqual(previews, [])   # 土台は preview には出ない

    def test_window_stashes_base_without_showing(self):
        win = SettingsAndDebugMixin.__new__(SettingsAndDebugMixin)
        img = Image.new("RGB", (2, 2), (255, 0, 255))
        win._stash_base(img)   # 重ね表示オフのときは、取っておくだけで何も出さない
        self.assertIs(win._base_thumb, img)


if __name__ == "__main__":
    unittest.main()
