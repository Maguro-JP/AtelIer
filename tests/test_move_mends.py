"""アタリのずれは描き直さずに絵を動かして直し、消すときは消しゴムで線をなぞって消す（利用者の決まり）"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw  # noqa: E402
import numpy as np  # noqa: E402

from atelier.ai import phase_tools as pt  # noqa: E402


def _app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication(sys.argv)


class StrokeEraserTest(unittest.TestCase):
    def setUp(self):
        _app()

    def _picture(self):
        im = Image.new("RGB", (64, 96), "white")
        d = ImageDraw.Draw(im)
        d.line([(32, 10), (32, 85)], fill=0, width=3)   # 残す線
        d.line([(10, 40), (20, 50)], fill=0, width=2)   # 消す線
        mk = Image.new("L", (64, 96), 0)
        ImageDraw.Draw(mk).rectangle([5, 35, 25, 55], fill=255)
        return im, mk

    def test_eraser_tool_is_used_along_the_line(self):
        """アプリの消しゴム（brush.stamp の erase）が、線に沿ったストロークで呼ばれている"""
        from atelier.paint import brush
        im, mk = self._picture()
        calls = []
        real = brush.stamp

        def spy(*a, **k):
            calls.append(k.get("erase"))
            return real(*a, **k)
        with mock.patch.object(brush, "stamp", spy):
            out, strokes, px = pt.stroke_erase(im, mk)
        self.assertEqual(strokes, 1)
        self.assertTrue(calls and all(calls), "消しゴムの道具が使われていない")
        self.assertGreater(px, 0)

    def test_eraser_removes_only_the_line_and_nothing_outside(self):
        """消しゴムは効いて線が消え、囲みの外も、線から離れた紙も 1 画素も変わらない（面で塗りつぶさない）"""
        im, mk = self._picture()
        out, _s, px = pt.stroke_erase(im, mk)
        a, b = np.asarray(im), np.asarray(out)
        changed = (a != b).any(2)
        inside = np.asarray(mk) > 0
        self.assertEqual(int((changed & ~inside).sum()), 0)
        self.assertEqual(int((np.asarray(out.convert("L"))[35:56, 5:26] < 100).sum()), 0, "線が消えていない")
        self.assertLess(int(changed.sum()), int(inside.sum()) // 4, "囲みを丸ごと塗りつぶしている")
        self.assertLess(np.asarray(out.convert("L"))[50, 32], 100, "残す線まで消えた")


class MoveMendsTest(unittest.TestCase):
    def test_lean_rotates_the_body_over_the_feet(self):
        im = Image.new("RGB", (64, 96), "white")
        ImageDraw.Draw(im).polygon([(28, 90), (36, 90), (50, 20), (42, 20)], fill=0)
        before = pt.balance(im)["balance"]
        out, angle = pt.lean_fix(im)
        self.assertNotEqual(angle, 0.0)
        self.assertLess(pt.balance(out)["balance"], before / 3)

    def test_recenter_moves_the_picture(self):
        im = Image.new("RGB", (64, 96), "white")
        ImageDraw.Draw(im).rectangle([2, 10, 20, 90], fill=0)
        out, dx = pt.recenter(im)
        self.assertGreater(dx, 0)
        self.assertLess(pt.thumb_weight(out)["weight_x"], pt.WEIGHT_MOST)

    def test_reattach_cuts_and_pastes_the_detached_part(self):
        im = Image.new("RGB", (64, 96), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([28, 10, 36, 90], fill=0)
        d.rectangle([42, 40, 48, 50], fill=0)
        self.assertEqual(pt.detached(im)["count"], 1)
        out, n = pt.reattach(im)
        self.assertEqual(n, 1)
        self.assertEqual(pt.detached(out)["count"], 0)
        dark = (np.asarray(out.convert("L")) < 100).sum()
        self.assertEqual(int(dark), int((np.asarray(im.convert("L")) < 100).sum()), "切り貼りで線の量が変わった（描き直していない）")


if __name__ == "__main__":
    unittest.main()
