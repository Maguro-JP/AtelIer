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
DUST_PATTERN_MIN = 8       # ゴミ: 同じくらいの大きさの小さい塊がこれ以上あれば、ゴミではなく模様（星・雪・質感）（私の推測）
DUST_PATTERN_SPAN = 0.25   # ゴミ: 模様とみなすには、塊の集まりが絵の幅・高さのこの割合以上に広がっていること（私の推測）。一か所に固まった欠片は模様ではない
DETAIL_RANGE = 24          # ディテール: 局所の明暗の変化がこれを超えた画素をディテールとする（私の推測）
DETACH_MOST = 0.08         # 位置ずれ: 主役から離れた塊が、短い辺のこの割合より近くにあれば体から離れた部位（私の推測）
DETACH_ERASE_MOST = 0.06   # 位置ずれ: 枠の長い辺が短い辺のこの割合以下なら、部位ではなく欠片とみなして線画で消して扱う（私の推測）
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
    返すのは (絵, 変えた画素の数)。
    対応する検品（lines の weight）が通っている線には掛けない。太らせるのは「線の強弱が無い」と
    検品で出たときだけの直しで、清書（clean_lines）が検品を見ずに毎回掛けると、正常な線画まで
    狙いの太さ（2r+3）に膨らまされて壊れる（利用者の指摘、2026-11-27）"""
    import numpy as np
    from PIL import Image
    # 対応する検品（lines の weight）と同じ物差しを、ここで直接測る。lines() を呼ぶと
    # 検品の数え直しになり、流れの中で測る回数が変わってしまうので呼ばない
    _lum = luminance(image)
    _m = silhouette(image)
    if _m.sum() >= 50:
        _filled = _filled_silhouette(image)
        _band = _dilate(_filled, 1) & ~_erode(_filled, 2)
        _dark = _lum <= np.percentile(_lum[_m], 20)
        if _band.sum() and float((_band & _dark).sum()) / max(int(_band.sum()), 1) >= LINE_WEIGHT_LEAST:
            return image, 0   # 外の輪郭に強弱がもうある。正常な線は触らない
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
    # 既に十分太い線は、これ以上太らせない。太らせる直しを繰り返すたびに太り続けて、
    # 正常な線画が 10 倍ぐらいの太さになった（利用者の指摘）。今の線の太さは、暗い線の
    # 中での「線でない所までの距離」から見積もる（細長い線では、平均距離の 4 倍が太さの目安）。
    # 狙いの太さ（細い線 2 画素 + 両側に r ずつ）に達していたら、膨らませるのは止める
    thick = np.zeros_like(hit)
    if hit.any():
        from scipy import ndimage
        dist = ndimage.distance_transform_edt(dark & m)
        # 太さの見積もりは、暗い画素ぜんぶで見る。輪郭の帯の画素だけで見ると、線の
        # 縁の浅い所ばかり拾って太さを浅く見積もり、太らせる処理を何度も重ねて
        # 線が極太になった（利用者の指摘）
        width_now = 4.0 * float(dist[dark & m].mean())
        if width_now < 2 * r + 3:
            thick = _dilate(hit, r) & ~hit   # 線の周り（内側と外側の紙）を太らせる。内側の細い線は太らせない
    if thick.any() and hit.any():
        line_col = np.median(a[hit], axis=0)   # 線の色（暗くした外の輪郭の線の色の中央）
        a[thick] = line_col
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8")), int(hit.sum() + thick.sum())


def line_like(image) -> bool:
    """線画らしい絵かどうか（紙の白が大半で、中間の灰色が少なく、色が付いていない）。

    色の上に乗せてよい線レイヤーは、本物の線画だけ。色の付いた絵や灰色の
    面が多い絵を乗せると、絵全体がその絵の暗さで沈む（乗算は線画の前提で
    しか正しくない）。判定は、明るさ 40〜200 の中間の割合と、色の濃さの平均。
    """
    import numpy as np
    a = _np(image).astype(np.float32)
    lum = luminance(image).astype(np.float32)
    mid = float(((lum > 40) & (lum < 200)).mean())
    sat = float((a.max(axis=2) - a.min(axis=2)).mean())
    return mid <= 0.10 and sat <= 15.0


def strip_own_lines(color, line):
    """色の絵が自分で描いた線を消し、周りの色で埋めた絵を返す。

    下塗りの描き重ね（img2img）は色だけでなく線も描き直す。その線は清書の線より
    太く・ずれていることが多く、線レイヤーを乗算で乗せる合成（over_lines）は色の
    暗さを消せないので、結果の線は色の線と清書の線が合わさった太さになって壊れる
    （利用者の目撃、2026-11-27: 下塗りの描く工程で線が太くなる）。
    消すのは、線レイヤーに無い暗い細い線だけ。線レイヤーにもある暗さ（清書の線の
    位置）と、太い暗い塊（髪の束のような色の面）は、色の一部として残す"""
    import numpy as np
    from PIL import Image
    if color.size != line.size:
        line = line.convert("RGB").resize(color.size)
    dark_c = luminance(color) < 128
    if not dark_c.any():
        return color
    dark_l = luminance(line) < 128
    near = _dilate(dark_l, 2)   # 清書の線と、その周りの滲み・わずかなずれは残す
    stray = dark_c & ~near
    if not stray.any():
        return color
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ、線の切り分けができないのでそのまま返す
        return color
    lab, n = ndimage.label(stray)
    if not n:
        return color
    dist = ndimage.distance_transform_edt(stray)
    maxd = ndimage.maximum(dist, lab, range(1, n + 1))
    filled_l = _filled_silhouette(line)
    near2 = _dilate(near, 2)
    thin = []
    for k in range(n):
        if maxd[k] > 3:
            continue   # 一番太い所でも線らしい細さの塊だけ
        comp = lab == k + 1
        # 消すのは、描き直された線らしい物だけ: 清書の線に接しているか、主役の輪郭の
        # 内側にある物。背景に離れてある暗い点はゴミで、清書よりあとでは消さない
        # （ゴミ取りは清書だけ、という利用者の規則）。数えるだけにする
        if (comp & near2).any() or (comp & filled_l).sum() > comp.sum() / 2:
            thin.append(k + 1)
    if not thin:
        return color
    # 埋めるのは、はみ出した線に、清書の線の周りにある色自身の暗部も加えた範囲。
    # 周りの暗部を種に残すと、その暗い色が横に写って線が残る。清書の線の位置の
    # 色は、線レイヤーを乗せれば黒くなるので要らない
    keep = np.isin(lab, thin) | (dark_c & near)
    return erase_fill(color, Image.fromarray((keep * 255).astype("uint8")))


def over_lines(color, line):
    """色のレイヤーの上に、線のレイヤーを乗せて合成する（乗算）。

    線の所は線画の暗さがそのまま残り、線の無い所（紙の白）は色がそのまま
    出る。色を線画に描き重ねるだけだと、色の工程が線を薄くしてしまう
    （検証 45696035067 で下塗りが良い線画を壊した）。線を別レイヤーに
    残して上に乗せれば、色を塗り直しても線は壊れない。
    """
    import numpy as np
    from PIL import Image
    c = _np(color).astype(np.float32)
    ln = _np(line.convert("RGB").resize(color.size)).astype(np.float32) / 255.0
    return Image.fromarray(np.clip(c * ln, 0, 255).astype("uint8"))


def underlay(line, rough, strength=0.35):
    """線のレイヤーの下に、ラフを薄くして敷いた、見せるための合成。

    ラフは線の紙の色へ寄せて薄くし（暗さが strength の割合だけ残る）、線とは
    画素ごとに暗い方を取る。線の画素はそのまま残り、線の無い所ではラフが
    薄く見える。人がラフを透かして、その上に線を描く見え方に合わせたもの。
    検品や次の工程に使う絵ではない（そちらは線のレイヤーそのものを使う）。
    """
    import numpy as np
    from PIL import Image
    ln = _np(line.convert("RGB")).astype(np.float32)
    rf = _np(rough.convert("RGB").resize(line.size)).astype(np.float32)
    paper = np.array(paper_color(line), dtype=np.float32)
    faded = paper + (rf - paper) * strength
    return Image.fromarray(np.clip(np.minimum(ln, faded), 0, 255).astype("uint8"))


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


def _dust_labels(image):
    """ゴミとみなす成分の番号の一覧と、成分の表を返す。主役・実の線から離れた所に孤立した
    小さな塊だけをゴミとする。主役の中にある小さな塊（目・ボタン・模様）や、線の近くの欠片は
    ディテールなのでゴミにしない（必要な線までゴミとして消される事故の再発防止）。
    主役が読めなければ None"""
    import numpy as np
    got = _components(image)
    if got is None:
        return None
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return None
    h, w = lab.shape
    limit = max(3, min(h, w) * DUST_SIZE_MOST)
    margin = max(3, min(h, w) // 50)
    from scipy import ndimage
    anchor = np.isin(lab, [k for k in range(1, len(sizes) + 1) if sizes[k - 1] > DUST_MAX_PIXELS])
    inside = ndimage.binary_fill_holes(anchor) if anchor.any() else np.zeros(lab.shape, bool)
    dist = ndimage.distance_transform_edt(~anchor) if anchor.any() else None
    cand = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        if k == big or sl is None or sizes[k - 1] > DUST_MAX_PIXELS:
            continue
        box = (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)
        if max(box[3] - box[1], box[2] - box[0]) > limit:
            continue
        comp = lab[sl] == k
        if inside[sl][comp].any():
            continue   # 主役の中の小さな塊はディテール（目・ボタン・模様）
        if dist is not None and float(dist[sl][comp].min()) <= margin:
            continue   # 実の線の近くの欠片もディテール（線の一部）
        cand.append(k)
    if len(cand) >= DUST_PATTERN_MIN:
        # 同じくらいの大きさの小さい塊が、画面に広く散らばってたくさんあるのは、
        # ゴミではなく模様（星・雪・雨・背景の質感）。模様と同じ大きさの帯にある塊は
        # ゴミにしない。大きさの違う塊だけが、模様に紛れた本当のゴミとして残る。
        # 一か所に固まった塊（髪の線の欠片など）は広がっていないので模様にしない
        objs = ndimage.find_objects(lab)
        cxs = [(objs[k - 1][1].start + objs[k - 1][1].stop) / 2 for k in cand]
        cys = [(objs[k - 1][0].start + objs[k - 1][0].stop) / 2 for k in cand]
        if (max(cxs) - min(cxs) >= w * DUST_PATTERN_SPAN
                and max(cys) - min(cys) >= h * DUST_PATTERN_SPAN):
            ordered = sorted(sizes[k - 1] for k in cand)
            med = ordered[len(ordered) // 2]
            cand = [k for k in cand if not (med / 2 <= sizes[k - 1] <= med * 2)]
    return lab, cand


def dust(image) -> dict:
    """ゴミ: 主役から離れた所に孤立した、小さな暗い塊（点・汚れ）。主役の中や線の近くの
    小さな塊はディテールなので数えない。主役が無ければ読めない。
    返すのは {"readable", "boxes", "count"}。boxes は (x0, y0, x1, y1)"""
    got = _dust_labels(image)
    if got is None:
        return {"readable": False, "boxes": [], "count": 0}
    lab, keep = got
    from scipy import ndimage
    objs = ndimage.find_objects(lab)
    boxes = []
    for k in keep:
        sl = objs[k - 1]
        boxes.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
    return {"readable": True, "boxes": boxes, "count": len(boxes)}


def dust_mask(image):
    """ゴミの塊そのものの囲み（L の絵）。dust と同じ物差しで選んだ塊の画素だけを囲む。
    枠の円で囲むと塊より何倍も広くなり、細い線の欠片が集まった所（顔など）では円が重なって広い面になる。
    その面を紙の色で消すと、絵が平らな塊に覆われる（検証 45696035067 の仕上げ）。
    主役が読めなければ None"""
    import numpy as np
    from PIL import Image
    got = _dust_labels(image)
    if got is None:
        return None
    lab, keep = got
    m = np.isin(lab, keep) if keep else np.zeros(lab.shape, bool)
    return Image.fromarray((m * 255).astype("uint8"))


def local_texture(image, mask) -> float:
    """囲みの中の明るさのばらつき（標準偏差）。線や質感がある所は大きく、
    塗りつぶされた所は 0 に近くなる。直しが形を塗りつぶしていないかを見る"""
    import numpy as np
    lum = luminance(image).astype(np.float32)
    m = np.asarray(mask.convert("L")) > 127 if mask is not None else None
    if m is None or m.shape != lum.shape or not m.any():
        return 0.0
    return float(lum[m].std())


def new_specks(before, after) -> int:
    """前には無かった、暗い小さな塊（点・短い線）の数。仕上げ系の描き重ねが
    ゴミの線を散らかしていないかを見る（利用者の指摘: ゴミの線をばらまいて、
    壊すことを仕上げだと思ってる）。既にある暗さに重なる・つながる物は数えない"""
    import numpy as np
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ数えられない（0 を返し、止めない）
        return 0
    lb = luminance(before) < 80
    la = luminance(after) < 80
    new = la & ~ndimage.binary_dilation(lb, iterations=1)
    lab, n = ndimage.label(new)
    if not n:
        return 0
    sizes = ndimage.sum(new, lab, range(1, n + 1))
    return int((sizes <= DUST_MAX_PIXELS).sum())


def new_bumps(before, after) -> int:
    """滑らかだった所に新しくできた、小さな強い変化の塊の数。ディテールの
    描き重ねが、肌などの滑らかな面にブツブツ（でき物）を足していないかを見る。
    滑らかな所への強い小さな変化は、質感ではなく汚れ・でき物（利用者の指摘）"""
    import numpy as np
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ数えられない（0 を返し、止めない）
        return 0
    a = np.asarray(before.convert("RGB"), np.int16)
    b = np.asarray(after.convert("RGB"), np.int16)
    diff = np.abs(a - b).max(axis=2) > 36
    lum = luminance(before).astype(np.float32)
    mean = ndimage.uniform_filter(lum, size=5)
    var = ndimage.uniform_filter(lum * lum, size=5) - mean * mean
    smooth = var < 36.0   # 前の絵で滑らかだった所（ばらつき 6 未満）
    mask = diff & smooth
    lab, n = ndimage.label(mask)
    if not n:
        return 0
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return int(((sizes >= 2) & (sizes <= DUST_MAX_PIXELS)).sum())


def grain(image) -> float:
    """色の粒（ブツブツ）の割合。3x3 の中央値と大きく違う画素の割合で測る。
    下塗りで色をのせたはずが粒だらけになっていないかを見る（利用者の指摘）"""
    import numpy as np
    from PIL import ImageFilter
    im = image.convert("RGB")
    a = np.asarray(im, np.int16)
    med = np.asarray(im.filter(ImageFilter.MedianFilter(3)), np.int16)
    return float((np.abs(a - med).max(axis=2) > 24).mean())


def flatten_base(image):
    """下塗りの色を平らにする。面の中で一番多い色に寄せるので、1〜2 画素の粒は消え、
    面の色と境目は残る。下塗りはベタ塗りが正しい（粒は影や質感の工程で付ける）"""
    from PIL import ImageFilter
    return image.convert("RGB").filter(ImageFilter.ModeFilter(5))


def blotch_mask(image):
    """下塗りの面にできた斑点（でき物のような塊）の囲み（L の絵）と数を返す。無ければ (None, 0)。

    粒の物差し（grain）は 3x3 の中央値との差なので、縁のくっきりした塊は中の画素の
    中央値が塊自身の色になって測れない。ここでは平らにした絵と比べて、滑らかだった
    所にできた強い変化の塊を、その塊の形（穴を埋めた形）で見る。
    目の光のような紙に近い白と、線のインクのような暗い塊は、斑点ではなく絵の一部
    として数えない。細い線（口など中身の無い形）も数えない"""
    import numpy as np
    from PIL import Image, ImageFilter
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ測れない（斑点は無いことにする）
        return None, 0
    # 参照は、面の色だけを残した絵（ModeFilter(9)）。斑点より小さい窓で平らにすると
    # 斑点の芯が残って差が出ず、滑らかさで絞ると斑点の縁そのものが「滑らかでない」に
    # なるので、切り分けは形（面積・中身・色）だけで行う
    flat = image.convert("RGB").filter(ImageFilter.ModeFilter(9))
    a = np.asarray(flat, np.int16)
    b = np.asarray(image.convert("RGB"), np.int16)
    cand = np.abs(a - b).max(axis=2) > 36
    lab, n = ndimage.label(cand)
    if not n:
        return None, 0
    lum = luminance(image)
    keep = np.zeros(cand.shape, bool)
    count = 0
    for k in range(1, n + 1):
        comp = lab == k
        filled = ndimage.binary_fill_holes(comp)
        area = int(filled.sum())
        if area < 9 or area > 1024:
            continue
        if ndimage.distance_transform_edt(filled).max() < 3:
            continue   # 中身の無い細い形（線の一部）
        px = b[filled]
        if px.min(axis=1).mean() > 240:
            continue   # 紙に近い白（目の光など）は斑点ではない
        if lum[filled].mean() < 50:
            continue   # インクの暗さ（線の一部）は斑点ではない
        keep |= filled
        count += 1
    if not count:
        return None, 0
    return Image.fromarray((keep * 255).astype("uint8")), count


def area_fill(image, mask):
    """囲みの中を、周りの面の色で埋める。erase_fill と違い、種は主役の範囲にある
    線でない色だけにする。輪郭や線の黒を種にすると、一番近いのが線というだけで
    黒が内側に広がってしまう（塗り残しを埋めたら線の黒で汚れた。検証で確認）。
    囲みの外は変えない"""
    import numpy as np
    from PIL import Image
    im = image.convert("RGB")
    m = np.asarray(mask.convert("L").resize(im.size)) > 0
    if not m.any():
        return im
    seeds = ~m & silhouette(im) & (luminance(im) >= 80)
    if not seeds.any():
        return erase_fill(im, mask)
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001
        return erase_fill(im, mask)
    _dist, inds = ndimage.distance_transform_edt(~seeds, return_indices=True)
    arr = np.asarray(im).copy()
    ys, xs = np.nonzero(m)
    arr[ys, xs] = arr[inds[0][ys, xs], inds[1][ys, xs]]
    return Image.fromarray(arr)


def coverage_mask(image):
    """塗り残しの囲みと割合を返す: 主役の輪郭の内側なのに、紙の色のままの所。
    色の数を数える範囲（紙でない所）には、色の付いていない所は入らないので、
    今まで塗り残しは測れなかった。輪郭で囲まれた内側を埋めた形と比べて測る。
    囲みが無ければ (None, 0.0)"""
    import numpy as np
    from PIL import Image
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001
        return None, 0.0
    sil = silhouette(image)
    if sil.sum() < 50:
        return None, 0.0
    filled = ndimage.binary_fill_holes(sil)
    hole = filled & ~sil
    if not hole.any():
        return None, 0.0
    share = float(hole.sum()) / max(int(filled.sum()), 1)
    return Image.fromarray((hole * 255).astype("uint8")), share


def posterize_base(image, most):
    """色が散っている下塗りを、近い色同士を寄せて色数を減らした絵にする。
    色の差の崩れには、今まで模型の描き直ししか手が無く、描き直すたびに色数が
    変わって責任の判定で戻され、直し切れずに未完成で終わっていた（利用者の報告）。
    主役の範囲（紙でない所）の中で、2% 以上を占める色が most 以下になるまで寄せる。
    紙の所と、主役の外は変えない"""
    import numpy as np
    from PIL import Image
    im = image.convert("RGB")
    m = silhouette(im)
    if m.sum() < 50:
        return im
    q = im.quantize(colors=32, method=Image.MEDIANCUT)
    _pal = (q.getpalette() or [])[:96]
    pal = np.zeros(96, np.uint8)
    pal[:len(_pal)] = _pal
    pal = pal.reshape(32, 3).astype(np.float32)
    idx = np.asarray(q)
    counts = np.bincount(idx[m].ravel(), minlength=32).astype(np.float32)
    total = max(float(counts.sum()), 1.0)
    big = [i for i in range(32) if counts[i] / total >= 0.02]
    if len(big) <= most:
        return im
    order = sorted(big, key=lambda i: -counts[i])
    step = 24.0
    centers = None
    while step <= 200.0:
        centers = []   # (中心の色, その色に寄せる元の色の番号)
        for i in order:
            for c in centers:
                if np.abs(pal[i] - c[0]).max() <= step:
                    c[1].append(i)
                    break
            else:
                centers.append([pal[i].copy(), [i]])
        if len(centers) <= most:
            break
        step *= 1.5
    arr = np.asarray(im).astype(np.float32)
    for center, members in centers or []:
        wsum = sum(counts[i] for i in members)
        col = sum(pal[i] * counts[i] for i in members) / max(wsum, 1.0)
        sel = m & np.isin(idx, members)
        arr[sel] = col
    from PIL import Image as _Image
    return _Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def detail_density(image) -> dict:
    """ディテールの量: 主役の内側で、隣の画素との明暗の差が強い画素の割合（density）と、
    その差の平均（sharp: 線や質感の鋭さ。ぼやけると下がる）。
    質感・小さい印・汚しなどの細部が多いほど大きい。主役が読めなければ readable は False。
    返すのは {"readable", "density", "sharp"}"""
    import numpy as np
    got = _components(image)
    if got is None:
        return {"readable": False, "density": None, "sharp": None}
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return {"readable": False, "density": None, "sharp": None}
    from scipy import ndimage
    anchor = np.isin(lab, [k for k in range(1, len(sizes) + 1) if sizes[k - 1] > DUST_MAX_PIXELS])
    inside = ndimage.binary_fill_holes(anchor) if anchor.any() else anchor
    if not inside.any():
        return {"readable": False, "density": None, "sharp": None}
    g = np.asarray(image.convert("L"), dtype=float)
    grad = np.maximum(np.abs(np.diff(g, axis=0, prepend=g[:1])),
                      np.abs(np.diff(g, axis=1, prepend=g[:, :1])))
    det = (grad > DETAIL_RANGE) & inside
    return {"readable": True,
            "density": round(float(det.sum() / inside.sum()), 3),
            "sharp": round(float(grad[inside].mean()), 2)}


def enhance_detail(image):
    """質感の締め直し: 主役の内側だけ、輪郭と質感を締める純粋な加工。
    新しい物は描かないし、何も消さない。模型の描き直しと違ってゴミを撒かない"""
    import numpy as np
    from PIL import Image, ImageFilter
    sharp = image.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    got = _components(image)
    if got is None:
        return sharp
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return sharp
    from scipy import ndimage
    anchor = np.isin(lab, [k for k in range(1, len(sizes) + 1) if sizes[k - 1] > DUST_MAX_PIXELS])
    inside = ndimage.binary_fill_holes(anchor) if anchor.any() else anchor
    if not inside.any():
        return sharp
    a = np.asarray(image).astype(float)
    b = np.asarray(sharp).astype(float)
    out = np.where(inside[..., None], b, a)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def edge_leftovers(before, after, mask):
    """消して描き直す直しの後始末: 囲みの縁の外に残った、消した物の欠片の囲み（L の絵）を返す。
    欠片 = 直す前の絵で囲みに掛かっていた物の成分が、直した絵でも囲みの外にだけ残り、
    囲みの中の新しい絵につながっていない小さな塊。線が縁を越えて続いている物は、
    囲みの中につながっているので欠片にしない。無ければ None"""
    import numpy as np
    if before is None or after is None or mask is None or before.size != after.size:
        return None
    got_b = _components(before)
    got_a = _components(after)
    if got_b is None or got_a is None:
        return None
    lab_b, sizes_b, big_b = got_b
    lab_a, sizes_a, big_a = got_a
    if big_a == 0 or len(sizes_a) == 0:
        return None
    from scipy import ndimage
    m = np.asarray(mask.convert("L")) > 0
    if not m.any():
        return None
    ring = ndimage.binary_dilation(m, iterations=3) & ~m
    out = np.zeros(lab_a.shape, bool)
    n = 0
    for k, sl in enumerate(ndimage.find_objects(lab_a), 1):
        if sl is None or sizes_a[k - 1] > DUST_MAX_PIXELS:
            continue
        comp_full = lab_a == k
        if comp_full[m].any():
            continue   # 囲みの中の新しい絵につながっている（線の続き）ので残す
        if not comp_full[ring].any():
            continue   # 縁の近くにある物だけを見る
        comp = lab_a[sl] == k
        prev = lab_b[sl][comp]
        hit = False
        for pk in np.unique(prev):
            if pk and (lab_b == pk)[m].any():
                hit = True
                break
        if not hit:
            continue   # 直す前から囲みと無関係だった物は、直しの残りではない
        out |= comp_full
        n += 1
    if not n:
        return None
    from PIL import Image
    return Image.fromarray((out * 255).astype("uint8"))


def line_pixels(image):
    """絵の中の「線らしい」暗い画素（線の芯、lum < 40）。線のレイヤーにも、線でない
    暗い塊（崩れの印や塗りの塊）が混ざることがある。塊は後の直しで正しく消える物
    なので、線の残りを数える参照からは外す（塊: 辺が太く、枠の中をほぼ埋めている成分）。
    線の縁（薄い画素）は描き重ねで明るくなってよいので、参照は芯だけにする"""
    import numpy as np
    from scipy import ndimage
    dark = luminance(image) < 40
    if not dark.any():
        return dark
    lab, n = ndimage.label(dark)
    if n == 0:
        return dark
    edt = ndimage.distance_transform_edt(dark)
    keep = np.ones(n + 1, dtype=bool)
    objs = ndimage.find_objects(lab)
    for idx, sl in enumerate(objs, 1):
        comp = lab[sl] == idx
        area = int(comp.sum())
        if area < 16:
            continue
        bbox_area = comp.size
        if area / bbox_area > 0.7 and float(edt[lab == idx].max()) >= 3:
            keep[idx] = False   # 枠を埋める太い塊は線ではない
    keep[0] = False
    return keep[lab]


def restore_missing_lines(source, after):
    """source（清書のレイヤー）の線のうち、after で消えている部分だけを戻す。
    戻すのは、残っている線に両端がつながる「途切れた線分」だけ。近くに線が
    無い孤立した部分は戻さない（描き直しで位置が変わった線を、二重に描かないため）。
    返すのは (絵, 戻した画素数)"""
    import numpy as np
    if source is None or after is None or source.size != after.size:
        return after, 0
    from scipy import ndimage
    dark_s = luminance(source) < 80
    dark_a = luminance(after) < 80
    missing = dark_s & ~dark_a
    if not missing.any():
        return after, 0
    lab_m, n_m = ndimage.label(missing)
    if n_m == 0:
        return after, 0
    touch = ndimage.binary_dilation(dark_a, iterations=1)
    joined = np.unique(lab_m[touch & (lab_m > 0)])
    if len(joined) == 0:
        return after, 0
    keep = np.isin(lab_m, joined)
    n = int(keep.sum())
    if not n:
        return after, 0
    a = np.asarray(after).astype(float)
    s = np.asarray(source).astype(float)
    out = np.where(keep[..., None], np.minimum(a, s), a)
    from PIL import Image
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8")), n


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


def detached_erasure_mask(image):
    """位置ずれのうち、小さい欠片だけの囲み（L の絵）。線画の段階では、部位とは言えない
    小さい離れた欠片は模型で描き直さず消して扱う（清書までの直しは「消して描き直す」
    レベル、という利用者の規則。模型の描き直しは 1 回に何分かかり、欠片の数だけ
    繰り返すと検証が制限時間に終わらない）。大きい離れた物は部位かもしれないので
    消さない。ゴミの大きさの物はゴミの方で扱う。欠片が無ければ None"""
    import numpy as np
    got = _components(image)
    if got is None:
        return None
    lab, sizes, big = got
    if big == 0 or len(sizes) == 0:
        return None
    h, w = lab.shape
    from scipy import ndimage
    objs = ndimage.find_objects(lab)
    big_sl = objs[big - 1]
    bx0, bx1 = big_sl[1].start, big_sl[1].stop
    by0, by1 = big_sl[0].start, big_sl[0].stop
    near = min(h, w) * DETACH_MOST
    dust_limit = max(3, min(h, w) * DUST_SIZE_MOST)
    small_most = min(h, w) * DETACH_ERASE_MOST
    keep = []
    for k, sl in enumerate(objs, 1):
        if k == big or sl is None:
            continue
        box = (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)
        long_side = max(box[3] - box[1], box[2] - box[0])
        if sizes[k - 1] <= DUST_MAX_PIXELS and long_side <= dust_limit:
            continue   # ゴミの大きさの物は、ゴミの方で扱う
        dx = max(bx0 - box[2], box[0] - bx1, 0)
        dy = max(by0 - box[3], box[1] - by1, 0)
        if max(dx, dy) > near:
            continue   # 主役から遠い物は別の物
        if long_side > small_most:
            continue   # 大きい物は部位かもしれない。消さずに描き直す方へ回す
        keep.append(k)
    if not keep:
        return None
    from PIL import Image
    return Image.fromarray((np.isin(lab, keep) * 255).astype("uint8"))


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


def erase_fill(image, mask):
    """囲んだ所を消す。紙の色（四隅の中央）1 色で平らに塗りつぶすのではなく、
    囲みの外の色だけを種に、色合いを内側へ広げて流し込む。消す物自体の色は
    混ぜない（混ぜると、消したはずの線や塊がにじんで残る）。
    1 色で塗ると、色や影や階調のある所では塗りつぶした塊に見える
    （利用者の指摘: 「消すが上から塗りつぶす動きをしてる」）。
    広げ方は、平均を取らずに一番近い外の画素の色をそのまま写す。平均で広げると
    色同士が混ざって滲み、消しゴムでこすった汚れに見える（利用者の指摘:
    「滲ませてる」「下手な消しゴム」）。写すだけなら、色は混ざらない。
    囲みの外は変えない。返すのは消したあとの絵"""
    import numpy as np
    from PIL import Image
    im = image.convert("RGB")
    m = np.asarray(mask.convert("L").resize(im.size)) > 0
    if not m.any():
        return im
    if not (~m).any():   # 囲みが絵全体（写す種が無い）なら紙の色で埋める
        out = im.copy()
        out.paste(paper_color(im), (0, 0) + im.size)
        return out
    try:
        from scipy import ndimage
    except Exception:   # noqa: BLE001  scipy が無ければ、下の平均で広げる方へ
        ndimage = None
    if ndimage is not None:
        _dist, inds = ndimage.distance_transform_edt(m, return_indices=True)
        src = np.asarray(im)
        out = src.copy()
        out[m] = src[inds[0][m], inds[1][m]]
        return Image.fromarray(out)
    h, w = m.shape
    work = np.asarray(im).astype(np.float32)
    known = ~m
    work[m] = 0.0
    for _ in range(512):   # 囲みの縁から 1 画素ずつ内側へ広げる。たいていの囲みは数回で埋まる
        if known.all():
            break
        wp = np.pad(work, ((1, 1), (1, 1), (0, 0)), mode="edge")
        kp = np.pad(known, ((1, 1), (1, 1)), mode="constant", constant_values=True)
        s = np.zeros_like(work)
        c = np.zeros(m.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            kv = kp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            s += wp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] * kv[..., None]
            c += kv
        new = (~known) & (c > 0)
        if not new.any():
            break
        work[new] = s[new] / c[new][..., None]
        known |= new
    if not known.all():   # 広すぎて広げきれなかった所は紙の色で埋める
        work[~known] = np.array(paper_color(im), dtype=np.float32)
    return Image.fromarray(np.clip(work, 0, 255).astype("uint8"))


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


def on_subject_regions(image, regions):
    """検品の枠のうち、主役の絵に重なっている物だけを返す。

    背景の何も無い所を「崩れた手」と読んだ枠をそのまま直すと、直しがそこに
    手を描いてしまう（関係ない所に手足が量産される）。主役の範囲が取れない・
    主役が写っていない・範囲が絵の大半を覆っていて切り分けられないときは、
    判断できないので枠をそのまま返す（判断できない物を止めない）。
    """
    seg = parts(image)
    subj = (seg > 0) if seg is not None else silhouette(image)
    if subj is None or not subj.any() or subj.mean() > 0.5:
        return regions
    kept = []
    for b, t in regions:
        x0, y0, x1, y1 = (int(c) for c in b)
        if subj[max(0, y0):max(0, y1), max(0, x0):max(0, x1)].any():
            kept.append((b, t))
    return kept


def ink_share(image) -> float:
    """濃い線の割合（明るさ 80 未満の画素の割合）。

    tone() の dark は暗い方から 5% の明るさを見るので、絵の 2〜3% しかない
    細い線が薄くなっても数字が動かない（検証 45696035067 の線画で、濃い線が
    3.2% → 0.5% に落ちたのに tone は異常なしだった）。線の薄れは、この割合で見る。
    """
    import numpy as np
    lum = luminance(image)
    return float((lum < 80).mean())


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


# 風景と車・物の検品（水の光・葉のつや・タイヤの丸み・左右対称・遠近の収束）
WATER_LIGHT_LEAST = 20    # 水の明るさの広がり（95%点-50%点）がこれ未満なら、水に光が無い（光あり 148、光なし 0。私の推測）
LEAF_GLOSS_LEAST = 20     # 葉の明るさの広がりがこれ未満なら、葉につやが無い（つやあり 123、つやなし 0。私の推測）
TIRE_CV_MOST = 0.12       # タイヤの境界の半径の変動係数がこれを超えたら、タイヤが丸くない（円 0.02、平ら 0.14、楕円 0.11。私の推測）
SYMMETRY_IOU_LEAST = 0.6  # シルエットの鏡像との重なりがこれ未満なら、左右対称でない（対称 1.0、非対称 0.43。私の推測）
TIRE_PAIR_RATIO_MOST = 1.3  # 左右のタイヤの大きさの比がこれを超えたら、タイヤがそろっていない（私の推測）
VANISH_ANGLE_LEAST = 10.0  # 遠近の線の角度の差がこれ未満なら、線が平行で収束が無い（収束する道 52 度。私の推測）


def water_mask(image):
    """水の所（青い画素）。下半分だけを見る（上の空の青を水としない）"""
    import numpy as np
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b > r + 10) & (b > g + 5)
    lower = np.zeros((h, w), bool)
    lower[h // 2:, :] = True
    return blue & lower


def leaf_mask(image):
    """葉の所（緑の画素）"""
    import numpy as np
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g > r + 10) & (g > b + 10)


def _highlight_spread(image, mask):
    """色の面の明るさの広がり（95%点 - 50%点）。光・つやがあれば明るい所ができ、広がりが大きくなる。
    面が無ければ None"""
    import numpy as np
    if mask.sum() < 50:
        return None
    L = luminance(image)[mask]
    return round(float(np.percentile(L, 95) - np.percentile(L, 50)), 1)


def water_light(image) -> dict:
    """水の光: 水の所の明るさの広がり。水が少なければ読めない。返すのは {"readable", "spread", "share", "box"}。
    青い服（縦に細い）を水としないため、水は横に広い帯でなければならない（下半分のどこかの行で、幅の半分以上を水が占める）"""
    import numpy as np
    m = water_mask(image)
    h, w = m.shape
    if m.sum() < h * w * 0.02:
        return {"readable": False}
    row_share = m[h // 2:, :].mean(axis=1)   # 下半分の各行で、水が幅のどれだけを占めるか
    if row_share.max() < 0.5:
        return {"readable": False}   # 横に広い帯が無い。青い服などの細い物
    spread = _highlight_spread(image, m)
    ys, xs = np.nonzero(m)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return {"readable": True, "spread": spread, "share": round(float(m.mean()), 3), "box": box}


def leaf_gloss(image) -> dict:
    """葉のつや: 葉の所の明るさの広がり。葉が少なければ読めない。返すのは {"readable", "spread", "share", "box"}"""
    import numpy as np
    m = leaf_mask(image)
    h, w = m.shape
    if m.sum() < h * w * 0.02:
        return {"readable": False}
    spread = _highlight_spread(image, m)
    ys, xs = np.nonzero(m)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return {"readable": True, "spread": spread, "share": round(float(m.mean()), 3), "box": box}


def shine_water(image):
    """水の光の直し: 水の所に、光の筋（縦の明るい帯）を付ける。水の真ん中に筋を置き、
    地平線（水の上の端）で一番明るく、下へ行くほど薄くする（光の反射は地平線で強い）。返すのは (絵, 変えた画素の数)"""
    import numpy as np
    from PIL import Image
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    m = water_mask(image)
    if m.sum() < 50:
        return image, 0
    h, w = m.shape
    if m[h // 2:, :].mean(axis=1).max() < 0.5:
        return image, 0   # 横に広い帯が無い。青い服などの細い物には光を付けない
    ys, xs = np.nonzero(m)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    cx = (x0 + x1) // 2
    half = max(2, (x1 - x0) // 12)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    band = (np.abs(xx - cx) <= half) & m
    depth = np.clip((yy - y0) / max(y1 - y0, 1), 0, 1)   # 0=地平線、1=下
    factor = 1.0 + 0.8 * (1.0 - depth)   # 地平線で 1.8 倍、下で 1.0 倍
    hit = band
    a[hit] = np.clip(a[hit] * factor[hit][..., None], 0, 255)
    return Image.fromarray(a.astype("uint8")), int(hit.sum())


def shine_leaf(image):
    """葉のつやの直し: 葉に、つやの点を散らす（葉の画素のうち、座標で決まる散らばった所だけを明るくする）。
    葉が均一な色だと、明るい所だけを明るくしても全部が同じ色で広がりが出ないので、散らして点を付ける。
    返すのは (絵, 変えた画素の数)"""
    import numpy as np
    from PIL import Image
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    m = leaf_mask(image)
    if m.sum() < 50:
        return image, 0
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    hit = m & (((xx * 5 + yy * 11) % 13) < 2)   # 葉の約 15% を散らして選ぶ
    a[hit] = np.clip(a[hit] * 1.6, 0, 255)
    return Image.fromarray(a.astype("uint8")), int(hit.sum())


def _dark_blobs(image, lum_max=50):
    """暗い塊（タイヤの候補）。下の 3 分の 2 だけを見る。穴を埋めてから測る（タイヤは輪で、中のハブが穴になる）。
    返すのは [{"area", "cv", "box"}]。cv は境界の半径の変動係数（円なら小さく、平ら・ゆがみなら大きい）"""
    import numpy as np
    from scipy import ndimage
    L = luminance(image)
    h, w = L.shape
    dark = L < lum_max
    lower = np.zeros((h, w), bool)
    lower[h // 3:, :] = True
    m = dark & lower
    lab, n = ndimage.label(m)
    out = []
    for k in range(1, n + 1):
        comp = ndimage.binary_fill_holes(lab == k)
        area = int(comp.sum())
        if area < 50 or area > h * w * 0.15:
            continue
        ys, xs = np.nonzero(comp)
        cy, cx = ys.mean(), xs.mean()
        er = ndimage.binary_erosion(comp)
        by, bx = np.nonzero(comp & ~er)
        if len(bx) < 8:
            continue
        r = np.hypot(bx - cx, by - cy)
        cv = float(r.std() / max(r.mean(), 1))
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        out.append({"area": area, "cv": round(cv, 3), "box": box})
    return out


def tire_roundness(image) -> dict:
    """タイヤの丸み: 暗い塊（タイヤ）の境界の半径の変動係数。タイヤが無ければ読めない。
    返すのは {"readable", "tires", "worst", "boxes"}"""
    tires = _dark_blobs(image)
    if not tires:
        return {"readable": False, "tires": [], "worst": None, "boxes": []}
    worst = max(t["cv"] for t in tires)
    return {"readable": True, "tires": tires, "worst": round(worst, 3),
            "boxes": [t["box"] for t in tires]}


def mirror_symmetry(image) -> dict:
    """左右対称: シルエットの鏡像との重なり（IoU）。絵の真ん中を軸に反転し、重なる割合を測る。
    絵の真ん中を軸にするのは、構図は主役を真ん中に置くため。シルエット自身の真ん中を軸にすると、
    片側が潰れた絵でも潰れた形の真ん中で反転して対称に見えてしまう。
    シルエットが無ければ読めない。返すのは {"readable", "iou"}"""
    import numpy as np
    m = silhouette(image)
    if m.sum() < 50:
        return {"readable": False}
    h, w = m.shape
    cx = w / 2
    cols = np.arange(w)
    mx = np.round(2 * cx - cols).astype(int)
    ok = (mx >= 0) & (mx < w)
    mirrored = np.zeros_like(m)
    mirrored[:, ok] = m[:, mx[ok]]
    inter = float((m & mirrored).sum())
    union = float((m | mirrored).sum())
    iou = round(inter / union, 3) if union else 0.0
    return {"readable": True, "iou": iou}


def symmetry(image) -> dict:
    """左右対称: シルエットの鏡像との重なりと、左右のタイヤの大きさの比。
    返すのは {"readable", "iou", "tire_ratio", "tire_dy", "small_box"}。
    タイヤが 2 つ無ければ tire_ratio は None"""
    import numpy as np
    got = mirror_symmetry(image)
    if not got.get("readable"):
        return {"readable": False}
    out = {"readable": True, "iou": got["iou"], "tire_ratio": None, "tire_dy": None, "small_box": None}
    tires = _dark_blobs(image)
    if len(tires) >= 2:
        # 一番大きい 2 つのタイヤで比べる（小さいゴミはタイヤにしない）
        big = sorted(tires, key=lambda t: t["area"], reverse=True)[:2]
        a1, a2 = big[0]["area"], big[1]["area"]
        out["tire_ratio"] = round(max(a1, a2) / max(min(a1, a2), 1), 2)
        cy1 = (big[0]["box"][1] + big[0]["box"][3]) / 2
        cy2 = (big[1]["box"][1] + big[1]["box"][3]) / 2
        out["tire_dy"] = round(abs(cy1 - cy2), 1)
        out["small_box"] = big[1]["box"] if a1 >= a2 else big[0]["box"]
    return out


def mirror_fix(image):
    """左右対称の直し: シルエットの画素の多い方（より完全な方）を、少ない方に鏡写しする。軸は絵の真ん中
    （構図は主役を真ん中に置く。検品の mirror_symmetry と同じ軸にする）。
    鏡像の所は鏡像の色、鏡像に物が無くてこちらに物がある所は紙の色にする（片側だけの出っ張りを消す）。
    返すのは (絵, 変えた画素の数)"""
    import numpy as np
    from PIL import Image
    a = np.asarray(image.convert("RGB")).copy()
    m = silhouette(image)
    if m.sum() < 50:
        return image, 0
    h, w = m.shape
    cx = w / 2
    paper = np.array(paper_color(image), dtype=np.uint8)
    left_n = int(m[:, :int(cx)].sum())
    right_n = int(m[:, int(np.ceil(cx)):].sum())
    cols = np.arange(w)
    mx = np.round(2 * cx - cols).astype(int)
    ok = (mx >= 0) & (mx < w)
    mirrored = np.zeros_like(a)
    mirrored[:, ok] = a[:, mx[ok]]
    mirrored_m = np.zeros_like(m)
    mirrored_m[:, ok] = m[:, mx[ok]]
    out = a.copy()
    if left_n >= right_n:
        target = (cols > cx)[None, :] & (mirrored_m | m)   # 左を右に写す
    else:
        target = (cols < cx)[None, :] & (mirrored_m | m)   # 右を左に写す
    use_mirror = target & mirrored_m
    use_paper = target & ~mirrored_m
    out[use_mirror] = mirrored[use_mirror]
    out[use_paper] = paper
    return Image.fromarray(out), int(target.sum())


def _hough_lines(image, max_lines=8):
    """ハフ変換で長い直線を拾う。返すのは [(法線の角度(度), 距離, 強さ)]。強い順。
    勾配の方向から法線を絞って投票する（全部の角度に投票するより速い）"""
    import numpy as np
    from scipy import ndimage
    L = luminance(image)
    h, w = L.shape
    gx = ndimage.sobel(L, axis=1)
    gy = ndimage.sobel(L, axis=0)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 90)
    ys, xs = np.nonzero(mag > thr)
    if len(xs) < 50:
        return []
    thetas = np.deg2rad(np.arange(0, 180, 2))
    diag = int(np.hypot(h, w))
    acc = np.zeros((len(thetas), 2 * diag + 1), dtype=np.int32)
    ang = np.mod(np.rad2deg(np.arctan2(gy[ys, xs], gx[ys, xs])), 180)
    ti = (np.round(ang / 2).astype(int)) % 90
    for dt in (-1, 0, 1):
        t_idx = (ti + dt) % 90
        th = thetas[t_idx]
        rho = np.round(xs * np.cos(th) + ys * np.sin(th)).astype(int) + diag
        np.add.at(acc, (t_idx, rho), 1)
    flat = acc.ravel()
    order = np.argsort(flat)[::-1]
    lines, taken = [], []
    for i in order:
        v = int(flat[i])
        if v < 20:
            break
        t, rho = divmod(int(i), acc.shape[1])
        rho -= diag
        if any(abs(t - tt) <= 2 and abs(rho - rr) <= 4 for tt, rr in taken):
            continue
        taken.append((t, rho))
        lines.append((float(np.rad2deg(thetas[t])), rho, v))
        if len(lines) >= max_lines:
            break
    return lines


def _lines_box(image, lines):
    """線の所の枠。線の近くの強い縁の画素の枠（直しの囲み）。線が無ければ None"""
    import math
    import numpy as np
    from scipy import ndimage
    L = luminance(image)
    h, w = L.shape
    gx = ndimage.sobel(L, axis=1)
    gy = ndimage.sobel(L, axis=0)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 90)
    ys, xs = np.nonzero(mag > thr)
    if len(xs) == 0:
        return None
    keep = np.zeros(len(xs), bool)
    for (t, rho, _v) in lines:
        a = math.radians(t)
        d = np.abs(xs * math.cos(a) + ys * math.sin(a) - rho)
        keep |= d < 3
    if not keep.any():
        return None
    kx, ky = xs[keep], ys[keep]
    return (int(kx.min()), int(ky.min()), int(kx.max()) + 1, int(ky.max()) + 1)


def vanishing(image) -> dict:
    """遠近の収束: 斜めの強い線を 2 本取り、その角度の差を測る。平行（角度の差が小さい）なら収束が無い。
    斜めの線が 2 本無ければ読めない（水平な線は地平線、垂直な線は建物の縁で、平行で当たり前なので除く）。
    返すのは {"readable", "angle", "point", "box"}。point は 2 本の線の交点（消失点）"""
    import math
    lines = _hough_lines(image)
    # 斜めの線だけ。15〜75 度と 105〜165 度（法線の角度）。水平（90 度）と垂直（0/180 度）は除く
    dg = [l for l in lines if 15 <= l[0] <= 75 or 105 <= l[0] <= 165]
    if len(dg) < 2:
        return {"readable": False}
    (t1, r1, _), (t2, r2, _) = dg[0], dg[1]
    d = abs(t1 - t2)
    angle = min(d, 180 - d)
    a1, a2 = math.radians(t1), math.radians(t2)
    det = math.cos(a1) * math.sin(a2) - math.cos(a2) * math.sin(a1)
    point = None
    if abs(det) > 1e-6:
        x = (r1 * math.sin(a2) - r2 * math.sin(a1)) / det
        y = (math.cos(a1) * r2 - math.cos(a2) * r1) / det
        point = (round(float(x), 1), round(float(y), 1))
    box = _lines_box(image, dg[:2])
    return {"readable": True, "angle": round(float(angle), 1), "point": point, "box": box}
