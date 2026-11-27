"""描くための道具（draw_tools）の試験: ブラシ・色・柄・図形が、言われた通りに描くか"""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from atelier.ai import draw_tools as dt


def blank(w=120, h=90):
    return Image.new("RGB", (w, h), (255, 255, 255))


def full_mask(w=120, h=90):
    return Image.new("L", (w, h), 255)


class BrushTest(unittest.TestCase):
    def test_pen_stroke_paints_along_the_path(self):
        out = dt.stroke(blank(), [(10, 45), (110, 45)], color=(0, 0, 0), width=3, kind="pen")
        a = np.asarray(out)
        self.assertLess(int(a[45, 60].sum()), 100)      # 線の上は黒い
        self.assertEqual(int(a[10, 60].sum()), 765)     # 離れた所は白いまま

    def test_gpen_tapers_at_the_ends(self):
        out = dt.stroke(blank(), [(10, 45), (110, 45)], color=(0, 0, 0), width=9, kind="gpen")
        a = np.asarray(out.convert("L"))
        middle = int((a[40:51, 60] < 128).sum())
        end = int((a[40:51, 12] < 128).sum())
        self.assertGreater(middle, end)                 # 入りは細く、真ん中は太い

    def test_pencil_is_lighter_than_pen(self):
        pen = dt.stroke(blank(), [(10, 45), (110, 45)], color=(0, 0, 0), width=5, kind="pen")
        pen_sum = int(np.asarray(pen.convert("L"))[45, 60])
        pencil = dt.stroke(blank(), [(10, 45), (110, 45)], color=(0, 0, 0), width=5, kind="pencil", seed=3)
        pencil_sum = int(np.asarray(pencil.convert("L"))[45, 60])
        self.assertGreater(pencil_sum, pen_sum)         # 鉛筆の方が薄い

    def test_unknown_brush_is_refused(self):
        with self.assertRaises(ValueError):
            dt.stroke(blank(), [(0, 0), (10, 10)], kind="airbrush")


class ShapeTest(unittest.TestCase):
    def test_line_and_circle(self):
        out = dt.draw_line(blank(), (5, 5), (115, 5), color=(0, 0, 0), width=3)
        self.assertLess(int(np.asarray(out)[5, 60].sum()), 100)
        out = dt.draw_circle(blank(), (60, 45), 20, color=(0, 0, 0), width=3)
        a = np.asarray(out)
        self.assertLess(int(a[45, 80].sum()), 300)      # 円周の上
        self.assertEqual(int(a[45, 60].sum()), 765)     # 中は白いまま（fill 無し）

    def test_curve_passes_near_the_points(self):
        out = dt.draw_curve(blank(), [(10, 80), (60, 10), (110, 80)], color=(0, 0, 0), width=3)
        a = np.asarray(out.convert("L"))
        self.assertLess(int(a[10, 60]), 128)            # 山の頂点を通る


class ColorTest(unittest.TestCase):
    def test_fill_and_gradient_and_tint(self):
        mask = full_mask()
        out = dt.fill_region(blank(), mask, (200, 30, 30))
        self.assertEqual(tuple(np.asarray(out)[45, 60]), (200, 30, 30))
        out = dt.gradient_fill(blank(), mask, (0, 0, 0), (255, 255, 255))
        a = np.asarray(out)
        self.assertLess(int(a[5, 60][0]), int(a[85, 60][0]))   # 上が暗く下が明るい
        img = blank()
        dr = ImageDraw.Draw(img)
        dr.rectangle([0, 0, 119, 89], fill=(120, 120, 120))
        out = dt.tint(img, mask, (200, 80, 80), strength=1.0)
        px = np.asarray(out)[45, 60]
        self.assertGreater(int(px[0]), int(px[1]))      # 赤へ寄る
        self.assertAlmostEqual(int(px[0]), 200, delta=30)   # 明るさの比で色が決まる


class PatternTest(unittest.TestCase):
    def test_dots_and_check(self):
        out = dt.pattern_fill(blank(), full_mask(), kind="dots", fg=(0, 0, 0), bg=(255, 255, 255), scale=10)
        a = np.asarray(out.convert("L"))
        self.assertLess(int(a[5, 5]), 128)              # 点の中心
        self.assertGreater(int(a[5, 10]), 128)          # 点と点の間は地
        out = dt.pattern_fill(blank(), full_mask(), kind="check", fg=(0, 0, 0), bg=(255, 255, 255), scale=10)
        a = np.asarray(out.convert("L"))
        self.assertLess(int(a[5, 5]), 128)
        self.assertGreater(int(a[5, 15]), 128)          # 隣のマスは地

    def test_halftone_dots_follow_darkness(self):
        img = blank()
        dr = ImageDraw.Draw(img)
        dr.rectangle([0, 0, 59, 89], fill=(30, 30, 30))       # 左は暗い
        dr.rectangle([60, 0, 119, 89], fill=(230, 230, 230))  # 右は明るい
        out = dt.pattern_fill(img, full_mask(), kind="halftone", fg=(0, 0, 0), scale=10)
        a = np.asarray(out.convert("L"))
        dark_side = int((a[:, :60] < 128).sum())
        light_side = int((a[:, 60:] < 128).sum())
        self.assertGreater(dark_side, light_side * 3)   # 暗い側ほど点が大きい

    def test_pattern_stays_inside_the_mask(self):
        mask = Image.new("L", (120, 90), 0)
        ImageDraw.Draw(mask).rectangle([40, 30, 79, 59], fill=255)
        out = dt.pattern_fill(blank(), mask, kind="dots", fg=(0, 0, 0), bg=(255, 0, 0), scale=8)
        a = np.asarray(out)
        self.assertEqual(tuple(a[5, 5]), (255, 255, 255))     # 囲みの外は元のまま
        self.assertEqual(tuple(a[47, 62]), (255, 0, 0))       # 囲みの中、点の無い所は地の色


class RegistryTest(unittest.TestCase):
    def test_tool_list_and_apply(self):
        names = [n for n, _d in dt.tool_list()]
        for want in ("stroke", "draw_line", "draw_curve", "draw_circle",
                     "fill_region", "gradient_fill", "tint", "pattern_fill"):
            self.assertIn(want, names)
        out = dt.apply("fill_region", blank(), mask=full_mask(), color=(1, 2, 3))
        self.assertEqual(tuple(np.asarray(out)[0, 0]), (1, 2, 3))
        with self.assertRaises(ValueError):
            dt.apply("laser", blank())


if __name__ == "__main__":
    unittest.main()
