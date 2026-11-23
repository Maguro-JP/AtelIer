"""加工が色の境界に頼んでいない線を引かないことの確かめ。

赤・青・白の面と細い線の絵に、模型を使わない加工を全部掛け（絵全体と囲みの中）、前と後の差から
「境界から 3 画素以内に出来た、幅 5 画素以下・長さ 10 画素以上の筋」を数える。面ごとに色が変わるだけの
加工（光、質感）は筋に数えない（11 画素の中央値の差を引く）。
前は、ディテール追加が境界の全部に暗い縁を付け（7 本）、光・質感の加工が線の周り 13 画素を元の色に戻して
白い縁・赤い縁を残し、清書が塗った絵の面を消して境界に線を引いた"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

SCIPY = importlib.util.find_spec("scipy") is not None
SKIMAGE = importlib.util.find_spec("skimage") is not None


def blocks() -> Image.Image:
    im = Image.new("RGB", (384, 384), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 180, 200), fill=(220, 30, 30))
    d.ellipse((200, 40, 360, 220), fill=(30, 60, 210))
    d.polygon([(40, 250), (180, 360), (20, 370)], fill=(30, 60, 210))
    d.rectangle((210, 250, 360, 360), fill=(220, 30, 30))
    for i in range(5):
        d.line((200, 240 + i * 25, 370, 230 + i * 30), fill=(20, 20, 20), width=2)
    d.arc((60, 60, 150, 160), 0, 300, fill=(20, 20, 20), width=3)
    return im


def region() -> Image.Image:
    m = Image.new("L", (384, 384), 0)
    ImageDraw.Draw(m).rectangle((100, 100, 300, 300), fill=255)
    return m


def boundary(a):
    import numpy as np
    q = a.astype(int)
    e = np.zeros(q.shape[:2], bool)
    e[:, 1:] |= np.abs(q[:, 1:] - q[:, :-1]).sum(2) > 60
    e[1:, :] |= np.abs(q[1:] - q[:-1]).sum(2) > 60
    return e


def streaks(src, out, zone=None) -> int:
    import numpy as np
    from scipy import ndimage as ndi
    a, b = np.asarray(src.convert("RGB")), np.asarray(out.convert("RGB"))
    if zone is None:
        zone = ndi.binary_dilation(boundary(a), iterations=3)
    d = b.astype(float) - a.astype(float)
    r = np.stack([np.abs(d[..., c] - ndi.median_filter(d[..., c], 11)) for c in range(3)], -1).max(-1)
    new = (r > 25) & zone & ~(a.max(2) < 80)
    lab, _ = ndi.label(new, structure=np.ones((3, 3)))
    n = 0
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        length = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)
        if length >= 10 and int((lab[sl] == i).sum()) / length <= 5:
            n += 1
    return n


@unittest.skipUnless(SCIPY, "scipy が無い")
class NoEdgeLinesTest(unittest.TestCase):
    def test_detail_adds_no_line_on_color_boundaries(self):
        from atelier.ai import finishers
        src = blocks()
        self.assertEqual(streaks(src, finishers.run("detail", src)), 0)
        self.assertEqual(streaks(src, finishers.run("detail", src, region())), 0)

    def test_air_and_material_leave_no_band_around_lines(self):
        """光・質感は面の色を変えるが、線の周りに元の色の帯（白い縁、赤い縁）を残さない"""
        import numpy as np
        from scipy import ndimage as ndi
        from atelier.ai import finishers
        src = blocks()
        a = np.asarray(src)
        line = finishers.structural_lines(a.astype(np.float32))
        band = ndi.binary_dilation(line, iterations=7) & ~ndi.binary_dilation(line, iterations=2) & ~(a.max(2) < 80)
        for name in ("air_haze", "mat_metal", "mat_gem", "mat_slime"):
            with self.subTest(name=name):
                out = finishers.run(name, src)
                self.assertEqual(streaks(src, out), 0, name)
                # 線の近くの帯で、加工の差が周りの差から外れていない（元の色のまま残っていない）
                d = np.asarray(out, float) - a
                r = np.stack([np.abs(d[..., c] - ndi.median_filter(d[..., c], 15)) for c in range(3)], -1).max(-1)
                self.assertLess(float(r[band].mean()), 6.0, name)

    def test_region_rim_has_no_line_and_outside_is_same(self):
        import numpy as np
        from scipy import ndimage as ndi
        from atelier.ai import finishers
        src, m = blocks(), region()
        mm = np.asarray(m) > 127
        rim = ndi.binary_dilation(mm, iterations=3) & ~ndi.binary_erosion(mm, iterations=3)
        for name in ("detail", "mat_metal", "air_holy", "mat_gem"):
            with self.subTest(name=name):
                out = finishers.run(name, src, m)
                self.assertEqual(streaks(src, out, rim), 0, name)
                diff = np.abs(np.asarray(out, int) - np.asarray(src, int)).max(2)
                self.assertEqual(int((diff[~mm] > 0).sum()), 0, name)   # 囲みの外は 1 画素も変えない

    @unittest.skipUnless(SKIMAGE, "scikit-image が無い")
    def test_ink_does_not_turn_painted_picture_into_boundary_lines(self):
        """清書を塗った絵に掛けると面が消え、境界に線が引かれた。塗った絵には掛けずに理由を返す。線の絵には掛ける"""
        from atelier.ai import finishers
        with self.assertRaises(finishers.Unavailable):
            finishers.run("ink", blocks())
        sk = Image.new("RGB", (160, 200), "white")
        ImageDraw.Draw(sk).ellipse((30, 20, 130, 180), outline=(30, 30, 30), width=3)
        self.assertTrue(finishers.is_line_sketch(sk))
        self.assertFalse(finishers.is_line_sketch(blocks()))
        out = finishers.run("ink", sk)
        self.assertEqual(out.size, sk.size)


if __name__ == "__main__":
    unittest.main()
