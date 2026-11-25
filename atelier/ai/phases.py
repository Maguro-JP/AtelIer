"""人の描き方の工程に分けて描く（精度優先）。工程の調べは docs/knowledge/drawing-phases.md。

人は 1 回で描き上げない。目的を決め、構図を線のラフ画で 1 枚直接描いて決め、アタリで構図を調整しつつ
体の形・顔と手と足・服と髪と持ち物の下描きを済ませ、線を清書し、初めて色を下塗りし、光源を決めて影を 2 段に置き、
光と艶を足し、最後に縮めて見る・反転して見るで崩れを探す。工程ごとに見る物が決まっていて、崩れを見つけたら、
その崩れが決まった工程まで戻って直す。次の工程は、前の工程で決めた物を土台にして壊さずに足す。線画は色を塗る前の工程で、色のついた絵に上から線を引かない。

設計の決まり（工程の管理の設計は docs/knowledge/drawing-phases.md の「工程の管理の設計」）:
- 9 の工程（PHASES）は人の描き方の段。段の中を、描く工程・確かめる工程（項目ごと、atelier/ai/phase_items.py）・
  直す工程（崩れ 1 つにつき 1 つ）・確かめ直す工程（直した項目だけ）・聞く工程に分け、計画（atelier/ai/phase_plan.py）の表に並べる。
  確かめる工程が崩れを見つけたら、直す工程と確かめ直す工程を表に差し込む。表示・一時停止・聞く所・記録は全部この表から出す
- 描く工程は測らない・直さない。測るのは確かめる工程、直すのは直す工程だけ（前は 1 つの工程の中で描く・測る・直すを全部していた）
- 構図（サムネイル）を選んだあとは、ゼロから描かない。崩れが残っても前の工程へ戻らず、種を替えて描き直すこともしない
- 直しは鉛筆と消しゴムと同じ。今の絵をそのまま土台に、崩れの場所（検品の枠、部位分け、人物の形）だけを囲み、その中だけを描き直す
  （redraw。外は Image.composite で 1 画素も変えない）。囲めない崩れは聞く工程にする。勝手に構図へ戻らない
- 直しの回数に上限は置かない（止めるのは利用者だけ）。絵がほとんど変わらない直し（差の平均が DIFF_MIN 未満）は累計に数えず、
  次の直す工程は囲みを広げ、強さを上げる。MENDS 回手を替えても消えない崩れは聞く工程で利用者に聞く
- 模型に渡す言葉は頼みを訳した言葉だけ。ただし線の工程（サムネイル・アタリ・線画）では線のラフ画の言葉（SKETCH_WORDS）を足す。渡した言葉は「模型に渡す言葉:」の知らせにし、進み具合の欄の詳細にだけ置く
- 工程の始めには必ず「工程 i/N「名前」」の知らせを出す（i と N は計画の中の見せる工程の番号と数）。計画が伸びたら「要る工程 a→b」を出す
- 前の工程の絵に描き重ねたら、前の絵の色と明るさに合わせる（phase_tools.guard）
- 確かめ（confirm）を渡すと、9 の工程の 1 つが終わるたびに呼び、「進める」「この工程を描き直す」「言葉を足して描き直す」を受ける
- 止める旗が立ったら、工程の区切りで止まる
"""
from __future__ import annotations

import gc
import json
import re
import sys
import time
from pathlib import Path

# 工程の名前、決める物、見る物、判定の数字
HIDDEN = ("目的",)   # 描かない工程。利用者に見せる番号と名前から外す（atelier/ui/phase_display.py と同じ）
NO_PREVIEW = ("目的", "サムネイル", "アタリ")   # 描いている途中の絵（模型の拡散の途中）をキャンバスに出さない工程。描けた工程の絵は SHOW_FROM から出す
SHOW_FROM = "サムネイル"   # ラフ（サムネイル）から先の絵は、描けたら窓の作業用のレイヤーに筆で描き込んで見せる（線画・塗り・仕上げも同じ）
SKETCH_WORDS = "lineart, monochrome, greyscale, white background, clean lines, no color"   # 線のラフ画の言葉（atelier/ai/restyle.py の線画スタイルと同じ）。線の工程（サムネイル・アタリ・線画）で頼みの訳に足す
BASE_COLOR = 0.6   # 下塗り: 線の絵に初めて色をのせるときの描き重ねの強さ（線を残して色を付ける。私の推測）
PHASE_TAG = "atelier_phase"   # 工程の絵に付ける印（Image.info）。窓はこの印のある絵を途中の絵ではなく工程の絵として置く

PHASES = [
    ("目的", "何を一番見せるか（主役）", "頼み", "頼みの言葉の数、主役の言葉"),
    ("サムネイル", "ラフ画（線で構図を 1 枚直接描いて決める）", "白と黒の塊、画面の重さ", "人数、描かれていない物、重さの片寄り（weight_x）"),
    ("アタリ", "構図の調整と下描き（体の形・顔・手・足・服・髪・持ち物）", "立てるか、等身、体の形、手・足・顔、頼んだ物", "重心のずれ（balance）、等身（heads）、人数、骨の長さの比、目の傾き（eye_tilt）、手・指・足・顔の崩れの数、描かれていない物"),
    ("線画", "線の清書（ほぼ修正済みで微調整だけ）", "輪郭の途切れ、線のメリハリ", "外の輪郭の途切れ（gap）、線の明るさの差（contrast）"),
    ("下塗り", "部位ごとの色", "色の塊、色の数", "色の数（colors）"),
    ("光源", "光の向き 1 つ", "光の来る側", "左右・上下の明るさの差（dx, dy）"),
    ("影 2 段", "影 1 段目・2 段目", "影の向きのそろい、影が光より明るくないか", "影の側の暗い画素の割合（shade_share）、影と光の明るさの差"),
    ("光・艶・目のハイライト", "目の光、髪の艶", "目の中の光", "両目の一番明るい画素（eye_max）"),
    ("仕上げ", "全体の崩れ", "縮めて見る、反転して見る", "手・足・顔・体の崩れの数、縮めた明るさの差、顔の反転の差（asym）"),
]
NAMES = [p[0] for p in PHASES]
THUMB_SCALE = 1.0     # サムネイルの大きさ（描く大きさの割合）。同じ種・同じ大きさならアタリが同じ構図になるので縮めない
THUMB_STEPS = 1.0     # サムネイルの描く工程の数の割合。選んだサムネイルをそのままアタリにする（半分の工程で描いてから同じ種でアタリを
                      # 描き直すと、同じ構図を 2 度描いて 214 秒かかり、描き直した絵は別の色になった。0.25 ではぼやけた絵になった）
LINE_STRENGTH = 0.6   # 下描き: アタリの線に沿う強さ（T2I-Adapter の効き。0.8 では霞みと枠が出た）
REFINE = 0.45         # 下描き: アタリの絵に描き重ねる強さ（色と明るさを残す）
REPAINT = 0.35        # 服・髪・持ち物: 描かれていない物を足すときの描き直しの強さ（形は残す）
FIX = 0.55            # 顔・手・足の直し: 崩れた枠の中だけを描き直す強さ（1 回目）
FIXES = (0.55, 0.7, 0.85, 0.95)   # 直しを重ねるたびに強くする。同じ強さで戻って直すと崩れた指の形をなぞり、下描きから最後まで同じ崩れが残った
SHINE = 0.35          # 目の光の直し: 目の囲みの中だけを描き直す強さ
COLORS_MOST = 14      # 下塗り: 人物の 2% 以上を占める色がこれより多ければ、色が散っている（私の推測）
DIFF_MIN = 0.5       # 前の絵との画素の差の平均（0〜255）がこれ未満なら「変わらなかった」として数えない（私の推測）
MEND = (0.45, 0.55, 0.65, 0.75, 0.85, 0.95)   # 囲みの直しの強さ。変わらなかった・同じ崩れが続いた回ごとに 1 段上げる
GROW = 12            # 囲みを広げる画素の数（1 段ごと）
RESTART, GO_ON, REDPEN = "restart", "go", "redpen"   # REDPEN の答えは ("redpen", 囲みの白黒の絵の道)
MENDS = 3            # 同じ工程で手を替えて囲みを直す回数。消えなければ絵を前のまま残し、残った崩れとして次の工程へ進む
FIX_WORDS = {"hand": "correct hand, five fingers, anatomically correct fingers",
             "foot": "correct foot, five toes, anatomically correct toes",
             "face": "correct face, anatomically correct face"}   # 枠の種類ごとの、直す内容の言葉
COMPOSITION_ITEMS = ("頼んだ物", "位置ずれ")   # アタリの構図の崩れ。囲みの中だけでは直せない（腕の位置・物の配置は全体で決まる）


def fix_words(regions):
    """枠の種類（hand/foot/face）から、直す内容の言葉を作る。直す言葉が無い種類は入れない"""
    seen = []
    for _b, t in regions or []:
        w = FIX_WORDS.get(t)
        if w and w not in seen:
            seen.append(w)
    return ", ".join(seen)
WORDS_NOTE = "模型に渡す言葉: "   # この頭の知らせは会話に出さず、進み具合の欄の詳細にだけ置く（atelier/panels/activity_panel.py）
GO, REDO, WORDS = "go", "redo", "words"   # 工程の確かめの答え


class Checks:
    """工程ごとの検品。試験はこの組を偽物に差し替える"""

    @staticmethod
    def request(image, prompt):
        from atelier.qc import request_check as requestcheck
        return requestcheck.check(image, prompt)

    @staticmethod
    def body(image, prompt, tags=None):
        from atelier.qc import sanity
        return sanity.check(image, prompt, tags=tags)

    @staticmethod
    def points(image):
        """体の 17 点（VitPose）。同じ絵は 1 回だけ推論する（twostage._vitpose が置いておく）"""
        from atelier.ai import two_stage as twostage
        return {"readable": True, "points": twostage.keypoints(image)}

    @staticmethod
    def pose(image):
        """骨組みを読み、骨の比を測る。map は骨組みを重ねた絵（工程の絵に残す）"""
        try:
            from atelier.qc import sanity
            from atelier.ai import two_stage as twostage
            kp = twostage.keypoints(image)
            skel, _n = twostage.pose_map(image)
        except Exception as e:   # noqa: BLE001  骨組みの部品が無い。見ていない物を通ったことにしない
            return {"readable": False, "bad": [], "reason": f"骨組みを読めません（{e}）"}
        bad = []
        if len(kp) < 10:
            bad.append(f"骨組みが読めない（体の点 {len(kp)}/17）")
        for chain in sanity.ARM_CHAINS + sanity.LEG_CHAINS:
            r = sanity.bone_ratio(kp, chain)
            if r is not None and (r > sanity.BONE_MOST or r < 1 / sanity.BONE_MOST):
                bad.append(f"骨の長さの比が外れている（{chain[1]} {r}）")
        from PIL import Image
        over = Image.blend(image.convert("RGB"), skel.convert("RGB").resize(image.size), 0.45)
        return {"readable": True, "bad": bad, "map": over, "points": len(kp)}

    @staticmethod
    def hands(image, prompt):
        from atelier.qc import hand_check as handcheck
        return handcheck.check(image, asked=prompt)


class _Safe:
    """検品の 1 つが例外を出したら（部品が無い・試験の偽物に無い検品も）、その検品を「読めなかった」にして次へ進む"""

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        fn = getattr(self.inner, name, None)

        def call(*a, **k):
            if fn is None:
                return {"readable": False, "bad": [], "reason": f"検品 {name} がありません"}
            try:
                return fn(*a, **k)
            except Exception as e:   # noqa: BLE001  見ていない物を通ったことにしない（readable を False にする）
                if type(e).__name__ == "Stopped":
                    raise
                return {"readable": False, "bad": [], "reason": f"検品できませんでした（{type(e).__name__}: {e}）"}
        return call


def abilities(painter) -> tuple[bool, bool]:
    """(線に沿って描けるか, 枠の中だけ直せるか)。偽の模型は abilities を持てる"""
    own = getattr(painter, "abilities", None)
    if own is not None:
        return tuple(own)
    from atelier.models.catalog import family, image_model
    f = family(image_model(getattr(painter, "model", "")).family)
    return bool(f.sketch), bool(f.inpaint)


def release() -> float:
    """工程の区切りでメモリを返し、今の常駐の大きさ（MB）を返す"""
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:   # noqa: BLE001
            pass
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:   # noqa: BLE001
        return 0.0


def _shape(flaws) -> list[str]:
    """崩れの文から数字を外した形。「0.745」と「0.759」のように値だけ違う崩れを同じ崩れとして比べる"""
    return [re.sub(r"\d+(?:\.\d+)?", "#", str(f)) for f in flaws]


def _mask(size, regions):
    from PIL import Image, ImageDraw
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    for (x0, y0, x1, y1), _kind in regions:
        cx, cy, rr = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * 0.6
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=255)
    return mask


def _people(req: dict) -> list[str]:
    if not req.get("readable"):
        return []
    return [f"人数が違う: {p}" for p in req.get("people", [])] + list(req.get("body", []))


def _missing(req: dict) -> list[str]:
    return [f"描かれていない: {m}" for m in req.get("missing", [])] if req.get("readable") else []


def _extra(req: dict) -> list[str]:
    return [f"頼んでいない: {e}" for e in req.get("extra", [])] if req.get("readable") else []


PERSON_WORDS = ("1girl", "1boy", "girl", "boy", "woman", "man", "person", "people", "character", "portrait",
                "child", "baby", "lady", "figure", "女の子", "男の子", "女性", "男性", "キャラクター", "人物", "少女", "少年")
# 頼みの言葉に人物を表す言葉（英語の訳・日本語とも）
ANIMAL_WORDS = ("dog", "cat", "bird", "horse", "animal", "fox", "wolf", "bear", "rabbit", "deer", "lion", "tiger",
                "elephant", "monkey", "mouse", "fish", "owl", "snake", "frog", "pig", "cow", "sheep", "goat",
                "chicken", "duck", "penguin", "dolphin", "whale", "shark", "octopus", "spider", "butterfly", "bee",
                "犬", "猫", "鳥", "馬", "動物", "狐", "狼", "熊", "兎", "鹿", "ライオン", "虎", "象", "猿",
                "魚", "フクロウ", "蛇", "蛙", "豚", "牛", "羊", "山羊", "鶏", "鴨", "ペンギン", "イルカ", "鯨", "鮫", "蜘蛛", "蝶", "蜂")
# 頼みの言葉に動物を表す言葉
CREATURE_WORDS = ("dragon", "creature", "monster", "demon", "angel", "elf", "fairy", "alien", "orc", "goblin",
                  "troll", "vampire", "zombie", "ghost", "spirit", "centaur", "mermaid", "harpy", "arachne",
                  "竜", "ドラゴン", "モンスター", "悪魔", "天使", "エルフ", "妖精", "宇宙人", "オーク", "ゴブリン",
                  "吸血鬼", "ゾンビ", "幽霊", "人魚", "ハーピー", "アラクネ", "生き物", "妖怪", "ケンタウロス")
# 頼みの言葉に架空の生き物を表す言葉（顔・目・足がある）
HUMANOID_WORDS = ("humanoid", "android", "人型", "アンドロイド", "cyborg", "サイボーグ")
# 頼みの言葉に人型を表す言葉（人型ロボットは顔・目・手足がある）
NON_HUMANOID_WORDS = ("box", "箱", "car", "車", "machine", "機械", "tank", "戦車", "vehicle", "乗り物",
                      "airplane", "飛行機", "ship", "船", "truck", "トラック", "train", "電車", "building", "建物", "house", "家")
# 頼みの言葉に人型でない物を表す言葉（箱型の機械・車など。顔・目・足は無い）
ROBOT_WORDS = ("robot", "ロボット", "mecha", "メカ")
# 頼みの言葉にロボットを表す言葉（人型か箱型か分からなければ、人型とみなす）
LOCATION_WORDS = ("beach", "mountain", "lake", "river", "forest", "sky", "night", "sunset", "sunrise", "city",
                  "street", "room", "indoors", "outdoors", "garden", "park", "snow", "desert", "ocean", "sea",
                  "clouds", "stars", "moon", "rain", "winter", "summer", "school", "cafe", "kitchen", "bedroom",
                  "station", "airport", "bridge", "tower", "castle", "village", "town", "countryside", "field",
                  "meadow", "cliff", "cave", "island", "waterfall", "volcano", "space", "underwater",
                  "海辺", "山", "湖", "川", "森", "空", "夜", "夕日", "朝日", "街", "道", "部屋", "室内", "屋外",
                  "庭", "公園", "雪", "砂漠", "海", "雲", "星", "月", "雨", "冬", "夏", "学校", "カフェ", "台所",
                  "寝室", "駅", "空港", "橋", "塔", "城", "村", "町", "田舎", "野原", "崖", "洞窟", "島", "滝", "火山", "宇宙", "水中")
# 頼みの言葉に場所・背景を表す言葉（タガーが読む場所のタグ）
ROTATE_MOST = 5.0   # 画角の直し: 地平線の傾きがこれ（度）を超えたら、回して直さない（大きく回すと絵が歪むので、残った崩れにする。私の推測）


def _has_word(low, words) -> bool:
    """頼みの言葉（小文字）に、単語が入っているか。英字の続きでは数えない（'humanoid' の中の 'man' は数えない）。
    複数形の s は数える（'dogs' の 'dog' は数える）。数字の前は数える（'1girl' の 'girl' は数える）。
    日本語は英字ではないので、そのまま数える"""
    import re
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?:s)?(?![a-z])", low) for w in words)


def subject_kind(prompt, req=None) -> str:
    """描く物の種類。「person」（人）、「face」（顔・目・足がある人以外：動物・人型ロボット・架空の生き物）、
    「object」（物・風景・人型でないロボット）。顔・目・足があるかどうかで分ける。
    頼みの言葉に人物の言葉があれば人、動物・生き物・人型の言葉があれば顔のある物、人型でない物の言葉があれば物。
    ロボットは人型か箱型か分からなければ人型とみなす（箱型は「箱」などの言葉で物になる）。
    タガーが読めて、人物・動物・生き物を見つけなければ物。決め手が無ければ曖昧なので人として扱う（検品を全部回す側に倒す）"""
    low = str(prompt).lower()
    if _has_word(low, PERSON_WORDS):
        return "person"
    if _has_word(low, ANIMAL_WORDS + CREATURE_WORDS + HUMANOID_WORDS):
        return "face"
    if _has_word(low, NON_HUMANOID_WORDS):
        return "object"
    if _has_word(low, ROBOT_WORDS):
        return "face"
    if req is not None and req.get("readable"):
        if req.get("people"):
            return "person"
        read = req.get("read", {}) or {}
        tags = " ".join(k.lower() for k, v in read.items() if v >= 0.3)
        if _has_word(tags, PERSON_WORDS):
            return "person"
        if _has_word(tags, ANIMAL_WORDS + CREATURE_WORDS + HUMANOID_WORDS + ROBOT_WORDS):
            return "face"
        return "object"
    return "person"


def is_person_subject(prompt, req=None) -> bool:
    """後方互換: 描く物が人物かどうか。subject_kind が "person" のときだけ真"""
    return subject_kind(prompt, req) == "person"


def _background_flaws(prompt, req) -> list[str]:
    """背景の検品: 頼んだ場所・背景と、タガーが読んだ背景が合っているか。
    頼んだ場所が読めず、代わりに別の場所が高く読めたら、背景が違う。頼んだ場所が読めないだけなら、頼んだ物の検品が見る"""
    if not req.get("readable"):
        return []
    read = req.get("read", {}) or {}
    asked = [t.strip().lower() for t in str(prompt).split(",") if t.strip()]
    wanted = [t for t in asked if any(w in t for w in LOCATION_WORDS)]
    if not wanted:
        return []
    out = []
    for loc in wanted:
        if read.get(loc, 0.0) >= 0.2:
            continue   # 頼んだ場所が読めている
        others = [t for t, v in read.items()
                  if v >= 0.5 and any(w in t.lower() for w in LOCATION_WORDS) and t.lower() != loc]
        if others:
            out.append(f"背景が違う: {loc} を頼んだのに {others[0]} が描かれている")
    return out


def _face_bad(res: dict) -> list[str]:
    """手・顔・足の検品（hand_check）の崩れのうち、顔・目・足の物だけを返す。人の手の指の崩れは、動物・人型ロボット・
    架空の生き物には要らないので外す。手の崩れは「手」で始まり、足は「足」、顔は「顔」、脚の本数は「脚」で始まる"""
    return [f for f in res.get("bad", []) if not str(f).startswith("手")]


def _inside(tried, img, mask):
    """直した絵を、囲みの中だけ採り、外は元の絵の画素のまま返す（外は 1 画素も変えない）"""
    from PIL import Image
    if tried is None:
        return img
    if tried.size != img.size:
        tried = tried.resize(img.size)
    return Image.composite(tried.convert(img.mode), img, mask.convert("L"))


def diff(a, b, mask=None) -> dict:
    """2 枚の絵の画素の差。mean は全体の平均（0〜255）、outside は囲みの外の差の最大、inside は囲みの中の平均"""
    import numpy as np
    if a is None or b is None:
        return {"mean": None, "outside": None, "inside": None}
    x = np.asarray(a.convert("RGB").resize(b.size), dtype=np.int16)
    y = np.asarray(b.convert("RGB"), dtype=np.int16)
    d = np.abs(x - y).max(axis=2)
    out = {"mean": round(float(d.mean()), 3), "outside": None, "inside": None}
    if mask is not None:
        m = np.asarray(mask.convert("L").resize(b.size)) > 0
        out["outside"] = int(d[~m].max()) if (~m).any() else 0
        out["inside"] = round(float(d[m].mean()), 3) if m.any() else 0.0
    return out


GROW_MOST = 0.5   # 広げた囲みが絵のこの割合を超えたら、広げ方を半分にする（私の推測）


def _share(mask) -> float:
    import numpy as np
    return float((np.asarray(mask.convert("L")) > 0).mean())


def _grow(mask, r):
    from PIL import ImageFilter
    return mask if r <= 0 else mask.filter(ImageFilter.MaxFilter(2 * r + 1))


DRAWS = (1, 2, 3, 4, 6)   # 描く工程のある工程（サムネイル、アタリ、線画、下塗り、影 2 段）。ほかは測るだけで、描く工程を表に置かない


def draw(painter, prompt: str, seed: int, size, keep: Path, say=lambda m: None, on_step=None, checks=Checks, on_preview=None,
         confirm=None, pause_key: str | None = None, pause_job: dict | None = None, ask=None, answer=None) -> dict:
    """計画（atelier/ai/phase_plan.py の工程の並び）に沿って 1 枚を描く。返り値は {"image": 最後の絵, "phases": 工程ごとの最後の記録,
    "history": 全部の記録, "plan": 工程の並び, "left": [], "checked": True, "complete": True, "backs": 戻った回数,
    "total": 累計の工程の数, "need": 要る工程の数}。
    返るのは全部の工程が検品を通ったときか、利用者に聞いて止まったとき（asked）だけ。止めるのは利用者の「止める」（Stopped）だけ。
    confirm(i, 名前, 絵, 記録) は工程（9 の工程の 1 つ）の最後に呼び、"go"・"redo"・("words", 足す言葉の訳) を返す。
    pause_key があれば、打ち切られたとき・聞いて止まったときに、計画と位置と土台を atelier/files/pause_keep.py に残す。
    同じ鍵で呼び直すと計画の同じ工程から続け、answer があれば止まった聞く工程の答えにする"""
    from PIL import Image
    from atelier.ai.engine import Stopped, emphasize
    from atelier.qc import hand_check as handcheck
    from atelier.ai import phase_tools as pt
    from atelier.ai import phase_items as items
    from atelier.ai.phase_plan import Plan, step
    from atelier.files import pause_keep as pausekeep
    keep.mkdir(parents=True, exist_ok=True)
    pv = {"on_preview": on_preview} if on_preview is not None else {}   # 描いている途中の絵を窓に渡す
    can_line, can_fix = abilities(painter)
    can_refine = hasattr(painter, "refine")
    checks = _Safe(checks)
    w, h = (size or (832, 1216))
    n = len(PHASES)
    st = {"image": None, "prompt": prompt, "thumb": None, "points": {}, "light": {}, "height": 0, "seed": seed}
    memo = {"thumbs": {}, "measured": {}, "check": False}   # 描いた絵と測った結果を使い回す（同じ絵を 2 度描かない・測らない）
    tones = []

    def tell(words):
        say(f"{WORDS_NOTE}{words}")

    def sketch_prompt():
        """線のラフ画を描く言葉（頼みの訳に線画の言葉を足した物）。サムネイル・アタリ・線画で使う"""
        return f"{st['prompt']}, {SKETCH_WORDS}"

    def phase_prompt(i):
        """工程 i で直すときに模型に渡す言葉。線の工程（アタリ・線画まで）は線の言葉、色の工程（下塗りから）は頼みの訳だけ"""
        return sketch_prompt() if i <= 3 else st["prompt"]

    def _kind():
        """描く物の種類。m_atari が頼みの言葉とタガーの結果で決めて st に置く。決まっていなければ人として扱う"""
        return st.get("kind", "person")

    def _is_person():
        """人かどうか"""
        return _kind() == "person"

    def _has_face():
        """顔・目・足があるかどうか（人・動物・人型ロボット・架空の生き物）。物・風景・人型でないロボットは偽"""
        return _kind() in ("person", "face")

    def keep_tone(img, ref, where, mask=None):
        """描き重ねた絵を、前の工程の絵の色と明るさに合わせる（霞み・枠・色褪せを次の工程へ持ち越さない）"""
        if img is None or ref is None:
            return img
        try:
            out, rec = pt.guard(img, ref, mask)
        except Exception as e:   # noqa: BLE001  色・明るさの保全を検証できない候補は採用しない
            say(f"{where}: 色と明るさを検証できなかったため、修正前の絵に戻します（{type(e).__name__}: {e}）")
            return ref
        rec["where"] = where
        tones.append(rec)
        if rec["raw_flaws"]:
            say(f"{where}: 描き重ねで " + "、".join(rec["raw_flaws"]) + (" ので、前の絵を使います" if rec["kept_ref"] else " のを、色合わせで直しました"))
        return out

    def stop():
        if getattr(painter, "stop", False) is True:
            raise Stopped("止めました")

    def steps(ratio):
        s0 = getattr(painter, "steps", None)
        if isinstance(s0, int):
            painter.steps = max(4, int(s0 * ratio))
        return s0

    def unsteps(s0):
        if isinstance(s0, int):
            painter.steps = s0

    def points(img):
        got = checks.points(img)
        return dict(got.get("points") or {}) if got.get("readable") else {}

    # 描く工程。どれも {"image", "words", "note", "numbers"} を返し、測ることも直すこともしない
    def d_thumbs(v):
        # AI モードと同じ始まり。1 枚を直接描いて構図を決める（前は 2 枚描いて比べ、崩れの少ない方を選んでいた）。
        # 選ぶ手間を省く代わり、構図は確かめる工程が測り、悪ければ構図から描き直す。線のラフ画として描く（色を付けない）
        tw, th = (w, h) if THUMB_SCALE >= 1 else (max(256, int(w * THUMB_SCALE) // 8 * 8), max(256, int(h * THUMB_SCALE) // 8 * 8))
        s0 = steps(THUMB_STEPS)
        s = st["seed"] + v * 1000
        words = []
        try:
            stop()
            say(f"サムネイルを描いています（{tw}x{th}）")
            tell(sketch_prompt())
            words.append(sketch_prompt())
            img = painter.paint(sketch_prompt(), s, on_step=on_step, size=(tw, th))   # サムネイルは途中の絵もキャンバスに出さない（NO_PREVIEW）
            if THUMB_SCALE >= 1 and THUMB_STEPS >= 1:
                memo["thumbs"][(st["prompt"], s)] = img
            req = checks.request(img, st["prompt"])   # 構図を測る。崩れは確かめる工程が項目ごとに出す
            wt = pt.thumb_weight(img)
            flaws = _people(req) + _missing(req) + (["画面の重さが片寄っている"] if wt["weight_x"] > pt.WEIGHT_MOST else [])
            rows = [{"seed": s, **wt, "flaws": len(flaws), "score": [len(flaws), wt["weight_x"]]}]
        finally:
            unsteps(s0)
        st["thumb"], st["seed_pick"] = img, s
        say(f"サムネイルを直接描きました（種 {s}、崩れ {len(flaws)}）")
        out = img.resize((w, h))
        memo["measured"][1] = (out, st["prompt"], {"flaws": flaws, "numbers": {"thumbs": rows, "picked": s},
                                                   "readable": bool(req.get("readable"))})
        return {"image": out, "words": words, "numbers": {"thumbs": rows, "picked": s}}

    def d_atari(v):
        # アタリは構図の調整と下描きを 1 つの工程にする。サムネイル（線のラフ画）を土台に、体の形・顔と手と足・服と髪と持ち物の
        # 下描きを描き重ねる。線の工程なので色は付けない。返す前に st["image"] を描く前の土台に戻す（描く工程の前後比較が働くように）
        words = []
        base = st["image"]
        s = st.get("seed_pick", st["seed"])
        got = memo["thumbs"].get((st["prompt"], s))
        if got is not None:   # 同じ種・同じ大きさ・同じ工程の数で描いたサムネイルがあれば、それがそのままアタリ（描き直さない）
            say(f"サムネイル（種 {s}）をそのままアタリにします")
            img = got
        else:
            s0 = steps(1.0)
            try:
                tell(sketch_prompt())
                words.append(sketch_prompt())
                img = painter.paint(sketch_prompt(), s, on_step=on_step, size=(w, h))   # アタリも途中の絵を出さない（NO_PREVIEW）
            finally:
                unsteps(s0)
        st["image"] = img
        d = d_draft(v)
        img = d["image"]
        words += d["words"]
        if st["prompt"] != prompt:   # 利用者が言葉を足したときだけ、服・髪・持ち物を描き足す
            st["image"] = img
            w2 = d_wear(v)
            img = w2["image"]
            words += w2["words"]
        st["image"] = base
        return {"image": img, "words": words}

    def d_draft(v):
        img, words, note = st["image"], [], ""
        s = st["seed"] + v * 1000
        base = img
        if can_refine:   # 描き重ね（絵から絵）を先にする。線に沿って白紙から描き直すと、霞み・枠・色褪せと服の変わりが出た
            say("アタリの絵に描き重ねて、顔・手・足を描き込んでいます")
            tell(sketch_prompt())
            words.append(sketch_prompt())
            img = keep_tone(painter.refine(sketch_prompt(), s, img, strength=REFINE, on_step=on_step, **pv), base, "下描き")
        elif can_line:
            say("アタリの線に沿って、顔・手・足を描き込んでいます")
            tell(sketch_prompt())
            words.append(sketch_prompt())
            img = keep_tone(painter.paint(sketch_prompt(), s, on_step=on_step, base=img, strength=LINE_STRENGTH, size=(w, h), **pv), base, "下描き")
        else:
            note = "この模型は描き重ねられないので、アタリの絵のまま顔・手・足を確かめます"
        return {"image": img, "words": words, "note": note}

    def d_wear(v):
        """アタリの中で呼ぶ。利用者が言葉を足したときだけ、足した言葉を服・髪・持ち物の所だけに描く"""
        img, words = st["image"], []
        if not can_fix:
            return {"image": img, "words": words, "note": "この模型は囲みの中だけを直せないので、足した言葉を描けません"}
        req = checks.request(img, st["prompt"])
        missing = list(req.get("missing", [])) if req.get("readable") else []
        words2 = emphasize(sketch_prompt(), missing) if missing else sketch_prompt()
        say("足した言葉を、服・髪・持ち物の所だけに描き足しています")
        tell(words2)
        words.append(words2)
        protect = [b for b in [pt.face_box(st.get("points") or {})] if b]
        mask, by_parts = pt.wear_mask(img, protect)
        tried = _inside(keep_tone(painter.redraw(words2, st["seed"] + 131 + v * 1000, img, mask, strength=REPAINT), img, "服・髪・持ち物", mask), img, mask)
        return {"image": tried, "words": words, "numbers": {"by_parts": by_parts}}

    def d_lines(v):
        say("線の強弱を付けています（外の輪郭を太く濃く、内側の線はそのまま）")
        out, hit = pt.weight_lines(st["image"])
        return {"image": out, "numbers": {"pixels": hit}}

    def d_base(v):
        """下塗り。線の工程までは色を付けないので、ここで初めて色をのせる。線の絵に色を描き重ねる。
        keep_tone は掛けない。pt.guard は色を土台（線の絵）に合わせて戻すので、せっかくのせた色が消える。
        途中の絵（on_preview）は渡さない。色をのせた絵がそのまま工程の絵になるので、途中の絵と工程の絵が同じになり、同じ絵を続けて出すことになる"""
        img, words = st["image"], []
        s = st["seed"] + v * 1000
        if can_refine:
            say("線画に、初めて色を下塗りしています")
            tell(st["prompt"])
            words.append(st["prompt"])
            return {"image": painter.refine(st["prompt"], s, img, strength=BASE_COLOR, on_step=on_step), "words": words}
        if can_line:
            say("線画に、初めて色を下塗りしています")
            tell(st["prompt"])
            words.append(st["prompt"])
            return {"image": painter.paint(st["prompt"], s, on_step=on_step, base=img, strength=BASE_COLOR, size=(w, h)), "words": words}
        return {"image": img, "words": words, "note": "この模型は描き重ねられないので、線画のまま色を確かめます"}

    def d_shadow(v):
        img, lit = st["image"], st.get("light") or {}
        keep_m = None
        fb = pt.face_box(st.get("points") or {})
        if fb:
            import numpy as np
            keep_m = np.zeros((img.height, img.width), bool)
            x0, y0, x1, y1 = (int(max(0, c)) for c in fb)
            keep_m[y0:y1, x0:x1] = True   # 顔に濃い影を足さない
        say("影の 2 段目を、光源と反対の側の暗い所だけに置いています")
        out, hit = pt.shade_second(img, lit, keep_m)
        return {"image": out, "numbers": {"pixels": hit}}

    def draws(i):
        return i in DRAWS

    drawer = {1: d_thumbs, 2: d_atari, 3: d_lines, 4: d_base, 6: d_shadow}

    # 測る。どれも {"flaws", "numbers", "readable", "regions", "eyes", "missing", "show", "note"} を返す。描かない
    def m_purpose(img):
        tags = [t.strip() for t in st["prompt"].split(",") if t.strip()]
        return {"flaws": [] if tags else ["頼みが空です"], "numbers": {"words": len(tags), "main": tags[0] if tags else ""}, "readable": True}

    def m_thumbs(img):
        req = checks.request(img, st["prompt"])
        wt = pt.thumb_weight(img)
        return {"flaws": _people(req) + _missing(req) + (["画面の重さが片寄っている"] if wt["weight_x"] > pt.WEIGHT_MOST else []),
                "numbers": wt, "readable": bool(req.get("readable"))}

    def m_atari(img):
        # アタリの確かめは、旧「アタリ」「体の形」「顔・手・足の下描き」「服・髪・持ち物」を 1 つにした物。
        # 頼んだ物があるかの確かめ（request）は 1 回だけ呼び、結果を使い回す
        req = checks.request(img, st["prompt"])
        st["kind"] = subject_kind(st["prompt"], req)
        flaws = _people(req) + _missing(req) + _extra(req)
        numbers = {"missing": len(_missing(req)), "extra": len(_extra(req))}
        if st["prompt"] != prompt and not can_fix:
            flaws.append("追加指示を反映できません（この模型は描き直し不可）")
        # どの種類でも見る物：地平線の傾き（画角）、背景、体から離れた物（位置ずれ）
        regions = []
        tilt_h = None
        hz = pt.horizon(img)
        if hz.get("readable") and abs(hz["tilt"]) > pt.HORIZON_TILT_MOST:
            flaws.append(f"地平線が傾いている（{hz['tilt']} 度）")
            tilt_h = hz["tilt"]
            numbers["horizon_tilt"] = hz["tilt"]
        flaws += _background_flaws(st["prompt"], req)
        det = pt.detached(img)
        if det.get("readable") and det["count"]:
            flaws.append(f"体から離れている物がある（{det['count']} 個）")
            regions += [(b, "part") for b in det["boxes"]]
            numbers["detached"] = det["count"]
        if _kind() == "object":
            # 物・風景・人型でないロボットは、頼んだ物と画面の重さ（構図）だけを確かめる。顔・目・足を見る模型は使わない
            wt = pt.thumb_weight(img)
            numbers["weight_x"] = wt["weight_x"]
            if wt["weight_x"] > pt.WEIGHT_MOST:
                flaws.append("画面の重さが片寄っている")
            return {"flaws": flaws, "regions": regions, "numbers": numbers,
                    "missing": list(req.get("missing", [])) if req.get("readable") else [],
                    "tilt": tilt_h, "readable": bool(req.get("readable"))}
        # 顔・目・足がある物（人・動物・人型ロボット・架空の生き物）は、重心と顔・目・足を見る
        pc = checks.points(img)
        pts = dict(pc.get("points") or {}) if pc.get("readable") else {}
        bal = pt.balance(img)
        if bal.get("readable") and bal["balance"] > pt.BALANCE_MOST:
            flaws.append(f"重心が足の上に無い（{bal['balance']}）")
        res = checks.hands(img, st["prompt"])
        faces = res.get("faces") or []
        if faces and faces[0].get("box"):
            st["face_box"] = faces[0]["box"]
        tilt = pt.eye_tilt(pts)
        if _is_person():
            # 人のときだけ、等身・骨組みの比・体の検品と、手の指・服の検品を使う
            hd = pt.heads(pts, bal.get("height", 0)) if bal.get("readable") else None
            if hd is not None and not (pt.HEADS[0] <= hd <= pt.HEADS[1]):
                flaws.append(f"等身が外れている（{hd}）")
            pz, bd = checks.pose(img), checks.body(img, st["prompt"])
            flaws += (list(pz.get("bad", [])) if pz.get("readable") else []) + (list(bd.get("bad", [])) if bd.get("readable") else [])
            flaws += list(res.get("bad", []))
            regions += list(handcheck.bad_regions(res))
            numbers.update({"heads": hd, "points": len(pts)})
            show = pz.get("map")
            note = "" if pz.get("readable") else pz.get("reason", "骨組みを読めませんでした")
            readable = bool(req.get("readable")) and bool(bal.get("readable")) and bool(pz.get("readable")) and bool(bd.get("readable")) and bool(res.get("readable")) and bool(pc.get("readable"))
        else:
            # 動物・人型ロボット・架空の生き物は、顔・目・足だけを見る。人の手の指・服・等身・骨組みの比は使わない
            # 顔・足の模型が読めたかどうかで、読めたことにする（手の模型は人専用で、動物には手が無いので読めなくて当たり前）
            face_ok = bool(res.get("readable")) or bool(faces) or bool(res.get("feet")) or bool((res.get("face") or {}).get("readable"))
            flaws += _face_bad(res)
            regions += [(b, k) for b, k in handcheck.bad_regions(res) if k in ("foot", "face")]
            numbers.update({"points": len(pts)})
            show = None
            note = ""
            readable = bool(req.get("readable")) and bool(bal.get("readable")) and face_ok
        if tilt is not None and tilt > pt.EYE_TILT:
            flaws.append(f"左右の目の高さがずれている（{tilt}）")
            if pt.face_box(pts):
                regions.append((pt.face_box(pts), "face"))
        st["points"], st["height"] = pts, bal.get("height", 0)
        numbers.update({"balance": bal.get("balance"), "eye_tilt": tilt, "bad": len(res.get("bad", []))})
        return {"flaws": flaws, "regions": regions, "numbers": numbers, "show": show,
                "missing": list(req.get("missing", [])) if req.get("readable") else [],
                "note": note, "tilt": tilt_h, "readable": readable}

    def m_lines(img):
        m = pt.lines(img)
        flaws = []
        regions = []
        if m.get("readable"):
            if m["gap"] > pt.LINE_GAP_MOST:
                flaws.append(f"外の輪郭が途切れている（{m['gap']}）")
            if m.get("max_gap", 0) > pt.LINE_MAX_GAP_MOST:
                flaws.append(f"線が途中でずれている（途切れが {m['max_gap']}）")
            if m.get("weight") is not None and m["weight"] < pt.LINE_WEIGHT_LEAST:
                flaws.append("線の強弱が無い（外の輪郭が細く薄い）")
        d = pt.dust(img)
        if d.get("readable") and d["count"]:
            flaws.append(f"ゴミがある（{d['count']} 個）")
            regions += [(b, "dust") for b in d["boxes"]]
        return {"flaws": flaws, "regions": regions, "numbers": m, "readable": bool(m.get("readable"))}

    def m_base(img):
        import numpy as np
        m = pt.silhouette(img)
        if m.sum() < 50:
            return {"flaws": [], "readable": False, "numbers": {}}
        q = img.convert("RGB").quantize(colors=32, method=Image.MEDIANCUT)
        a = np.asarray(q)[m]
        counts = np.bincount(a.ravel(), minlength=32) / max(a.size, 1)
        colors = int((counts >= 0.02).sum())
        p = pt.parts(img)
        flaws = [f"色が散っている（{colors} 色）"] if colors > COLORS_MOST else []
        regions = []
        b = pt.bleed(img)
        if b.get("readable") and b["share"] > pt.BLEED_MOST:
            flaws.append(f"色が紙にはみ出している（にじみ {b['share']}）")
            regions += [(box, "bleed") for box in b["boxes"]]
        return {"flaws": flaws, "regions": regions, "readable": True,
                "numbers": {"colors": colors, "parts": None if p is None else int(len(set(np.unique(p).tolist()) - {0}))}}

    def m_light(img):
        lit = pt.light(img)
        st["light"] = lit
        flat = lit.get("readable") and abs(lit["dx"]) < 2 and abs(lit["dy"]) < 2
        if lit.get("readable"):
            say(f"光源を{lit['side']}{'上' if lit['dy'] < 0 else '下'}に決めました")
        return {"flaws": ["光の向きが決まらない（明るさが平たい）"] if flat else [], "numbers": lit, "readable": bool(lit.get("readable"))}

    def m_shadow(img):
        sh = pt.shadows(img, st.get("light") or {})
        # 暗い画素の左右比率は線画・髪・服の色にも左右されるため、影側が光側より明るいかだけを主に見る
        # （shade_share は濃い細部を影と混同して誤検出するので、矛盾の検品には使わない）
        flaws = [f"影が光より明るい（{sh['shade_minus_lit']}）"] if sh.get("readable") and sh["shade_minus_lit"] > 0 else []
        return {"flaws": flaws, "numbers": sh, "readable": bool(sh.get("readable"))}

    def m_shine(img):
        if not _has_face():
            # 顔・目・足の無い物・風景は目の光の確かめを飛ばす（目は無い）
            return {"flaws": [], "numbers": {"eye_max": []}, "readable": True}
        pts = points(img)   # 目の光は今の絵から読んだ座標だけで確かめる（古い目の位置で通さない）
        cl = pt.catchlights(img, pts)
        if cl.get("readable"):
            return {"flaws": [f"目の光が無い（{x}）" for x in cl.get("eye_max", []) if x < pt.CATCHLIGHT],
                    "eyes": [(b, "eye") for b in cl.get("boxes", [])], "numbers": {"eye_max": cl.get("eye_max")},
                    "readable": True}
        if _is_person():
            # 人の目は体の点で読めなければ、目の光は検品できない
            return {"flaws": [], "numbers": {"eye_max": []}, "readable": False}
        # 動物・人型ロボット・架空の生き物は、人の体の点では目を読めない。アタリで読んだ顔の枠の上の半分（目の所）で、
        # 一番明るい画素を見る。顔の枠も無ければ、目の光の確かめは飛ばす（顔の検品が目を読んでいる）
        fb = st.get("face_box")
        if not fb:
            return {"flaws": [], "numbers": {"eye_max": []}, "readable": True}
        lum = pt.luminance(img)
        x0, y0, x1, y1 = (int(v) for v in fb)
        eye_y1 = (y0 + y1) // 2   # 顔の上の半分が目の所
        part = lum[max(0, y0):max(0, eye_y1), max(0, x0):max(0, x1)]
        best = int(part.max()) if part.size else 0
        eye_box = (x0, y0, x1, eye_y1)
        return {"flaws": [f"目の光が無い（{best}）"] if best < pt.CATCHLIGHT else [],
                "eyes": [(eye_box, "eye")], "numbers": {"eye_max": [best]}, "readable": True}

    def m_finish(img):
        sv = pt.shrink_view(img)
        flaws = []
        numbers = {"shrink": sv.get("contrast"), "asym": None}
        d = pt.dust(img)   # 仕上げでも、ゴミが残っていないか見る
        regions = []
        if d.get("readable") and d["count"]:
            flaws.append(f"ゴミがある（{d['count']} 個）")
            regions += [(b, "dust") for b in d["boxes"]]
        if not _has_face():
            # 顔・目・足の無い物・風景は、手・足・顔・体の崩れの確かめを飛ばす。縮めて見るだけ
            if sv.get("readable") and sv["contrast"] < pt.SHRINK_CONTRAST:
                flaws.append(f"縮めると主役が目立たない（{sv['contrast']}）")
            return {"flaws": flaws, "regions": regions, "numbers": numbers, "readable": bool(sv.get("readable"))}
        res = checks.hands(img, st["prompt"])
        body = checks.body(img, st["prompt"]) if _is_person() else {"readable": True, "bad": []}
        pts = points(img)
        face = pt.face_box(pts) or st.get("face_box")
        fv = pt.flip_view(img, face) if face else {"readable": False}
        if _is_person():
            flaws += list(res.get("bad", [])) + (list(body.get("bad", [])) if body.get("readable") else [])
            regions += list(handcheck.bad_regions(res))
        else:
            # 動物・人型ロボット・架空の生き物は、顔・目・足だけを見る。人の手の指・体は使わない
            flaws += _face_bad(res)
            regions += [(b, k) for b, k in handcheck.bad_regions(res) if k in ("foot", "face")]
        if sv.get("readable") and sv["contrast"] < pt.SHRINK_CONTRAST:
            flaws.append(f"縮めると主役が目立たない（{sv['contrast']}）")
        if fv.get("readable") and fv["asym"] > pt.FLIP_MOST:
            flaws.append(f"反転すると顔が片側に歪んで見える（{fv['asym']}）")
        numbers["asym"] = fv.get("asym")
        if _is_person():
            return {"flaws": flaws, "regions": regions, "numbers": numbers,
                    "readable": bool(res.get("readable")) and bool(body.get("readable")) and bool(pts)
                    and bool(sv.get("readable")) and bool(fv.get("readable"))}
        # 動物・人型ロボット・架空の生き物は、顔・足の模型が読めたかどうかで、読めたことにする。人の体の点は要らない
        face_ok = bool(res.get("readable")) or bool(res.get("faces")) or bool(res.get("feet")) or bool((res.get("face") or {}).get("readable"))
        return {"flaws": flaws, "regions": regions, "numbers": numbers,
                "readable": bool(sv.get("readable")) and face_ok}

    measurer = [m_purpose, m_thumbs, m_atari, m_lines, m_base, m_light, m_shadow, m_shine, m_finish]
    assert len(measurer) == n

    def measure(i, fresh=False):
        """工程 i の見る物を今の絵で測る。同じ絵・同じ言葉なら測り直さない（確かめる工程が項目ごとに同じ結果を読む）"""
        img = st.get("image")
        got = memo["measured"].get(i)
        if not fresh and got is not None and got[0] is img and got[1] == st["prompt"] and "by_item" in got[2]:
            return got[2]
        # サムネイルは選ぶときに測った結果を使う（同じ絵を 2 度測らない）
        res = got[2] if got is not None and got[0] is img and got[1] == st["prompt"] and not fresh else measurer[i](img)
        flaws = list(res.get("flaws", []))
        if not res.get("readable") and items.UNREADABLE not in flaws:
            flaws.append(items.UNREADABLE)   # 読めない絵は崩れとして扱う
        res["flaws"] = flaws
        res["by_item"] = items.split(flaws)
        memo["measured"][i] = (img, st["prompt"], res)
        return res

    # 計画と記録
    saved = pausekeep.state(pause_key) if pause_key else None
    if saved and "plan" in saved:   # 一時停止した工程から続ける。済んだ工程の絵と記録はそのまま使う
        plan = Plan.load(NAMES, HIDDEN, saved["plan"])
        final, history, entry, visits = saved["final"], saved["history"], saved["entry"], saved["visits"]
        backs, total, fixes = saved["backs"], saved["total"], saved["fixes"]
        tries, passed_over, phase_left = saved["tries"], saved["passed_over"], saved["phase_left"]
        remaining = dict(saved.get("remaining") or {})
        st.clear()
        st.update(saved["st"])
        if saved.get("asked") and answer is not None:   # 止めて聞いた工程に、窓で選んだ答えを渡す（一度だけ）
            given = [answer]
            ask = lambda *_a: given.pop() if given else None   # noqa: E731
        j, nn = plan.number()
        say(f"一時停止した工程 {j}/{nn}「{plan.label(plan.current())}」から続けます（累計 {total} 工程まで描いてあります）")
    else:
        saved = None
        plan = Plan.initial(NAMES, draws, HIDDEN)
        final, history, entry, visits = {}, [], {}, [0] * n
        backs, total, fixes = 0, 0, 0
        tries: dict = {}          # (工程, 項目) ごとの、直しの強さの段（手を替えた回数）
        passed_over: list = []    # 利用者が「このまま進む」を選んだ崩れ
        remaining: dict = {}      # 直らずに次の工程へ持ち越した崩れ（項目ごと）。あとの確かめで消えたら外す
        phase_left: dict = {}     # 工程ごとの、項目ごとの残った崩れ
    asked = None
    resumed = saved is not None

    def tkey(i, item):
        return f"{i}:{item}"

    def progress(state, left=()):
        """止めたときに窓が読む今の状態。裏の糸が止められて返りが無くても、ここから止めた所までの絵と崩れを出す"""
        rows = [final[k] for k in sorted(final, key=int) if final.get(k) is not None]
        cur = plan.current()
        j, nn = plan.number()
        try:
            (keep / "progress.json").write_text(json.dumps(
                {"state": state, "phase": NAMES[cur["phase"]] if cur else NAMES[-1], "step": plan.label(cur) if cur else "",
                 "no": j, "total": total, "need": nn, "left": list(left),
                 "images": [r["image"] for r in rows if r.get("image")], "names": [r["phase"] for r in rows if r.get("image")],
                 "image": next((r["image"] for r in reversed(history) if r.get("image")), None)},
                ensure_ascii=False, default=str), encoding="utf-8")
        except OSError:
            pass

    def save_img(img, i, name_tail):
        nonlocal total
        total += 1
        path = keep / f"{total:03d}-{i + 1:02d}-{name_tail}.png"   # 累計の順の名前。絵が変わった工程だけ保存する
        img.save(path)
        if on_preview is not None and i >= NAMES.index(SHOW_FROM):   # ラフ（サムネイル）から先の絵は、描けたら筆で見せる
            try:
                shown = img.copy()
                j, nn = plan.number()
                shown.info[PHASE_TAG] = {"phase": NAMES[i], "no": j, "need": nn, "total": total}
                on_preview(shown)
            except Exception:   # noqa: BLE001  見せるだけ。描く流れは止めない
                pass
        return str(path)

    def keep_pause(why_label, extra=None):
        pausekeep.save(pause_key, "phases", why_label, pause_job,
                       {"plan": plan.state(), "st": entry_step, "final": final, "history": history, "entry": entry, "visits": visits,
                        "backs": backs, "total": total, "fixes": fixes, "tries": tries, "passed_over": passed_over, "remaining": remaining,
                        "phase_left": phase_left, "need": plan.need(), **(extra or {})})

    def phase_row(i):
        """今の工程（9 の工程の 1 つ）の記録。工程に入るたびに 1 つ作り、その中の確かめ・直しの結果を積む"""
        row = final.get(i)
        if row is None or row.get("visit") != visits[i] or row.get("closed"):
            row = {"phase": NAMES[i], "decides": PHASES[i][1], "checks": PHASES[i][2], "numbers_of": PHASES[i][3],
                   "image": None, "found": [], "fixed": False, "after": [], "words": [], "numbers": {}, "readable": True,
                   "seconds": 0.0, "mem_mb": 0.0, "visit": visits[i], "total": total, "need": plan.need(), "diff": None,
                   "changed": False, "mends": [], "steps": [], "recheck": False}
            final[i] = row
            history.append(row)
            phase_left[str(i)] = {}
        return row

    def mend_mask(img, how):
        """直す工程の囲み（L の絵）。囲めなければ None"""
        import numpy as np
        kind = how.get("mask")
        mask = None
        if kind == "regions" and how.get("regions"):
            mask = _mask(img.size, [(tuple(b), t) for b, t in how["regions"]])
        elif kind == "eyes" and how.get("regions"):
            mask = _mask(img.size, [(tuple(b), t) for b, t in how["regions"]])
        elif kind == "boxes" and how.get("regions"):
            # 枠をそのまま四角で囲む（離れた物の枠。_mask の円は長い辺で広がりすぎる）
            mask = _box_mask(img.size, [tuple(b) for b, _t in how["regions"]])
        elif kind == "background":
            # 背景（人物の外）。人物の範囲の反対。広すぎれば、後の割合の確かめで囲めないことになる
            import numpy as np
            m = pt.silhouette(img)
            mask = Image.fromarray(((~m) * 255).astype("uint8"))
        elif kind == "shadow_side":
            # 影の側（光源と反対の側）の人物の範囲
            mask = pt.shadow_side_mask(img, st.get("light") or {})
        elif kind == "wear":
            fb = pt.face_box(st.get("points") or {})
            mask, _ = pt.wear_mask(img, [fb] if fb else [])
        elif kind == "pen":
            try:
                mask = Image.open(str(how["pen"])).convert("L").resize(img.size)
            except OSError:
                mask = None
        else:
            words = " ".join(str(x) for x in how.get("flaws", []))
            fb = pt.face_box(st.get("points") or {})
            if any(k in words for k in ("描かれていない", "頼んでいない")):
                mask, _ = pt.wear_mask(img, [fb] if fb else [])
            elif fb and any(k in words for k in ("目", "顔")):
                mask = _mask(img.size, [(fb, "face")])
            elif "人数" in words:
                mask = extra_people_mask(img)   # 余分な人の枠だけ（本人は囲まない）
            elif items.UNREADABLE in words or "検品できません" in words:
                mask = unreadable_mask(img, how)   # 読めなかった部位の枠（手なら手、体なら体）
            elif any(k in words for k in ("腕", "脚", "頭", "骨", "重心", "等身", "体", "輪郭", "線", "色", "影", "光", "主役",
                                          "手", "指", "足")):
                seg = pt.parts(img)   # 部位分けがあれば人の所だけ。無ければ紙でない所
                m = (seg > 0) if seg is not None else pt.silhouette(img)
                # 人の形が絵の半分を超えたら、背景まで人と読んでいる。広く直すと物が変わるので、ここでは囲まない（残った崩れにする）
                if m.sum() >= 50 and m.mean() <= GROW_MOST:
                    mask = Image.fromarray((m * 255).astype("uint8"))
        if mask is None or np.asarray(mask.convert("L")).max() == 0:
            return None
        if _share(mask) > GROW_MOST:   # 絵の半分を超える囲みは絵全体の描き直しと同じ。直さずに残った崩れにする
            return None
        return mask

    def _person(img):
        import numpy as np
        seg = pt.parts(img)
        return (seg > 0) if seg is not None else np.asarray(pt.silhouette(img), bool)

    def _box_mask(size, boxes):
        """枠をそのまま四角で囲む（_mask の円は長い辺で広がり、縦長の体の枠では絵の全体を覆った）"""
        if not boxes:
            return None
        from PIL import ImageDraw
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        for b in boxes:
            x0, y0, x1, y1 = (int(c) for c in b)
            d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
        return m

    def extra_people_mask(img):
        """人の塊のうち、一番大きい塊（本人）を除いた塊の枠。塊が 1 つなら囲めない（None）"""
        import numpy as np
        from scipy import ndimage
        m = _person(img)
        if m.mean() > GROW_MOST:   # 背景まで人と読んでいる。塊を分けられない
            return None
        lab, n = ndimage.label(m)
        if n < 2:
            return None
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        big = int(np.argmax(sizes)) + 1
        small = max(50, int(m.size * 0.002))   # 塵は人として数えない
        boxes = []
        for k, sl in enumerate(ndimage.find_objects(lab), 1):
            if k != big and sl is not None and sizes[k - 1] >= small:
                boxes.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
        return _box_mask(img.size, boxes)

    def unreadable_mask(img, how):
        """読めなかった部位の枠。手・足・顔の枠が検品から出ていればそれ、無ければ体（人の形の外枠）"""
        import numpy as np
        regs = [tuple(b) for b, _t in (how.get("regions") or [])]
        if regs:
            return _box_mask(img.size, regs)
        m = _person(img)
        if not m.any() or m.mean() > GROW_MOST:
            return None
        ys, xs = np.nonzero(m)
        return _box_mask(img.size, [(xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)])

    def mends_for(i, item, flaws, res, k):
        """崩れを直す工程を作る。手・足・顔は検品の枠ごと（枠と崩れの数が合わなければ枠をまとめて 1 つ）、頼んだ物は服・髪・持ち物の所、
        目の光は目の囲みで 1 つ、ゴミ・にじみは紙の色で消し、位置ずれは離れた物の枠、画角は回し、背景は背景の所、線の強弱は太らせ、
        影は影の側、ほかは崩れ 1 つにつき 1 つ。直す工程には、必ず対応する検品がある（検品の無い直しは入れない）"""
        if item in items.REGION_ITEMS and res.get("regions"):
            regs = [[list(b), t] for b, t in res["regions"] if t in ("hand", "foot", "face")]
            if regs:
                if len(regs) == len(flaws) and len(flaws) > 1:
                    return [step("mend", i, item, flaws=[f], k=k, how={"mask": "regions", "regions": [r]}) for f, r in zip(flaws, regs)]
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs})]
        if item == "頼んだ物" and i == 2:
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "wear", "missing": list(res.get("missing", []))})]
        if item == "目の光" and res.get("eyes"):
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "eyes", "regions": [[list(b), t] for b, t in res["eyes"]]})]
        if item in ("ゴミ", "色のにじみ"):
            # ゴミ・にじみは、検品の枠の中を紙の色で消す（模型で描き直さない）
            kind = "dust" if item == "ゴミ" else "bleed"
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == kind]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs, "op": "erase"})]
        if item == "位置ずれ":
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == "part"]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "boxes", "regions": regs})]
        if item == "画角":
            tilt = res.get("tilt")
            if tilt is not None and abs(tilt) <= ROTATE_MOST:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "rotate", "angle": tilt})]
            return []   # 大きく傾いている。回して直さない（残った崩れとして次へ進む）
        if item == "背景":
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "background"})]
        if item == "線の強弱":
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "thicken"})]
        if item == "影":
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "shadow_side"})]
        regs = [[list(b), tt] for b, tt in (res.get("regions") or [])]
        return [step("mend", i, item, flaws=[f], k=k, how={"mask": "shape", "flaws": [f], **({"regions": regs} if regs else {})})
                for f in flaws]

    def grew(old):
        new = plan.need()
        if new != old:
            say(f"要る工程 {old}→{new}")

    def queue_fix(i, item, flaws, res, k, why=None):
        """崩れを囲みの中だけで直す工程と、その項目の確かめ直しを差し込む。囲めない・手を替え尽くした崩れは、
        絵を前のまま残し、「残った崩れ」として次の工程へ進む（利用者に聞いて止まらない。絵の全体も描き直さない）。
        次の工程の確かめと直しが、同じ崩れをまた囲みで直しにいく"""
        old = plan.need()
        if why is None and not can_fix:
            why = "この模型は囲みの中だけを直せません"
        if why is None and k >= MENDS:
            why = f"{MENDS} 回手を替えて囲みの中を直しても消えませんでした"
        if why is None:
            new = mends_for(i, item, flaws, res, k)
            at = plan.last_pending(("mend",), i, item)
            at = plan.pos + 1 if at is None else at + 1
            plan.insert(new + ([] if plan.pending("recheck", i, item) else [step("recheck", i, item)]), at)
        else:
            for x in list(plan.steps[plan.pos + 1:]):
                if x["phase"] == i and x.get("item") == item and x["kind"] in ("mend", "recheck") and x["status"] == "todo":
                    plan.steps.remove(x)
            remaining[item] = [f"{NAMES[i]}: {f}" for f in flaws]
            tries.pop(tkey(i, item), None)
            say(f"「{NAMES[i]}」の「{item}」は直りませんでした（{why}）。絵は前のまま残し、残った崩れとして次の工程へ進みます: "
                + "、".join(flaws[:3]))
        grew(old)

    def finish_phase(i, row):
        """工程（9 の 1 つ）の最後の工程が済んだ。記録をまとめ、確かめ（confirm）を受ける。描き直しを頼まれたら True"""
        nonlocal backs
        left = [f for fl in phase_left.get(str(i), {}).values() for f in fl]
        row["after"] = list(left)
        row["fixed"] = bool(row["mends"]) or row["fixed"]
        row["mem_mb"] = release()
        row["total"], row["need"] = total, plan.need()
        row["tone"] = pt.tone(st["image"]) if st.get("image") is not None else None
        row["tone_guard"] = [t for t in tones if t.get("phase") == NAMES[i]]
        say(f"「{NAMES[i]}」の検品: " + ("崩れは見つかりませんでした" if not left else "残った崩れ " + "、".join(left[:4])))
        progress("drawing", left)
        if confirm is None:
            return False
        ans = confirm(i, NAMES[i], st.get("image"), row)
        kind = ans[0] if isinstance(ans, (tuple, list)) else ans
        if kind not in (REDO, WORDS):
            return False
        backs += 1   # 利用者が頼んだ描き直しだけは、この工程の土台から描く
        added = False
        if kind == WORDS and isinstance(ans, (tuple, list)) and len(ans) > 1 and str(ans[1]).strip():
            add = str(ans[1]).strip()
            entry[i]["prompt"] = f"{entry[i]['prompt']}, {add}"
            say(f"言葉を足しました: {add}")
            added = True
        target = 2 if added and i >= 2 else i
        if target != i:
            entry[target] = dict(entry.get(target) or entry[i])
            entry[target]["prompt"] = entry[i]["prompt"]
            entry[target]["image"] = st["image"]   # 戻っても、今の絵を土台にする（前の工程の絵に巻き戻さない）
        say(f"描き直しを頼まれたので「{NAMES[target]}」から順に進めます")
        row["closed"] = True
        st.clear()
        st.update(entry[target])
        visits[target] += 1
        old = plan.need()
        plan.restart(target, draws)
        grew(old)
        return True

    entry_step = dict(st)
    left_now: list = []
    try:
        while not plan.done():
            stop()
            s = plan.current()
            i, item, kind = s["phase"], s.get("item", ""), s["kind"]
            entry_step = dict(st)   # 打ち切られたら、この工程に入ったときの土台から続ける
            row = phase_row(i)
            if not row["steps"] and not resumed:
                entry[i] = dict(st)   # 利用者の「この工程を描き直す」は、この工程に入ったときの土台から描く
            resumed = False
            j, nn = plan.number()
            label = plan.label(s)
            say(f"工程 {j}/{nn}「{label}」（直し {fixes} 回、累計 {total} 工程）: "
                + (PHASES[i][1] if kind == "draw" else f"見る物: {PHASES[i][2]}" if kind in ("check", "recheck") else "、".join(s.get("flaws", [])[:3])))
            progress("drawing", left_now)
            tones.clear()
            t0 = time.time()
            try:
                if kind == "draw":
                    got = drawer[i](visits[i])
                    before, img = st.get("image"), got.get("image")
                    d = diff(before, img) if img is not None else {"mean": None}
                    s["diff"] = d.get("mean")
                    s["changed"] = img is not None and (before is None or (d["mean"] or 0) >= DIFF_MIN)
                    s["words"] = list(got.get("words", []))
                    if img is not None:
                        st["image"] = img
                    row["words"] += s["words"]
                    row["numbers"].update(got.get("numbers") or {})
                    if got.get("note"):
                        row["note"] = got["note"]
                    if s["changed"]:
                        s["image"] = save_img(img, i, NAMES[i])
                        row.update({"image": s["image"], "changed": True, "diff": s["diff"]})
                    elif before is not None and img is not None:
                        say(f"「{NAMES[i]}」は絵を変えなかったので、工程として数えません")
                    s["status"] = "done"
                elif kind in ("check", "recheck"):
                    res = measure(i, fresh=(kind == "recheck"))
                    got_flaws = list(res["by_item"].get(item, []))
                    s["found"] = got_flaws
                    s["numbers"] = res.get("numbers", {})
                    s["readable"] = bool(res.get("readable"))
                    s["status"] = "done"
                    row["readable"] = bool(res.get("readable"))
                    row["numbers"].update(res.get("numbers") or {})
                    if res.get("note"):
                        row["note"] = res["note"]
                    if kind == "check" and not row["found"] and not row.get("measured"):
                        row["found"] = list(res["flaws"])   # 工程で初めに見つけた崩れ（全部の項目）
                        row["measured"] = True
                    if res.get("show") is not None and not row.get("show") and kind == "check":   # 骨組みを重ねた確かめの絵。数えずに残す
                        p_show = keep / f"{i + 1:02d}-{NAMES[i]}-確かめ.png"
                        res["show"].save(p_show)
                        row["show"] = str(p_show)
                    if kind == "check":   # 初めの並びに無い項目に崩れが出たら、その工程の確かめの最後に確かめる工程を足す
                        planned = {x.get("item") for x in plan.steps[:plan.end_of_phase(i)] if x["phase"] == i
                                   and x["kind"] == "check" and x.get("visit", visits[i]) == visits[i]}
                        extra = [it for it in res["by_item"] if it not in planned]
                        if extra:
                            old = plan.need()
                            plan.insert([step("check", i, it, visit=visits[i]) for it in extra], plan.end_of_phase(i))
                            grew(old)
                    if kind == "recheck":
                        prev = phase_left.get(str(i), {}).get(item, [])
                        if prev and len(got_flaws) > len(prev) and memo.get(("before", i, item)) is not None:
                            # 直しで崩れが増えた。直す前の絵に戻し、手を替えて直し直す（ゼロには戻らない）
                            say(f"「{item}」の直しで崩れが増えたので、直す前の絵に戻します")
                            st["image"] = memo[("before", i, item)]
                            got_flaws = prev
                            s["reverted"] = True
                    phase_left.setdefault(str(i), {})[item] = got_flaws
                    memo.pop(("before", i, item), None)
                    left_now = got_flaws
                    say(f"「{label}」: " + ("崩れは見つかりませんでした" if not got_flaws else "崩れ " + "、".join(got_flaws[:4])))
                    if got_flaws:
                        if i <= 1:
                            # 目的とサムネイルは直さずに次へ進む（サムネイルを描き直し続けて先へ進まなかった）。
                            # サムネイルの崩れは、そのあとの工程の確かめがもう一度見つけ、そこで囲んで直す
                            say(f"「{NAMES[i]}」の崩れは、次の工程から囲んで直します")
                            s["status"] = "carried"
                            row["carried"] = row.get("carried", []) + got_flaws
                            phase_left[str(i)][item] = []
                        else:
                            k = tries.get(tkey(i, item), -1) + 1
                            tries[tkey(i, item)] = k
                            queue_fix(i, item, got_flaws, res, k)
                    else:
                        tries.pop(tkey(i, item), None)
                        remaining.pop(item, None)   # 持ち越した崩れが、この工程の確かめで消えた
                elif kind == "mend":
                    cur = st["image"]
                    how = s.get("how") or {}
                    op = how.get("op")
                    k = int(s.get("k", 0))
                    if op in ("rotate", "thicken", "erase"):
                        # 模型で描き直さない直し（純粋な操作）。直す工程には、必ず対応する検品がある
                        tried = None
                        dd = None
                        changed = False
                        mend_name = {"rotate": "回す", "thicken": "太らせる", "erase": "消す"}[op]
                        if cur is None:
                            s["status"] = "skipped"
                            queue_fix(i, item, s.get("flaws", []), {}, k, why="絵がありません")
                        elif op == "rotate":
                            angle = float(how.get("angle") or 0)
                            # 地平線が右下がり（傾きが正）のとき、反時計回り（正の角度）に回すと水平になる
                            say(f"地平線の傾きを直すため、絵を {angle} 度回しています: " + "、".join(s.get("flaws", [])[:3]))
                            tried = cur.rotate(angle, resample=Image.BICUBIC, fillcolor=pt.paper_color(cur))
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        elif op == "thicken":
                            say(f"線を太らせ直しています: " + "、".join(s.get("flaws", [])[:3]))
                            r = pt.outline_radius(cur) * (k + 1)   # 直し直すたびに太くする
                            tried, _hit = pt.weight_lines(cur, r=r)
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        else:  # erase
                            mask = mend_mask(cur, how)
                            if mask is None:
                                s["status"] = "skipped"
                                queue_fix(i, item, s.get("flaws", []), {}, k, why="囲めない崩れです")
                            else:
                                import numpy as np
                                paper = pt.paper_color(cur)
                                arr = np.asarray(cur.convert("RGB")).copy()
                                arr[np.asarray(mask.convert("L")) > 0] = paper
                                tried = Image.fromarray(arr.astype("uint8"))
                                dd = diff(cur, tried, mask)
                                # 小さなゴミは全体の差が小さいので、囲みの中の差で変わったかを見る
                                changed = (dd["inside"] or 0) >= 10
                        if tried is not None and dd is not None:
                            s.update({"strength": 1.0, "diff": dd["mean"], "outside": dd.get("outside"), "inside": dd.get("inside"),
                                      "words": [], "changed": changed})
                            mrow = {"phase": NAMES[i], "mend": mend_name, "item": item,
                                    "strength": 1.0, "found": list(s.get("flaws", [])), "diff": dd["mean"], "outside": dd.get("outside"),
                                    "inside": dd.get("inside"), "words": [], "readable": True, "image": None, "changed": changed,
                                    "visit": visits[i]}
                            row["mends"].append(mrow)
                            if changed:
                                fixes += 1
                                memo.setdefault(("before", i, item), cur)
                                st["image"] = tried
                                s["image"] = mrow["image"] = save_img(tried, i, f"{NAMES[i]}-直し")
                                s["status"] = "done"
                            else:
                                say(f"直しで絵がほとんど変わらなかったので（差 {dd['mean']}）、数えずに直し直します")
                                s["status"] = "unchanged"
                                nk = max(k + 1, tries.get(tkey(i, item), 0) + 1)
                                tries[tkey(i, item)] = nk
                                old = plan.need()
                                if nk < MENDS:
                                    plan.insert([step("mend", i, item, flaws=list(s.get("flaws", [])), k=nk, how=how)])
                                grew(old)
                    else:
                        k = int(s.get("k", 0))
                        seed = st["seed"] + 509 * (k + 1) + 31 * i + 7 * len(row["mends"])
                        full = False
                        attempted = False
                        if i == 2 and item in COMPOSITION_ITEMS and can_refine:
                            # 構図の崩れ（頼んだ物が無い・物が離れている）は、囲みの中だけでは直せない。
                            # 腕の位置や物の配置はアタリ全体で決まるので、アタリ全体を描き直す（絵から絵）。囲みは要らない
                            strength = MEND[min(k, len(MEND) - 1)]
                            words = phase_prompt(i)
                            missing = how.get("missing") or []
                            if missing:
                                # 描かれていない物は言葉の頭に置く。後ろに足すだけでは埋もれて、模型は同じ物を描かない。
                                # 頭の言葉ほど拡散で重みが大きい
                                words = f"{', '.join(str(x) for x in missing)}, {words}"
                            say(f"アタリ全体を描き直しています（強さ {strength}）: " + "、".join(s.get("flaws", [])[:3]))
                            tell(words)
                            raw = painter.refine(words, seed, cur, strength=strength)
                            tried = raw
                            dd = diff(cur, tried)
                            full = True
                            attempted = True
                        else:
                            mask = mend_mask(cur, how) if cur is not None else None
                            if mask is None:
                                s["status"] = "skipped"
                                queue_fix(i, item, s.get("flaws", []), {}, s.get("k", 0), why="囲めない崩れです")
                            else:
                                if how.get("mask") == "pen":
                                    strength, m = MEND[0], mask
                                else:
                                    strength = (FIXES[min(k, len(FIXES) - 1)] if how.get("mask") == "regions"
                                                else (REPAINT if k == 0 else MEND[min(k, len(MEND) - 1)]) if how.get("mask") == "wear"
                                                else (SHINE if k == 0 else MEND[min(k, len(MEND) - 1)]) if how.get("mask") == "eyes"
                                                else MEND[min(k, len(MEND) - 1)])
                                    m = _grow(mask, GROW * k)
                                    r = GROW * k
                                    while r > 0 and _share(m) > max(_share(mask), GROW_MOST):   # 広げすぎて絵全体の描き直しにならないようにする
                                        r //= 2
                                        m = _grow(mask, r)
                                words = emphasize(phase_prompt(i), how["missing"]) if how.get("mask") == "wear" and how.get("missing") else phase_prompt(i)
                                clean = False
                                if how.get("mask") == "regions":
                                    # 手・足・顔の形の崩れ：囲みの中を消してから描き直す。
                                    # 囲みの中に渡すのは、その囲みの直す内容の言葉だけ。
                                    # 依頼の文（場面の説明）は渡さない。囲みの外の絵が場面を教える。
                                    # 線の工程では線の言葉だけを足して、線画の調子を保つ。
                                    fw = fix_words(how.get("regions"))
                                    if fw:
                                        words = f"{fw}, {SKETCH_WORDS}" if i <= 3 else fw
                                    clean = True
                                say(f"崩れた所の囲みの中だけを直しています（強さ {strength}）: " + "、".join(s.get("flaws", [])[:3]))
                                tell(words)
                                raw = painter.redraw(words, seed, cur, m, strength=strength, clean=clean)
                                if how.get("mask") == "wear":
                                    raw = keep_tone(raw, cur, "服・髪・持ち物", m)
                                tried = _inside(raw, cur, m)
                                dd = diff(cur, tried, m)
                                attempted = True
                        if attempted:
                            s.update({"strength": strength, "diff": dd["mean"], "outside": dd["outside"], "inside": dd["inside"],
                                      "words": [words], "changed": (dd["mean"] or 0) >= DIFF_MIN})
                            mrow = {"phase": NAMES[i], "mend": "赤ペン" if how.get("mask") == "pen" else k + 1, "item": item,
                                    "strength": strength, "found": list(s.get("flaws", [])), "diff": dd["mean"], "outside": dd["outside"],
                                    "inside": dd["inside"], "words": [words], "readable": True, "image": None, "changed": s["changed"],
                                    "visit": visits[i], **({"pen": True} if how.get("mask") == "pen" else {}),
                                    **({"full": True} if full else {})}
                            row["mends"].append(mrow)
                            if s["changed"]:
                                fixes += 1
                                memo.setdefault(("before", i, item), cur)
                                st["image"] = tried
                                s["image"] = mrow["image"] = save_img(tried, i, f"{NAMES[i]}-{'赤ペンの' if how.get('mask') == 'pen' else ''}直し")
                                s["status"] = "done"
                            else:
                                # 絵がほとんど変わらなかった直しは工程として数えず、囲みを広げ、強さを上げて直し直す（同じ入力を繰り返さない）
                                say(f"直しで絵がほとんど変わらなかったので（差 {dd['mean']}）、数えずに囲みを広げ、強さを上げます")
                                s["status"] = "unchanged"
                                nk = max(k + 1, tries.get(tkey(i, item), 0) + 1)
                                tries[tkey(i, item)] = nk
                                old = plan.need()
                                if nk < MENDS and how.get("mask") != "pen":
                                    plan.insert([step("mend", i, item, flaws=list(s.get("flaws", [])), k=nk, how=how)])
                                # 手を替え尽くしたら差し込まない。待っている確かめ直しが同じ崩れを見つけ、聞く工程を差し込む
                                grew(old)
                elif kind == "ask":
                    why = s.get("why", "")
                    flaws = list(s.get("flaws", []))
                    choices = ["赤ペンで囲んで直す", "言葉を足して直す", "構図から描き直す", "このまま進む"]
                    say(f"「{NAMES[i]}」で崩れが残りました（{why}）: " + "、".join(flaws[:4]) + "。直し方を選んでください: " + "、".join(choices))
                    ans = ask(i, NAMES[i], flaws, choices) if ask is not None else None
                    akind = ans[0] if isinstance(ans, (tuple, list)) else ans
                    s["answer"] = akind
                    if akind == RESTART:
                        say("構図から描き直します（利用者が選びました）")
                        s["status"] = "done"
                        backs += 1
                        row["closed"] = True
                        st.clear()
                        st.update(entry[1])
                        st["seed"] = st.get("seed", seed) + 7919 * (visits[1] + 1)
                        visits[1] += 1
                        tries.clear()
                        memo["thumbs"].clear()
                        old = plan.need()
                        plan.restart(1, draws)
                        grew(old)
                    elif akind == WORDS and isinstance(ans, (tuple, list)) and len(ans) > 1 and str(ans[1]).strip():
                        st["prompt"] = f"{st['prompt']}, {str(ans[1]).strip()}"
                        say(f"言葉を足しました: {str(ans[1]).strip()}")
                        s["status"] = "done"
                        tries[tkey(i, item)] = 0
                        old = plan.need()
                        plan.insert([step("recheck", i, item)])   # 足した言葉で測り直し、残れば直す工程を差し込む
                        grew(old)
                    elif akind == REDPEN and isinstance(ans, (tuple, list)) and len(ans) > 1:
                        s["status"] = "done"
                        say("赤ペンで囲んだ所の中だけを直します（利用者が選びました）")
                        old = plan.need()
                        plan.insert([step("mend", i, item, flaws=flaws, k=0, how={"mask": "pen", "pen": str(ans[1])}),
                                     step("recheck", i, item)])
                        tries[tkey(i, item)] = 0
                        grew(old)
                    elif akind == GO_ON:
                        s["status"] = "done"
                        passed_over += [f"{NAMES[i]}: {x}" for x in flaws]
                        phase_left.setdefault(str(i), {})[item] = []
                        tries.pop(tkey(i, item), None)
                    else:
                        asked = {"phase": NAMES[i], "index": i, "item": item, "left": flaws, "why": why, "choices": choices,
                                 "step": plan.number()[0]}
                        s["status"] = "asked"
                        if pause_key:   # 窓のボタンで選んだ答えを持って、この聞く工程から続けられるように残す
                            s["status"] = "todo"
                            entry_step = dict(st)
                            keep_pause(f"「{NAMES[i]}」で崩れが残って止まり、直し方を待っています", {"asked": asked})
                            asked["key"] = pause_key
                        break
            except Exception as e:   # noqa: BLE001  止めて捨てずに、この工程に入ったときの計画と土台を残す
                if not pause_key or isinstance(e, (Stopped, pausekeep.Paused)):
                    raise
                st.clear()
                st.update(entry_step)
                keep_pause(f"「{label}」（累計 {total} 工程）で一時停止")
                progress("paused")
                raise pausekeep.Paused(f"「{label}」で一時停止しました（{type(e).__name__}: {e}）。"
                                       "途中まで保存したので、「再開」でこの工程から続けます", pause_key) from e
            s["seconds"] = round(time.time() - t0, 2)
            row["seconds"] = round(row["seconds"] + s["seconds"], 2)
            row["steps"].append(plan.number()[0])
            for t in tones:
                t.setdefault("phase", NAMES[i])
            nxt = plan.next_phase()
            if s["status"] in ("done", "carried", "skipped", "unchanged") and nxt != i and not row.get("closed"):
                finish_phase(i, row)   # 描き直しを頼まれたら、計画は今の位置のあとに積み直してある
            plan.advance()
    except Stopped:
        progress("stopped", left_now)
        (keep / "phases.json").write_text(json.dumps({"history": history, "plan": plan.rows(), "left": left_now, "stopped": True,
                                                      "total": total, "need": plan.need()}, ensure_ascii=False, indent=1, default=str),
                                          encoding="utf-8")
        raise
    rows = [final[k] for k in range(n) if final.get(k) is not None]
    unresolved = (list(asked["left"]) if asked else []) + passed_over + [f for fl in remaining.values() for f in fl]
    complete = not unresolved
    if complete or (not asked and pause_key):
        pausekeep.clear(pause_key)
    progress("done" if complete else "asked", unresolved)
    out = {"phases": rows, "history": history, "plan": plan.rows(), "left": unresolved, "checked": True, "complete": complete,
           "asked": asked, "backs": backs, "total": total, "need": plan.need(), "fixes": fixes,
           "remaining": [f for fl in remaining.values() for f in fl]}
    (keep / "phases.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {"image": st["image"], **out, "blocked": None, "unresolved": unresolved}
