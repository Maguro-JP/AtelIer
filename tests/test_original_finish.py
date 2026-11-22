"""このリポジトリで作ってきた仕上げ（tools/gen の retouch・inking・atmosphere・materials）と、
キャラクターデザインの流れ（設定資料集・三面図・表情差分）を、アプリから使えるか。絵の模型は偽物に替えて流れだけを確かめる"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ATELIER_CHECK", "off")
sys.path.insert(0, str(ROOT / ".cache" / "simple" / "lib"))
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageChops, ImageDraw  # noqa: E402

from atelier.ai import finishers
from atelier.ai import omakase  # noqa: E402

SCIPY = importlib.util.find_spec("scipy") is not None
SKIMAGE = importlib.util.find_spec("skimage") is not None


def figure(size=(160, 200), specks=True) -> Image.Image:
    """白い地に主線の人型と、線から離れた黒い粒（AI の描き残しに当たる崩れ）"""
    im = Image.new("RGB", size, (250, 248, 245))
    d = ImageDraw.Draw(im)
    d.ellipse((50, 20, 110, 80), fill=(240, 205, 180), outline=(20, 20, 20), width=3)
    d.rectangle((45, 85, 115, 180), fill=(90, 120, 200), outline=(20, 20, 20), width=3)
    if specks:
        for x, y in ((15, 20), (140, 30), (20, 150), (140, 170), (12, 100)):
            d.ellipse((x, y, x + 3, y + 3), fill=(10, 10, 10))
    return im


def box_mask(size, box) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    return m


def outside_same(a, b, mask) -> bool:
    keep = Image.new("RGB", a.size)
    inv = mask.point(lambda v: 0 if v >= 128 else 255)
    return ImageChops.difference(Image.composite(a, keep, inv), Image.composite(b, keep, inv)).getbbox() is None


class OwnFinishers(unittest.TestCase):
    def test_registered_with_tooltips(self):
        names = {f["name"] for f in finishers.available()}
        for n in ("retouch", "retouch_full", "ink", "air_holy", "air_komorebi", "air_haze", "mat_metal", "mat_gem", "mat_slime"):
            self.assertIn(n, names)
            f = finishers.REGISTRY[n]
            self.assertTrue(f.tip and f.label)
            self.assertNotIn(f.tip, f.label)   # 説明はボタンの中に書かず、ツールチップに出す

    def test_auto_finish_only_shape_keeping(self):
        self.assertNotIn("retouch", omakase.AUTO_FINISH)   # 自動の仕上げは掛けない（omakase.AUTO_FINISH の注）。retouch は手動の加工から
        for n in ("retouch_full", "ink", "air_holy", "mat_metal"):   # 形や見た目を変えうる物はおまかせで掛けない
            self.assertNotIn(n, omakase.AUTO_FINISH)
        self.assertEqual(omakase.auto_finish([dict(name="retouch", ready=True), dict(name="ink", ready=True)]), [])   # 自動では何も掛けない
        self.assertNotIn("deburr", finishers.RETOUCH_SAFE)   # 顔の細い線に掛かりうる工程はおまかせに入れない
        for n in ("heal", "sharpen"):   # ボタンを消し、髪の筋に継ぎ目を作ったので既定から外した
            self.assertNotIn(n, finishers.RETOUCH_SAFE)

    @unittest.skipUnless(SCIPY, "scipy が無い")
    def test_repair_returns_only_new_flaw_pixels(self):
        import numpy as np
        a = np.asarray(figure(specks=False)).astype(float)
        b = a.copy()
        b[150:153, 10:13] = 5      # 直しで出来た黒い粒（崩れ）
        b[100:110, 60:70] += 3     # 直しで良くした所（崩れではない）
        out = finishers.repair(a, b)
        self.assertTrue((out[150:153, 10:13] == a[150:153, 10:13]).all())   # 崩れの所だけ元に戻す
        self.assertTrue((out[100:110, 60:70] == b[100:110, 60:70]).all())   # ほかの直しは残す
        self.assertLessEqual(finishers.flaws(out), finishers.flaws(a))

    def test_missing_script_reports_reason(self):
        with TemporaryDirectory() as d, mock.patch.object(finishers, "_gen_dir", lambda: Path(d)):
            row = next(f for f in finishers.available() if f["name"] == "retouch")
            self.assertFalse(row["ready"])
            self.assertIn("retouch.py", row["reason"])
            with self.assertRaises(finishers.Unavailable):
                finishers.run("retouch", figure())

    @unittest.skipUnless(SCIPY, "scipy が無い")
    def test_retouch_removes_specks_without_new_flaws(self):
        im = figure()
        a = __import__("numpy").asarray(im).astype(float)
        out = finishers.run("retouch", im)
        b = __import__("numpy").asarray(out).astype(float)
        self.assertEqual(out.size, im.size)
        self.assertLessEqual(finishers.flaws(b), finishers.flaws(a))
        rt = finishers._gen("retouch")
        self.assertLessEqual(rt.specks(b), rt.specks(a))   # 粒は増やさない（粒消しはボタンを消したので既定から外した）
        self.assertEqual(rt.line_broken(a, b), "")     # 主線は切れていない
        self.assertTrue(finishers.LAST_REPORT["steps"])

    @unittest.skipUnless(SCIPY, "scipy が無い")
    def test_mask_keeps_outside_for_every_own_tool(self):
        im = figure()
        mask = box_mask(im.size, (40, 15, 120, 90))
        names = ["retouch", "air_holy", "air_haze", "mat_metal", "mat_gem"] + (["retouch_full", "ink"] if SKIMAGE else [])
        for n in names:
            out = finishers.run(n, im, mask)
            self.assertEqual(out.size, im.size, n)
            self.assertTrue(outside_same(im, out, mask), n)   # 囲みの外は 1 画素も変えない

    def test_atmosphere_changes_look(self):
        im = figure(specks=False)
        out = finishers.run("air_holy", im)
        self.assertIsNotNone(ImageChops.difference(im, out).getbbox())


if __name__ == "__main__":
    unittest.main()
