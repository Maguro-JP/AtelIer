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
- 土台（2026-11-26 の方針）: アタリの頭で、頼みの言葉そのままで一発の絵を描く（生成 AI の一発は、人間で言う 80 点のサムネイル）。
  工程の仕事は、その 80 点を 100 点へ磨き上げること。土台は検品一式（頼んだ物・手足顔・体・ゴミ）で測って崩れの重さを基準として持ち、
  最後の絵の重さが土台より小さくなければ完成にしない。土台の絵は画面に出さず、工程の絵として保存もしない
  （見せるのは、白い紙から段階の絵が筆で描き上がる今の流れだけ。土台をいきなり完成品として見せることはしない）
- 色の工程は、線の段階の絵を土台として確かめてから始める。下塗りの直前に線画のゴミを測り、残っていれば塊そのものだけを消してから色を塗る
  （汚れた土台の上に下塗りを始めると、汚れが色に焼き付く）
- 直しは鉛筆と消しゴムと同じ。今の絵をそのまま土台に、崩れの場所（検品の枠、部位分け、人物の形）だけを囲み、その中だけを描き直す
  （redraw。外は Image.composite で 1 画素も変えない）。囲めない崩れは聞く工程にする。勝手に構図へ戻らない
- 直しの回数に上限は置かない（止めるのは利用者だけ）。絵がほとんど変わらない直し（差の平均が DIFF_MIN 未満）は累計に数えず、
  次の直す工程は囲みを広げ、強さを上げる。MENDS 回手を替えても消えない崩れは聞く工程で利用者に聞く
- 模型に渡す言葉は頼みを訳した言葉だけ。ただし線の工程では、ラフ（サムネイル・アタリ）は鉛筆のラフの言葉（ROUGH_WORDS）、線画はペンの言葉（PEN_WORDS）を足す。渡した言葉は「模型に渡す言葉:」の知らせにし、進み具合の欄の詳細にだけ置く
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
ROUGH_WORDS = "rough pencil sketch, light sketchy lines, construction lines, monochrome, greyscale, white background, no color"   # ラフ画の言葉（鉛筆や色鉛筆でさっと描く）。サムネイル・アタリで頼みの訳に足す
PEN_WORDS = "lineart, clean inked lines, monochrome, greyscale, white background, no color"   # 線画の言葉（ペンでなぞって描く）。線画で頼みの訳に足す
DETAIL_WORDS = "detailed texture, fine details, intricate details, delicate details"   # ディテールの言葉（質感の足し方だけ。新しく描く物の言葉は入れない）。ディテールで頼みの訳に足す
GPEN_WORDS = "clean inked lines drawn with a G-pen, varied line weight, tapered stroke ends, bold outer contours, thin inner lines, monochrome, greyscale, white background, no color"   # 清書の言葉（Gペンで仕上げる）。線の仕上げで頼みの訳に足す
WATERCOLOR_WORDS = "watercolor painting, soft translucent color washes, wet edges, paper texture"   # 画材に水彩の指定があったときだけ使う言葉
BRUSH_WORDS = {"pencil": ROUGH_WORDS, "pen": PEN_WORDS, "gpen": GPEN_WORDS, "watercolor": WATERCOLOR_WORDS}   # 画材（draw_tools の BRUSHES の名前）→ 模型に渡す描き方の言葉
MEDIUM_WORDS = (("gpen", ("gペン", "g-pen", "g pen", "gpen")),
                ("pencil", ("鉛筆", "色鉛筆", "pencil")),
                ("watercolor", ("水彩", "watercolor")),
                ("pen", ("ペン", "pen")))   # 頼みの言葉の中の画材の指定。Gペンは「ペン」を含むので先に見る
LINE_ART_WORDS = ("線画", "モノクロ", "白黒", "線だけ", "monochrome", "greyscale", "grayscale", "line art", "lineart")   # 線画で終わる頼みの言葉


def wants_line_art(prompt) -> bool:
    """線画で終わる頼みか。線画・清書はスタートラインで、指定が無いのに線画で終わることは
    しない。指定があれば、色の工程の代わりに線の質を上げて線画で完成にする（利用者の規則）"""
    p = (prompt or "").lower()
    return any(w in p for w in LINE_ART_WORDS)


def request_medium(prompt):
    """頼みの言葉に画材の指定があれば、その画材（draw_tools の BRUSHES の名前）。無ければ None。
    「鉛筆の画像」のような指定がある場合だけ、その指定の画材で描く（利用者の指示、2026-11-27）。
    指定は工程の既定の画材（ラフ=鉛筆、線画=ペン、清書=Gペン）より勝つ"""
    low = (prompt or "").lower()
    for kind, words in MEDIUM_WORDS:
        if _has_word(low, words):
            return kind
    return None
BASE_COLOR = 0.6   # 下塗り: 線の絵に初めて色をのせるときの描き重ねの強さ（線を残して色を付ける。私の推測）
BASE_OVER = 0.52   # 下塗り: 土台の色を線の下に敷いた絵に描き重ねる強さ（色と線の位置を残して塗り直す。私の推測。直しの強さの段と重ならない値にして、記録で見分ける）
BASE_GRAIN_MOST = 0.02   # 下塗り: 色の粒（ブツブツ）の割合がこれを超えたら、面の色に寄せて平らにする
PHASE_TAG = "atelier_phase"   # 工程の絵に付ける印（Image.info）。窓はこの印のある絵を途中の絵ではなく工程の絵として置く
BASE_TAG = "atelier_base"     # 土台の絵の印。土台は on_base の専用の渡し口で窓へ渡す（preview には流さない）。この印は、万一 preview に土台が混ざっても窓が出さないための受け止め用に残す

PHASES = [
    ("目的", "何を一番見せるか（主役）", "頼み", "頼みの言葉の数、主役の言葉"),
    ("サムネイル", "ラフ画（線で構図を 1 枚直接描いて決める）", "白と黒の塊、画面の重さ", "人数、描かれていない物、重さの片寄り（weight_x）"),
    ("アタリ", "構図の調整と下描き（体の形・顔・手・足・服・髪・持ち物）", "立てるか、等身、体の形、手・足・顔、頼んだ物", "重心のずれ（balance）、等身（heads）、人数、骨の長さの比、目の傾き（eye_tilt）、手・指・足・顔の崩れの数、描かれていない物"),
    ("線画", "ペンでなぞって描き、清書で仕上げる（パーツの検品はここまでで済ませる）", "輪郭の途切れ、線のメリハリ、手・足・顔、頼んだ物", "外の輪郭の途切れ（gap）、線の明るさの差（contrast）、手・足・顔の崩れの数、描かれていない物"),
    ("下塗り", "部位ごとの色", "色の塊、色の数", "色の数（colors）"),
    ("光源", "光の向き 1 つ", "光の来る側", "左右・上下の明るさの差（dx, dy）"),
    ("影 2 段", "影 1 段目・2 段目", "影の向きのそろい、影が光より明るくないか", "影の側の暗い画素の割合（shade_share）、影と光の明るさの差"),
    ("光・艶・目のハイライト", "目の光、髪の艶、水の光、葉のつや", "目の中の光、水の光、葉のつや", "両目の一番明るい画素（eye_max）、水の明るさの広がり、葉の明るさの広がり"),
    ("ディテール", "質感・小さい印・汚し・影の締め（仕上げの直前。消す直しはしない）", "ディテールの量、影の締まり", "主役の内側の質感の密度（detail_density）、影と光の明るさの差（shade_minus_lit）"),
    ("仕上げ", "全体の崩れ", "縮めて見る、反転して見る、タイヤの丸み、左右対称、遠近の収束", "手・足・顔・体の崩れの数、縮めた明るさの差、顔の反転の差（asym）、タイヤの丸み、対称、遠近の線の角度"),
]
NAMES = [p[0] for p in PHASES]
# サムネイルは土台（頼みの言葉そのままの 1 枚。工程の数は減らさない）から抜くので、サムネイルだけの大きさ・工程の数の割合は持たない。
# 前はラフを半分の工程の数で別に描き、土台もアタリの頭で描いていた（ゼロから 2 枚）。今はゼロから描くのは土台の 1 枚だけで、序盤は前より短い
EARLY_STEPS = 0.5     # アタリの描く速さ（工程の数の割合）。アタリはラフで、線画や清書と同じレベルまで仕上げない
LINE_STEPS = 0.8      # 線画の描く速さ。清書以降（下塗り・光源・影・ディテール・仕上げ）は割合 1.0 で時間をかける
LINE_STRENGTH = 0.6   # 下描き: アタリの線に沿う強さ（T2I-Adapter の効き。0.8 では霞みと枠が出た）
LINE_INK_KEEP = 0.6   # 線画: ペンなぞりのあと、濃い線の割合が土台のこの割合を切ったら線の暗さを戻す（私の推測）
REFINE = 0.45         # 下描き: アタリの絵に描き重ねる強さ（色と明るさを残す）
REPAINT = 0.35        # 服・髪・持ち物: 描かれていない物を足すときの描き直しの強さ（形は残す）
FIX = 0.55            # 顔・手・足の直し: 崩れた枠の中だけを描き直す強さ（1 回目）
FIXES = (0.45, 0.5, 0.55, 0.6)   # 直しの強さは少しずつだけ上げる。同じ強さでは崩れた指の形をなぞって同じ崩れが残った（昔の記録）が、
                      # 一気に強くすると囲みの中を丸ごと描き直す形になり、変化が大きくて崩れる。小さい変化を繰り返すと
                      # 崩れずに整っていく（利用者の指摘: 一気に消して一気に描くと崩れやすい）
SHINE = 0.35          # 目の光の直し: 目の囲みの中だけを描き直す強さ
DETAIL_LEAST = 0.03   # ディテール: 主役の内側の質感の密度がこれ未満なら、ディテールが薄い（私の推測）
SPECKS_MOST = 8       # ディテール: 描き重ねで増えた新しい暗い塊（ゴミの線・点）がこれを超えたら採用しない
FLAT_KEEP = 0.35      # 直し: 囲みの中の質感（明るさのばらつき）が直す前のこれ未満になったら、塗りつぶしとみて採用しない
FORM_CRUSH = 0.5      # 完成の判定: 最後の絵の質感の密度と鋭さが、両方とも土台のこれ未満なら、形が潰れたとみる
TONE_CRUSH = 0.85     # ディテール: 描き重ねでコントラストが元のこの割合を切ったら、影や濃い細部が潰れたとみて採用しない（私の推測）
DETAIL_CRUSH = 0.7    # ディテール: 描き重ねで質感の密度が元のこの割合を切ったら、細部が潰れたとみて採用しない（私の推測）
COLORS_MOST = 14      # 下塗り: 人物の 2% 以上を占める色がこれより多ければ、色が散っている（私の推測）
COVERAGE_MOST = 0.10  # 下塗り: 主役の輪郭の内側で紙の色のままの割合がこれを超えたら、塗り残し（私の推測）
LINE_FAT_MOST = 0.5    # 下塗り: 描き重ねで線のすぐ外側に増えた暗い画素が、線の画素のこの割合を超えたら、線が太ったとみる（私の推測）
LINE_LOSS_MOST = 0.02  # 色・仕上げの工程の出口: 清書の線のうち、合成で暗く残っていない割合がこれを超えたら埋もれ（私の推測）
DIFF_MIN = 0.5       # 前の絵との画素の差の平均（0〜255）がこれ未満なら「変わらなかった」として数えない（私の推測）
MEND = (0.45, 0.5, 0.55, 0.6, 0.65, 0.7)   # 囲みの直しの強さ。上げる幅は小さくする（FIXES と同じ理由。一気に変えない）
GROW = 12            # 囲みを広げる画素の数（1 段ごと）。直しの縁で切れた線や接合部は、広げた囲みで
                      # 描き直して初めてつながる（囲みの中だけでは、縁の切り口が残る）。変化を小さくするのは
                      # 強さの上げ幅と「1 枠ずつ」で行う（利用者の指摘: 一気に消して一気に描くと崩れる）
RESTART, GO_ON, REDPEN = "restart", "go", "redpen"   # REDPEN の答えは ("redpen", 囲みの白黒の絵の道)
MENDS = 3            # 同じ工程で手を替えて囲みを直す回数。消えなければ絵を前のまま残し、残った崩れとして次の工程へ進む
NO_PROGRESS = MENDS  # 直しても崩れの重さが下がらない直しがこの回数続いた項目は、後の工程で同じ直しを繰り返さない
# 直しの回数は精度のために削らない（利用者の指摘: 問題は回数ではなく速度）。
# 序盤で時間をかけないのは、回数ではなく 1 回の直しを速くすることで守る
FIX_WORDS = {"hand": "correct hand, five fingers, anatomically correct fingers",
             "foot": "correct foot, five toes, anatomically correct toes",
             "face": "correct face, anatomically correct face",
             "tire": "correct round tire, circular wheel, round tire",
             "perspective": "correct perspective, converging lines, vanishing point on horizon"}   # 枠の種類ごとの、直す内容の言葉
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
        self.failures = []   # (検品の名前, 読めなかった理由)。部品が無い・例外で落ちた検品だけを記録する

    def __getattr__(self, name):
        fn = getattr(self.inner, name, None)

        def call(*a, **k):
            if fn is None:
                reason = f"検品 {name} がありません"
                self.failures.append((name, reason))
                return {"readable": False, "bad": [], "reason": reason}
            try:
                return fn(*a, **k)
            except Exception as e:   # noqa: BLE001  見ていない物を通ったことにしない（readable を False にする）
                if type(e).__name__ == "Stopped":
                    raise
                reason = f"検品できませんでした（{type(e).__name__}: {e}）"
                self.failures.append((name, reason))
                return {"readable": False, "bad": [], "reason": reason}
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


def _severity(flaws) -> float:
    """崩れの重さ。文の数に、（）の中の数（1 以上）を足したもの。
    「体から離れている物がある（124 個）」「ゴミがある（2349 個）」のように数が文に埋まっている崩れは、
    文の数だけでは増えたことが分からない（いつも 1 本のまま数が増える）。
    1 未満の数（線の鋭さの倍率など）は小さいほど悪いことがあるので数えない"""
    total = float(len(flaws))
    for f in flaws:
        for n in re.findall(r"（[^）]*?(\d+(?:\.\d+)?)", str(f)):
            if float(n) >= 1:
                total += float(n)
    return total


def _compare_severity(flaws) -> float:
    """土台（最初の一発の絵）と最後の絵を比べるための重さ。
    ゴミの文だけは、埋まった個数を数えず 1 件として数える。ゴミの検品は線の欠片まで
    数えるので（良い線画でも 758 個）、個数で比べると、色の一発絵と線から仕上げた絵では
    物差しが違い、絵の良し悪しではなくゴミの数だけで「良くなっていない」が決まってしまう。
    それ以外の崩れは _severity と同じ物差しにする（戻しの判定とそろえる）"""
    total = 0.0
    for f in flaws:
        total += 1.0 if str(f).startswith("ゴミがある") else _severity([f])
    return total


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
WATER_WORDS = ("lake", "river", "sea", "ocean", "waterfall", "pond", "water", "stream", "beach",
               "湖", "川", "海", "滝", "池", "水", "水辺", "渓流", "波")
# 頼みの言葉に水を表す言葉（水の光の検品を回す）
LEAF_WORDS = ("tree", "forest", "leaves", "leaf", "plant", "plants", "foliage", "garden",
              "木", "森", "葉", "植物", "林", "庭", "草", "花")
# 頼みの言葉に葉・木を表す言葉（葉のつやの検品を回す）
CAR_WORDS = ("car", "vehicle", "truck", "bus", "automobile", "sedan", "taxi", "wheel", "tire",
             "車", "自動車", "トラック", "バス", "タクシー", "乗り物", "タイヤ")
# 頼みの言葉に車・乗り物を表す言葉（タイヤ・対称の検品を回す）
FRONT_WORDS = ("front", "front view", "facing", "正面", "正面から", "前から")
# 頼みの言葉に正面を表す言葉（左右対称の検品を回す）
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


DRAWS = (1, 2, 3, 4, 6, 8)   # 描く工程のある工程（サムネイル、アタリ、線画、下塗り、影 2 段、ディテール）。ほかは測るだけで、描く工程を表に置かない


def draw(painter, prompt: str, seed: int, size, keep: Path, say=lambda m: None, on_step=None, checks=Checks, on_preview=None,
         confirm=None, pause_key: str | None = None, pause_job: dict | None = None, ask=None, answer=None,
         resume: bool = False, on_base=None, only_draw: bool = False) -> dict:
    """計画（atelier/ai/phase_plan.py の工程の並び）に沿って 1 枚を描く。返り値は {"image": 最後の絵, "phases": 工程ごとの最後の記録,
    "history": 全部の記録, "plan": 工程の並び, "left": [], "checked": True, "complete": True, "backs": 戻った回数,
    "total": 累計の工程の数, "need": 要る工程の数}。
    返るのは全部の工程が検品を通ったときか、利用者に聞いて止まったとき（asked）だけ。止めるのは利用者の「止める」（Stopped）だけ。
    confirm(i, 名前, 絵, 記録) は工程（9 の工程の 1 つ）の最後に呼び、"go"・"redo"・("words", 足す言葉の訳) を返す。
    pause_key があれば、打ち切られたとき・聞いて止まったときに、計画と位置と土台を atelier/files/pause_keep.py に残す。
    続きから描くのは resume=True のときだけ（窓の「再開」と、聞いて止まった工程への答え）。
    resume でない呼び直しは新しい描画で、残っていた途中は引き継がず白い紙から描く
    （同じ頼み・種の新しい描画が、前の絵の上に描き始める事故があった。利用者の報告、2026-11-27）。
    only_draw=True は測る台（phase_bench の draws）だけが使う。確かめる工程を計画に置かず（光源の測りだけは残す）、描く工程だけを 1 回ずつ流す
    （描く工程が絵を壊していないかを、検品と直しの繰り返し無しで速く見る）"""
    from PIL import Image
    from atelier.ai.engine import Stopped, emphasize
    from atelier.qc import hand_check as handcheck
    from atelier.ai import phase_tools as pt
    from atelier.ai import draw_tools as dt
    from atelier.ai import phase_items as items
    from atelier.ai.phase_plan import Plan, step
    from atelier.files import pause_keep as pausekeep
    keep.mkdir(parents=True, exist_ok=True)
    pv = {"on_preview": on_preview} if on_preview is not None else {}   # 描いている途中の絵を窓に渡す
    can_line, can_fix = abilities(painter)
    can_refine = hasattr(painter, "refine")
    checks = _Safe(checks)
    # 線画の頼みなら、工程は線画までの 4 つ＋「線の仕上げ」。色の工程は置かず、
    # その分の手間を線の質上げに回す。指定が無ければ通常の 10 工程
    line_art = wants_line_art(prompt)
    names = list(NAMES)
    phase_info = list(PHASES)
    items_by_phase = None
    if line_art:
        names = NAMES[:4] + ["線の仕上げ"]
        phase_info = list(PHASES[:4]) + [("線の仕上げ", "線の質（清書の続き。色には進まない）",
                                          "線の途切れ、線の強弱、ゴミ、手・足・顔、頼んだ物",
                                          "外の輪郭の途切れ（gap）、線の明るさの差（contrast）、ゴミの数")]
        items_by_phase = {4: ["ゴミ", "線の強弱", "線の途切れ"]}   # 線の仕上げは線の質を上げる工程なので、線の強弱も扱う（通常の線画では扱わない）。線の途切れはここでも最後に見る
    if only_draw:
        # 光源だけは測る（画素を数えるだけで模型を使わない）。光の向きが決まらないと、影の工程が何も描かない
        items_by_phase = {i: (["光の向き"] if names[i] == "光源" else []) for i in range(len(names))}
    w, h = (size or (832, 1216))
    n = len(phase_info)
    st = {"image": None, "prompt": prompt, "thumb": None, "points": {}, "light": {}, "height": 0, "seed": seed,
          "layers": {}}   # レイヤー: 線画・清書・下塗りを別々に残す。表示と検品は合成した st["image"] で行う
    memo = {"thumbs": {}, "measured": {}, "check": False}   # 描いた絵と測った結果を使い回す（同じ絵を 2 度描かない・測らない）
    tones = []
    # 工程ごとの道具（画材）。指定が無ければ、見ただけで工程が分かるようにラフ=鉛筆、
    # 線画=ペン、清書=Gペン。頼みに画材の指定があれば、線の工程は全部その画材で描く
    medium = request_medium(prompt)
    rough_brush = medium or "pencil"   # ラフ（サムネイル・アタリ）
    pen_brush = medium or "pen"        # 線画のペンなぞり
    clean_brush = medium or "gpen"     # 清書（線画の中の仕上げと、線画モードの線の仕上げ）

    def tell(words):
        say(f"{WORDS_NOTE}{words}")

    def rough_prompt():
        """ラフ画を描く言葉（頼みの訳に、ラフの画材の言葉を足した物）。サムネイル・アタリで使う"""
        return f"{st['prompt']}, {BRUSH_WORDS[rough_brush]}"

    def pen_prompt():
        """線画を描く言葉（頼みの訳に、線画の画材の言葉を足した物）。線画で使う"""
        return f"{st['prompt']}, {BRUSH_WORDS[pen_brush]}"

    def gpen_prompt():
        """清書を描く言葉（頼みの訳に、清書の画材の言葉を足した物）。線の仕上げで使う"""
        return f"{st['prompt']}, {BRUSH_WORDS[clean_brush]}"

    def detail_prompt():
        """ディテールを足す言葉（頼みの訳に、質感の足し方だけの言葉を足した物）。新しい物は足さない"""
        return f"{st['prompt']}, {DETAIL_WORDS}"

    def line_words(i):
        """線の工程の、線の描き方だけの言葉（頼みの訳は入れない）。その工程の画材の言葉"""
        return BRUSH_WORDS[rough_brush] if i <= 2 else BRUSH_WORDS[pen_brush] if i == 3 else ""

    def phase_prompt(i):
        """工程 i で直すときに模型に渡す言葉。ラフの工程（サムネイル・アタリ）は鉛筆のラフの言葉、線画はペンの言葉、色の工程（下塗りから）は頼みの訳だけ"""
        if i <= 2:
            return rough_prompt()
        if i == 3:
            return pen_prompt()
        return st["prompt"]

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

    def measure_base(img, full=True):
        """1 枚の絵を、土台と比べるための検品一式で測る。bench の final_check と同じ組（頼んだ物・手足顔・体）に、
        画素の物差し（ゴミ）を足す。返すのは {"flaws", "severity", "kind"}。頼んだ物の検品が読めなければ None
        （比べられない物を比べたことにしない）。物・風景では手足顔・体を見る模型は使わない（工程の検品と同じ分け方）。
        full=False は候補のふるい用: 一番重い体の検品（部位分け・人数の模型）だけを省き、アタリの物差し
        （頼んだ物・手足顔・ゴミ）で測る。体の検品には、頼んだ物の検品が読んだタグを使い回す
        （同じ絵のタグを 2 度読まない）"""
        req = checks.request(img, st["prompt"])
        if not req.get("readable"):
            return None
        flaws = _people(req) + _missing(req) + _extra(req)
        kind = subject_kind(st["prompt"], req)
        if kind == "person":
            res = checks.hands(img, st["prompt"])
            if res.get("readable"):
                flaws += list(res.get("bad", []))
            if full:
                bd = checks.body(img, st["prompt"], tags=req.get("read"))
                if bd.get("readable"):
                    flaws += list(bd.get("bad", []))
        elif kind == "face":
            res = checks.hands(img, st["prompt"])
            if res.get("readable"):
                flaws += _face_bad(res)
        d = pt.dust(img)
        if d.get("readable") and d["count"]:
            flaws.append(f"ゴミがある（{d['count']} 個）")
        return {"flaws": flaws, "severity": _compare_severity(flaws), "kind": kind}

    def paint_base():
        """土台: 頼みの言葉そのままで一発で描いた絵（人間で言う 80 点のサムネイル）。工程はこの絵を 100 点へ磨き上げる。
        土台の絵は内側の基準だけに使い、画面に出さない・工程の絵として保存しない（見せるのは白い紙から描き上がる工程の絵だけ）。
        検品一式で測って、崩れの重さを st["base"] に残す。返すのは模型に渡した言葉"""
        stop()
        words = []
        img = st.pop("base_raw", None)   # サムネイルの工程で描いた土台があれば、それを測るだけ（同じ絵を 2 度描かない）
        if img is None:
            say("土台の絵を描いています（頼みの言葉そのままの一発の絵。画面には出さず、工程の基準にします）")
            tell(st["prompt"])
            words.append(st["prompt"])
            img = painter.paint(st["prompt"], st.get("seed_pick", st["seed"]), size=(w, h))
        got = measure_base(img)
        st["base"] = {"image": img, "flaws": [] if got is None else got["flaws"],
                      "severity": None if got is None else got["severity"], "kind": None if got is None else got["kind"]}
        if on_base is not None:
            # 土台の絵は画面に出さないのが決まり。preview（見せる絵の通り道）には流さず、
            # デバッグモードで「何を直そうとしているのか」を薄く重ねて見るためだけに、
            # 専用の渡し口（on_base）で窓へ渡す。前は印を付けて preview に流していたが、
            # 受け側が印を見落とすと土台がそのまま画面とタイムラプスに出た（0.1.28）。
            # 通り道自体を分ければ、見落としでは出ない
            on_base(img.copy())
        if got is None:
            say("土台の絵を検品できませんでした（良くなったかを比べる基準は無しで進めます）")
        else:
            say(f"土台の絵の崩れの重さは {got['severity']} です（最後の絵の重さがこれより小さいことが、仕上がりの条件です）")
        return words

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

    def stage_steps(i):
        """工程ごとの描く速さ（工程の数の割合）。序盤（サムネイル・アタリ）はラフで十分なので
        軽くし、線画は少し軽く、清書以降（下塗り・光源・影・ディテール・仕上げ）は 1.0。
        時間をかけるべきは線画以降、特に清書以降（利用者の指示、2026-11-27）"""
        if i <= 2:
            return EARLY_STEPS
        if i == 3 or (line_art and i == 4):
            return LINE_STEPS
        return 1.0

    def points(img):
        got = checks.points(img)
        return dict(got.get("points") or {}) if got.get("readable") else {}

    # 描く工程。どれも {"image", "words", "note", "numbers"} を返し、測ることも直すこともしない
    def d_thumbs(v):
        # AI モードと同じ始まり。頼みの言葉そのままで 1 枚を描き（土台。画面には出さない）、その絵から鉛筆のラフを抜いて構図にする。
        # 前は「鉛筆のラフ」の言葉を足して別の絵を白紙から描かせ、その線に色を描き重ねていた。白い紙の線からの描き重ねは
        # 紙の白を動かせず、最後まで灰色の紙に破線の絵になった（検証 46089737769）。土台と別の構図になるので、土台の色も使えなかった。
        # ラフ・線・色を同じ土台から出すと、線と色の位置がずれず、最後の絵が AI モードの絵より崩れない
        s = st["seed"] + v * 1000
        words = []
        stop()
        say(f"サムネイルを描いています（{w}x{h}）")
        tell(st["prompt"])
        words.append(st["prompt"])
        raw = painter.paint(st["prompt"], s, on_step=on_step, size=(w, h))   # 土台。途中の絵も描けた絵もキャンバスに出さない
        st["base_raw"], st["base"] = raw, None   # 土台の検品はアタリの頭で行う（paint_base）
        img = pt.rough_from(raw)
        memo["thumbs"][(st["prompt"], s)] = img   # アタリはこの絵に描き重ねる（描き直さない）
        req = checks.request(img, st["prompt"])   # 構図を測る。崩れは確かめる工程が項目ごとに出す
        wt = pt.thumb_weight(img)
        flaws = _people(req) + _missing(req) + (["画面の重さが片寄っている"] if wt["weight_x"] > pt.WEIGHT_MOST else [])
        rows = [{"seed": s, **wt, "flaws": len(flaws), "score": [len(flaws), wt["weight_x"]]}]
        st["thumb"], st["seed_pick"] = img, s
        say(f"サムネイルを直接描きました（種 {s}、崩れ {len(flaws)}）")
        out = img.resize((w, h))
        memo["measured"][1] = (out, st["prompt"], {"flaws": flaws, "numbers": {"thumbs": rows, "picked": s},
                                                   "readable": bool(req.get("readable"))})
        return {"image": out, "words": words, "numbers": {"thumbs": rows, "picked": s, "brush": rough_brush}}

    def d_atari(v):
        # アタリは構図の調整と下描きを 1 つの工程にする。サムネイル（線のラフ画）を土台に、体の形・顔と手と足・服と髪と持ち物の
        # 下描きを描き重ねる。線の工程なので色は付けない。返す前に st["image"] を描く前の土台に戻す（描く工程の前後比較が働くように）
        words = []
        if st.get("base") is None:   # 土台（80 点の一発の絵）は、描く作業の始まりであるアタリの頭で描く。描き直しで土台が無くなっていたら、ここで描き直す
            words += paint_base()
        base = st["image"]
        s = st.get("seed_pick", st["seed"])
        got = memo["thumbs"].get((st["prompt"], s))
        if got is not None:   # 同じ種・同じ大きさ・同じ工程の数で描いたサムネイルがあれば、それがそのままアタリ（描き直さない）
            say(f"サムネイル（種 {s}）をそのままアタリにします")
            img = got
        else:
            s0 = steps(EARLY_STEPS)
            try:
                tell(rough_prompt())
                words.append(rough_prompt())
                img = painter.paint(rough_prompt(), s, on_step=on_step, size=(w, h))   # アタリも途中の絵を出さない（NO_PREVIEW）
            finally:
                unsteps(s0)
        st["image"] = img
        s0 = steps(EARLY_STEPS)   # アタリはラフ。下描きの描き重ねも軽く描く（線画や清書と同じレベルまで仕上げない）
        try:
            d = d_draft(v)
            img = d["image"]
            words += d["words"]
            if st["prompt"] != prompt:   # 利用者が言葉を足したときだけ、服・髪・持ち物を描き足す
                st["image"] = img
                w2 = d_wear(v)
                img = w2["image"]
                words += w2["words"]
        finally:
            unsteps(s0)
        st["image"] = base
        # 見せ方: アタリはラフの上に描く物。ラフを薄く下に敷いた合成を表示に使うと、
        # 筆の見せ方でラフの線が消えず、新しい線だけが足されていく。敷かないと、
        # ずれた線が二重に見えてチラつき、後から元の線を消す汚い見え方になる
        display = None
        rough = st["layers"].get("ラフ")
        if rough is not None and rough.size == img.size:
            display = pt.underlay(img, rough)
        return {"image": img, "display": display, "words": words, "numbers": {"brush": rough_brush}}

    def d_draft(v):
        img, words, note = st["image"], [], ""
        s = st["seed"] + v * 1000
        base = img
        if can_refine:   # 描き重ね（絵から絵）を先にする。線に沿って白紙から描き直すと、霞み・枠・色褪せと服の変わりが出た
            say("アタリの絵に描き重ねて、顔・手・足を描き込んでいます")
            tell(rough_prompt())
            words.append(rough_prompt())
            img = keep_tone(painter.refine(rough_prompt(), s, img, strength=REFINE, on_step=on_step, **pv), base, "下描き")
            if v == 0 and img is not None:
                # 最初のアタリは、複数枚描いて一番良い物を採る。枚数を惜しむ話ではない:
                # 裏で何枚描いても良いから、一番崩れの少ないアタリで工程を終わらせる
                # （悪いアタリを検品と直しで何度もいじるより速く、見栄えも良い。利用者の指示）
                # 候補の順位付けはふるい（full=False）で測る。検品一式は一番重い体の検品
                # （部位分け・人数の模型）まで入っていて、候補 4 枚に全部回すと、それだけで
                # アタリの大半を食う。ラフの順位付けはアタリの物差し（頼んだ物・手足顔・ゴミ）
                # で足り、採った 1 枚は直後の工程の確かめ（m_atari）が一式で測る
                first = measure_base(img, full=False)
                if first is not None:
                    best, best_sev, drawn = img, first["severity"], 1
                    for extra in (500, 501, 502):   # 合わせて最大 4 枚。崩れの無い物が描けたら、そこで止める
                        if best_sev <= 0:
                            break
                        alt = keep_tone(painter.refine(rough_prompt(), s + extra, base, strength=REFINE, on_step=on_step, **pv), base, "下描き")
                        drawn += 1
                        if alt is None or alt.size != img.size:
                            continue
                        got = measure_base(alt, full=False)
                        if got is not None and got["severity"] < best_sev:
                            best, best_sev = alt, got["severity"]
                    if drawn > 1:
                        say(f"アタリを {drawn} 枚描いて、一番崩れの少ない物を選びました（崩れの重さ {best_sev}）")
                        img = best
        elif can_line:
            say("アタリの線に沿って、顔・手・足を描き込んでいます")
            tell(rough_prompt())
            words.append(rough_prompt())
            img = keep_tone(painter.paint(rough_prompt(), s, on_step=on_step, base=img, strength=LINE_STRENGTH, size=(w, h), **pv), base, "下描き")
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
        words2 = emphasize(rough_prompt(), missing) if missing else rough_prompt()
        say("足した言葉を、服・髪・持ち物の所だけに描き足しています")
        tell(words2)
        words.append(words2)
        protect = [b for b in [pt.face_box(st.get("points") or {})] if b]
        mask, by_parts = pt.wear_mask(img, protect)
        tried = _inside(keep_tone(painter.redraw(words2, st["seed"] + 131 + v * 1000, img, mask, strength=REPAINT, max_scale=1.0), img, "服・髪・持ち物", mask), img, mask)
        return {"image": tried, "words": words, "numbers": {"by_parts": by_parts}}

    def clean_lines(img, kind="gpen"):
        """清書の実務: ゴミを塊そのものだけ消す。線の強弱は Gペンの画材（kind）のときだけ付ける
        （入り抜きと強弱は Gペンの線の質そのもの。鉛筆など他の画材の指定があるときは、
        その画材の線の質感のままにして強弱付けをしない）。
        返すのは (絵, 太らせた画素の数, 消す前のゴミの数。読めなければ None)"""
        out, hit = pt.weight_lines(img) if kind == "gpen" else (img, 0)
        d = pt.dust(out)
        cleaned = out
        if d.get("readable") and d["count"]:
            mask = pt.dust_mask(out)
            if mask is not None and mask.getextrema()[1] != 0:
                cleaned = pt.erase_fill(out, mask)
        return cleaned, hit, (d.get("count") if d.get("readable") else None)

    def d_line_finish(v):
        """線の仕上げ: 線画の頼みのときだけ置く工程。色の工程の代わりに、線の質を上げる
        （弱い描き重ねで線を整え直し、清書をもう一度かける）。線が薄くなる描き重ねは
        採用しない。線画はスタートラインだが、線画の頼みではここが完成の質を決める"""
        img = st["image"]
        if img is None:
            return {"image": img}
        words = []
        if can_refine:
            say("線の仕上げをしています（色には進まず、線の質を上げます）")
            tell(gpen_prompt())
            words.append(gpen_prompt())
            raw = keep_tone(painter.refine(gpen_prompt(), st["seed"] + v * 1000, img, strength=SHINE, on_step=on_step, **pv), img, "線の仕上げ")
            ink_before, ink_after = pt.ink_share(img), pt.ink_share(raw)
            if ink_before > 0 and ink_after < ink_before * LINE_INK_KEEP:
                say("仕上げの描き重ねで線が薄くなるので、元の線のまま清書だけします")
            else:
                img = raw
        say("清書しています（線の強弱を付け、ゴミを消す）")
        cleaned, hit, dust_count = clean_lines(img, clean_brush)
        return {"image": cleaned, "words": words,
                "numbers": {"pixels": hit, "dust": dust_count, "brush": clean_brush}}

    def d_lines(v):
        """線画: ラフをペンでなぞって線にする。なぞったあと清書する（線の強弱を付け、ゴミを消す）。
        前は太らせる加工だけで、線を描く工程になっていなかった（利用者の指摘）"""
        img, words = st["image"], []
        base_line = img   # ペンでなぞる前の線。なぞった絵の線が薄れたら、暗さをここから戻す
        s = st["seed"] + v * 1000
        s0 = steps(LINE_STEPS)   # 線画は少し軽く描く。時間をかけるのは清書以降
        try:
            if can_refine:
                say("ラフをペンでなぞって、線画を描いています")
                tell(pen_prompt())
                words.append(pen_prompt())
                img = keep_tone(painter.refine(pen_prompt(), s, img, strength=REFINE, on_step=on_step, **pv), img, "線画")
            elif can_line:
                say("ラフをペンでなぞって、線画を描いています")
                tell(pen_prompt())
                words.append(pen_prompt())
                img = keep_tone(painter.paint(pen_prompt(), s, on_step=on_step, base=img, strength=LINE_STRENGTH, size=(w, h), **pv), img, "線画")
            else:
                say("この模型は描き重ねられないので、ラフのまま線を確かめます")
        finally:
            unsteps(s0)
        if base_line is not None and img is not None:
            # 線の濃さの見張り。色と明るさの見張り（keep_tone）は暗い所の下位 5% を見るので、
            # 細い線が薄くなる崩れを見逃す。濃い線の割合が土台の 6 割を切ったら、土台の線の
            # 暗さを乗せて戻す（線の無い所は変えない。線が土台に無い絵では何もしない）
            ink_before, ink_after = pt.ink_share(base_line), pt.ink_share(img)
            if ink_before > 0 and ink_after < ink_before * LINE_INK_KEEP:
                say(f"ペンなぞりで線が薄くなったので（濃い線 {ink_before:.1%} → {ink_after:.1%}）、土台の線の暗さを戻します")
                img = pt.over_lines(img, base_line)
        if img is not None and pen_brush in ("pen", "gpen"):
            img = pt.ink_levels(img)   # ペンの線にそろえる（紙は白、線は黒、色の面は紙に戻す）。線のレイヤーは色の上に乗せるので、薄い線・灰色の紙・色の面を残さない
        # 清書: 線の強弱を付け、残ったゴミを塊そのものだけ消して、線を仕上げる
        say("清書しています（線の強弱を付け、ゴミを消す）")
        cleaned, hit, dust_count = clean_lines(img, clean_brush)
        # 表示用の合成: ラフのレイヤーがあれば、薄くして線の下に敷く。返す絵（検品と
        # 次の工程の土台）は線のレイヤーそのもの。工程の絵だけが合成になる。
        # 下に敷くラフは、ゴミだけ消した写しを使う。清書まで終わった工程の絵に
        # ラフのゴミの影が写ると、消えていないように見える（ラフのレイヤー自体は残す）
        display = None
        rough = st["layers"].get("ラフ")
        if rough is not None and rough.size == cleaned.size:
            under = rough
            rmask = pt.dust_mask(rough)
            if rmask is not None and rmask.getextrema()[1] != 0:
                under = pt.erase_fill(rough, rmask)
            display = pt.underlay(cleaned, under)
        return {"image": cleaned, "display": display, "words": words,
                "numbers": {"pixels": hit, "dust": dust_count, "brush": pen_brush, "clean_brush": clean_brush}}

    def d_base(v):
        """下塗り。線の工程までは色を付けないので、ここで初めて色をのせる。
        レイヤーで管理する: 色は「下塗り」レイヤーとして別に塗り、絵は色の上に清書レイヤーを
        乗せた合成にする。線画に直接描き重ねると色が線を薄くする（検証 45696035067 で、
        良い線画が下塗りと仕上げの直しで壊れた）。線はレイヤーに残るので、色を塗り直しても壊れない。
        keep_tone は掛けない。pt.guard は色を土台（線の絵）に合わせて戻すので、せっかくのせた色が消える。
        途中の絵（on_preview）は渡さない。色をのせた絵がそのまま工程の絵になるので、途中の絵と工程の絵が同じになり、同じ絵を続けて出すことになる"""
        img, words = st["image"], []
        s = st["seed"] + v * 1000
        color = None
        # 線画の紙が灰色だと、描き重ねは灰色の絵から始まって色がほとんど乗らず、
        # 線画らしいかの判定も外れて線レイヤーを乗せられなかった（検証 46030668432）。
        # 紙を白に戻した線画を、描き重ねの土台と乗せる線の両方に使う。模型に渡す言葉は変えない
        base_in = pt.whiten_paper(img)
        if not pt.line_like(base_in):
            base_in = img
        # 白い紙の線画からの描き重ねは、紙の白をほとんど動かせず、色が乗らない（検証 46089737769 で
        # 彩度 6.4・紙の明るさ 170 のまま。強さ 0.6 でも同じ）。土台（頼みの言葉そのままの絵）の色を
        # 線の下に敷き、その上に描き重ねる。色の位置は土台、線の位置は清書で、同じ絵から出ている
        over_base, under = False, base_in
        if can_refine:
            strength = BASE_COLOR
            base_img = (st.get("base") or {}).get("image")
            if base_img is not None and base_img.size == img.size:
                # 線が線画らしくないとき（鉛筆の画材の指定などで灰色の面が多い）は、乗算で絵が沈むので線は敷かず、土台の色だけから描き重ねる
                under = pt.over_lines(base_img, base_in) if pt.line_like(base_in) else base_img
                strength, over_base = BASE_OVER, True
            say("線画に、初めて色を下塗りしています")
            tell(st["prompt"])
            words.append(st["prompt"])
            color = painter.refine(st["prompt"], s, under, strength=strength, on_step=on_step)
        elif can_line:
            say("線画に、初めて色を下塗りしています")
            tell(st["prompt"])
            words.append(st["prompt"])
            color = painter.paint(st["prompt"], s, on_step=on_step, base=base_in, strength=BASE_COLOR, size=(w, h))
        if color is None:
            return {"image": img, "words": words, "note": "この模型は描き重ねられないので、線画のまま色を確かめます"}
        if pt.grain(color) > BASE_GRAIN_MOST:   # 色をのせたはずが粒（ブツブツ）だらけのときだけ、面の色に寄せて平らにする（きれいな色は触らない）
            flat = pt.flatten_base(color)
            if pt.grain(flat) < pt.grain(color):
                say("下塗りの色に粒が出たので、面の色に寄せて平らにします（下塗りはベタ塗り）")
                color = flat
        line = pt.whiten_paper(st["layers"].get("清書") or img)
        numbers = {}
        if over_base and color.size == line.size and pt.line_like(line):
            # 土台の色と清書の線を敷いた絵に描き重ねた絵は、線も色も初めから持っている。線が埋もれても太ってもいなければ、
            # 描き重ねた絵をそのまま使う。色の絵の線を消して清書の線を乗せ直す合成（下の道）は、本物の絵では線の周りの色まで
            # 埋めて、顔と輪郭を潰した（検証 46127844791 の下塗り）。線を消して乗せ直すのは、線が太ったときだけにする
            lost = pt.line_loss(line, color)
            fat = pt.line_fattening(line, under, color)
            numbers.update({"line_lost": round(lost, 3), "line_fat": round(fat, 3)})
            if fat <= LINE_FAT_MOST:
                out = color
                if lost > LINE_LOSS_MOST:   # 線が埋もれただけなら、色の絵は触らずに清書の線を上に乗せる
                    say(f"下塗りの描き重ねで清書の線が埋もれたので（{lost:.0%}）、清書の線を上に乗せます")
                    out = pt.over_lines(color, line)
                st["layers"]["下塗り"] = color
                for lname, limg in st["layers"].items():
                    limg.save(keep / f"layer-{4 + 1:02d}-{lname}.png")
                return {"image": out, "words": words, "numbers": {"layers": list(st["layers"]), **numbers}}
            say(f"下塗りの描き重ねで線が太ったので（線の外側に増えた暗い画素が線の {fat:.0%}）、色の絵の線を消して清書の線を乗せ直します")
        if pt.line_like(line):
            # 色の絵が自分で描いた線は消してから乗せる。乗算の合成は色の暗さを消せず、
            # 色の線が残ると清書の線と合わさった太さになって、下塗りで線が太く壊れる。
            # 線は清書レイヤーだけが持ち、下塗りレイヤーは色だけにする
            color = pt.strip_own_lines(color, line)
            out = pt.over_lines(color, line)
        else:
            say("線の土台が線画らしくないため、色の絵をそのまま使います（線レイヤーは残してあります）")
            out = color
        st["layers"]["下塗り"] = color
        for lname, limg in st["layers"].items():   # レイヤーはファイルにも残す（表示には出さない。あとで線画が残っているか確かめられる）
            limg.save(keep / f"layer-{4 + 1:02d}-{lname}.png")
        return {"image": out, "words": words,
                "numbers": {"layers": list(st["layers"]), **numbers}}

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

    def detail_pass(img, strength, seed):
        """ディテールの描き重ね。色と明るさの見張り（keep_tone）と、潰れの見張り
        （コントラストと暗さが元の絵から大きく落ちたら、影や濃い細部が潰れたとみる）を
        通った結果だけを返す。通らなければ None（呼び出し側は元の絵のまま進む）"""
        if not can_refine or img is None:
            return None
        out = painter.refine(detail_prompt(), seed, img, strength=strength, on_step=on_step, **pv)
        if out is None or out.size != img.size:
            return None
        out = keep_tone(out, img, "ディテール")
        tb, ta = pt.tone(img), pt.tone(out)
        if ta["contrast"] < tb["contrast"] * TONE_CRUSH or ta["dark"] > tb["dark"] + 25:
            return None   # 影や濃い細部が潰れている。採用しない
        db, da = pt.detail_density(img), pt.detail_density(out)
        if (db.get("readable") and da.get("readable")
                and (da["density"] < db["density"] * DETAIL_CRUSH
                     or da["sharp"] < db["sharp"] * DETAIL_CRUSH)):
            return None   # 質感が潰れている（ぼやけ等）。採用しない
        if pt.new_specks(img, out) > SPECKS_MOST:
            return None   # 新しいゴミ（暗い点・短い線の塊）が増えている。足すはずが散らかしている。採用しない
        if pt.new_bumps(img, out) > SPECKS_MOST:
            return None   # 滑らかだった所にブツブツ（でき物）が増えている。質感ではなく汚れ。採用しない
        entry = st.get("detail_entry")
        if entry is not None and entry.size == out.size:
            # 工程全体の見張り: 1 回ごとの見張りだけだと、境目未満の斑点を何度も足して
            # 積み重ねられる（描く・弱く描き直す・質感の締め直しが同じ工程で繰り返される）。
            # 工程に入ったときの絵と比べて、増えた斑点の合計でも見る
            if pt.new_specks(entry, out) > SPECKS_MOST or pt.new_bumps(entry, out) > SPECKS_MOST:
                return None   # 工程の中で斑点が積み重なっている。採用しない
        return out

    TONE_WORDS = ("網点", "トーン", "screentone", "halftone")

    def tone_pattern(img):
        """頼みに網点・トーンがあれば、影の側に網点の柄を道具で入れる（漫画のトーン）。
        頼みに無い柄は入れない。光の向きが読めなければ入れない。返すのは (絵, 入れたか)"""
        if not any(w in st["prompt"] for w in TONE_WORDS):
            return img, False
        lit = st.get("light") or {}
        mask = pt.shadow_side_mask(img, lit) if lit.get("readable") else None
        if mask is None:
            return img, False
        out = dt.pattern_fill(img, mask, kind="halftone", fg=(40, 40, 40), scale=10)
        say("頼みの網点を、影の側に道具で入れています")
        return out, True

    def d_detail(v):
        """ディテール: 仕上げの直前に、質感と小さい印を足して整える。消す直しはしない
        （清書より後に消すと、足した表現まで消える）。足すことで影や汚しなどの表現が
        潰れるくらいなら、弱い強さで試し直し、それでも駄目なら足さずに元の絵で進む"""
        img = st["image"]
        if img is None:
            return {"image": img}
        st["detail_entry"] = img   # ディテール工程に入ったときの絵。工程全体で増えた斑点の見張りの基準
        out = detail_pass(img, SHINE, st["seed"] + v * 1000)
        if out is None:
            out = detail_pass(img, SHINE / 2, st["seed"] + v * 1000 + 1)
        if out is None:
            say("ディテールを足すと影や細部が潰れるので、元の絵のまま進みます")
            img, _toned = tone_pattern(img)
            return {"image": img, "numbers": {"detail": pt.detail_density(img).get("density")}}
        say("ディテールを足しています（質感・小さい印。消す直しはしません）")
        out, _toned = tone_pattern(out)
        return {"image": out, "words": [detail_prompt()],
                "numbers": {"detail": pt.detail_density(out).get("density")}}

    def draws(i):
        return i in DRAWS or (line_art and i == 4)   # 線の仕上げも描く工程

    drawer = {1: d_thumbs, 2: d_atari, 3: d_lines, 4: d_base, 6: d_shadow, 8: d_detail}
    if line_art:
        drawer[4] = d_line_finish   # 下塗りの代わりに線の仕上げ

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
            # 等身は全身が写っているときだけ測れる。足首の点が無い構図（上半身だけなど）では
            # 人物の高さそのものが写っていないので、比を出しても意味が無く、直しでも直らない
            full = "left_ankle" in pts and "right_ankle" in pts
            hd = pt.heads(pts, bal.get("height", 0)) if bal.get("readable") and full else None
            if hd is not None and not (pt.HEADS[0] <= hd <= pt.HEADS[1]):
                flaws.append(f"等身が外れている（{hd}）")
            pz, bd = checks.pose(img), checks.body(img, st["prompt"], tags=req.get("read"))   # タグは頼んだ物の検品が読んだ物を使い回す（同じ絵を 2 度読まない）
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
        # パーツの検品は清書（この工程）までに済ませる（利用者の設計、2026-11-26）。
        # 線だけを測ると、アタリから持ち越した手・顔・頼んだ物の崩れが、測ってもいないのに
        # 「この工程の確かめで消えた」として外れてしまう。体の検品も同じ絵で測る
        body = m_atari(img)
        numbers = dict(body.get("numbers") or {})
        numbers.update(m)
        return {"flaws": flaws + list(body["flaws"]), "regions": regions + list(body.get("regions") or []),
                "numbers": numbers, "missing": body.get("missing", []), "show": body.get("show"),
                "note": body.get("note", ""), "tilt": body.get("tilt"), "readable": bool(m.get("readable"))}

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
        numbers = {"colors": colors, "parts": None if p is None else int(len(set(np.unique(p).tolist()) - {0}))}
        _bm, blotches = pt.blotch_mask(img)
        if blotches:
            flaws.append(f"色に斑点がある（{blotches} 個）")   # 粒の物差し（grain）では塊の斑点は測れない。平らにした絵と比べて測る
            numbers["blotches"] = blotches
        _cm, uncolored = pt.coverage_mask(img)
        if uncolored > COVERAGE_MOST:
            flaws.append(f"塗り残しがある（主役の {uncolored} が紙の色のまま）")
            numbers["uncolored"] = uncolored
            ys, xs = np.nonzero(np.asarray(_cm.convert("L")) > 0)
            if len(xs):
                regions.append(((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1), "cover"))
        return {"flaws": flaws, "regions": regions, "readable": True, "numbers": numbers}

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
        # 水の光と葉のつやは、顔の有無に関わらず、頼みに水・葉の言葉があれば見る（風景の光・艶の検品）
        flaws, numbers, eyes = [], {"eye_max": []}, []
        low = st["prompt"].lower()
        if _has_word(low, WATER_WORDS):
            wl = pt.water_light(img)
            if wl.get("readable"):
                numbers["water_spread"] = wl["spread"]
                if wl["spread"] < pt.WATER_LIGHT_LEAST:
                    flaws.append(f"水に光が無い（明るさの広がり {wl['spread']}）")
        if _has_word(low, LEAF_WORDS):
            lg = pt.leaf_gloss(img)
            if lg.get("readable"):
                numbers["leaf_spread"] = lg["spread"]
                if lg["spread"] < pt.LEAF_GLOSS_LEAST:
                    flaws.append(f"葉につやが無い（明るさの広がり {lg['spread']}）")
        if not _has_face():
            # 顔・目・足の無い物・風景は目の光の確かめを飛ばす（目は無い）
            return {"flaws": flaws, "numbers": numbers, "readable": True}
        pts = points(img)   # 目の光は今の絵から読んだ座標だけで確かめる（古い目の位置で通さない）
        cl = pt.catchlights(img, pts)
        if cl.get("readable"):
            flaws += [f"目の光が無い（{x}）" for x in cl.get("eye_max", []) if x < pt.CATCHLIGHT]
            eyes = [(b, "eye") for b in cl.get("boxes", [])]
            numbers["eye_max"] = cl.get("eye_max")
            return {"flaws": flaws, "eyes": eyes, "numbers": numbers, "readable": True}
        if _is_person():
            # 人の目は体の点で読めなければ、目の光は検品できない
            return {"flaws": flaws, "numbers": numbers, "readable": False}
        # 動物・人型ロボット・架空の生き物は、人の体の点では目を読めない。アタリで読んだ顔の枠の上の半分（目の所）で、
        # 一番明るい画素を見る。顔の枠も無ければ、目の光の確かめは飛ばす（顔の検品が目を読んでいる）
        fb = st.get("face_box")
        if not fb:
            return {"flaws": flaws, "numbers": numbers, "readable": True}
        lum = pt.luminance(img)
        x0, y0, x1, y1 = (int(v) for v in fb)
        eye_y1 = (y0 + y1) // 2   # 顔の上の半分が目の所
        part = lum[max(0, y0):max(0, eye_y1), max(0, x0):max(0, x1)]
        best = int(part.max()) if part.size else 0
        eye_box = (x0, y0, x1, eye_y1)
        if best < pt.CATCHLIGHT:
            flaws.append(f"目の光が無い（{best}）")
        eyes = [(eye_box, "eye")]
        numbers["eye_max"] = [best]
        return {"flaws": flaws, "eyes": eyes, "numbers": numbers, "readable": True}

    def m_detail(img):
        """ディテールの検品: 量と、影の締まりだけを見る。他の工程の検品一式は背負わない
        （線画がアタリの検品を背負って直しが膨らんだ事故の再発防止）。ゴミは数えるだけ
        （消すのは清書だけ。ディテール追加の後に消すと、足した表現まで消える）"""
        flaws, numbers = [], {}
        dd = pt.detail_density(img)
        if dd.get("readable"):
            numbers["detail"] = dd["density"]
            if dd["density"] < DETAIL_LEAST:
                flaws.append(f"ディテールが薄い（{dd['density']}）")
        sh = pt.shadows(img, st.get("light") or {})
        if sh.get("readable"):
            numbers["shade_minus_lit"] = sh["shade_minus_lit"]
            if sh["shade_minus_lit"] > 0:
                flaws.append(f"影の締まりが弱い（影が光より明るい {sh['shade_minus_lit']}）")
        d = pt.dust(img)
        if d.get("readable"):
            numbers["dust"] = d["count"]
        return {"flaws": flaws, "numbers": numbers, "readable": True}

    def m_finish(img):
        sv = pt.shrink_view(img)
        flaws = []
        numbers = {"shrink": sv.get("contrast"), "asym": None}
        d = pt.dust(img)   # 仕上げではゴミを数えるだけ（消すのは清書だけ。都度のゴミ消しが線やディテールを壊す）
        numbers["dust"] = d["count"] if d.get("readable") else None
        regions = []
        if not _has_face():
            # 顔・目・足の無い物・風景は、手・足・顔・体の崩れの確かめを飛ばす。縮めて見るだけ
            if sv.get("readable") and sv["contrast"] < pt.SHRINK_CONTRAST:
                flaws.append(f"縮めると主役が目立たない（{sv['contrast']}）")
            # 車・物の検品（タイヤの丸み・左右対称・遠近の収束）。車の言葉があればタイヤと対称、遠近は線があれば見る
            low = st["prompt"].lower()
            if _has_word(low, CAR_WORDS):
                tr = pt.tire_roundness(img)
                if tr.get("readable"):
                    numbers["tire_cv"] = tr["worst"]
                    for t in tr.get("tires", []):
                        if t["cv"] > pt.TIRE_CV_MOST:
                            flaws.append(f"タイヤが丸くない（変動 {t['cv']}）")
                            regions.append((t["box"], "tire"))
                sy = pt.symmetry(img)
                if sy.get("readable"):
                    numbers["sym_iou"] = sy["iou"]
                    if sy.get("tire_ratio") is not None and sy["tire_ratio"] > pt.TIRE_PAIR_RATIO_MOST:
                        flaws.append(f"左右のタイヤの大きさが違う（比 {sy['tire_ratio']}）")
                        regions.append((sy["small_box"], "tire"))
                    if _has_word(low, FRONT_WORDS) and sy["iou"] < pt.SYMMETRY_IOU_LEAST:
                        flaws.append(f"左右対称でない（鏡像の重なり {sy['iou']}）")
            vn = pt.vanishing(img)
            if vn.get("readable"):
                numbers["vanish_angle"] = vn["angle"]
                if vn["angle"] < pt.VANISH_ANGLE_LEAST:
                    flaws.append(f"遠近の収束が無い（線の角度の差 {vn['angle']} 度）")
                    if vn.get("box"):
                        regions.append((vn["box"], "perspective"))
            # 全画面の風景・物は紙の縁が無く、縮めて見るが読めない。ゴミ・タイヤ・対称・遠近の検品が回っていれば、仕上げは読める
            return {"flaws": flaws, "regions": regions, "numbers": numbers, "readable": True}
        res = checks.hands(img, st["prompt"])
        body = checks.body(img, st["prompt"]) if _is_person() else {"readable": True, "bad": []}
        pz = checks.pose(img) if _is_person() else {"readable": True, "bad": []}   # 仕上げの項目にある骨組みの比も、実際に測る（測らずに通さない）
        pts = points(img)
        face = pt.face_box(pts) or st.get("face_box")
        fv = pt.flip_view(img, face) if face else {"readable": False}
        if _is_person():
            flaws += list(res.get("bad", [])) + (list(body.get("bad", [])) if body.get("readable") else []) + (list(pz.get("bad", [])) if pz.get("readable") else [])
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
                    "readable": bool(res.get("readable")) and bool(body.get("readable")) and bool(pz.get("readable")) and bool(pts)
                    and bool(sv.get("readable")) and bool(fv.get("readable"))}
        # 動物・人型ロボット・架空の生き物は、顔・足の模型が読めたかどうかで、読めたことにする。人の体の点は要らない
        face_ok = bool(res.get("readable")) or bool(res.get("faces")) or bool(res.get("feet")) or bool((res.get("face") or {}).get("readable"))
        return {"flaws": flaws, "regions": regions, "numbers": numbers,
                "readable": bool(sv.get("readable")) and face_ok}

    measurer = [m_purpose, m_thumbs, m_atari, m_lines, m_base, m_light, m_shadow, m_shine, m_detail, m_finish]
    # 工程ごとの検品が実際に測っている項目。測っていない項目の崩れを、その工程の確かめで
    # 「消えた」ことにしない（持ち越した崩れが黙って外れる事故の再発防止）
    atari_covers = ["人数", "頼んだ物", "画角", "背景", "位置ずれ", "画面の重さ", "重心と等身", "骨組みの比", "手", "足", "顔"]
    covers = [["頼み"],
              ["人数", "頼んだ物", "画面の重さ"],
              atari_covers,
              # 線画が扱うのは、線の事だけ（途切れとゴミ）。構図の項目（画角・背景・位置ずれ・
              # 等身・骨組み・画面の重さ・人数）はアタリの仕事、パーツ（手・足・顔・頼んだ物）の
              # 直しはアタリと仕上げの仕事。線画はただのスタートラインで、ここで完成にしようと
              # しない（利用者の指摘）。測ること自体は状態の把握に使うが、直すのは適所でだけにする
              ["線の途切れ", "ゴミ"],
              ["色の差", "色のにじみ", "斑点", "塗り残し"],
              ["光の向き"],
              ["影"],
              ["目の光", "水の光", "葉のつや"],
              ["ディテール", "影の締まり"],
              ["手", "足", "顔", "骨組みの比", "反転して見る", "縮めて見る", "タイヤの丸み", "左右対称", "遠近の収束"]]
    if line_art:
        # 線の仕上げ（工程 4）は、線画と同じ物差しで測り、線画の項目に線の強弱を足して扱う
        measurer = measurer[:4] + [m_lines]
        covers = covers[:4] + [covers[3] + ["線の強弱"]]
    assert len(measurer) == n and len(covers) == n

    def measure(i, fresh=False):
        """工程 i の見る物を今の絵で測る。同じ絵・同じ言葉なら測り直さない（確かめる工程が項目ごとに同じ結果を読む）"""
        img = st.get("image")
        got = memo["measured"].get(i)
        if not fresh and got is not None and got[0] is img and got[1] == st["prompt"] and "by_item" in got[2]:
            return got[2]
        # サムネイルは選ぶときに測った結果を使う（同じ絵を 2 度測らない）
        if got is not None and got[0] is img and got[1] == st["prompt"] and not fresh:
            res = got[2]
        else:
            before_failures = len(checks.failures)
            res = measurer[i](img)
            # この計測の間に部品不足・例外で読めなかった検品（理由つき）。検品が動いて
            # 「読めない」と返した物はここには入らない（そちらは絵を直せば読めることがある）
            new_failures = checks.failures[before_failures:]
            if new_failures and not res.get("readable"):
                res["unreadable"] = new_failures
        flaws = list(res.get("flaws", []))
        if not res.get("readable") and items.UNREADABLE not in flaws:
            flaws.append(items.UNREADABLE)   # 読めない絵は崩れとして扱う
        res["flaws"] = flaws
        res["by_item"] = items.split(flaws)
        res["covers"] = covers[i]   # この工程の検品が実際に測っている項目
        memo["measured"][i] = (img, st["prompt"], res)
        return res

    # 計画と記録
    saved = pausekeep.state(pause_key) if (pause_key and resume) else None
    if saved and "plan" in saved:   # 一時停止した工程から続ける。済んだ工程の絵と記録はそのまま使う
        plan = Plan.load(names, HIDDEN, saved["plan"])
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
        say(f"一時停止した工程 {j}/{nn}「{plan.label(plan.current())}」から続けます")
    else:
        saved = None
        plan = Plan.initial(names, draws, HIDDEN, items_by_phase=items_by_phase)
        final, history, entry, visits = {}, [], {}, [0] * n
        backs, total, fixes = 0, 0, 0
        tries: dict = {}          # (工程, 項目) ごとの、直しの強さの段（手を替えた回数）
        passed_over: list = []    # 利用者が「このまま進む」を選んだ崩れ
        remaining: dict = {}      # 直らずに次の工程へ持ち越した崩れ（項目ごと）。あとの確かめで消えたら外す
        phase_left: dict = {}     # 工程ごとの、項目ごとの残った崩れ
    asked = None
    resumed = saved is not None
    # 部品不足・例外で読めなかった検品の理由のうち、直しを 1 度試した物。同じ理由で
    # 読めないままなら、それ以上は絵を直さない（検品の故障は絵を直しても直らない）
    unreadable_hopeless: set = set()
    # 項目ごとに、直しても崩れの重さが下がらなかった直しの回数。重さが下がれば数え直す
    no_progress: dict = {}
    # アタリで実際に直しをかけた構成の項目。アタリで手を尽くした構成を、線画以降で
    # 振り直すと清書した線まで壊れ、崩れの顔ぶれが変わり続けて直しが終わらない
    # （検証 #27 の監査）。アタリで直していない（初めて見つかった）欠けはこの限りではない
    composition_mended: set = set()

    def tkey(i, item):
        return f"{i}:{item}"

    def progress(state, left=()):
        """止めたときに窓が読む今の状態。裏の糸が止められて返りが無くても、ここから止めた所までの絵と崩れを出す"""
        rows = [final[k] for k in sorted(final, key=int) if final.get(k) is not None]
        cur = plan.current()
        j, nn = plan.number()
        try:
            (keep / "progress.json").write_text(json.dumps(
                {"state": state, "phase": names[cur["phase"]] if cur else names[-1], "step": plan.label(cur) if cur else "",
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
        if on_preview is not None and i >= names.index(SHOW_FROM):   # ラフ（サムネイル）から先の絵は、描けたら筆で見せる
            try:
                shown = img.copy()
                j, nn = plan.number()
                shown.info[PHASE_TAG] = {"phase": names[i], "no": j, "need": nn, "total": total}
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
            row = {"phase": names[i], "decides": phase_info[i][1], "checks": phase_info[i][2], "numbers_of": phase_info[i][3],
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
            regs = [(tuple(b), t) for b, t in how["regions"]]
            # 検品の枠が主役の絵に全く重なっていない物は直さない。背景の何も無い所を
            # 「崩れた手」と読んだ枠を囲んで消して描き直すと、直しがそこに手を描いて
            # しまう（関係ない所に手足が量産される）。主役の範囲が絵の大半を覆って
            # いて切り分けられないときは、今までどおり直す（判断できない物を止めない）
            subj = _person(img)
            if subj is not None and subj.mean() <= GROW_MOST:
                kept = []
                for b, t in regs:
                    x0, y0, x1, y1 = (int(c) for c in b)
                    if subj[max(0, y0):max(0, y1), max(0, x0):max(0, x1)].any():
                        kept.append((b, t))
                    else:
                        say(f"検品の枠 {list(b)} は主役の絵に重なっていないので、誤検出として直しません")
                if not kept:
                    return None
                regs = kept
            mask = _mask(img.size, regs)
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
                # 枠ごとに 1 つずつ直す。全部の枠を一度に消して描くと変化が大きくて崩れる。
                # 1 枠ずつ小さく消して描いてを繰り返すと、変化が小さいので崩れずに整っていく（利用者の指摘）
                if len(regs) == len(flaws):
                    return [step("mend", i, item, flaws=[f], k=k, how={"mask": "regions", "regions": [r]}) for f, r in zip(flaws, regs)]
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": [r]}) for r in regs]
        if item == "頼んだ物" and i == 2:
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "wear", "missing": list(res.get("missing", []))})]
        if item == "目の光" and res.get("eyes"):
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "eyes", "regions": [[list(b), t] for b, t in res["eyes"]]})]
        if item in ("ゴミ", "色のにじみ"):
            # ゴミ・にじみは、検品の枠の中を紙の色で消す（模型で描き直さない）
            kind = "dust" if item == "ゴミ" else "bleed"
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == kind]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs, "op": "erase", "what": kind})]
        if item == "位置ずれ":
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == "part"]
            if i == 3 and k == 0:
                # 線画の最初の一手だけ: 部位とは言えない小さい離れた欠片は、模型で
                # 描き直さず消して扱う。消せる欠片が無ければ、直しの側で囲みの
                # 描き直しに切り替わる（regions を一緒に渡すのは、そのため）
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "erase_detached", "regions": regs})]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "boxes", "regions": regs})]
        if item == "画角":
            tilt = res.get("tilt")
            if tilt is not None and abs(tilt) <= ROTATE_MOST:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "rotate", "angle": tilt})]
            return []   # 大きく傾いている。回して直さない（残った崩れとして次へ進む）
        if item == "背景":
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "background"})]
        if item == "斑点":
            # 斑点は、平らにした絵と比べて見つけた塊を、周りの色で埋めて消す（純粋な操作）
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "blotch"})]
        if item == "塗り残し":
            if k == 0:
                regs = [[list(b), t] for b, t in res.get("regions", []) if t == "cover"]
                if regs:
                    return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "boxes", "regions": regs})]
            # 描き直しで直らなければ、輪郭の内側の紙のままの所を周りの色で埋める（純粋な操作）
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "cover"})]
        if item == "色の差":
            if k == 0:
                # 近い色を寄せて色数を減らす（純粋な操作）。描き直しだけだと、色数が
                # 変わるたびに責任の判定で戻され、直し切れずに未完成で終わっていた
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "posterize"})]
        if item == "線の強弱":
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "thicken"})]
        if item == "ディテール":
            # 質感の締め直し（純粋な操作）。新しい物は描かないし、何も消さない
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "detail"})]
        if item == "影の締まり":
            # 弱い強さでディテールを描き直す（潰れの見張りを通らなければ元のまま＝直らなかった扱い）
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "detail_retry"})]
        if item == "影":
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "shadow_side"})]
        if item == "水の光":
            # 水に光の筋を付ける（模型で描き直さない、純粋な操作）
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "shine", "shine": "water"})]
        if item == "葉のつや":
            # 葉につやの点を付ける（模型で描き直さない、純粋な操作）
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "shine", "shine": "leaf"})]
        if item == "タイヤの丸み":
            # 丸くないタイヤの枠を消してから、丸いタイヤの言葉で描き直す
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == "tire"]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs})]
        if item == "左右対称":
            # 左右のタイヤがそろっていない：小さいタイヤの枠を描き直す。車体が対称でない：鏡写しで直す
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == "tire"]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs})]
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"op": "mirror"})]
        if item == "遠近の収束":
            # 収束しない線の所を消してから、遠近の言葉で描き直す
            regs = [[list(b), t] for b, t in res.get("regions", []) if t == "perspective"]
            if regs:
                return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs})]
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
        if why is None and item in composition_mended and i > 2:
            # アタリで手を尽くした構成は、線画以降では振り直さない（監査の結論）
            why = "構成の直しはアタリで終えているので、ここでは描き直しません"
        if why is None and no_progress.get(item, 0) >= NO_PROGRESS:
            why = "直しても崩れの重さが変わりませんでした"
        if why is None and k >= MENDS:
            why = f"{MENDS} 回手を替えて囲みの中を直しても消えませんでした"
        if why is None:
            if i == 2 and item in ("頼んだ物", "人数"):
                composition_mended.add(item)
            new = mends_for(i, item, flaws, res, k)
            at = plan.last_pending(("mend",), i, item)
            at = plan.pos + 1 if at is None else at + 1
            plan.insert(new + ([] if plan.pending("recheck", i, item) else [step("recheck", i, item)]), at)
        else:
            for x in list(plan.steps[plan.pos + 1:]):
                if x["phase"] == i and x.get("item") == item and x["kind"] in ("mend", "recheck") and x["status"] == "todo":
                    plan.steps.remove(x)
            remaining[item] = [f"{names[i]}: {f}" for f in flaws]
            tries.pop(tkey(i, item), None)
            say(f"「{names[i]}」の「{item}」は直りませんでした（{why}）。絵は前のまま残し、残った崩れとして次の工程へ進みます: "
                + "、".join(flaws[:3]))
        grew(old)

    def line_integrity(i, row):
        """色・仕上げの工程の出口で、清書の線が埋もれていないか確かめる（利用者の指摘、
        2026-11-27: 先の工程に行ったら壊れてても修正に戻らない）。工程は自分の範囲しか
        直さないので、後の工程が清書の線を埋めても、最終検品まで誰も気づかなかった。
        埋もれていたら清書のレイヤーから戻し、戻し切れなければ残った崩れとして数える
        （黙って完成にしない）。清書のレイヤー自体は書き換えない"""
        line = (st.get("layers") or {}).get("清書")
        img = st.get("image")
        if line is None or img is None or line.size != img.size:
            return
        # 比べるのは線らしい画素だけ（pt.line_pixels: 線でない暗い塊は、後の直しで
        # 正しく消える物なので参照にしない）。仕上げや艶の描き重ねで線の縁が明るく
        # なったり、回す直しで線が数画素ずれたりするのは、埋もれではない
        core_l = pt.line_pixels(line)
        total = int(core_l.sum())
        if not total:
            return
        r = max(2, round(min(img.size) / 32))   # この近さに暗い画素があれば、線はそこにある

        def missing(im):
            present = pt._dilate(pt.luminance(im) < 80, r)
            return float((core_l & ~present).sum()) / total

        if missing(img) <= LINE_LOSS_MOST:
            return
        restored, _n = pt.restore_missing_lines(line, img)
        if restored is not img and missing(restored) < missing(img):
            st["image"] = restored
            img = restored
            if row.get("image"):
                row["image"] = save_img(img, i, names[i])
            say(f"「{names[i]}」で埋もれた清書の線を、清書のレイヤーから戻しました")
        if missing(img) > LINE_LOSS_MOST:
            msg = f"清書の線が埋もれている（{names[i]}の出口で {missing(img):.0%}）"
            phase_left.setdefault(str(i), {})["線の完全性"] = [msg]
            remaining["線の完全性"] = [f"{names[i]}: {msg}"]

    def finish_phase(i, row):
        """工程（9 の 1 つ）の最後の工程が済んだ。記録をまとめ、確かめ（confirm）を受ける。描き直しを頼まれたら True"""
        nonlocal backs
        if i in (4, 5, 6, 7, 9):   # 下塗り・光源・影・艶・仕上げ: 清書の線を埋めうる工程の出口で確かめる
            line_integrity(i, row)
        left = [f for fl in phase_left.get(str(i), {}).values() for f in fl]
        row["after"] = list(left)
        row["fixed"] = bool(row["mends"]) or row["fixed"]
        row["mem_mb"] = release()
        row["total"], row["need"] = total, plan.need()
        row["tone"] = pt.tone(st["image"]) if st.get("image") is not None else None
        row["tone_guard"] = [t for t in tones if t.get("phase") == names[i]]
        say(f"「{names[i]}」の検品: " + ("崩れは見つかりませんでした" if not left else "残った崩れ " + "、".join(left[:4])))
        progress("drawing", left)
        if confirm is None:
            return False
        ans = confirm(i, names[i], st.get("image"), row)
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
        say(f"描き直しを頼まれたので「{names[target]}」から順に進めます")
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
            say(f"工程 {j}/{nn}「{label}」（直し {fixes} 回）: "
                + (phase_info[i][1] if kind == "draw" else f"見る物: {phase_info[i][2]}" if kind in ("check", "recheck") else "、".join(s.get("flaws", [])[:3])))
            progress("drawing", left_now)
            tones.clear()
            t0 = time.time()
            try:
                if kind == "draw":
                    if i == 3 and st.get("image") is not None:
                        # ラフをレイヤーとして残す。線画はこの上に描き、工程の絵では
                        # ラフを薄くして下に敷く（利用者の進め方）。検品と直しは線の絵で行う
                        st["layers"]["ラフ"] = st["image"]
                        st["image"].save(keep / f"layer-{2 + 1:02d}-ラフ.png")
                    if i == 4 and st.get("image") is not None:
                        # 線のレイヤーを残す。ゴミ取りは清書（線画）で済んでいるので、ここでは消さない
                        # （色の直前にもう一度消すと、細い線やディテールまで消える。利用者の規則）
                        st["layers"]["線画"] = st["image"]
                        st["layers"]["清書"] = st["image"]   # 清書レイヤー: 清書の済んだ線画。色はこの上に乗せる
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
                        # 工程の絵は表示用の合成があればそちら（線画は薄いラフの上に線）。
                        # 検品・次の工程・前後比較は、レイヤーそのもの（img）で進める
                        s["image"] = save_img(got.get("display") or img, i, names[i])
                        row.update({"image": s["image"], "changed": True, "diff": s["diff"]})
                    elif before is not None and img is not None:
                        say(f"「{names[i]}」は絵を変えなかったので、工程として数えません")
                    s["status"] = "done"
                elif kind in ("check", "recheck"):
                    res = measure(i, fresh=(kind == "recheck"))
                    got_flaws = list(res["by_item"].get(item, []))
                    # この工程の検品がその項目を実際に測っているか。測っていない項目は、崩れが
                    # 出なかったのではなく見ていないだけなので、持ち越した崩れを外さない
                    covered = item in (res.get("covers") or ()) or bool(got_flaws)
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
                        p_show = keep / f"{i + 1:02d}-{names[i]}-確かめ.png"
                        res["show"].save(p_show)
                        row["show"] = str(p_show)
                    if kind == "check":   # 初めの並びに無い項目に崩れが出たら、その工程の確かめの最後に確かめる工程を足す。
                        # ただし足すのは、その工程が扱う項目（covers）だけ。測る工程が広いと
                        # （線画は状態の把握にアタリの検品一式でも測る）、他の工程の仕事まで
                        # その場で直し始めて、適所でない直しが膨らみ、絵も壊れる
                        planned = {x.get("item") for x in plan.steps[:plan.end_of_phase(i)] if x["phase"] == i
                                   and x["kind"] == "check" and x.get("visit", visits[i]) == visits[i]}
                        extra = [it for it in res["by_item"] if it not in planned
                                 and (it in (res.get("covers") or ()) or it in (items.OTHER, items.READABLE))]
                        if extra:
                            old = plan.need()
                            plan.insert([step("check", i, it, visit=visits[i]) for it in extra], plan.end_of_phase(i))
                            grew(old)
                    if kind == "recheck":
                        prev = phase_left.get(str(i), {}).get(item, [])
                        # 責任の判定: この直しで別の項目の崩れが増えていたら、それは新しい
                        # 仕事ではなく、この直しが壊した物。直す前の絵に戻し、この直しの
                        # 失敗として数える（壊した分を別の直しに回して「直った」ことに
                        # しない。塗りつぶして見えなくするのも同じで、そもそも壊さない）
                        beforeby = memo.get(("beforeby", i, item))
                        if beforeby is not None and memo.get(("before", i, item)) is not None:
                            afterby = res.get("by_item") or {}
                            others_worse = [k2 for k2, fl in afterby.items()
                                            if k2 != item and _severity(fl) > _severity(beforeby.get(k2, [])) + 0.5]
                            if others_worse:
                                say(f"「{item}」の直しで「{'、'.join(others_worse)}」が壊れたので、直す前の絵に戻します（壊した分は、この直しの失敗として数えます）")
                                st["image"] = memo[("before", i, item)]
                                got_flaws = prev
                                s["reverted"] = True
                                no_progress[item] = no_progress.get(item, 0) + 1
                        if prev and got_flaws:
                            # 直したのに崩れの重さが下がらなかった（同じか増えた）ら数える。
                            # 重さが下がれば、直しが効いているので数え直す
                            if _severity(got_flaws) >= _severity(prev):
                                no_progress[item] = no_progress.get(item, 0) + 1
                            else:
                                no_progress.pop(item, None)
                        if prev and _severity(got_flaws) > _severity(prev) and memo.get(("before", i, item)) is not None:
                            # 直しで崩れが増えた。直す前の絵に戻し、手を替えて直し直す（ゼロには戻らない）
                            say(f"「{item}」の直しで崩れが増えたので、直す前の絵に戻します")
                            st["image"] = memo[("before", i, item)]
                            got_flaws = prev
                            s["reverted"] = True
                    if covered:
                        phase_left.setdefault(str(i), {})[item] = got_flaws
                    memo.pop(("before", i, item), None)
                    memo.pop(("beforeby", i, item), None)
                    left_now = got_flaws
                    say(f"「{label}」: " + ("崩れは見つかりませんでした" if not got_flaws else "崩れ " + "、".join(got_flaws[:4])))
                    if got_flaws:
                        if i <= 1:
                            # 目的とサムネイルは直さずに次へ進む（サムネイルを描き直し続けて先へ進まなかった）。
                            # サムネイルの崩れは、そのあとの工程の確かめがもう一度見つけ、そこで囲んで直す
                            say(f"「{names[i]}」の崩れは、次の工程から囲んで直します")
                            s["status"] = "carried"
                            row["carried"] = row.get("carried", []) + got_flaws
                            phase_left[str(i)][item] = []
                        else:
                            k = tries.get(tkey(i, item), -1) + 1
                            tries[tkey(i, item)] = k
                            flaws_now = got_flaws
                            if items.UNREADABLE in flaws_now:
                                # 読めなかった検品の扱い。部品が無い・例外で落ちた検品は、絵を直しても
                                # 読めるようにはならない。理由が分かる物は直しを 1 度だけ試し、それでも
                                # 読めなければ絵を直さず、未検品として理由つきで残す（完成にはしない）。
                                # 理由の分からない読めなさ（検品が動いて読めなかった）は、今までどおり直して確かめる
                                flaws_now = [f for f in flaws_now if f != items.UNREADABLE]
                                reasons = [r for _n, r in (res.get("unreadable") or [])]
                                if reasons and (any("がありません" in r for r in reasons)
                                                or any(r in unreadable_hopeless for r in reasons)):
                                    remaining[item] = [f"{names[i]}: 検品できませんでした（{r}）" for r in reasons]
                                    say(f"「{names[i]}」の検品ができませんでした（{'、'.join(reasons)}）。"
                                        "検品の故障は絵を直しても直らないので、絵は直さず、未検品として残します")
                                else:
                                    if reasons:
                                        unreadable_hopeless.update(reasons)
                                    queue_fix(i, item, [items.UNREADABLE], res, k)
                            if flaws_now:
                                queue_fix(i, item, flaws_now, res, k)
                    else:
                        tries.pop(tkey(i, item), None)
                        if covered:
                            remaining.pop(item, None)   # 持ち越した崩れが、この工程の確かめで消えた
                elif kind == "mend":
                    cur = st["image"]
                    how = s.get("how") or {}
                    op = how.get("op")
                    k = int(s.get("k", 0))
                    if op == "erase_detached" and how.get("regions") and pt.detached_erasure_mask(cur) is None:
                        # 消せる欠片が無い（離れた物は全部、部位かもしれない大きさ）。
                        # 同じ消す直しを繰り返さず、囲みの描き直しに切り替える
                        say("消せる欠片は無いので、離れた物の囲みを描き直します")
                        how = {"mask": "boxes", "regions": how["regions"]}
                        op = None
                    if op in ("rotate", "thicken", "erase", "shine", "mirror", "detail", "detail_retry", "erase_detached",
                              "blotch", "cover", "posterize"):
                        # 模型で描き直さない直し（純粋な操作）。直す工程には、必ず対応する検品がある
                        tried = None
                        dd = None
                        changed = False
                        mend_name = {"rotate": "回す", "thicken": "太らせる", "erase": "消す",
                                     "shine": "光を付ける", "mirror": "鏡写し",
                                     "detail": "質感を締める", "detail_retry": "弱く描き直す",
                                     "erase_detached": "欠片を消す", "blotch": "斑点を消す",
                                     "cover": "塗り残しを埋める", "posterize": "色を寄せる"}[op]
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
                            r = pt.outline_radius(cur)   # 太さの狙いは直すたびに同じ。半径を大きくして繰り返すと、正常な線画が 10 倍ぐらいの太さになった
                            tried, _hit = pt.weight_lines(cur, r=r)
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        elif op == "shine":
                            kind = how.get("shine") or "water"
                            say(f"{'水に光の筋' if kind == 'water' else '葉につやの点'}を付けています: " + "、".join(s.get("flaws", [])[:3]))
                            tried, _hit = pt.shine_water(cur) if kind == "water" else pt.shine_leaf(cur)
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        elif op == "mirror":
                            say(f"左右対称になるよう、鏡写しで直しています: " + "、".join(s.get("flaws", [])[:3]))
                            tried, _hit = pt.mirror_fix(cur)
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        elif op == "erase_detached":
                            say(f"部位とは言えない小さい離れた欠片を消しています: " + "、".join(s.get("flaws", [])[:3]))
                            mask = pt.detached_erasure_mask(cur)
                            if mask is None:
                                tried = cur
                                dd = diff(cur, tried)
                                dd["outside"], dd["inside"] = dd["mean"], dd["mean"]
                                changed = False
                            else:
                                tried = pt.erase_fill(cur, mask)
                                dd = diff(cur, tried, mask)
                                changed = (dd["inside"] or 0) >= 10
                        elif op == "detail":
                            say(f"質感を締め直しています: " + "、".join(s.get("flaws", [])[:3]))
                            tried = pt.enhance_detail(cur)
                            dentry = st.get("detail_entry")   # 名前は entry にしない（draw の工程の入り口の記録と別物）
                            if (dentry is not None and dentry.size == tried.size
                                    and (pt.new_specks(dentry, tried) > SPECKS_MOST or pt.new_bumps(dentry, tried) > SPECKS_MOST)):
                                say("質感の締め直しで、ディテール工程に入ってから増えた斑点が境目を超えたので、採用しません")
                                tried = cur   # 工程全体で増えた斑点の見張り（1 回ごとでは境目未満でも積み重なる）
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        elif op == "detail_retry":
                            say(f"影を潰さないよう、弱い強さでディテールを描き直しています: " + "、".join(s.get("flaws", [])[:3]))
                            got2 = detail_pass(cur, SHINE / 2, st["seed"] + k * 77)
                            tried = got2 if got2 is not None else cur
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        elif op == "blotch":
                            say(f"色の面の斑点を、周りの色で埋めて消しています: " + "、".join(s.get("flaws", [])[:3]))
                            mask, _n = pt.blotch_mask(cur)
                            if mask is None:
                                tried = cur
                                dd = diff(cur, tried)
                                dd["outside"], dd["inside"] = dd["mean"], dd["mean"]
                                changed = False
                            else:
                                tried = pt.area_fill(cur, mask)
                                dd = diff(cur, tried, mask)
                                changed = (dd["inside"] or 0) >= 10
                        elif op == "cover":
                            say(f"塗り残し（輪郭の内側で紙のままの所）を、周りの色で埋めています: " + "、".join(s.get("flaws", [])[:3]))
                            mask, _cshare = pt.coverage_mask(cur)
                            if mask is None:
                                tried = cur
                                dd = diff(cur, tried)
                                dd["outside"], dd["inside"] = dd["mean"], dd["mean"]
                                changed = False
                            else:
                                tried = pt.area_fill(cur, mask)
                                dd = diff(cur, tried, mask)
                                changed = (dd["inside"] or 0) >= 10
                        elif op == "posterize":
                            say(f"散らかった色を、近い色同士で寄せて減らしています: " + "、".join(s.get("flaws", [])[:3]))
                            tried = pt.posterize_base(cur, COLORS_MOST)
                            dd = diff(cur, tried)
                            dd["outside"], dd["inside"] = dd["mean"], dd["mean"]   # 絵全体の操作なので、外も中も全体の差
                            changed = (dd["mean"] or 0) >= DIFF_MIN
                        else:  # erase
                            if how.get("what") == "dust":
                                # ゴミは塊そのものだけを消す。枠の円で広げると、線の欠片が集まった所（顔など）が
                                # 紙の色の塊で覆われる（検証 45696035067 の仕上げ: 円の囲みが頭の 19% を覆った）
                                mask = pt.dust_mask(cur)
                                if mask is not None and (mask.getextrema()[1] == 0 or _share(mask) > GROW_MOST):
                                    mask = None
                            else:
                                mask = mend_mask(cur, how)
                            if mask is None:
                                s["status"] = "skipped"
                                queue_fix(i, item, s.get("flaws", []), {}, k, why="囲めない崩れです")
                            else:
                                import numpy as np
                                tried = pt.erase_fill(cur, mask)
                                dd = diff(cur, tried, mask)
                                # 小さなゴミは全体の差が小さいので、囲みの中の差で変わったかを見る
                                changed = (dd["inside"] or 0) >= 10
                        if tried is not None and dd is not None:
                            s.update({"strength": 1.0, "diff": dd["mean"], "outside": dd.get("outside"), "inside": dd.get("inside"),
                                      "words": [], "changed": changed})
                            mrow = {"phase": names[i], "mend": mend_name, "item": item,
                                    "strength": 1.0, "found": list(s.get("flaws", [])), "diff": dd["mean"], "outside": dd.get("outside"),
                                    "inside": dd.get("inside"), "words": [], "readable": True, "image": None, "changed": changed,
                                    "visit": visits[i]}
                            row["mends"].append(mrow)
                            if changed:
                                fixes += 1
                                memo.setdefault(("before", i, item), cur)
                                memo.setdefault(("beforeby", i, item), measure(i)["by_item"])   # 責任の判定用: 直す前の項目別の崩れ
                                st["image"] = tried
                                s["image"] = mrow["image"] = save_img(tried, i, f"{names[i]}-直し")
                                s["status"] = "done"
                            else:
                                say(f"直しで絵がほとんど変わらなかったので（差 {dd['mean']}）、数えずに直し直します")
                                s["status"] = "unchanged"
                                no_progress[item] = no_progress.get(item, 0) + 1   # 絵が変わらなかった直しは、進まなかった直しとして数える
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
                            s0 = steps(stage_steps(i))
                            try:
                                raw = painter.refine(words, seed, cur, strength=strength, on_step=on_step)
                            finally:
                                unsteps(s0)
                            # 下描きの描き重ねと同じ守りを掛ける。守りが無いと、直しのたびに霞んで色が薄くなり、
                            # 汚れが広がって良いアタリが壊れる（検証 45696035067: アタリの直しのあとで対比 35.9 → 12.8）
                            tried = keep_tone(raw, cur, "構図の直し")
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
                                # 消してから描くのが順番（利用者の規則、2026-11-27）。形を変える直しを
                                # 古い形の上に描くと、古い線が薄く残って二重になり、検品に残り続ける。
                                # 前は手・足・顔（regions）だけが消してから描いていて、アタリの骨組み・
                                # 位置ずれ・頼んだ物などは上に描いていた。目（光を足す）・影の側（調子）・
                                # 赤ペン（利用者の印）だけは、元の絵を土台に描き重ねる
                                clean = how.get("mask") not in ("eyes", "shadow_side", "pen")
                                if how.get("mask") == "regions":
                                    # 手・足・顔の形の崩れ：囲みの中を消してから描き直す。
                                    # 囲みの中に渡すのは、その囲みの直す内容の言葉だけ。
                                    # 依頼の文（場面の説明）は渡さない。囲みの外の絵が場面を教える。
                                    # 線の工程では線の言葉だけを足して、線画の調子を保つ。
                                    fw = fix_words(how.get("regions"))
                                    if fw:
                                        words = f"{fw}, {line_words(i)}" if i <= 3 else fw
                                say(f"崩れた所の囲みの中だけを直しています（強さ {strength}）: " + "、".join(s.get("flaws", [])[:3]))
                                tell(words)
                                # 線の段階（〜線画。線画モードの「線の仕上げ」も）の直しは、絵を広げずに
                                # 描く。線だけの絵に細部の画素数を稼ぐ広げは要らず、広げた分だけ
                                # 1 回の直しが重くなる（画素数 2.25 倍）。色の段階の直しは今までどおり広げる。
                                # 速さも工程ごとに分ける（序盤は軽く、清書以降はそのまま）。
                                # 途中の絵も出す（on_step）。出さないと、直しの間ずっと筆が止まって見える
                                s0 = steps(stage_steps(i))
                                try:
                                    raw = painter.redraw(words, seed, cur, m, strength=strength, clean=clean, on_step=on_step,
                                                         max_scale=1.0 if (i <= 3 or (line_art and i == 4)) else None)
                                finally:
                                    unsteps(s0)
                                if how.get("mask") == "wear":
                                    raw = keep_tone(raw, cur, "服・髪・持ち物", m)
                                tried = _inside(raw, cur, m)
                                if clean:
                                    # 後始末の検品: 消して描き直した直しで、消した物の欠片が
                                    # 囲みの縁の外に残っていたら、その直しの中で消す
                                    left = pt.edge_leftovers(cur, tried, m)
                                    if left is not None:
                                        say("消した物の欠片が囲みの縁に残っていたので、後始末で消します")
                                        tried = pt.erase_fill(tried, left)
                                dd = diff(cur, tried, m)
                                # 塗りつぶしの見張り: 囲みの中に線や質感があったのに、描き直しで
                                # 平らになっていたら、それは直しではなく塗りつぶして誤魔化した物。
                                # 採用せず元の絵のままにする（形を無くして、判定だけ良く見せない）
                                tex_b = pt.local_texture(cur, m)
                                if tex_b >= 10 and pt.local_texture(tried, m) < tex_b * FLAT_KEEP:
                                    say(f"「{item}」の描き直しが囲みの中を塗りつぶしたので、採用しません（形を無くして良く見せる直しはしません）")
                                    tried = cur
                                    dd = diff(cur, tried, m)
                                    s["rejected"] = True
                                # 斑点の見張り: 描き直しで新しい暗い塊やブツブツが増えていたら採用しない。
                                # 今までこの見張りはディテールの描き重ね（detail_pass）の中だけにあり、
                                # 下塗りの色の直し・影・目の直しなどは斑点を散らかしても採用されていた
                                if pt.new_specks(cur, tried) > SPECKS_MOST or pt.new_bumps(cur, tried) > SPECKS_MOST:
                                    say(f"「{item}」の描き直しで斑点（新しい暗い塊・ブツブツ）が増えたので、採用しません")
                                    tried = cur
                                    dd = diff(cur, tried, m)
                                    s["rejected"] = True
                                attempted = True
                        if attempted:
                            s.update({"strength": strength, "diff": dd["mean"], "outside": dd["outside"], "inside": dd["inside"],
                                      "words": [words], "changed": (dd["mean"] or 0) >= DIFF_MIN})
                            mrow = {"phase": names[i], "mend": "赤ペン" if how.get("mask") == "pen" else k + 1, "item": item,
                                    "strength": strength, "found": list(s.get("flaws", [])), "diff": dd["mean"], "outside": dd["outside"],
                                    "inside": dd["inside"], "words": [words], "readable": True, "image": None, "changed": s["changed"],
                                    "visit": visits[i], **({"pen": True} if how.get("mask") == "pen" else {}),
                                    **({"full": True} if full else {})}
                            row["mends"].append(mrow)
                            if s["changed"]:
                                fixes += 1
                                memo.setdefault(("before", i, item), cur)
                                memo.setdefault(("beforeby", i, item), measure(i)["by_item"])   # 責任の判定用: 直す前の項目別の崩れ
                                st["image"] = tried
                                s["image"] = mrow["image"] = save_img(tried, i, f"{names[i]}-{'赤ペンの' if how.get('mask') == 'pen' else ''}直し")
                                s["status"] = "done"
                            else:
                                # 絵がほとんど変わらなかった直しは工程として数えず、囲みを広げ、強さを上げて直し直す（同じ入力を繰り返さない）
                                say(f"直しで絵がほとんど変わらなかったので（差 {dd['mean']}）、数えずに囲みを広げ、強さを上げます")
                                s["status"] = "unchanged"
                                no_progress[item] = no_progress.get(item, 0) + 1   # 絵が変わらなかった直しは、進まなかった直しとして数える
                                nk = max(k + 1, tries.get(tkey(i, item), 0) + 1)
                                tries[tkey(i, item)] = nk
                                old = plan.need()
                                # 見張りに採用されなかった直しは、同じ手（囲みを広げ・強さを上げた描き直し）を
                                # 繰り返さない。確かめ直しが次の手（mends_for の次の段）を差し込む。
                                # 同じ手を繰り返すと、確実に効く手（塗り残しを埋める等）に永遠に届かない
                                if nk < MENDS and how.get("mask") != "pen" and not s.get("rejected"):
                                    plan.insert([step("mend", i, item, flaws=list(s.get("flaws", [])), k=nk, how=how)])
                                # 手を替え尽くしたら差し込まない。待っている確かめ直しが同じ崩れを見つけ、聞く工程を差し込む
                                grew(old)
                elif kind == "ask":
                    why = s.get("why", "")
                    flaws = list(s.get("flaws", []))
                    choices = ["赤ペンで囲んで直す", "言葉を足して直す", "構図から描き直す", "このまま進む"]
                    say(f"「{names[i]}」で崩れが残りました（{why}）: " + "、".join(flaws[:4]) + "。直し方を選んでください: " + "、".join(choices))
                    ans = ask(i, names[i], flaws, choices) if ask is not None else None
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
                        passed_over += [f"{names[i]}: {x}" for x in flaws]
                        phase_left.setdefault(str(i), {})[item] = []
                        tries.pop(tkey(i, item), None)
                    else:
                        asked = {"phase": names[i], "index": i, "item": item, "left": flaws, "why": why, "choices": choices,
                                 "step": plan.number()[0]}
                        s["status"] = "asked"
                        if pause_key:   # 窓のボタンで選んだ答えを持って、この聞く工程から続けられるように残す
                            s["status"] = "todo"
                            entry_step = dict(st)
                            keep_pause(f"「{names[i]}」で崩れが残って止まり、直し方を待っています", {"asked": asked})
                            asked["key"] = pause_key
                        break
            except Exception as e:   # noqa: BLE001  止めて捨てずに、この工程に入ったときの計画と土台を残す
                if not pause_key or isinstance(e, (Stopped, pausekeep.Paused)):
                    raise
                st.clear()
                st.update(entry_step)
                keep_pause(f"「{label}」で一時停止")
                progress("paused")
                raise pausekeep.Paused(f"「{label}」で一時停止しました（{type(e).__name__}: {e}）。"
                                       "途中まで保存したので、「再開」でこの工程から続けます", pause_key) from e
            s["seconds"] = round(time.time() - t0, 2)
            row["seconds"] = round(row["seconds"] + s["seconds"], 2)
            row["steps"].append(plan.number()[0])
            for t in tones:
                t.setdefault("phase", names[i])
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
    # 最終チェック（仕上げの後、完成の前）: 清書より後の直しで消えた線が無いかを見る。
    # 線は清書のレイヤーに残っているので、途切れた線分（残っている線に両端がつながる物）
    # だけをレイヤーから戻せる。戻した上で線の途切れとゴミを数え直し、途切れが残れば
    # 完成にせず、残った崩れとして出す
    final_check = {"flaws": [], "restored": 0, "dust": None}
    line_layer = st["layers"].get("清書")
    if st.get("image") is not None and line_layer is not None and line_layer.size == st["image"].size:
        fixed, n_px = pt.restore_missing_lines(line_layer, st["image"])
        if n_px:
            say(f"最終チェック: 直しで消えた線（{n_px} 画素）を、清書のレイヤーから戻しました")
            st["image"] = fixed
            final_check["restored"] = n_px
        lm = pt.lines(st["image"])
        if lm.get("readable"):
            if lm["gap"] > pt.LINE_GAP_MOST:
                final_check["flaws"].append(f"外の輪郭が途切れている（{lm['gap']}）")
            if lm.get("max_gap", 0) > pt.LINE_MAX_GAP_MOST:
                final_check["flaws"].append(f"線が途中でずれている（途切れが {lm['max_gap']}）")
        dd = pt.dust(st["image"])
        if dd.get("readable"):
            final_check["dust"] = dd["count"]
    # 磨き上げの最低条件: 最後の絵の崩れの重さが、土台（80 点の一発の絵）より小さくなければ完成にしない。
    # 土台も最後も崩れが無ければ（比べる検品で 0 同士なら）悪くなってはいないので、そのまま完成にする
    base_rec = st.get("base") or {}
    base_sev = base_rec.get("severity")
    final_sev = None
    if base_sev is not None and st.get("image") is not None:
        got_f = measure_base(st["image"])
        final_sev = None if got_f is None else got_f["severity"]
    not_better = None
    if base_sev is not None and final_sev is not None and final_sev >= base_sev and (base_sev > 0 or final_sev > 0):
        not_better = f"最初の絵より良くなっていない（崩れの重さ {base_sev} → {final_sev}）"
        say(f"最後の絵の崩れの重さは {final_sev} で、土台の {base_sev} より小さくなっていません")
    if not_better is None and base_rec.get("image") is not None and st.get("image") is not None:
        # 形の見張り: 崩れの数が減っていても、塗りつぶされて原型が無くなっていたら
        # 良くなったことにはならない（利用者の指摘: 殆ど塗りつぶされて原型が無くなった。
        # でも判定は良くなってるの？）。数だけでなく、形が残っているかも見る
        db, da = pt.detail_density(base_rec["image"]), pt.detail_density(st["image"])
        # 潰れたと言えるのは、密度と鋭さの両方が半分以下になったときだけ（片方だけの
        # 低下は、柔らかい画風や単純な色面でも起きる。両方いっぺんに無くなるのが
        # 「塗りつぶされて原型が無い」状態）
        if (db.get("readable") and da.get("readable")
                and da["sharp"] < db["sharp"] * FORM_CRUSH and da["density"] < db["density"] * FORM_CRUSH):
            not_better = "最初の絵より形が潰れている（塗りつぶされて原型が残っていない）"
            say("最後の絵は最初の絵より形が潰れています（塗りつぶされて原型が残っていない）。崩れの数が減っても、完成にはしません")
    unresolved = (list(asked["left"]) if asked else []) + passed_over + [f for fl in remaining.values() for f in fl] + ([not_better] if not_better else [])
    unresolved += [f for f in final_check["flaws"] if f not in unresolved]
    complete = not unresolved
    if complete or (not asked and pause_key):
        pausekeep.clear(pause_key)
    progress("done" if complete else "asked", unresolved)
    out = {"phases": rows, "history": history, "plan": plan.rows(), "left": unresolved, "checked": True, "complete": complete,
           "asked": asked, "backs": backs, "total": total, "need": plan.need(), "fixes": fixes,
           "remaining": [f for fl in remaining.values() for f in fl],
           "base": {"severity": base_sev, "flaws": list(base_rec.get("flaws", [])), "kind": base_rec.get("kind")},
           "final_severity": final_sev, "final_check": final_check}
    (keep / "phases.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {"image": st["image"], **out, "blocked": None, "unresolved": unresolved}
