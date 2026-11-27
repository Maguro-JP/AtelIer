"""AI の絵を、人が描くように筆で描き込んで見せる。

AI の絵がいきなりキャンバスに出ると、描いた過程が何も見えなかった。そこで前の絵（無ければ白）から次の絵へ移るとき、
差のある所だけを 線画 → 大きな塗り → 細かい塗り → 仕上げ の順に、筆の運びで少しずつ描き込む。
- 線画: timelapse.reconstruct と同じ「周りより暗い所」を線とし、つながった線ごとに端から線に沿って伸ばす
- 塗り: 色を均した平塗りの塊（同じ色でつながった所）ごとに、真ん中から塗り広げる。大きな塊を先、細かい塊を後にする
- 仕上げ: 残った細かい差を、出ている所から近い順に描く。最後の 1 枚は AI の絵そのもの。
  全体を薄く混ぜて出すと、筆と関係ない所に線でも何でもない物が薄く出現するので混ぜない
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
MIN_LINE_PX = 5          # これより小さい塊は線としてなぞらない（筆で 1 点ずつ描くと、点々が出現して見える）
LINE_END, BIG_END, SMALL_END = 0.30, 0.62, 0.84   # 各段が終わる時刻（0〜1）。残りが仕上げ
BIG_AREA = 0.004         # 絵の面積に対するこの割合より大きい塊を「大きな塗り」にする
LINE_PX_PER_SEC = 600.0   # 線をなぞる速さ（縮めた絵の画素／秒）。線が多いほど線画の段は長くかかる
LINE_SECONDS_MAX = 12.0   # 線画の段の長さの上限（秒）
SECONDS = 2.4             # 線の無い移りの長さ（秒）
SECONDS_MAX = 20.0        # 1 回の移りの長さの上限（秒）
HATCH_PERIOD = 7          # はらいの間隔（画素）。斜めの線の繰り返し
HATCH_WIDTH = 2           # はらいの線の太さ（画素）


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


def _stroke_order(line: np.ndarray, lab: np.ndarray, n: int, starts: list) -> np.ndarray:
    """線の画素に、ペンが通る順の番号を付ける。種から深さ優先にたどるので、
    枝分かれは 1 本ずつ順に描かれる。距離の順だと、種から同じ距離にある全部の枝が
    同時に伸びて、複数本を同時に描く見え方になる（ペンではありえない）"""
    order = np.full(line.shape, -1, np.int32)
    h, w = line.shape
    for i in range(n):
        seed = starts[i]
        stack = [seed]
        seen = {seed}
        idx = 0
        while stack:
            y, x = stack.pop()
            order[y, x] = idx
            idx += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    q = (y + dy, x + dx)
                    if q in seen or not (0 <= q[0] < h and 0 <= q[1] < w):
                        continue
                    if lab[q] == i + 1:
                        seen.add(q)
                        stack.append(q)
    return order


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
        # 消えた所（前の絵で暗かった所が明るくなった）も線の段で見せる。消えた所を
        # 仕上げの段に回すと、絵全体の中でじわっと薄れて、フェードアウトに見える
        # （利用者の指摘: 「消すのがフェードアウトしてる」）。消しゴムも筆と同じで、
        # 通った所から順に消えていく見え方にする。線の濃さではなく明るさの変化で見る
        # （ベタの塊は内側に線の濃淡が無いので、線として拾うと縁しか消えない）
        lum_b = np.asarray(b.convert("L"), np.float32)
        lum_a = np.asarray(gray, np.float32)
        line = line | (diff & (lum_b < 128) & (lum_a - lum_b > 40))
        self._a = a
        self.line = line
        self._finish_t = None   # 仕上げの段で各画素を描く時刻（元の大きさ）。fill() で計算する
        self.ready = False   # 塗りの段を計算し終えたか。終わるまでは線画の段だけを見せる
        # 縮めた大きさの座標を元の大きさへ写す表（最近傍）
        self._ry = np.minimum((np.arange(self.full[1]) * h) // self.full[1], h - 1)
        self._rx = np.minimum((np.arange(self.full[0]) * w) // self.full[0], w - 1)
        t = np.full((h, w), np.inf, np.float32)
        tips: list[tuple[float, float, float]] = []   # (時刻, x, y)
        # 線画: つながった線ごと。順は、前の線の終わりから一番近い線へつなぐ
        lab, n = ndimage.label(line, ndimage.generate_binary_structure(2, 2))
        if n:
            sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
            # 小さすぎる塊は線ではない（色の段のざらつきやゴミ）。筆で 1 点ずつ描くと、
            # 筆と関係ない所に点々が出現して見える。線の段からは外し、塗りの段で一緒に出す
            keep = sizes >= MIN_LINE_PX
            if not keep.all():
                line = line & keep[lab - 1]
                self.line = line
                lab, n = ndimage.label(line, ndimage.generate_binary_structure(2, 2))
                sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1)) if n else np.zeros(0)
        if n:
            objs = ndimage.find_objects(lab)
            total = float(sizes.sum()) or 1.0
            starts = []
            for i in range(n):
                ys, xs = objs[i]
                sub = lab[ys, xs] == i + 1
                yy, xx = np.argwhere(sub)[0]
                starts.append((ys.start + yy, xs.start + xx))
            dist = _stroke_order(line, lab, n, starts)
            ends = []
            for i in range(n):
                ys, xs = objs[i]
                sub = np.where(lab[ys, xs] == i + 1, dist[ys, xs], -1)
                yy, xx = np.unravel_index(int(np.argmax(sub)), sub.shape)
                ends.append((ys.start + yy, xs.start + xx))
            # 画面の上から順に飛ぶと筆が関係ない所へ跳ぶ。一番上の線から始め、
            # あとは終わりから一番近い線へつないでいく（人の手の動きに寄せる）
            order = []
            left = set(range(n))
            cur = min(left, key=lambda i: (starts[i][0], starts[i][1]))
            while True:
                order.append(cur)
                left.discard(cur)
                if not left:
                    break
                ey, ex = ends[cur]
                cur = min(left, key=lambda i: (starts[i][0] - ey) ** 2 + (starts[i][1] - ex) ** 2)
            at = 0.0
            for i in order:
                span = LINE_END * float(sizes[i]) / total
                tips.extend(self._lay(t, lab, dist, objs[i], i + 1, at, span))
                at += span
        tips.sort()
        self.t, self.tips = t, tips
        # その場の線の太さ（筆の太さにする）。線の画素から一番近い線でない所までの距離の 2 倍
        from scipy.ndimage import distance_transform_edt
        self._line_width = distance_transform_edt(line) * 2.0
        # 線画の段の長さ。線が多いほど長くかけ、0.72 秒で終わることはなくする
        line_px = float(line.sum())
        self.line_seconds = min(LINE_SECONDS_MAX, line_px / LINE_PX_PER_SEC) if line_px else 0.0
        self.seconds = (max(SECONDS, min(SECONDS_MAX, self.line_seconds / LINE_END))
                        if self.line_seconds else SECONDS)

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
            # はらい：斜めの線の表。塗りはこの線を先に描いてから間を埋める
            yy, xx = np.indices((h, w))
            hatch = ((yy + xx) % HATCH_PERIOD) < HATCH_WIDTH
            for lo, hi, pick in ((LINE_END, BIG_END, area >= big_px), (BIG_END, SMALL_END, area < big_px)):
                ids = [i for i in np.argsort(-area) if pick[i]]
                tot = float(sum(area[i] for i in ids)) or 1.0
                at = lo
                for i in ids:
                    span = (hi - lo) * float(area[i]) / tot
                    tips.extend(self._lay(t, blobs, dist, bobjs[i], i + 1, at, span, hatch=hatch))
                    at += span
        t[diff & ~np.isfinite(t)] = SMALL_END
        # 仕上げの段: 縮めた絵では拾えなかった細かい差（元の大きさでだけ違う所）を、
        # もう出ている所から近い順に描く時刻を付ける。全体を薄く混ぜて出すと、
        # 筆と関係ない所に線でも何でもない物が薄く出現する（利用者の指摘）
        A = self.A_full.astype(np.float32)
        B = self.B_full.astype(np.float32)
        fd = np.abs(A - B).max(axis=2) > DIFF_MIN
        shown0 = (t <= SMALL_END)[self._ry][:, self._rx]
        rest = fd & ~shown0
        ft = np.full(fd.shape, np.inf, np.float32)
        if rest.any():
            from scipy.ndimage import distance_transform_edt
            dist = distance_transform_edt(~shown0)
            top = float(dist[rest].max()) or 1.0
            ft[rest] = SMALL_END + (1.0 - SMALL_END) * np.clip(dist[rest] / top, 0.0, 1.0)
            for k in range(1, 7):   # 仕上げの筆先: 区切りごとに、これから描く所の真ん中
                lo = SMALL_END + (1.0 - SMALL_END) * (k - 1) / 6
                hi = SMALL_END + (1.0 - SMALL_END) * k / 6
                sel = rest & (ft > lo) & (ft <= hi)
                if sel.any():
                    ys, xs = np.nonzero(sel)
                    tips.append((hi, float(xs.mean()) * self.scale, float(ys.mean()) * self.scale))
        self._finish_t = ft
        tips.sort()
        self.t, self.tips = t, tips   # 入れ替えは 1 回の代入で（再生の糸が途中の表を見ないように）
        self.ready = True

    @staticmethod
    def _lay(t, lab, dist, sl, ident, at: float, span: float, steps: int = 6, hatch=None):
        """1 つの線・塊に描く時刻を入れ、筆先が通る点（距離の段ごとの真ん中）を返す。
        塊ごとに絵全体を見ると数千の塊で遅かったので、塊の外枠の中だけを見る。
        hatch（はらいの線の表）を渡すと、はらいを先に、間を後に描く。どちらも距離の順に描く"""
        m = lab[sl] == ident
        d = dist[sl][m].astype(np.float32)
        top = max(1.0, float(d.max()))
        sub = t[sl]
        if hatch is not None:
            hm = hatch[sl][m]
            sub[m] = np.where(hm, at + span * 0.5 * d / top,
                              at + span * 0.5 + span * 0.5 * d / top)
        else:
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
        if t > SMALL_END:   # 仕上げ: 残った差を、出ている所から近い順に描く（全体を薄く混ぜない）
            shown = (self.t <= t)[self._ry][:, self._rx]
            if self._finish_t is not None:
                shown = shown | (self._finish_t <= t)
            return Image.fromarray(np.where(shown[..., None], self.A_full, self.B_full))
        shown = (self.t <= t)[self._ry][:, self._rx]
        return Image.fromarray(np.where(shown[..., None], self.A_full, self.B_full))

    def tip(self, t: float):
        """時刻 t の筆先の位置と太さ（元の絵の大きさの座標）。動いていないときは None。
        太さはその場の線の太さに合わせる。細い線でも見える大きさを保ち、太すぎないようにする"""
        if not self.tips or t >= 1.0:
            return None
        i = min(range(len(self.tips)), key=lambda j: abs(self.tips[j][0] - t))
        _, x, y = self.tips[i]
        wx = min(self.size[0] - 1, max(0, int(x)))
        wy = min(self.size[1] - 1, max(0, int(y)))
        half = float(self._line_width[wy, wx]) / 2.0
        r = min(12.0, max(3.0, half)) / self.scale
        return x / self.scale, y / self.scale, r


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

    SECONDS = SECONDS   # 線の無い移りの長さ（秒）。線のある移りは Plan.seconds（線の量で決まる）を使う
    MID_SECONDS = 1.0   # 描いている途中の絵の移りの長さ（秒）。次々届くので短くして筆を動かし続ける
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
        self.seconds = self.SECONDS   # 今の移りの長さ（秒）。運びが決まったら Plan.seconds にする
        self.max_seconds: float | None = None   # 移りの長さの上限（show の引き数。途中の絵で短くする）
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
        if hasattr(canvas, "changed"):
            canvas.changed.connect(self._layers_changed)

    def _layers_changed(self):
        """置いた絵を見せている途中にレイヤーが変わった（消した・隠した・元に戻した）ら、すぐ見せ終える。
        重ね絵は置いたときの絵の写しなので、そのままだと消したレイヤーの絵が見せ終えるまで画面に残った"""
        if self.active() and not self.keep:
            self.finish()

    def active(self) -> bool:
        return self.timer.isActive()

    def visible(self) -> Image.Image | None:
        """今キャンバスの上に見えている途中の絵（無ければ None）。見せている途中なら最後まで飛ばしてから返す"""
        self.finish()
        return self.shown

    def show(self, before: Image.Image | None, after: Image.Image, keep: bool = False, max_seconds: float | None = None):
        """前の絵から次の絵への筆の運びを見せる。keep=False は絵を先にレイヤーへ置いた場合で、見せ終えたら重ね絵を外す。
        keep=True は途中の絵で、最後に重ね絵として残す。max_seconds は移りの長さの上限（秒）。
        描いている途中の絵は次々届くので、長くかけると次の絵に追いつかず筆が飛ぶ。短くして筆を動かし続ける"""
        self.finish()
        self.token += 1
        tok = self.token
        self.final = after
        self.keep = keep
        self.max_seconds = max_seconds
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
            self.seconds = getattr(plan, "seconds", self.SECONDS)
            if self.max_seconds is not None:   # 途中の絵は短く（次の絵が来る前に筆を動かし終える）
                self.seconds = min(self.seconds, self.max_seconds)
        self.t = min(1.0, self.t + self.TICK_MS / 1000.0 / self.seconds)
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
        """筆先の丸。pos は (x, y, 太さ)（元の絵の大きさの座標）。線の色で塗った丸にする。
        前は縁だけの薄い丸で、線をなぞっているのが見えなかった"""
        from PySide6.QtGui import QBrush, QColor, QPen
        from PySide6.QtWidgets import QGraphicsEllipseItem
        if self.tip_item is None:
            if pos is None:
                return
            self.tip_item = QGraphicsEllipseItem()
            self.tip_item.setZValue(1e8 + 1)
            self.tip_item.setPen(QPen(QColor(30, 30, 30, 200)))
            self.tip_item.setBrush(QBrush(QColor(30, 30, 30, 150)))
            self.tip_item.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
            self.canvas.scene().addItem(self.tip_item)
        if pos is None:
            self.tip_item.setVisible(False)
            return
        x, y, r = pos
        w, h = self.canvas.size_px()
        fw, fh = self.final.size if self.final is not None else (w, h)
        z = self.canvas.transform().m11() if hasattr(self.canvas, "transform") else 1.0
        rr = max(3.0, min(16.0, r * (w / fw) * z))   # 線の太さに合わせた筆の太さ（画面の画素）
        self.tip_item.setRect(-rr, -rr, 2 * rr, 2 * rr)
        self.tip_item.setPos(x * w / fw, y * h / fh)
        self.tip_item.setVisible(True)
