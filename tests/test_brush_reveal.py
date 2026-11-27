"""筆で描き込む見せ方（brush_reveal）の試験。

ユーザーの指示：線画をなぞって描いている風に見せる。線の太さ・強弱を付け、はらいやブラシで描く。
前の作りは 1 回の移りが 2.4 秒で、線画の段は 0.72 秒しかなく、筆先も縁だけの薄い丸だったので、
線をなぞる様子が目に見えなかった。線の多い移りは線画の段だけで数秒かけ、筆先は線の色で塗った丸にする。
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def line_art(size=192) -> Image.Image:
    """白い紙に、太さの違う線を何本か描いた線画。外の輪郭は太く、内側は細い"""
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 172, 172), outline="black", width=5)   # 外の輪郭（太い）
    d.line((30, 100, 162, 100), fill="black", width=2)        # 内側の線（細い）
    d.line((96, 30, 96, 162), fill="black", width=2)
    d.arc((60, 60, 132, 132), 0, 180, fill="black", width=3)
    return im


class BrushRevealTest(unittest.TestCase):
    def test_line_phase_takes_seconds_not_a_flash(self):
        """線の多い移りは、線画の段だけで数秒かける（前は 2.4 秒の移りのうち 0.72 秒）"""
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (192, 192), "white")
        plan = br.Plan(before, line_art())
        plan.fill()
        # 線画の段が終わる時刻 × 移り全体の秒が、線をなぞるのに足る長さであること
        line_seconds = br.LINE_END * plan.seconds
        self.assertGreaterEqual(line_seconds, 4.0)

    def test_line_is_traced_gradually(self):
        """線画の段の途中では、線の一部だけが見えている（端から線に沿って伸びる）"""
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (192, 192), "white")
        after = line_art()
        plan = br.Plan(before, after)
        plan.fill()
        total_line = int(plan.line.sum())
        self.assertGreater(total_line, 100)
        mid = plan.frame(br.LINE_END / 2)
        shown = (np.asarray(mid.convert("L")) < 128).sum()
        self.assertGreater(shown, 0)
        self.assertLess(shown, total_line)

    def test_tip_is_a_filled_brush_sized_to_the_line(self):
        """筆先は線の色で塗った丸で、太さはその場の線の太さに合わせる（前は縁だけの薄い丸）"""
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (192, 192), "white")
        plan = br.Plan(before, line_art())
        plan.fill()
        tip = plan.tip(br.LINE_END / 2)
        self.assertIsNotNone(tip)
        x, y, r = tip
        self.assertGreater(r, 2.0)   # 画面で見える大きさ
        self.assertLess(r, 20.0)

    def test_fill_is_hatched_before_it_fills(self):
        """塗りの段は、はらい（斜めの線）を先に見せてから間を埋める"""
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (192, 192), "white")
        after = line_art().convert("RGB")
        # 色の面を足す（塗りの塊ができるように）
        d = ImageDraw.Draw(after)
        d.rectangle((40, 40, 80, 80), fill=(220, 60, 60))
        d.rectangle((110, 110, 150, 150), fill=(60, 120, 220))
        plan = br.Plan(before, after)
        plan.fill()
        # 塗りの段の初めは、はらいの線だけが見えている（面全体ではない）
        t0 = br.LINE_END + (br.BIG_END - br.LINE_END) * 0.15
        f = plan.frame(t0)
        a = np.asarray(after.convert("L"), np.float32)
        shown = np.asarray(f.convert("L"), np.float32)
        # 見えている塗りの画素は、後の段より少ない
        later = plan.frame(br.BIG_END)
        shown_later = (np.abs(np.asarray(later.convert("L"), np.float32) - 255) > 10).sum()
        shown_now = (np.abs(shown - 255) > 10).sum()
        self.assertGreater(shown_now, 0)
        self.assertLess(shown_now, shown_later)



    def test_specks_are_not_traced_as_lines(self):
        """小さな点々は線としてなぞらない。筆で 1 点ずつ描くと、筆と関係ない所に
        点々が出現して見える。点は線の段から外し、塗りの段で一緒に出す"""
        from atelier.paint import brush_reveal as br
        from scipy import ndimage
        im = Image.new("RGB", (192, 192), "white")
        d = ImageDraw.Draw(im)
        d.line((20, 96, 172, 96), fill="black", width=3)   # 本物の線
        for x, y in ((30, 30), (160, 40), (90, 160), (50, 170)):   # 離れた点々
            d.rectangle([x, y, x + 1, y + 1], fill="black")
        plan = br.Plan(Image.new("RGB", (192, 192), "white"), im)
        lab, n = ndimage.label(plan.line)
        sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1)) if n else []
        self.assertTrue(all(s >= br.MIN_LINE_PX for s in sizes), sizes)
        for x, y in ((30, 30), (160, 40), (90, 160), (50, 170)):
            self.assertFalse(bool(plan.line[y, x]), f"点 ({x},{y}) が線として残っている")

    def test_brush_moves_to_the_nearest_line(self):
        """線の順は、前の線の終わりから一番近い線へ。画面の上から順に飛ぶと、
        筆が関係ない所へ跳んで、線があちこちに出現して見える"""
        from atelier.paint import brush_reveal as br
        im = Image.new("RGB", (192, 192), "white")
        d = ImageDraw.Draw(im)
        d.line((10, 10, 40, 10), fill="black", width=3)      # A: 左上（最初）
        d.line((10, 60, 60, 60), fill="black", width=3)      # B: A の近く（下）
        d.line((165, 50, 185, 50), fill="black", width=3)    # C: B より上だが、ずっと右（遠い）
        plan = br.Plan(Image.new("RGB", (192, 192), "white"), im)

        def first_tip(x0, y0, x1, y1):
            ts = [t for t, x, y in plan.tips if x0 <= x <= x1 and y0 <= y <= y1]
            return min(ts) if ts else None
        tb = first_tip(5, 55, 65, 65)
        tc = first_tip(160, 45, 190, 55)
        self.assertIsNotNone(tb)
        self.assertIsNotNone(tc)
        self.assertLess(tb, tc, "近い線（B）より先に遠い線（C）を描いている")



    def test_branches_are_drawn_one_at_a_time(self):
        """枝分かれした線は、枝ごとに順に描く。距離の順だと、種から同じ距離の枝が
        同時に伸びて、複数本を同時に描くことになる（ペンではありえない）"""
        from atelier.paint import brush_reveal as br
        im = Image.new("RGB", (192, 192), "white")
        d = ImageDraw.Draw(im)
        d.line((96, 30, 96, 90), fill="black", width=3)    # 縦
        d.line((66, 60, 126, 60), fill="black", width=3)   # 横（真ん中で交わる）
        plan = br.Plan(Image.new("RGB", (192, 192), "white"), im)
        ends = [plan.t[90, 96], plan.t[60, 66], plan.t[60, 126]]   # 3 つの腕の先
        self.assertGreater(max(ends) - min(ends), br.LINE_END * 0.25,
                           f"腕の先がほぼ同時に描かれている: {ends}")


class MidDrawBrushTest(unittest.TestCase):
    def test_mid_preview_moves_the_brush(self):
        """描いている途中の絵も筆で見せる。裏で描いていても、画面上は今筆が動いている。
        前は途中の絵を重ね絵に直接置くだけで、筆は動かなかった"""
        from tempfile import TemporaryDirectory

        from tests.test_uifix import app, spin
        from tests.test_works import window
        with TemporaryDirectory() as d:
            w = window(d)
            w.thread = object()   # 描いている最中にする（無ければ途中の絵は捨てられる）
            try:
                w.show_preview(line_art())
                player = getattr(w, "_phase_player", None)
                self.assertIsNotNone(player)   # 途中の絵でも筆の再生を使う
                self.assertTrue(player.active())
                # 移りは短く（次の途中の絵が来る前に筆を動かし終える）
                import time
                for _ in range(100):
                    app().processEvents()
                    if player.plan is not None:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(player.plan)
                self.assertLessEqual(player.seconds, player.MID_SECONDS)
            finally:
                w.hide()
                w.deleteLater()
                spin()


if __name__ == "__main__":
    unittest.main()

class FinishStageTest(unittest.TestCase):
    """仕上げの段は、残った細かい差を全体に薄く混ぜて出さない。混ぜると、筆と
    関係ない所に線でも何でもない物が薄く出現する（利用者の指摘）。出ている所から
    近い順に描き、仕上げの間も筆先は消さない"""

    def _plan(self):
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (200, 200), "white")
        after = before.copy()
        d = ImageDraw.Draw(after)
        d.line((20, 20, 20, 180), fill="black", width=5)     # 先の段で描かれる線
        after.putpixel((190, 100), (225, 225, 225))          # 縮めた絵では拾えない細かい差（仕上げ行き）
        plan = br.Plan(before, after, work_side=100)
        plan.fill()
        return br, plan

    def test_finish_is_not_a_global_crossfade(self):
        br, plan = self._plan()
        mid = plan.frame(0.92)
        # 仕上げの途中では、その画素はまだ出ていない。混ぜて出すと 240 のような中間の色になる
        self.assertEqual(mid.getpixel((190, 100)), (255, 255, 255))
        self.assertEqual(plan.frame(1.0).getpixel((190, 100)), (225, 225, 225))

    def test_tip_stays_during_finish(self):
        br, plan = self._plan()
        self.assertIsNotNone(plan.tip(0.95))
