"""人物以外の題材の検品。題材を頼みの言葉から 10 種に分け、人が一目で気づく崩れを数字で測る。

人物の検品（手・足・顔・骨組み）は人の形を前提にしていて、建物・風景・乗り物・物・文字の絵では何も見ていなかった。
ここでは題材ごとに、模型が崩しやすく、人なら一目で分かる物を測る。
- 建物と街: 縦の線の倒れ、窓の並びの間隔、消える点のそろい
- 風景: 空と地面の間の塗り残しの帯、空が下にある逆さの絵
- 乗り物: 車輪の数（自転車・バイクなど、数の決まった物だけ）
- 動物: 足の数の崩れ（タグ）
- 物: 頼んだ数と、描いた塊の数
- 文字とロゴ: 頼んだ文字が読めるか（OCR の部品があるときだけ）
- 模様: 繰り返しのそろい
- 背景だけの絵: 頼んでいない人
測れなかった物は readable を False にし、「崩れが無い」とは返さない（unreadable に理由を残す）。
線の読み取りは phase_tools の Hough（_hough_lines）と塊（_components）を使い回し、同じ計算を 2 度作らない。
閾値は合成の絵と Actions の絵で決めた。動かすときは docs/knowledge/subject-qc.md の数字と比べる。
"""
from __future__ import annotations

import math
import re

# 題材の種類。順に見て、最初に当たった種類にする（「街の中の車」は乗り物を先に見る）
SUBJECTS = ["person", "animal", "vehicle", "text", "pattern", "building", "interior", "object", "landscape", "background"]
NAMES = {"person": "人物", "animal": "動物", "vehicle": "乗り物", "building": "建物と街", "landscape": "風景",
         "interior": "室内", "object": "物", "text": "文字とロゴ", "pattern": "模様", "background": "背景だけの絵"}
WORDS = {
    "person": ("1girl", "1boy", "girl", "boy", "woman", "man", "person", "people", "portrait", "少女", "少年", "女性", "男性", "人物", "人"),
    "animal": ("dog", "cat", "bird", "horse", "animal", "fox", "wolf", "bear", "rabbit", "deer", "lion", "tiger", "cow", "sheep",
               "犬", "猫", "鳥", "馬", "動物", "狐", "狼", "熊", "兎", "鹿", "牛", "羊"),
    "vehicle": ("car", "vehicle", "truck", "bus", "bicycle", "bike", "motorcycle", "train", "airplane", "ship", "boat", "tricycle",
                "車", "自動車", "自転車", "バイク", "電車", "列車", "飛行機", "船", "乗り物", "トラック", "バス"),
    "text": ("text", "logo", "lettering", "sign", "title", "文字", "ロゴ", "看板", "題字"),
    "pattern": ("pattern", "seamless", "tile", "texture", "wallpaper", "模様", "柄", "テクスチャ", "壁紙"),
    "building": ("building", "city", "street", "house", "tower", "castle", "skyscraper", "town", "architecture",
                 "建物", "街", "町", "家", "塔", "城", "ビル", "通り"),
    "interior": ("room", "interior", "kitchen", "bedroom", "office", "classroom", "cafe", "部屋", "室内", "台所", "寝室", "教室", "カフェ"),
    "object": ("food", "cake", "apple", "cup", "tool", "camera", "pen", "guitar", "device", "machine", "still life",
               "食べ物", "ケーキ", "林檎", "りんご", "カップ", "道具", "機材", "カメラ", "ペン", "ギター", "機械", "静物"),
    "landscape": ("landscape", "scenery", "sky", "sea", "ocean", "mountain", "forest", "lake", "field", "beach",
                  "風景", "景色", "空", "海", "山", "森", "湖", "野原", "浜"),
}
NO_PEOPLE = ("no humans", "no people", "scenery only", "background only", "人なし", "人物なし", "背景だけ", "背景のみ")

# 閾値（私の推測。Actions の絵で見直す）
VERTICAL_LEAN_MOST = 4.0     # 縦の線の倒れ（度）。見上げ・見下ろしの頼みでは見ない（三点透視で縦の線が倒れるのは正しい）
WINDOW_CV_MOST = 0.35        # 窓の間隔の変動係数
VANISH_SHARE_LEAST = 0.4     # 斜めの線の交点が、消える点の近くに集まる割合
GAP_ROWS_SHARE = 0.02        # 空と地面の間の、塗っていない帯の高さ（絵の高さに対する割合）
PATTERN_DIFF_MOST = 0.18     # 模様の繰り返しの、隣の区画との差（明るさの差の平均 / 255）
TEXT_SIMILAR_LEAST = 0.8     # 頼んだ文字と読んだ文字の近さ
LOW_ANGLE = ("from below", "from above", "low angle", "high angle", "worm's eye", "bird's eye", "fisheye",
             "見上げ", "見下ろし", "俯瞰", "あおり", "魚眼")
# 数の決まった乗り物の車輪（見える数の上限）。車は向きで見える数が変わるので入れない
WHEELS = {"unicycle": 1, "bicycle": 2, "bike": 2, "motorcycle": 2, "tricycle": 3,
          "一輪車": 1, "自転車": 2, "バイク": 2, "三輪車": 3}
# 足の数の崩れを示すタグと下限（wd-tagger の読み）
LEG_TAGS = {"extra legs": 0.35, "multiple legs": 0.5, "too many legs": 0.35, "missing limb": 0.4, "amputee": 0.5}
HAND_PEOPLE = ("1girl", "1boy", "2girls", "2boys", "multiple girls", "multiple boys", "solo", "1other")
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "一つ": 1, "二つ": 2, "三つ": 3, "四つ": 4, "五つ": 5, "六つ": 6, "七つ": 7, "八つ": 8, "九つ": 9, "十": 10,
           "1つ": 1, "2つ": 2, "3つ": 3, "4つ": 4, "5つ": 5, "6つ": 6, "7つ": 7, "8つ": 8, "9つ": 9}


def _has(low: str, w: str) -> bool:
    if re.fullmatch(r"[\x00-\x7f]+", w):
        return re.search(r"(?<![a-z])" + re.escape(w) + r"(?:s|es)?(?![a-z])", low) is not None
    return w in low


def kind(prompt: str) -> str:
    """頼みの言葉から題材の種類。人がいない頼み（no humans・背景だけ）は人物にしない。決め手が無ければ "unknown"
    （その場で調べる形 research_check に回す）"""
    low = str(prompt).lower()
    no_people = any(_has(low, w) for w in NO_PEOPLE)
    for k in SUBJECTS:
        if k == "background":
            continue
        if k == "person" and no_people:
            continue
        if no_people and k not in ("text", "pattern"):
            return "background"   # 人のいない頼みは、場所の語より「背景だけの絵」を先にする（人がいないかを見る）
        if any(_has(low, w) for w in WORDS[k]):
            return k
    return "unknown"


# 棚卸しの表。題材ごとに、今の検品が見ている物と見ていない物。docs/knowledge/subject-qc.md と同じ中身を持ち、試験が食い違いを見る
# 値: (見ている物, 見ていない物)。見ている物の後ろの括弧は測る部品
COVERAGE = {
    "person": (["人数（RT-DETR・タグ）", "頼んだ物（wd-tagger）", "手の指の数（hand_check）", "足・顔（hand_check）",
                "骨の比（VitPose）", "余分な部位（segformer の塊）", "反転・縮めて見る", "地平線の傾き"],
               ["持ち物の数と持ち方", "服の左右"]),
    "animal": (["頼んだ物（wd-tagger）", "顔・足の有無（subject_kind の face）", "足の数の崩れ（タグ、この検品）", "地平線の傾き"],
               ["足の本数を画素で数える", "尾・耳の数"]),
    "vehicle": (["タイヤの丸み・左右のタイヤの大きさ（phase_tools）", "左右対称（正面の頼み）", "遠近の収束",
                 "車輪の数（数の決まった乗り物、この検品）"],
                ["車の向きごとの見える車輪の数", "窓・扉の数"]),
    "building": (["地平線の傾き", "遠近の収束（2 本）", "縦の線の倒れ（この検品）", "窓の並び（この検品）", "消える点のそろい（この検品）"],
                 ["窓の大きさのそろい", "階の数"]),
    "landscape": (["地平線の傾き", "水の光・葉のつや", "空と地面の間の塗り残し（この検品）", "空が下の逆さの絵（この検品）"],
                  ["山の稜線の重なり", "影の向きのそろい"]),
    "interior": (["地平線の傾き", "遠近の収束", "縦の線の倒れ（この検品）", "消える点のそろい（この検品）"],
                 ["家具の脚の数", "床と壁の境目"]),
    "object": (["頼んだ物（wd-tagger）", "画面の重さ", "頼んだ数と塊の数（この検品）", "その場で調べた項目（research_check）"],
               ["部品の並び（その場で調べた項目のうち order は測る道具が無い）"]),
    "text": (["頼んだ文字が読めるか（OCR があるとき、この検品）"], ["字の形の崩れ（OCR が無いとき）", "ロゴの左右対称"]),
    "pattern": (["繰り返しのそろい（この検品）"], ["継ぎ目（端と端がつながるか）"]),
    "background": (["頼んでいない人（wd-tagger、この検品）", "地平線の傾き", "遠近の収束"], ["主役が無いことの確かめ"]),
}
# 描く道具の棚卸し。人物以外での動き
TOOLS = {
    "部品分け（segformer の顔・腕・脚）": "人物だけ。人物以外は塊が出ず、直しの囲みが作れない → subject_parts の空・地面・主役の面で補う",
    "囲み（hand/foot/face の枠）": "人物だけ。乗り物はタイヤの枠、遠近は線の枠（phase_tools）。建物の縦線・窓は線の枠（この検品の box）",
    "下塗りの面（主役のシルエット）": "どの題材でも動く（明るさのシルエット）。全画面の風景は主役が無く、空と地面の面に分ける（subject_parts）",
    "工程: 目的・サムネイル": "どの題材でも動く（頼み・画面の重さ）",
    "工程: アタリ": "人物前提（骨組み・等身）。物（object）は頼んだ物と画面の重さだけ。建物の遠近の線、風景の空と地面の段は STEPS で持つ",
    "工程: 線画・塗り・仕上げ": "線・塗りは題材を問わず動く。仕上げの手・足・顔は顔のある物だけ。物は縮めて見る・タイヤ・対称・遠近",
}


def _lines(image, most: int = 24):
    from atelier.ai import phase_tools as pt
    return pt._hough_lines(image, max_lines=most)


def vertical_lean(image) -> dict:
    """縦の線の倒れ。強い縁のうち縦に近い（縁の向きが縦から 20 度以内）画素の、縁の傾き（度）の中央値の絶対値。
    建物の縦の縁は、見上げ・見下ろしで無ければ縦に立つ。縦に近い縁が少なければ読めない。
    Hough（phase_tools）は 2 度刻みで、長い縁より窓の縁の数に引かれたので、縁の画素の向きを直に数える"""
    import numpy as np
    from scipy import ndimage
    from atelier.ai import phase_tools as pt
    L = ndimage.gaussian_filter(pt.luminance(image), 2.0)   # 画素の段差（ギザギザ）でなく、線の向きを見る
    gx = ndimage.sobel(L, axis=1)
    gy = ndimage.sobel(L, axis=0)
    mag = np.hypot(gx, gy)
    strong = mag > max(float(np.percentile(mag, 90)), 40.0)
    ang = np.degrees(np.arctan2(gy, gx))          # 勾配の向き。縦の縁は 0 か ±180
    ang = (ang + 90) % 180 - 90                   # -90..90 に畳む（明暗の向きを問わない）
    near = strong & (np.abs(ang) <= 20)
    if near.sum() < 0.002 * L.size:
        return {"readable": False, "reason": "縦の縁が足りません"}
    med = float(np.median(ang[near]))
    return {"readable": True, "lean": round(abs(med), 1), "count": int(near.sum())}


def window_grid(image) -> dict:
    """窓の並び。暗い小さな塊（窓）を取り、同じ高さの段ごとに、隣の窓との間隔の変動係数を測る（一番ばらつく段）。
    3 つ以上の窓が並ぶ段が無ければ読めない"""
    import numpy as np
    from scipy import ndimage
    from atelier.ai import phase_tools as pt
    L = pt.luminance(image)
    dark = L < min(90.0, float(np.percentile(L, 30)))
    lab, n = ndimage.label(dark)
    if n == 0:
        return {"readable": False, "reason": "窓の塊がありません"}
    area = L.size
    wins = []
    for sl in ndimage.find_objects(lab):
        hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if 0.0005 * area <= hh * ww <= 0.03 * area and 0.25 <= ww / hh <= 4:
            wins.append(((sl[1].start + sl[1].stop) / 2, (sl[0].start + sl[0].stop) / 2, hh))
    rows: list[list] = []
    for x, y, hh in sorted(wins, key=lambda t: t[1]):
        if rows and abs(rows[-1][0][1] - y) < rows[-1][0][2] / 2:
            rows[-1].append((x, y, hh))
        else:
            rows.append([(x, y, hh)])
    worst, used = None, 0
    for r in rows:
        if len(r) < 3:
            continue
        xs = np.sort([t[0] for t in r])
        gaps = np.diff(xs)
        cv = float(gaps.std() / gaps.mean()) if gaps.mean() else 1.0
        used += 1
        worst = cv if worst is None else max(worst, cv)
    if worst is None:
        return {"readable": False, "reason": "3 つ以上の窓が並ぶ段がありません"}
    return {"readable": True, "cv": round(worst, 3), "rows": used, "windows": len(wins)}


def vanish_spread(image) -> dict:
    """消える点のそろい。斜めの線どうしの交点のうち、交点の中央値から絵の対角の 15% 以内に入る割合。
    斜めの線が 4 本無ければ読めない（2 本なら phase_tools.vanishing で足りる）"""
    dg = [(t, r) for t, r, _v in _lines(image, most=32) if 15 <= t <= 75 or 105 <= t <= 165]
    if len(dg) < 4:
        return {"readable": False, "reason": f"斜めの線が {len(dg)} 本です"}
    pts = []
    for i in range(len(dg)):
        for j in range(i + 1, len(dg)):
            (t1, r1), (t2, r2) = dg[i], dg[j]
            a1, a2 = math.radians(t1), math.radians(t2)
            det = math.cos(a1) * math.sin(a2) - math.cos(a2) * math.sin(a1)
            if abs(det) < 0.05:
                continue
            pts.append(((r1 * math.sin(a2) - r2 * math.sin(a1)) / det, (math.cos(a1) * r2 - math.cos(a2) * r1) / det))
    if len(pts) < 3:
        return {"readable": False, "reason": "交点がありません"}
    w, h = image.size
    xs = sorted(p[0] for p in pts)
    ys = sorted(p[1] for p in pts)
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    near = 0.15 * math.hypot(w, h)
    share = sum(math.hypot(x - mx, y - my) <= near for x, y in pts) / len(pts)
    return {"readable": True, "share": round(share, 3), "point": (round(mx, 1), round(my, 1)), "lines": len(dg)}


def sky_ground(image) -> dict:
    """空と地面のつながり。行ごとの明るさのばらつきが無く、紙の白に近い行が続く帯（塗り残し）の高さと、
    上半分と下半分の青み（空が下にある逆さの絵）を測る"""
    import numpy as np
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    h = a.shape[0]
    lum = a.mean(axis=2)
    flat_white = (lum.mean(axis=1) > 235) & (lum.std(axis=1) < 6)
    # 上と下の端の白い行（紙の縁）は数えない。絵の真ん中 80% の中の一番長い帯
    run = best = 0
    for y in range(int(h * 0.1), int(h * 0.9)):
        run = run + 1 if flat_white[y] else 0
        best = max(best, run)
    blue = a[..., 2] - (a[..., 0] + a[..., 1]) / 2
    top, bottom = float(blue[: h // 3].mean()), float(blue[-h // 3:].mean())
    top_l, bottom_l = float(lum[: h // 3].mean()), float(lum[-h // 3:].mean())
    upside = bottom > top + 25 and bottom_l > top_l + 25   # 下の 3 分の 1 が上より青く明るい（空が下）
    return {"readable": True, "gap": round(best / h, 3), "upside_down": bool(upside)}


def pattern_repeat(image, tiles: int = 4) -> dict:
    """模様の繰り返しのそろい。明るさの自己相関で周期を読み、周期の区画どうしの差の平均を測る。周期が読めなければ読めない"""
    import numpy as np
    from atelier.ai import phase_tools as pt
    L = pt.luminance(image).astype(np.float32)
    h, w = L.shape
    best = None
    for axis, n in ((1, w), (0, h)):
        prof = L.mean(axis=0 if axis == 1 else 1)
        prof = prof - prof.mean()
        if prof.std() < 0.5:   # 向きに変化が無い（縦縞の縦の向き）。誤差だけの相関を周期と読まない
            continue
        ac = np.correlate(prof, prof, mode="full")[n - 1:]
        ac = ac / ac[0]
        lo = max(4, n // 16)
        hi = n // 2
        if hi <= lo:
            continue
        p = int(np.argmax(ac[lo:hi])) + lo
        if ac[p] > 0.3 and (best is None or ac[p] > best[2]):
            best = (axis, p, float(ac[p]))
    if best is None:
        return {"readable": False, "reason": "繰り返しの周期が読めません"}
    axis, p, _c = best
    diffs = []
    for k in range(min(tiles, (w if axis == 1 else h) // p - 1)):
        if axis == 1:
            d = np.abs(L[:, k * p:(k + 1) * p] - L[:, (k + 1) * p:(k + 2) * p]).mean()
        else:
            d = np.abs(L[k * p:(k + 1) * p] - L[(k + 1) * p:(k + 2) * p]).mean()
        diffs.append(float(d) / 255)
    if not diffs:
        return {"readable": False, "reason": "周期が絵の半分より長い"}
    return {"readable": True, "period": p, "diff": round(max(diffs), 3)}


def asked_count(prompt: str) -> int | None:
    """頼んだ物の数（"three apples"、"3 cups"、"林檎が三つ"）。数が無ければ None。人の数（1girl など）は数えない"""
    low = str(prompt).lower()
    m = re.search(r"(?<![a-z0-9])(\d{1,2})\s+(?!girls?\b|boys?\b|others?\b)([a-z]+)", low)
    if m:
        return int(m.group(1))
    for w, n in NUMBERS.items():
        if re.fullmatch(r"[a-z]+", w):
            if re.search(r"(?<![a-z])" + w + r"\s+(?!girls?\b|boys?\b)[a-z]+", low):
                return n
        elif w in low:
            return n
    return None


def count_blobs(image, least: float = 0.01) -> dict:
    """主役の塊の数。シルエットの連結成分のうち、絵の面積の least 以上の物。全画面が 1 つの塊なら読めない"""
    import numpy as np
    from atelier.ai import phase_tools as pt
    got = pt._components(image)
    if got is None:
        return {"readable": False, "reason": "塊を分ける部品（scipy）がありません"}
    lab, sizes, _big = got
    area = lab.size
    big = [s for s in sizes if s >= least * area]
    if len(big) == 1 and big[0] > 0.8 * area:
        return {"readable": False, "reason": "全画面が 1 つの塊です"}
    return {"readable": True, "count": int(len(big)), "share": round(float(np.sum(big)) / area, 3)}


def asked_text(prompt: str) -> str | None:
    """頼んだ文字（引用符か「」の中）。無ければ None"""
    m = re.search(r"[\"“「『]([^\"”」』]{1,40})[\"”」』]", str(prompt))
    return m.group(1).strip() if m else None


def read_text(image) -> dict:
    """絵の中の文字を OCR で読む。rapidocr_onnxruntime（Apache-2.0）か pytesseract（Apache-2.0、tesseract が要る）のどちらか。
    どちらも無ければ読めない"""
    try:
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
        res, _t = RapidOCR()(np.asarray(image.convert("RGB")))
        return {"readable": True, "text": " ".join(r[1] for r in res or [])}
    except ImportError:
        pass
    except Exception as e:   # noqa: BLE001  OCR が落ちても描く流れを止めない。読めなかったと返す
        return {"readable": False, "reason": f"OCR が落ちました（{type(e).__name__}）"}
    try:
        import pytesseract
        return {"readable": True, "text": pytesseract.image_to_string(image.convert("RGB"))}
    except Exception as e:   # noqa: BLE001
        return {"readable": False, "reason": f"文字を読む部品がありません（{type(e).__name__}）"}


def similar(a: str, b: str) -> float:
    import difflib
    na = re.sub(r"\s+", "", a.lower())
    nb = re.sub(r"\s+", "", b.lower())
    if not na:
        return 0.0
    if na in nb:
        return 1.0
    return round(difflib.SequenceMatcher(None, na, nb).ratio(), 3)


def _tag(tags, name):
    return float((tags or {}).get(name, 0.0))


def check(image, prompt: str, tags: dict | None = None, ocr=read_text) -> dict:
    """題材ごとの検品。返す欄: kind・flaws（崩れの文）・numbers・unreadable（測れなかった物と理由）・regions。
    tags は wd-tagger の読み（request_check の read）。無ければタグの検品は unreadable に入れる"""
    k = kind(prompt)
    low = str(prompt).lower()
    flaws, numbers, unreadable, regions = [], {"kind": k}, [], []

    def need(name, res):
        if not res.get("readable"):
            unreadable.append(f"{name}: {res.get('reason', '読めません')}")
            return False
        return True

    if k in ("building", "interior"):
        if not any(_has(low, w) for w in LOW_ANGLE):
            v = vertical_lean(image)
            if need("縦の線", v):
                numbers["vertical_lean"] = v["lean"]
                if v["lean"] > VERTICAL_LEAN_MOST:
                    flaws.append(f"建物の縦の線が倒れている（{v['lean']} 度）")
        vs = vanish_spread(image)
        if need("消える点", vs):
            numbers["vanish_share"] = vs["share"]
            if vs["share"] < VANISH_SHARE_LEAST:
                flaws.append(f"消失点がそろわない（交点の集まり {vs['share']}）")
    if k == "building" and any(_has(low, w) for w in ("window", "windows", "窓")):
        wg = window_grid(image)
        if need("窓の並び", wg):
            numbers["window_cv"] = wg["cv"]
            if wg["cv"] > WINDOW_CV_MOST:
                flaws.append(f"窓の並びの間隔がばらつく（変動 {wg['cv']}）")
    if k in ("landscape", "background"):
        sg = sky_ground(image)
        numbers["gap"] = sg["gap"]
        if sg["gap"] > GAP_ROWS_SHARE:
            flaws.append(f"空と地面の間が塗られていない（帯 {sg['gap']}）")
        if sg["upside_down"]:
            flaws.append("空と地面が逆さ（下の方が空の色）")
    if k == "vehicle":
        want = next((n for w, n in WHEELS.items() if _has(low, w)), None)
        if want is not None:
            from atelier.ai import phase_tools as pt
            tr = pt.tire_roundness(image)
            if need("車輪", tr):
                numbers["wheels"] = len(tr["tires"])
                if len(tr["tires"]) != want:
                    flaws.append(f"車輪の数が違う（{len(tr['tires'])} 個、頼んだ物は {want} 個）")
                    regions += [(b, "tire") for b in tr["boxes"]]
    if k == "animal":
        if tags is None:
            unreadable.append("足の数: タグが読めません")
        else:
            hit = [f"{t} {_tag(tags, t):.2f}" for t, least in LEG_TAGS.items() if _tag(tags, t) >= least and not _has(low, t)]
            if hit:
                flaws.append("足の数が崩れている（" + "、".join(hit) + "）")
    if k in ("object", "animal", "vehicle"):
        n = asked_count(prompt)
        if n is not None:
            cb = count_blobs(image)
            if need("物の数", cb):
                numbers["blobs"] = cb["count"]
                if cb["count"] != n:
                    flaws.append(f"物の数が違う（{cb['count']} 個、頼んだ物は {n} 個）")
    if k == "text":
        want = asked_text(prompt)
        if want is None:
            unreadable.append("文字: 頼んだ文字が引用符の中にありません")
        else:
            rt = ocr(image)
            if need("文字", rt):
                s = similar(want, rt["text"])
                numbers["text_similar"] = s
                if s < TEXT_SIMILAR_LEAST:
                    flaws.append(f"頼んだ文字が読めない（近さ {s}）")
    if k == "pattern":
        pr = pattern_repeat(image)
        if need("模様", pr):
            numbers["pattern_diff"] = pr["diff"]
            if pr["diff"] > PATTERN_DIFF_MOST:
                flaws.append(f"模様の繰り返しがそろわない（差 {pr['diff']}）")
    if k == "background":
        if tags is None:
            unreadable.append("人: タグが読めません")
        else:
            hit = [t for t in HAND_PEOPLE if _tag(tags, t) >= 0.4]
            if hit:
                flaws.append("背景だけの絵の人数が 0 でない（" + "、".join(hit) + "）")
    return {"kind": k, "flaws": flaws, "numbers": numbers, "unreadable": unreadable, "regions": regions,
            "readable": not unreadable}


def phase_flaws(image, prompt: str, req: dict | None = None, research=None) -> dict:
    """精度優先の工程から呼ぶ入口。題材の検品と、表に無い題材のときのその場の調べ物を 1 つにする。
    人物は今の検品（手・足・顔・骨組み）が見るので、ここでは何もしない。どの例外でも描く流れを止めない"""
    try:
        tags = (req or {}).get("read") if (req or {}).get("readable") else None
        res = check(image, prompt, tags=tags)
        if res["kind"] == "person":
            return {"flaws": [], "regions": [], "numbers": {}, "unreadable": []}
        if res["kind"] == "unknown":
            from atelier.qc import research_check
            rc = research_check.check(image, prompt, research=research)
            res["flaws"] += rc["flaws"]
            res["unreadable"] += rc["unreadable"]
            res["numbers"].update({f"調べた項目 {k}": v for k, v in rc["numbers"].items()})
        return res
    except Exception as e:   # noqa: BLE001  検品の部品が落ちても描く流れを止めない。読めなかったと残す
        return {"flaws": [], "regions": [], "numbers": {}, "unreadable": [f"題材の検品が落ちました（{type(e).__name__}）"]}
