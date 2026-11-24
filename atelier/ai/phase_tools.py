"""工程に分けて描く（atelier/ai/phases.py）の、模型を使わない測り方と処理。

人が描くときに工程の合間で見ている物（重心、等身、左右の目、画面の重さ、光源と影の向き、目の光、縮めて見る・反転して見る）を数字にし、
模型で描かなくてもできる事（線の強弱、影の 2 段目）は、ここで絵に掛ける。どれも numpy と Pillow だけで、1 回 1 秒に届かない軽さにする
（工程を重くすると進まず、まとめるとメモリが溢れて落ちたので）。

しきい値はどれも私の推測の値で、Actions の phase-bench の絵で見直す。
"""
from __future__ import annotations

BG_DIFF = 30          # 四隅の色からこれだけ離れた画素を人物（紙でない所）とする（0〜255 の RGB の距離）
BALANCE_MOST = 0.6    # 重心が足の幅の中心から、足の幅のこの割合より外れたら「立てない」とする
HEADS = (2.0, 9.5)    # 等身の範囲。外れたら体の比が崩れている
EYE_TILT = 0.25       # 左右の目の高さの差が、目の間の幅のこの割合を超えたら崩れ
WEIGHT_MOST = 0.35    # サムネイルの画面の重さ（暗い塊）の重心が、真ん中から幅のこの割合より外れたら釣り合いが悪い
LINE_GAP_MOST = 0.75  # 人物の外の輪郭のうち、線の無い所の割合がこれを超えたら輪郭が途切れている
LINE_WEIGHT_LEAST = 0.45   # 外の輪郭の帯のうち暗い画素の割合がこれ未満なら、線の強弱が無い（細い 1 画素の線は 0.32、太らせると 0.6。私の推測）   # 外の輪郭の帯のうち暗い画素の割合がこれ未満なら、線の強弱が無い（外の輪郭が細く薄い。私の推測）
LINE_MAX_GAP_MOST = 0.25   # 外の輪郭のうち、線の無い所が続く一番長い区間がこれを超えたら、線が途中でずれている（私の推測）
OUTLINE_GROW = 0.004       # 外の輪郭を太らせる幅（短い辺の割合。64 画素なら 1 画素、1216 画素なら 5 画素。私の推測）
DUST_MAX_PIXELS = 64       # ゴミ: 塊の画素数がこれ以下ならゴミ（私の推測）
DUST_SIZE_MOST = 0.05      # ゴミ: 塊の長い辺が短い辺のこの割合以下（ただし 3 画素以上）ならゴミ（私の推測）
DETACH_MOST = 0.08         # 位置ずれ: 主役から離れた塊が、短い辺のこの割合より近くにあれば体から離れた部位（私の推測）
HORIZON_TILT_MOST = 2.0    # 画角: 地平線の傾きがこれ（度）を超えたら傾いている（私の推測）
BLEED_SAT = 60             # 色のにじみ: 紙の上の画素の彩度がこれ以上なら色がはみ出している（私の推測）
BLEED_MOST = 0.005         # 色のにじみ: はみ出した色の画素が絵全体のこの割合を超えたらにじんでいる（私の推測）
# 暗い画素の左右の割合は髪・服の色にも左右されるので、極端な場合（3 割未満）だけ見る（私の推測）
OUTER_DARK = 0.65     # 線の強弱: 外の輪郭の線をこの倍率まで暗くする（手前・外側を太く濃く）
SHADE2 = 0.70         # 影の 2 段目: 影の中の一番暗い所をこの倍率で暗くする。0.82 では変わりが平均 0.20 で DIFF_MIN（0.5）を下回り、影の工程が絵を変えなかったので強くした
SHADE2_PART = 0.25    # 影の 2 段目にする割合（人物の画素のうち暗い方から）。0.12 では変わる画素が少なく、影の工程が絵を変えなかったので広げた
CATCHLIGHT = 200      # 目の中にこれより明るい画素が無ければ、目の光が無い
SHRINK = 8            # 縮めて見る倍率
SHRINK_CONTRAST = 12  # 縮めた絵で人物と紙の明るさの差がこれより小さければ、主役が目立たない
FLIP_MOST = 0.32      # 顔を左右に反転して重ねた差（0〜1）がこれを超えたら、顔が片側に歪んでいる

SKIN = {11, 12, 13, 14, 15}            # 部位分け（facefeat.seg）の顔・脚・腕
HAIR = {2}
WEAR = {1, 3, 4, 5, 6, 7, 8, 9, 10, 16, 17}   # 帽子・眼鏡・服・靴・鞄・マフラー


def _np(image):
    import numpy as np
    return np.asarray(image.convert("RGB"), dtype=np.int16)


def luminance(image):
    import numpy as np
    a = _np(image).astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def silhouette(image):
    """人物（紙でない所）の真偽の配列。四隅の色の中央を紙の色とする。部位分けがあればそれを使う"""
    import numpy as np
    a = _np(image)
    h, w = a.shape[:2]
    k = max(2, min(w, h) // 20)
    corners = np.concatenate([a[:k, :k].reshape(-1, 3), a[:k, -k:].reshape(-1, 3), a[-k:, :k].reshape(-1, 3), a[-k:, -k:].reshape(-1, 3)])
    paper = np.median(corners, axis=0)
    return np.sqrt(((a - paper) ** 2).sum(axis=2)) > BG_DIFF


def parts(image):
    """部位分けの番号の配列。部位分けの模型が無いときは None（測れなかったことを測れたことにしない）"""
    try:
        from atelier.ai import face_features as facefeat
        return facefeat.seg(image)
    except Exception:   # noqa: BLE001
        return None


def thumb_weight(image) -> dict:
    """サムネイルの画面の重さ: 64 画素に縮め、暗い塊の重心が真ん中からどれだけ外れているか（幅・高さの割合）"""
    import numpy as np
    from PIL import Image
    small = image.convert("L").resize((64, max(8, int(64 * image.height / image.width))), Image.BOX)
    a = 255.0 - np.asarray(small, dtype=np.float32)
    total = float(a.sum()) or 1.0
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    cx, cy = float((a * xs).sum() / total) / a.shape[1], float((a * ys).sum() / total) / a.shape[0]
    return {"weight_x": round(abs(cx - 0.5), 3), "weight_y": round(cy, 3), "ink": round(total / a.size / 255, 3)}


def balance(image, mask=None) -> dict:
    """重心: 人物の画素の重心の横の位置が、下の 8% の行（足）の幅の中心からどれだけ外れているか（足の幅の割合）"""
    import numpy as np
    m = silhouette(image) if mask is None else mask
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return {"readable": False}
    y1 = ys.max()
    y0 = y1 - max(2, int((y1 - ys.min()) * 0.08))
    feet = xs[ys >= y0]
    mid, width = (feet.min() + feet.max()) / 2, max(feet.max() - feet.min(), m.shape[1] * 0.1)
    off = abs(float(xs.mean()) - mid) / width
    return {"readable": True, "balance": round(off, 3), "height": int(y1 - ys.min())}


def heads(points: dict, height: int) -> float | None:
    """等身: 人物の高さ ÷ 頭の高さ。頭の高さは、目から肩の中ほどまでの 1.3 倍とみる（私の推測の比）"""
    need = ("left_eye", "right_eye", "left_shoulder", "right_shoulder")
    if not height or not all(k in points for k in need):
        return None
    eye = (points["left_eye"][1] + points["right_eye"][1]) / 2
    sh = (points["left_shoulder"][1] + points["right_shoulder"][1]) / 2
    head = abs(sh - eye) * 1.3
    return round(height / head, 2) if head > 1 else None


def eye_tilt(points: dict) -> float | None:
    """左右の目の高さの差 ÷ 目の間の幅"""
    if "left_eye" not in points or "right_eye" not in points:
        return None
    (lx, ly), (rx, ry) = points["left_eye"][:2], points["right_eye"][:2]
    return round(abs(ly - ry) / max(abs(lx - rx), 1.0), 3)


def _erode(m, r):
    from PIL import Image, ImageFilter
    import numpy as np
    img = Image.fromarray((m * 255).astype("uint8"))
    return np.asarray(img.filter(ImageFilter.MinFilter(2 * r + 1))) > 127


def _dilate(m, r):
    from PIL import Image, ImageFilter
    import numpy as np
    img = Image.fromarray((m * 255).astype("uint8"))
    return np.asarray(img.filter(ImageFilter.MaxFilter(2 * r + 1))) > 127


def _max_gap_run(edge, near):
    """輪郭のうち線の無い所が続く一番長い区間の、輪郭全体に対する割合。線の無い所を塊に分け、一番大きい塊で見る。
    散らばった小さな途切れは小さく、一か所で長く途切れた線のズレは大きく出る"""
    import numpy as np
    gap = edge & ~near
    if not gap.any() or not edge.any():
        return 0.0
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ、線の無い所の割合で代用する
        return float(gap.sum()) / max(int(edge.sum()), 1)
    lab, n = ndimage.label(gap)
    if n == 0:
        return 0.0
    sizes = ndimage.sum(gap, lab, range(1, n + 1))
    return float(sizes.max()) / max(int(edge.sum()), 1)


def _filled_silhouette(image):
    """シルエットの穴を埋めた物（外の輪郭を取るときに使う）。線画は輪郭だけの絵で、中の紙が穴になる。穴を埋めないと、内側の細い線まで外の輪郭と見てしまう。
    scipy が無ければ、埋めていないシルエットを返す"""
    import numpy as np
    m = silhouette(image)
    try:
        from scipy import ndimage
        return ndimage.binary_fill_holes(m)
    except Exception:   # noqa: BLE001  scipy が無ければ、穴を埋められない
        return m


def lines(image) -> dict:
    """線画を見る: 外の輪郭のうち線（暗い画素）の無い所の割合と、線と周りの明るさの差。
    weight は外の輪郭の帯のうち暗い画素の割合（線の強弱。太く濃い外の輪郭ほど高い）。
    max_gap は線の無い所が続く一番長い区間の割合（線のズレ。一か所で長く途切れていたら線がずれている）"""
    import numpy as np
    lum = luminance(image)
    m = silhouette(image)
    if m.sum() < 50:
        return {"readable": False}
    filled = _filled_silhouette(image)   # 外の輪郭だけを見る（内側の細い線は外の輪郭ではない）
    edge = filled & ~_erode(filled, 1)
    dark = lum <= np.percentile(lum[m], 20)   # 線は一番暗い所。真っ黒な線だけのとき 20 パーセント点が 0 になるので、< ではなく <= で見る
    near = _dilate(dark, 2)
    gap = 1.0 - float((edge & near).sum()) / max(int(edge.sum()), 1)
    contrast = float(lum[m & ~dark].mean() - lum[dark & m].mean()) if (dark & m).any() and (m & ~dark).any() else 0.0
    band = _dilate(filled, 1) & ~_erode(filled, 2)
    weight = float((band & dark).sum()) / max(int(band.sum()), 1)
    return {"readable": True, "gap": round(gap, 3), "contrast": round(contrast, 1),
            "weight": round(weight, 3), "max_gap": round(_max_gap_run(edge, near), 3)}


def outline_radius(image) -> int:
    """外の輪郭を太らせる幅（画素）。絵の短い辺に比例する（64 画素なら 1 画素、1216 画素なら 5 画素）"""
    return max(1, round(min(image.size) * OUTLINE_GROW))


def weight_lines(image, r=None):
    """線の強弱: 外の輪郭に掛かっている線だけを暗くし、外の輪郭の線を太らせる（手前・外側を太く濃く、内側の細い線はそのまま）。
    太らせるのは線の周り（内側と外側の紙）。線画は細い線だけなので、内側だけでは太らせる所が無い。
    太らせた所は線の色にする。遠くの紙は変えない。r は太らせる幅（画素）。無ければ絵の大きさから決める。
    返すのは (絵, 変えた画素の数)"""
    import numpy as np
    from PIL import Image
    a = _np(image).astype(np.float32)
    lum = luminance(image)
    m = silhouette(image)
    if m.sum() < 50:
        return image, 0
    filled = _filled_silhouette(image)   # 外の輪郭だけを太らせる（内側の細い線は太らせない）
    outer = _dilate(filled, 1) & ~_erode(filled, 2)
    dark = lum <= np.percentile(lum[m], 30)   # 線は一番暗い所。真っ黒な線だけのとき 30 パーセント点が 0 になるので、< ではなく <= で見る
    hit = outer & dark & m
    a[hit] *= OUTER_DARK
    r = outline_radius(image) if r is None else max(1, int(r))
    thick = _dilate(hit, r) & ~hit   # 線の周り（内側と外側の紙）を太らせる。内側の細い線は太らせない
    if thick.any() and hit.any():
        line_col = np.median(a[hit], axis=0)   # 線の色（暗くした外の輪郭の線の色の中央）
        a[thick] = line_col
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8")), int(hit.sum() + thick.sum())


def _components(image):
    """シルエットの連結成分。返すのは (ラベル配列, 成分の大きさの配列, 一番大きい成分の番号)。scipy が無ければ None"""
    import numpy as np
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ、塊を分けられない
        return None
    m = silhouette(image)
    lab, n = ndimage.label(m)
    if n == 0:
        return lab, np.array([]), 0
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    return lab, sizes, int(np.argmax(sizes)) + 1


def _component_boxes(lab, sizes, big, keep):
    """連結成分のうち、keep(番号, 大きさ, 枠) が真の物の枠 (x0, y0, x1, y1) の一覧"""
    from scipy import ndimage
    boxes = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        if k == big or sl is None:
            continue
        box = (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)
        if keep(k, sizes[k - 1], box):
            boxes.append(box)
    return boxes


def dust(image) -> dict:
    """ゴミ: 主役のシルエットにつながっていない、小さく孤立した暗い塊（点・汚れ・はみ出した線）。
    主役が無ければ読めない。返すのは {"readable", "boxes", "count"}。boxes は (x0, y0, x1, y1)"""
    import numpy as np
    got = _components(image)
    if got is None:
        return {"readable": False, "boxes": [], "count": 0}
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return {"readable": False, "boxes": [], "count": 0}
    h, w = lab.shape
    small = DUST_MAX_PIXELS
    boxes = _component_boxes(lab, sizes, big, lambda _k, size, box: (
        size <= small and max(box[3] - box[1], box[2] - box[0]) <= max(3, min(h, w) * DUST_SIZE_MOST)))
    return {"readable": True, "boxes": boxes, "count": len(boxes)}


def detached(image) -> dict:
    """位置ずれ: 主役から離れた、ゴミより大きい塊（体から離れた手・足・物）。主役の近く（DETACH_MOST 以内）にある物だけ。
    遠くにある物（空の鳥など）は別の物なので数えない。主役が無ければ読めない。返すのは {"readable", "boxes", "count"}"""
    import numpy as np
    got = _components(image)
    if got is None:
        return {"readable": False, "boxes": [], "count": 0}
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return {"readable": False, "boxes": [], "count": 0}
    h, w = lab.shape
    from scipy import ndimage
    big_sl = ndimage.find_objects(lab)[big - 1]
    bx0, bx1 = big_sl[1].start, big_sl[1].stop
    by0, by1 = big_sl[0].start, big_sl[0].stop
    near = min(h, w) * DETACH_MOST
    boxes = []
    for box in _component_boxes(lab, sizes, big, lambda _k, size, box: (
            not (size <= DUST_MAX_PIXELS
                 and max(box[3] - box[1], box[2] - box[0]) <= max(3, min(h, w) * DUST_SIZE_MOST)))):
        # 枠の距離（主役の枠から。0 なら重なっている）。枠の距離で見るのは、正確な画素の距離は重いため
        dx = max(bx0 - box[2], box[0] - bx1, 0)
        dy = max(by0 - box[3], box[1] - by1, 0)
        if max(dx, dy) <= near:
            boxes.append(box)
    return {"readable": True, "boxes": boxes, "count": len(boxes)}


def horizon(image) -> dict:
    """画角: 地平線の傾き。列ごとに一番強い横の線（地平線）の高さを読み、左と右の高さの差から傾き（度）を測る。
    横に長い線が無ければ読めない（人物だけの絵では地平線は無い）。返すのは {"readable", "tilt", "row"}"""
    import numpy as np
    lum = luminance(image)
    h, w = lum.shape
    gy = np.abs(np.diff(lum, axis=0))   # 縦の明るさの変化（横の線）
    col_max = gy.max(axis=0)
    col_arg = gy.argmax(axis=0)
    # 列ごとに、横の線として強い変化があるか。強い列が横に長く続くのが地平線
    strong = col_max > 20
    if strong.mean() < 0.6:
        return {"readable": False}   # 横に長い線ではない（人物の縁など）
    ys = col_arg[strong]
    xs = np.nonzero(strong)[0]
    # 左の 3 分の 1 と右の 3 分の 1 で、地平線の高さ（中央値）を比べる。中央値で、山などの凹凸に強くする
    left = ys[xs < w // 3]
    right = ys[xs >= 2 * w // 3]
    if len(left) < 3 or len(right) < 3:
        return {"readable": False}
    yl, yr = float(np.median(left)), float(np.median(right))
    tilt = float(np.degrees(np.arctan2(yr - yl, (5 * w // 6) - (w // 6))))
    return {"readable": True, "tilt": round(tilt, 2), "row": int(np.median(ys))}


def bleed(image) -> dict:
    """色のにじみ: 主役から離れた所に、彩度の高い色の小さな塊がある所（色が紙にはみ出している）。
    主役の近くの小さな色の塊だけを数える（遠くの赤い花など、別の物をにじみとしない）。主役が無ければ読めない。
    返すのは {"readable", "boxes", "count", "share"}"""
    import numpy as np
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1) * 255, 0)
    got = _components(image)
    if got is None:
        return {"readable": False, "boxes": [], "count": 0, "share": 0.0}
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return {"readable": False, "boxes": [], "count": 0, "share": 0.0}
    h, w = lab.shape
    from scipy import ndimage
    big_sl = ndimage.find_objects(lab)[big - 1]
    bx0, bx1 = big_sl[1].start, big_sl[1].stop
    by0, by1 = big_sl[0].start, big_sl[0].stop
    near = min(h, w) * DETACH_MOST
    boxes = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        if k == big or sl is None:
            continue
        # その塊の中に、彩度の高い画素があるか
        part_sat = sat[lab == k]
        if part_sat.size == 0 or (part_sat > BLEED_SAT).mean() < 0.5:
            continue
        if sizes[k - 1] > 200:   # 大きな色の塊は別の物（花など）で、にじみではない
            continue
        box = (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)
        dx = max(bx0 - box[2], box[0] - bx1, 0)
        dy = max(by0 - box[3], box[1] - by1, 0)
        if max(dx, dy) <= near:
            boxes.append(box)
    share = 0.0
    if boxes:
        m = np.zeros_like(lab, dtype=bool)
        for (x0, y0, x1, y1) in boxes:
            m[y0:y1, x0:x1] |= (lab[y0:y1, x0:x1] > 0) & (lab[y0:y1, x0:x1] != big)
        share = float((m & (sat > BLEED_SAT)).sum()) / max(h * w, 1)
    return {"readable": True, "boxes": boxes, "count": len(boxes), "share": round(share, 4)}


def shadow_side_mask(image, lit: dict):
    """影の側（光源と反対の側）の人物の範囲を L の絵で返す。光源が読めなければ None"""
    import numpy as np
    from PIL import Image
    if not lit.get("readable"):
        return None
    m = silhouette(image)
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return None
    cx = xs.mean()
    cols = np.arange(m.shape[1])[None, :]
    side = (cols <= cx) if lit["dx"] > 0 else (cols > cx)
    hit = m & side
    if hit.sum() < 50:
        return None
    return Image.fromarray((hit * 255).astype("uint8"))


def paper_color(image):
    """紙の色（四隅の色の中央）。ゴミ・にじみを消すときに使う"""
    import numpy as np
    a = _np(image)
    h, w = a.shape[:2]
    k = max(2, min(w, h) // 20)
    corners = np.concatenate([a[:k, :k].reshape(-1, 3), a[:k, -k:].reshape(-1, 3), a[-k:, :k].reshape(-1, 3), a[-k:, -k:].reshape(-1, 3)])
    return tuple(int(v) for v in np.median(corners, axis=0))


def light(image) -> dict:
    """光源: 人物の左右・上下の明るさの差から、光の来る向きを決める。dx が正なら右から、dy が負なら上から"""
    import numpy as np
    lum = luminance(image)
    m = silhouette(image)
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return {"readable": False}
    cx, cy = xs.mean(), ys.mean()
    v = lum[ys, xs]
    dx = float(v[xs > cx].mean() - v[xs <= cx].mean()) if (xs > cx).any() and (xs <= cx).any() else 0.0
    dy = float(v[ys > cy].mean() - v[ys <= cy].mean()) if (ys > cy).any() and (ys <= cy).any() else 0.0
    return {"readable": True, "dx": round(dx, 1), "dy": round(dy, 1), "side": "右" if dx > 0 else "左"}


def shadows(image, lit: dict) -> dict:
    """影の向き: 光源と反対の側の明るさが光の側より暗いか（影が光より明るくなっていないか）、暗い画素の何割が影の側にあるか"""
    import numpy as np
    lum = luminance(image)
    m = silhouette(image)
    ys, xs = np.nonzero(m)
    if len(xs) < 50 or not lit.get("readable"):
        return {"readable": False}
    cx = xs.mean()
    v = lum[ys, xs]
    shade_side = (xs <= cx) if lit["dx"] > 0 else (xs > cx)
    dark = v < np.percentile(v, 30)
    share = float((dark & shade_side).sum()) / max(int(dark.sum()), 1)
    brighter = float(v[shade_side].mean() - v[~shade_side].mean()) if shade_side.any() and (~shade_side).any() else 0.0
    return {"readable": True, "shade_share": round(share, 3), "shade_minus_lit": round(brighter, 1)}


def shade_second(image, lit: dict, keep=None):
    """影の 2 段目: 光源と反対の側の、人物の中で一番暗い所だけを一段暗くする。keep（守る所、真の所）は変えない"""
    import numpy as np
    from PIL import Image
    a = _np(image).astype(np.float32)
    lum = luminance(image)
    m = silhouette(image)
    ys, xs = np.nonzero(m)
    if len(xs) < 50 or not lit.get("readable"):
        return image, 0
    cx = xs.mean()
    cols = np.arange(m.shape[1])[None, :]
    side = (cols <= cx) if lit["dx"] > 0 else (cols > cx)
    hit = m & side & (lum <= np.percentile(lum[m], SHADE2_PART * 100))
    if keep is not None:
        hit &= ~keep
    a[hit] *= SHADE2
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8")), int(hit.sum())


def eye_boxes(points: dict) -> list[tuple[int, int, int, int]]:
    if "left_eye" not in points or "right_eye" not in points:
        return []
    (lx, ly), (rx, ry) = points["left_eye"][:2], points["right_eye"][:2]
    r = max(3, int(abs(lx - rx) * 0.3))
    return [(int(x - r), int(y - r), int(x + r), int(y + r)) for x, y in ((lx, ly), (rx, ry))]


def catchlights(image, points: dict) -> dict:
    """目の光: 両目の囲みの中の一番明るい画素"""
    lum = luminance(image)
    boxes = eye_boxes(points)
    if not boxes:
        return {"readable": False}
    h, w = lum.shape
    best = []
    for x0, y0, x1, y1 in boxes:
        part = lum[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
        best.append(int(part.max()) if part.size else 0)
    return {"readable": True, "eye_max": best, "boxes": boxes}


def shrink_view(image) -> dict:
    """縮めて見る: 1/8 に縮め、人物と紙の明るさの差（主役が目立つか）"""
    from PIL import Image
    small = image.resize((max(8, image.width // SHRINK), max(8, image.height // SHRINK)), Image.BOX)
    m = silhouette(small)
    lum = luminance(small)
    if m.sum() < 4 or (~m).sum() < 4:
        return {"readable": False}
    return {"readable": True, "contrast": round(abs(float(lum[m].mean() - lum[~m].mean())), 1)}


def flip_view(image, box) -> dict:
    """反転して見る: 顔の囲みを左右に反転して重ね、差の平均（0〜1）。人は反転すると片側に寄った歪みに気づく"""
    import numpy as np
    from PIL import ImageOps
    if not box:
        return {"readable": False}
    x0, y0, x1, y1 = (int(v) for v in box)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return {"readable": False}
    face = image.convert("L").crop((x0, y0, x1, y1))
    a = np.asarray(face, dtype=np.float32)
    b = np.asarray(ImageOps.mirror(face), dtype=np.float32)
    return {"readable": True, "asym": round(float(np.abs(a - b).mean()) / 255, 3)}


def face_box(points: dict):
    """体の点から顔の囲み（目・耳・鼻）"""
    keys = [k for k in ("nose", "left_eye", "right_eye", "left_ear", "right_ear") if k in points]
    if len(keys) < 3:
        return None
    xs = [points[k][0] for k in keys]
    ys = [points[k][1] for k in keys]
    r = max(max(xs) - min(xs), 8) * 0.8
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return (cx - r, cy - r * 1.1, cx + r, cy + r * 1.2)


def wear_mask(image, protect_boxes=()):
    """服・髪・持ち物の工程で描いてよい所（L の絵）。部位分けがあれば髪・服・持ち物、無ければ人物の全体。顔・手の囲みは除く"""
    import numpy as np
    from PIL import Image, ImageDraw
    p = parts(image)
    if p is not None:
        m = np.isin(p, list(HAIR | WEAR))
    else:
        m = silhouette(image)
    m = _dilate(m, 3)
    mask = Image.fromarray((m * 255).astype("uint8"))
    d = ImageDraw.Draw(mask)
    for b in protect_boxes:
        d.rectangle([int(v) for v in b], fill=0)
    return mask, p is not None


# 描き重ねの崩れ（霞み・枠・色褪せ）。phase-bench（Animagine XL 4.0、5 工程の版）の線画の工程で、T2I-Adapter で構図の絵に沿って
# 描き直すと、黒が浮いて全体が白く霞み（暗い方から 5% の明るさ 84 → 120）、四辺に額縁のような枠が出て（縁と内側の差 17 → 45）、
# そのあとの工程も引き継いだ。描き重ねたら、前の工程の絵の色と明るさに合わせ、枠は前の絵の縁に戻し、それでも外れたら前の絵を使う
HAZE_MOST = 15        # 暗い方から 5% の明るさが、前の絵よりこれだけ浮いたら霞んでいる
FRAME_MOST = 10       # 縁の帯と内側の帯の明るさの差が、前の絵よりこれだけ大きくなったら枠が出ている
FADE_MOST = 0.75      # 彩度の平均が前の絵のこの割合を下回ったら色が褪せている
FLAT_MOST = 0.75      # 明るさのばらつきが前の絵のこの割合を下回ったら、ぼやけて平たくなっている


def tone(image) -> dict:
    """霞み・枠・色褪せを見る数字: 暗い方から 5% の明るさ（dark）、彩度の平均（sat）、縁の帯と内側の帯の明るさの差（frame）"""
    import numpy as np
    lum = luminance(image)
    sat = np.asarray(image.convert("RGB").convert("HSV"), dtype=np.float32)[..., 1]
    h, w = lum.shape
    b = max(4, min(h, w) // 40)
    border = np.concatenate([lum[:b].ravel(), lum[-b:].ravel(), lum[:, :b].ravel(), lum[:, -b:].ravel()])
    inner = np.concatenate([lum[b:3 * b].ravel(), lum[-3 * b:-b].ravel(), lum[:, b:3 * b].ravel(), lum[:, -3 * b:-b].ravel()])
    return {"dark": round(float(np.percentile(lum, 5)), 1), "contrast": round(float(lum.std()), 1), "lum": round(float(lum.mean()), 1), "sat": round(float(sat.mean()), 1),
            "frame": round(float(abs(border.mean() - inner.mean())), 1), "band": b}


def tone_flaws(now: dict, ref: dict) -> list[str]:
    out = []
    if now["dark"] - ref["dark"] > HAZE_MOST:
        out.append(f"白く霞んでいる（暗い所 {ref['dark']} → {now['dark']}）")
    if now["frame"] - ref["frame"] > FRAME_MOST:
        out.append(f"四辺に枠が出ている（縁の差 {ref['frame']} → {now['frame']}）")
    if now.get("contrast") is not None and ref.get("contrast") and now["contrast"] < ref["contrast"] * FLAT_MOST:
        out.append(f"ぼやけて平たい（明るさのばらつき {ref['contrast']} → {now['contrast']}）")
    if ref["sat"] > 8 and now["sat"] < ref["sat"] * FADE_MOST:
        out.append(f"色が褪せている（彩度 {ref['sat']} → {now['sat']}）")
    return out


def match_colors(image, ref):
    """色合わせ: 描き重ねた絵の明るさ（輝度）を、前の工程の絵の範囲（暗い方 2% と明るい方 98%）に線形で合わせ、色の差（彩度）は
    明るさを広げた分だけ広げて、狭めない。R・G・B を別々に合わせる形は、白い背景で 3 色の範囲が 255 にそろい、色が灰色に寄った
    （phase-bench の下描きで彩度 20.4 → 12.9）。分布をそのまま写す形（分位の対応）は、平らな背景に色の粒を出したので使わない"""
    import numpy as np
    from PIL import Image
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    r = np.asarray(ref.convert("RGB").resize(image.size), dtype=np.float32)
    wts = np.array([0.299, 0.587, 0.114], np.float32)
    y, yr = a @ wts, r @ wts
    lo, hi = np.percentile(y, [2, 98])
    rlo, rhi = np.percentile(yr, [2, 98])
    scale = min(max((rhi - rlo) / max(hi - lo, 1.0), 0.5), 2.5)
    y2 = (y - lo) * scale + rlo
    out = y2[..., None] + (a - y[..., None]) * max(scale, 1.0)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def restore_border(image, ref, band: int):
    """縁の帯を前の絵に戻す（内側へ帯の幅でぼかしてつなぐ）"""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = image.size
    m = Image.new("L", (w, h), 255)
    ImageDraw.Draw(m).rectangle([band * 2, band * 2, w - 1 - band * 2, h - 1 - band * 2], fill=0)
    m = m.filter(ImageFilter.GaussianBlur(band))
    return Image.composite(ref.convert("RGB").resize((w, h)), image.convert("RGB"), m)


def _fix_dark_level(out, ref):
    """霞み（暗い所が浮いた）を直す。暗い所の明るさ（5%点）を、検品の上限（前の絵 + HAZE_MOST）ぎりぎりまで暗くする。
    前の絵の暗さまで完全に戻すと、中間の色まで暗くなりすぎた。描き重ねの内容（新しく描いた物）は残し、浮いた暗い所だけ暗くする。
    明るい所は変えない"""
    import numpy as np
    from PIL import Image
    a = np.asarray(out.convert("RGB"), dtype=np.float32)
    r = np.asarray(ref.convert("RGB"), dtype=np.float32)
    w = np.array([0.299, 0.587, 0.114], np.float32)
    ya, yr = a @ w, r @ w
    da, dr = float(np.percentile(ya, 5)), float(np.percentile(yr, 5))
    target = dr + HAZE_MOST - 1.0   # 検品を通るぎりぎりの暗さ（完全に戻さず、直す分を最小にする）
    if da <= target or da <= 0:
        return out
    ratio = target / da
    # 暗い所だけ暗くする（5%点で 1、5%点の 2 倍で 0）。明るい所・中間の色は変えない
    t = np.clip((2 * da - ya) / da, 0, 1)
    scale = 1.0 - t * (1.0 - ratio)
    lum_new = ya * scale
    factor = np.where(ya > 1, lum_new / np.maximum(ya, 1), 1.0)
    return Image.fromarray(np.clip(a * factor[..., None], 0, 255).astype("uint8"))


def guard(image, ref, mask=None) -> tuple:
    """描き重ねたあとの守り。描き重ねた絵に霞み・枠・色褪せが無ければ、そのまま使う（合わせない）。
    あれば色合わせ → 枠が出ていれば縁を戻す → それでも残れば前の絵を使う。崩れの無い絵にも色合わせを掛けていた間は、
    合わせで色が褪せ、描き重ねを捨てていた（phase-bench、種 7）。
    霞みだけが残ったときは、暗い所を暗くして直し、描き重ねの内容を残す。直らなければ前の絵を使う。
    mask（L）を渡したときは、その中だけを合わせ、外は前の絵のまま（囲みの外は 1 画素も変えない）。返すのは (絵, 記録)"""
    from PIL import Image
    ref = ref.convert("RGB").resize(image.size)
    image = image.convert("RGB")
    t_ref, t_raw = tone(ref), tone(image)
    raw_flaws = tone_flaws(t_raw, t_ref)
    out = image
    if raw_flaws:
        out = match_colors(image, ref)
        if tone(out)["frame"] - t_ref["frame"] > FRAME_MOST:
            out = restore_border(out, ref, t_ref["band"])
    if mask is not None:
        out = Image.composite(out, ref, mask.convert("L").resize(image.size))
    t_out = tone(out)
    left = tone_flaws(t_out, t_ref)
    dehazed = False
    if left and any("霞ん" in f for f in left):
        fixed = _fix_dark_level(out, ref)
        t_fixed = tone(fixed)
        left_fixed = tone_flaws(t_fixed, t_ref)
        if len(left_fixed) < len(left):
            out, t_out, left = fixed, t_fixed, left_fixed
            dehazed = True
    rec = {"ref": t_ref, "raw": t_raw, "out": t_out, "raw_flaws": raw_flaws, "matched": bool(raw_flaws), "left": left,
           "kept_ref": bool(left), "dehazed": dehazed}
    return (ref if left else out), rec
