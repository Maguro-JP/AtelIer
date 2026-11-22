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

WORK_SIDE = 384          # 筆の運びを計算する大きさ（長い辺）。見せるだけなので縮めて速くする
DIFF_MIN = 10            # これより小さい色の差は「変わっていない」とする（縮めたときの揺れ）
LINE_END, BIG_END, SMALL_END = 0.30, 0.62, 0.84   # 各段が終わる時刻（0〜1）。残りが仕上げ
BIG_AREA = 0.004         # 絵の面積に対するこの割合より大きい塊を「大きな塗り」にする


def _dist_from_seeds(mask: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """mask の中で seeds から何歩で届くか（つながった所に沿った距離）。届かない所は -1。
    膨らませを何百回も繰り返すと 2 秒かかったので、mask の画素をつないだ表の最短路（C の実装）で求める"""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    h, w = mask.shape
    dist = np.full(mask.shape, -1, np.int32)
    idx = np.full(mask.shape, -1, np.int64)
    ys, xs = np.nonzero(mask)
    n = len(ys)
    src = np.nonzero(seeds[ys, xs])[0]
    if n == 0 or len(src) == 0:
        return dist
    idx[ys, xs] = np.arange(n)
    rows, cols = [], []
    for dy, dx in ((0, 1), (1, -1), (1, 0), (1, 1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 < h) & (x2 >= 0) & (x2 < w)
        j = np.full(n, -1, np.int64)
        j[ok] = idx[y2[ok], x2[ok]]
        ok = j >= 0
        rows.append(np.nonzero(ok)[0]); cols.append(j[ok])
    r = np.concatenate(rows); c = np.concatenate(cols)
    g = coo_matrix((np.ones(len(r), np.float32), (r, c)), shape=(n, n)).tocsr()
    d = dijkstra(g, directed=False, indices=src, min_only=True)
    fin = np.isfinite(d)
    dist[ys[fin], xs[fin]] = d[fin].astype(np.int32)
    return dist


class Plan:
    """前の絵から次の絵への筆の運び。frame(t) で途中の絵、tip(t) で筆先の位置を返す"""

    def __init__(self, before: Image.Image | None, after: Image.Image, work_side: int = WORK_SIDE):
        from scipy import ndimage
        a = after.convert("RGB")
        self.full = a.size
        self.A_full = np.asarray(a, np.uint8)   # 見せる画素は元の大きさから切り出す（縮めた絵を引き伸ばすとぼやけた）
        self.B_full = (np.full_like(self.A_full, 255) if before is None
                       else np.asarray(before.convert("RGB").resize(a.size, Image.LANCZOS) if before.size != a.size
                                       else before.convert("RGB"), np.uint8))
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
        self._a = a
        self.line = line
        self.ready = False   # 塗りの段を計算し終えたか。終わるまでは線画の段だけを見せる
        # 縮めた大きさの座標を元の大きさへ写す表（最近傍）
        self._ry = np.minimum((np.arange(self.full[1]) * h) // self.full[1], h - 1)
        self._rx = np.minimum((np.arange(self.full[0]) * w) // self.full[0], w - 1)
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
                tips.extend(self._lay(t, lab, dist, objs[i], i + 1, at, span))
                at += span
        tips.sort()
        self.t, self.tips = t, tips

    def fill(self):
        """塗りの段の筆の運びを計算する。線画は先に見せ始め、これは裏で後から足す（初めに止まって見えないように）"""
        from scipy import ndimage
        a, diff, line = self._a, self.diff, self.line
        w, h = self.size
        t = self.t.copy()
        tips = list(self.tips)
        fill = diff & ~line
        flat = np.asarray(a.filter(ImageFilter.ModeFilter(7)).filter(ImageFilter.MedianFilter(5)), np.float32)
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
            bobjs = ndimage.find_objects(blobs)
            for i in range(nb):   # 塊の真ん中に一番近い、塊の中の点から塗り広げる
                sl = bobjs[i]
                ys, xs = np.nonzero(blobs[sl] == i + 1)
                j = int(np.argmin((ys + sl[0].start - cy[i]) ** 2 + (xs + sl[1].start - cx[i]) ** 2))
                seeds[ys[j] + sl[0].start, xs[j] + sl[1].start] = True
            dist = _dist_from_seeds(blobs > 0, seeds)
            for lo, hi, pick in ((LINE_END, BIG_END, area >= big_px), (BIG_END, SMALL_END, area < big_px)):
                ids = [i for i in np.argsort(-area) if pick[i]]
                tot = float(sum(area[i] for i in ids)) or 1.0
                at = lo
                for i in ids:
                    span = (hi - lo) * float(area[i]) / tot
                    tips.extend(self._lay(t, blobs, dist, bobjs[i], i + 1, at, span))
                    at += span
        t[diff & ~np.isfinite(t)] = SMALL_END
        tips.sort()
        self.t, self.tips = t, tips   # 入れ替えは 1 回の代入で（再生の糸が途中の表を見ないように）
        self.ready = True

    @staticmethod
    def _lay(t, lab, dist, sl, ident, at: float, span: float, steps: int = 6):
        """1 つの線・塊に描く時刻を入れ、筆先が通る点（距離の段ごとの真ん中）を返す。
        塊ごとに絵全体を見ると数千の塊で遅かったので、塊の外枠の中だけを見る"""
        m = lab[sl] == ident
        d = dist[sl][m].astype(np.float32)
        top = max(1.0, float(d.max()))
        sub = t[sl]
        sub[m] = at + span * d / top
        ys, xs = np.nonzero(m)
        out = []
        if span * 400 < 1 and len(d) < 30:   # 小さな点は筆先を飛ばさない（ちらつく）
            return out
        for k in range(steps + 1):
            sel = np.abs(d - top * k / steps) <= max(1.0, top / steps / 2)
            if sel.any():
                out.append((at + span * k / steps, float(xs[sel].mean() + sl[1].start), float(ys[sel].mean() + sl[0].start)))
        return out

    def empty(self) -> bool:
        return not self.diff.any()

    def frame(self, t: float) -> Image.Image:
        """時刻 t（0〜1）の途中の絵（計算した大きさ）。t>=1 は次の絵そのもの"""
        if t >= 1.0:
            return Image.fromarray(self.A_full)
        if t > SMALL_END:   # 仕上げ: 残った差を全部描く
            small = self.diff.copy()
        else:
            small = self.t <= t
        shown = small[self._ry][:, self._rx]
        if t > SMALL_END:   # 差が小さく残った所（縮めたときに拾えなかった所）も順に描く
            k = (t - SMALL_END) / (1.0 - SMALL_END)
            out = self.B_full * (1 - k) + self.A_full * k
            out = np.where(shown[..., None], self.A_full, out.astype(np.uint8))
            return Image.fromarray(out)
        return Image.fromarray(np.where(shown[..., None], self.A_full, self.B_full))

    def tip(self, t: float):
        """時刻 t の筆先の位置（元の絵の大きさの座標）。動いていないときは None"""
        if not self.tips or t >= SMALL_END + 0.01:
            return None
        i = min(range(len(self.tips)), key=lambda j: abs(self.tips[j][0] - t))
        _, x, y = self.tips[i]
        return x / self.scale, y / self.scale


def strokes(before: Image.Image | None, after: Image.Image, n: int = 18, work_side: int = 256) -> list[Image.Image]:
    """タイムラプスに残す筆の運び（n 枚、最後の 1 枚は次の絵そのもの）"""
    plan = Plan(before, after, work_side=work_side)
    plan.fill()
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
        self.shown: Image.Image | None = None   # 重ね絵として見せたままの途中の絵（次の移りの出発点）

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

    def visible(self) -> Image.Image | None:
        """今キャンバスの上に見えている途中の絵（無ければ None）。見せている途中なら最後まで飛ばしてから返す"""
        self.finish()
        return self.shown

    def show(self, before: Image.Image | None, after: Image.Image, keep: bool = False):
        self.finish()
        self.token += 1
        tok = self.token
        self.final = after
        self.keep = keep
        self.shown = None
        # 計算の間は前の絵を重ねておく（置いた絵がいきなり見えないように）
        self._overlay(before if before is not None else Image.new("RGB", after.size, "white"))

        def work():
            try:
                plan = Plan(before, after)
            except Exception:   # 見せ方の失敗で絵を出さないことはしない。最後の絵をそのまま出す
                plan = None
            self.queue.append((tok, plan))   # 線画の段ができたら再生を始め、塗りは裏で続けて計算する
            if plan is not None:
                try:
                    plan.fill()
                except Exception:
                    plan.ready = True
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
        if not self.plan.ready and self.t > LINE_END:   # 塗りの計算が終わるまで線画の終わりで待つ
            self.t = LINE_END
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
            self._overlay(self.final)
            self.shown = self.final
        else:
            self.canvas.show_overlay(None)
            self.shown = None
        self.final = None

    def _overlay(self, im: Image.Image):
        from atelier.app.window.image_convert import qimage_from_pil
        self.canvas.show_overlay(qimage_from_pil(im))

    def _tip(self, pos):
        from PySide6.QtGui import QBrush, QColor, QPen
        from PySide6.QtWidgets import QGraphicsEllipseItem
        if self.tip_item is None:
            if pos is None:
                return
            self.tip_item = QGraphicsEllipseItem()
            self.tip_item.setZValue(1e8 + 1)
            pen = QPen(QColor(60, 60, 60, 110))   # 縁だけの薄い丸（絵を隠さない）
            pen.setWidthF(1.0)
            pen.setCosmetic(True)
            self.tip_item.setPen(pen)
            self.tip_item.setBrush(QBrush())
            self.tip_item.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
            self.canvas.scene().addItem(self.tip_item)
        if pos is None:
            self.tip_item.setVisible(False)
            return
        w, h = self.canvas.size_px()
        fw, fh = self.final.size if self.final is not None else (w, h)
        z = self.canvas.transform().m11() if hasattr(self.canvas, "transform") else 1.0
        r = max(2.0, min(6.0, 2.5 * z))   # 描いている線の太さ程度（画面の画素）
        self.tip_item.setRect(-r, -r, 2 * r, 2 * r)
        self.tip_item.setPos(pos[0] * w / fw, pos[1] * h / fh)
        self.tip_item.setVisible(True)
