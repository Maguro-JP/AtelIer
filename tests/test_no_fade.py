"""見せ方にフェードを残さないための試験。

ユーザーの指示（2026-11-27）: 「フェードアウトとかやめて。機械が書いてるような感じじゃなく、
人が描いてるように魅せてよ」。0.1.26 で全体を薄く混ぜる出し方はやめたが、0.1.27 でも
「消すのがフェードアウトしてる」と再発した。残っていた経路は 3 つ:
- 仕上げの段が、残った差を出ている所からの距離で割り当て、画面全体に輪のように広がって
  変わる（画素は 1 段で切り替わっても、全体がじわっと出る・消える見え方になる）
- 筆先の印が線 1 本に 7 点しかなく、今伸びている所から遠くに跳んで出る
- タイムラプスの逆算（reconstruct）の仕上げが、平塗りから仕上がりへ Image.blend で混ぜる

基準: (1) 変わる画素は、そのとき筆先が通っている所の近くにだけある。
(2) どの画素も、前の値と後の値の中間の値を取らない（1 段で最終の値になる）。
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def cadence(plan):
    """再生（Player）が実際に刻む間隔（t の進み）"""
    from atelier.paint import brush_reveal as br
    return (br.Player.TICK_MS / 1000.0) / plan.seconds


def frames_between(plan, t0, t1):
    """[t0, t1] を再生の間隔で刻んだ (時刻, 絵) の列。最後は t1 ちょうど"""
    dt = cadence(plan)
    out = []
    t = t0
    while t < t1:
        out.append((t, np.asarray(plan.frame(t).convert("RGB"), np.int16)))
        t += dt
    out.append((t1, np.asarray(plan.frame(t1).convert("RGB"), np.int16)))
    return out


class NoFadeCase(unittest.TestCase):
    def assert_no_intermediate(self, plan, before, after):
        """(2) どの画素も中間の値を取らない"""
        b = np.asarray(before.convert("RGB"), np.int16)
        a = np.asarray(after.convert("RGB"), np.int16)
        for _t, f in frames_between(plan, 0.0, 1.0):
            ok = (f == b).all(axis=2) | (f == a).all(axis=2)
            self.assertTrue(bool(ok.all()),
                            f"中間の値を取った画素が {int((~ok).sum())} 個ある")

    def assert_tip_local(self, plan, t0=0.0, t1=1.0):
        """(1) 変わる画素は筆先の近くにだけある。筆先が無いのに変わることも無い。
        塊の境界をまたぐ数画素（前の塊の最後と次の塊の最初が同じ刻みに入る）は目に見えないので、
        画素数で重み付けた分布で見る: 半分（中央値）はごく近く、99% は近くの範囲に収まり、
        まとまって変わる区間（50 画素以上）では変わった所の真ん中も筆先の近くにあること"""
        diag = float(np.hypot(*plan.full))
        seq = frames_between(plan, t0, t1)
        dt = cadence(plan)
        excess = []
        for (ta, fa), (tb, fb) in zip(seq, seq[1:]):
            ch = (fa != fb).any(axis=2)
            if not ch.any():
                continue
            tip = plan.tip(min(ta + dt / 2, 0.999))
            self.assertIsNotNone(tip, f"t={ta:.3f} で筆先が無いのに {int(ch.sum())} 画素変わった")
            tx, ty, tr = tip
            ys, xs = np.nonzero(ch)
            excess.append(np.hypot(xs - tx, ys - ty) - tr)
            if len(ys) >= 50:
                cd = float(np.hypot(xs.mean() - tx, ys.mean() - ty)) - tr
                self.assertLessEqual(cd, 0.15 * diag,
                                     f"t={ta:.3f} で {len(ys)} 画素の真ん中が筆先から {cd:.0f}px 離れている")
        ex = np.concatenate(excess)
        self.assertLessEqual(float(np.median(ex)), 0.08 * diag,
                             f"変わった画素の半分が筆先から {float(np.median(ex)):.0f}px より遠い")
        self.assertLessEqual(float(np.percentile(ex, 99)), 0.30 * diag,
                             f"変わった画素の 1% 以上が筆先から {float(np.percentile(ex, 99)):.0f}px より遠い")


def drawn(size=200):
    """線・塗り・細かい点のある絵（描く側）"""
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, size - 20, size - 20), outline="black", width=5)
    d.line((30, 100, size - 30, 100), fill="black", width=2)
    d.rectangle((40, 40, 80, 80), fill=(220, 60, 60))
    d.rectangle((110, 110, 150, 150), fill=(60, 120, 220))
    for x, y in ((190, 10), (10, 190), (190, 190), (100, 100), (170, 60)):
        im.putpixel((x, y), (200, 200, 200))
    return im


def faint_marks(size=480, step=60):
    """縮めた絵では拾えない薄い点々だけの絵。差は全部「仕上げの段」行きになる"""
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    for y in range(step // 2, size, step):
        for x in range(step // 2, size, step):
            d.rectangle((x, y, x + 1, y + 1), fill=(232, 232, 232))
    return im


class DrawRevealNoFadeTest(NoFadeCase):
    def test_no_intermediate_values_when_drawing(self):
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (200, 200), "white")
        after = drawn()
        plan = br.Plan(before, after)
        plan.fill()
        self.assert_no_intermediate(plan, before, after)

    def test_no_intermediate_values_when_erasing(self):
        from atelier.paint import brush_reveal as br
        before = drawn()
        after = Image.new("RGB", (200, 200), "white")
        plan = br.Plan(before, after)
        plan.fill()
        self.assert_no_intermediate(plan, before, after)

    def test_changes_stay_at_the_tip_when_drawing(self):
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (200, 200), "white")
        plan = br.Plan(before, drawn())
        plan.fill()
        self.assert_tip_local(plan)

    def test_changes_stay_at_the_tip_when_erasing(self):
        from atelier.paint import brush_reveal as br
        after = Image.new("RGB", (200, 200), "white")
        plan = br.Plan(drawn(), after)
        plan.fill()
        self.assert_tip_local(plan)


class FinishStageNoFadeTest(NoFadeCase):
    """仕上げの段: 残った細かい差が画面全体に輪のように広がって出る・消えるのはフェードと同じ。
    塊ごとに、筆先の通る順に 1 か所ずつ変わること"""

    def test_finish_changes_stay_at_the_tip_when_drawing(self):
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (480, 480), "white")
        plan = br.Plan(before, faint_marks(), work_side=120)
        plan.fill()
        self.assert_tip_local(plan, br.SMALL_END, 1.0)

    def test_finish_changes_stay_at_the_tip_when_erasing(self):
        from atelier.paint import brush_reveal as br
        after = Image.new("RGB", (480, 480), "white")
        plan = br.Plan(faint_marks(), after, work_side=120)
        plan.fill()
        self.assert_tip_local(plan, br.SMALL_END, 1.0)

    def test_finish_has_no_intermediate_values(self):
        from atelier.paint import brush_reveal as br
        before = Image.new("RGB", (480, 480), "white")
        after = faint_marks()
        plan = br.Plan(before, after, work_side=120)
        plan.fill()
        self.assert_no_intermediate(plan, before, after)


class ReconstructNoFadeTest(unittest.TestCase):
    def test_finish_segment_is_not_a_blend(self):
        """逆算の仕上げは、平塗りから仕上がりへ薄く混ぜない。各画素は平塗りの値か
        仕上がりの値のどちらかだけを取り、少しずつ仕上がりの画素が増える"""
        from atelier.paint import timelapse
        im = Image.new("RGB", (120, 120), "white")
        d = ImageDraw.Draw(im)
        d.rectangle((20, 20, 100, 100), fill=(200, 80, 40))
        d.line((10, 110, 110, 10), fill="black", width=3)
        d.rectangle((45, 45, 75, 75), fill=(30, 30, 160))   # 平塗りでは消える細かい差
        frames = timelapse.reconstruct(im)
        self.assertEqual(len(frames), timelapse.RECON_LINE + timelapse.RECON_FLAT + timelapse.RECON_FINISH)
        flat = np.asarray(frames[timelapse.RECON_LINE + timelapse.RECON_FLAT - 1], np.int16)
        final = np.asarray(frames[-1], np.int16)
        seg = [np.asarray(f, np.int16) for f in frames[timelapse.RECON_LINE + timelapse.RECON_FLAT:]]
        for f in seg:
            ok = (f == flat).all(axis=2) | (f == final).all(axis=2)
            self.assertTrue(bool(ok.all()),
                            f"仕上げの途中で中間の値を取った画素が {int((~ok).sum())} 個ある")
        done = [(f == final).all(axis=2).sum() for f in seg]
        self.assertEqual(done[-1], final.shape[0] * final.shape[1])
        self.assertLess(done[0], done[-1])   # 最初の 1 枚で全部は出ない（少しずつ描く）


if __name__ == "__main__":
    unittest.main()
