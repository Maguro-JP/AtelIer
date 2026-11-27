"""素材（ブラシの穂先・柄）の試験。画像から柄と穂先が作れること、素材ファイルの読み書き"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atelier.paint import materials as mt   # noqa: E402


def _gradient(w=64, h=64):
    """左が暗く右が明るい画像。端同士の差が大きいので、タイル化の効果が見える"""
    a = np.tile(np.linspace(40, 220, w, dtype=np.uint8), (h, 1))
    return Image.fromarray(np.stack([a, a, a], axis=2))


def _seam_jump(image):
    """2 枚横に並べたときの、継ぎ目の列同士の差の平均"""
    tiled = Image.new("RGB", (image.width * 2, image.height))
    tiled.paste(image, (0, 0))
    tiled.paste(image, (image.width, 0))
    a = np.asarray(tiled.convert("L")).astype(np.int16)
    w = image.width
    return float(np.abs(a[:, w - 1] - a[:, w]).mean())


class TileableTest(unittest.TestCase):
    def test_seam_mostly_disappears(self):
        src = _gradient()
        out = mt.make_tileable(src)
        self.assertEqual(out.size, src.size)
        self.assertLess(_seam_jump(out), _seam_jump(src) * 0.25)

    def test_pattern_from_image_tiles(self):
        photo = _gradient(120, 80)
        tile = mt.pattern_from_image(photo, size=64)
        self.assertEqual(tile.size, (64, 64))
        self.assertLess(_seam_jump(tile), 24.0)


class TipTest(unittest.TestCase):
    def test_dark_shape_becomes_the_tip(self):
        img = Image.new("RGB", (64, 64), "white")
        ImageDraw.Draw(img).ellipse([20, 20, 44, 44], fill="black")
        tip = mt.tip_from_image(img, size=64)
        a = np.asarray(tip)
        self.assertGreater(int(a[32, 32]), 200)   # 形の中心は濃い
        self.assertLess(int(a[2, 2]), 30)         # 背景は透明（薄い）


class MaterialFileTest(unittest.TestCase):
    def test_roundtrip(self):
        tip = mt.tip_from_image(_gradient())
        pat = mt.pattern_from_image(_gradient())
        with TemporaryDirectory() as d:
            p = mt.save_material(Path(d) / "my-brush", kind="brush", name="私の筆",
                                 params={"hardness": 0.5, "flow": 0.8}, tip=tip, pattern=pat)
            self.assertTrue(p.name.endswith(mt.MATERIAL_SUFFIX))
            got = mt.load_material(p)
            self.assertEqual(got["kind"], "brush")
            self.assertEqual(got["name"], "私の筆")
            self.assertEqual(got["params"]["hardness"], 0.5)
            self.assertIsNotNone(got["tip"])
            self.assertIsNotNone(got["pattern"])
            self.assertIsNone(got["grain"])
            listed = mt.list_materials(d)
            self.assertEqual([m["name"] for m in listed], ["私の筆"])


if __name__ == "__main__":
    unittest.main()
