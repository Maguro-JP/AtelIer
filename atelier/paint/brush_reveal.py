"""AI の絵を、人が描くように筆で描き込んで見せる。

AI の絵がいきなりキャンバスに出ると、描いた過程が何も見えなかった。そこで前の絵（無ければ白）から次の絵へ移るとき、
差のある所だけを 線画 → 大きな塗り → 細かい塗り → 仕上げ の順に、筆の運びで少しずつ描き込む。
- 線画: timelapse.reconstruct と同じ「周りより暗い所」を線とし、つながった線ごとに端から線に沿って伸ばす
- 塗り: 色を均した平塗りの塊（同じ色でつながった所）ごとに、真ん中から塗り広げる。大きな塊を先、細かい塊を後にする
- 仕上げ: 平塗りから AI の絵へ移す。最後の 1 枚は AI の絵そのもの
囲みのある直しは、置く前と置いた後の差が囲みの中にしか無いので、筆も囲みの中だけを動く。

見せるのはキャンバスの上の重ね絵（overlay）と筆先の丸だけで、レイヤーの画素には触らない。絵は先にレイヤーへ置き、
見せ終えたら重ね絵を外すので、見せ終えたキャンバスは AI の絵と 1 画素も違わない。
筆の運びの計算は裏の糸で行い（描く処理も画面も待たせない）、再生は画面の糸のタイマーで追いかける。
"""
from __future__ import annotations

import threading
from collections import deque

import numpy as np
from PIL import Image, ImageChops, ImageFilter

WORK_SIDE = 512          # 筆の運びを計算する大きさ（長い辺）。見せるだけなので縮めて速くする
DIFF_MIN = 10            # これより小さい色の差は「変わっていない」とする（縮めたときの揺れ）
LINE_END, BIG_END, SMALL_END = 0.30, 0.62, 0.84   # 各段が終わる時刻（0〜1）。残りが仕上げ
BIG_AREA = 0.004         # 絵の面積に対するこの割合より大きい塊を「大きな塗り」にする


def _dist_from_seeds(mask: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """mask の中で seeds から何歩で届くか（つながった所に沿った距離）。届かない所は -1"""
    from scipy import ndimage
    dist = np.full(mask.shape, -1, np.int32)
    front = seeds & mask
    dist[front] = 0
    seen = front.copy()
    k = 0
    st = ndimage.generate_binary_structure(2, 2)
    while front.any() and k < 4000:
        k += 1
        grown = ndimage.binary_dilation(front, st) & mask & ~seen
        dist[grown] = k
        seen |= grown
        front = grown
    return dist


class Plan:
    """前の絵から次の絵への筆の運び。frame(t) で途中の絵、tip(t) で筆先の位置を返す"""

    def __init__(self, before: Image.Image | None, after: Image.Image, work_side: int = WORK_SIDE):
        from scipy import ndimage
        a = after.convert("RGB")
        self.full = a.size
        s = min(1.0, work_side / max(a.size))
        self.scale = s
        w, h = max(1, round(a.width * s)), max(1, round(a.height * s))
        a = a.resize((w, h), Image.LANCZOS) if s < 1 else a
        b = Image.new("RGB", (w, h), "white") if before is None else before.convert("RGB").resize((w, h), Image.LANCZOS)
        self.size = (w, h)
        self.A = np.asarray(a, np.float32)
        self.B = np.asarray(b, np.float32)
        diff = np.abs(self.A - self.B).max(axis=2) > DIFF_MIN
        diff = ndimage.binary_closing(diff, iterations=1) | diff
        self.diff = diff
        gray = a.convert("L")
        dark = np.asarray(ImageChops.subtract(gray.filter(ImageFilter.MaxFilter(5)), gray)) > 28   # reconstruct と同じ線の取り方
        line = dark & diff
        fill = diff & ~line
        flat = np.asarray(a.filter(ImageFilter.ModeFilter(7)).filter(ImageFilter.MedianFilter(5)), np.float32)
        self.F = flat
        t = np.full((h, w), np.inf, np.float32)
        tips: list[tuple[float, float, float]] = []   # (時刻, x, y)
        # 線画: つながった線ごと、上の線から順に。1 本の中は一番上の端から線に沿って伸ばす
        lab, n = ndimage.label(line, ndimage.generate_binary_structure(2, 2))
        if n:
            objs = ndimage.find_objects(lab)
            order = sorted(range(n), key=lambda i: (objs[i][0].start, objs[i][1].start))
            sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
            total = float(sizes.sum()) or 1.0
            seeds = np.zeros_like(line)
            for i in range(n):
                ys, xs = objs[i]
                sub = lab[ys, xs] == i + 1
                yy, xx = np.argwhere(sub)[0]
                seeds[ys.start + yy, xs.start + xx] = True
            dist = _dist_from_seeds(line, seeds)
            at = 0.0
            for i in order:
                span = LINE_END * float(sizes[i]) / total
                m = lab == i + 1
                d = dist[m].astype(np.float32)
                d = d / max(1.0, d.max())
                t[m] = at + span * d
                tips.extend(self._tips(m, dist, at, span))
                at += span
        # 塗り: 平塗りの色で塊に分ける（色を 32 段に丸めてつながった所）
        q = (flat // 32).astype(np.int32)
        key = q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]
        blobs = np.zeros((h, w), np.int32)
        nb = 0
        for v in np.unique(key[fill]):
            lb, k = ndimage.label(fill & (key == v))
            blobs[lb > 0] = lb[lb > 0] + nb
            nb += k
        if nb:
            area = ndimage.sum(np.ones_like(blobs), blobs, index=np.arange(1, nb + 1))
            cy = ndimage.mean(np.indices((h, w))[0], blobs, index=np.arange(1, nb + 1))
            cx = ndimage.mean(np.indices((h, w))[1], blobs, index=np.arange(1, nb + 1))
            big_px = BIG_AREA * w * h
            seeds = np.zeros((h, w), bool)
            for i in range(nb):   # 塊の真ん中に一番近い、塊の中の点から塗り広げる
                m = blobs == i + 1
                ys, xs = np.nonzero(m)
                j = int(np.argmin((ys - cy[i]) ** 2 + (xs - cx[i]) ** 2))
                seeds[ys[j], xs[j]] = True
            dist = _dist_from_seeds(blobs > 0, seeds)
            for lo, hi, pick in ((LINE_END, BIG_END, area >= big_px), (BIG_END, SMALL_END, area < big_px)):
                ids = [i for i in np.argsort(-area) if pick[i]]
                tot = float(sum(area[i] for i in ids)) or 1.0
                at = lo
                for i in ids:
                    span = (hi - lo) * float(area[i]) / tot
                    m = blobs == i + 1
                    d = dist[m].astype(np.float32)
                    d = d / max(1.0, d.max())
                    t[m] = at + span * d
                    tips.extend(self._tips(m, dist, at, span))
                    at += span
        t[diff & ~np.isfinite(t)] = SMALL_END
        self.t = t
        self.line = line
        tips.sort()
        self.tips = tips

    @staticmethod
    def _tips(m: np.ndarray, dist: np.ndarray, at: float, span: float, steps: int = 6):
        """塊の中を筆先が通る点（距離の段ごとの真ん中）"""
        d = dist[m]
        ys, xs = np.nonzero(m)
        top = max(1, int(d.max()))
        out = []
        for k in range(steps + 1):
            sel = np.abs(d - top * k / steps) <= max(1, top / steps / 2)
            if sel.any():
                out.append((at + span * k / steps, float(xs[sel].mean()), float(ys[sel].mean())))
        return out

    def empty(self) -> bool:
        return not self.diff.any()

    def frame(self, t: float) -> Image.Image:
        """時刻 t（0〜1）の途中の絵（計算した大きさ）。t>=1 は次の絵そのもの"""
        if t >= 1.0:
            return Image.fromarray(self.A.astype(np.uint8))
        shown = (self.t <= t)[..., None]
        out = np.where(shown, self.F, self.B)
        out = np.where((self.line & (self.t <= t))[..., None], self.A, out)   # 線は描いたらそのまま
        if t > SMALL_END:   # 仕上げ: 平塗りから仕上がりの色へ
            k = (t - SMALL_END) / (1.0 - SMALL_END)
            out = np.where(self.diff[..., None], out * (1 - k) + self.A * k, out)
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    def tip(self, t: float):
        """時刻 t の筆先の位置（元の絵の大きさの座標）。動いていないときは None"""
        if not self.tips or t >= SMALL_END + 0.01:
            return None
        i = min(range(len(self.tips)), key=lambda j: abs(self.tips[j][0] - t))
        _, x, y = self.tips[i]
        return x / self.scale, y / self.scale


def strokes(before: Image.Image | None, after: Image.Image, n: int = 18) -> list[Image.Image]:
    """タイムラプスに残す筆の運び（n 枚、最後の 1 枚は次の絵そのもの）"""
    plan = Plan(before, after, work_side=640)
    if plan.empty():
        return [after.convert("RGB")]
    return [plan.frame(i / n) for i in range(1, n)] + [after.convert("RGB")]


class Player:
    """キャンバスの上で筆の運びを再生する。canvas は atelier/paint/canvas.py の Canvas。
    show(before, after, keep) を呼ぶたびに、見せている途中の物は最後まで飛ばして次へ進む（遅れて溜めない）。
    keep=False は絵を先にレイヤーへ置いた場合で、見せ終えたら重ね絵を外す。True は途中の絵で、最後に重ね絵として残す"""

    SECONDS = 2.4   # 1 回の移りにかける秒（私の推測。描く処理を待たせないので短めにする）
    TICK_MS = 33

    def __init__(self, canvas):
        from PySide6.QtCore import QObject, QTimer
        self.canvas = canvas
        self.timer = QTimer()
        self.timer.setInterval(self.TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.queue: deque = deque(maxlen=1)   # 裏の糸で計算し終えた運び（新しい物だけを残す）
        self.plan: Plan | None = None
        self.keep = False
        self.final = None
        self.t = 0.0
        self.token = 0
        self.tip_item = None

        class _Touch(QObject):   # 見せている途中にキャンバスを触ったら、すぐ最後の絵にする（邪魔しない）
            def eventFilter(s, obj, e):
                from PySide6.QtCore import QEvent
                if self.active() and e.type() in (QEvent.MouseButtonPress, QEvent.TabletPress, QEvent.Wheel, QEvent.KeyPress):
                    self.finish()
                return False
        self._touch = _Touch()
        canvas.installEventFilter(self._touch)
        canvas.viewport().installEventFilter(self._touch)

    def active(self) -> bool:
        return self.timer.isActive()

    def show(self, before: Image.Image | None, after: Image.Image, keep: bool = False):
        self.finish()
        self.token += 1
        tok = self.token
        self.final = after
        self.keep = keep
        # 計算の間は前の絵を重ねておく（置いた絵がいきなり見えないように）
        self._overlay(before if before is not None else Image.new("RGB", after.size, "white"))

        def work():
            try:
                plan = Plan(before, after)
            except Exception:   # 見せ方の失敗で絵を出さないことはしない。最後の絵をそのまま出す
                plan = None
            self.queue.append((tok, plan))
        threading.Thread(target=work, daemon=True).start()
        self.t = -1.0
        self.timer.start()

    def _tick(self):
        if self.t < 0:
            if not self.queue:
                return
            tok, plan = self.queue.pop()
            if tok != self.token:
                return
            if plan is None or plan.empty():
                self.finish()
                return
            self.plan, self.t = plan, 0.0
        self.t = min(1.0, self.t + self.TICK_MS / 1000.0 / self.SECONDS)
        if self.t >= 1.0:
            self.finish()
            return
        self._overlay(self.plan.frame(self.t))
        self._tip(self.plan.tip(self.t))

    def finish(self):
        """今の移りを最後まで飛ばす。keep でなければ重ね絵を外し、置いてある絵（AI の絵そのもの）を見せる"""
        if not self.timer.isActive() and self.final is None:
            return
        self.timer.stop()
        self.token += 1
        self.plan = None
        self._tip(None)
        if self.final is not None and self.keep:
            self._overlay(self.final, full=True)
        else:
            self.canvas.show_overlay(None)
        self.final = None

    def _overlay(self, im: Image.Image, full: bool = False):
        from atelier.app.window.image_convert import qimage_from_pil
        self.canvas.show_overlay(qimage_from_pil(im))

    def _tip(self, pos):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QBrush, QColor, QPen
        from PySide6.QtWidgets import QGraphicsEllipseItem
        if self.tip_item is None:
            if pos is None:
                return
            self.tip_item = QGraphicsEllipseItem()
            self.tip_item.setZValue(1e8 + 1)
            self.tip_item.setPen(QPen(QColor(40, 40, 40, 220), 0))
            self.tip_item.setBrush(QBrush(QColor(255, 255, 255, 120)))
            self.tip_item.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
            self.canvas.scene().addItem(self.tip_item)
        if pos is None:
            self.tip_item.setVisible(False)
            return
        w, h = self.canvas.size_px()
        fw, fh = self.final.size if self.final is not None else (w, h)
        r = 9
        self.tip_item.setRect(-r, -r, 2 * r, 2 * r)
        self.tip_item.setPos(pos[0] * w / fw, pos[1] * h / fh)
        self.tip_item.setVisible(True)
        _ = Qt
