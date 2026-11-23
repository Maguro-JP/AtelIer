"""人の描き方の工程に分けて描く（精度優先）。工程の調べは docs/knowledge/drawing-phases.md。

人は 1 回で描き上げない。目的を決め、小さなサムネイルを何枚か比べて構図を選び、丸と棒のアタリで重心と等身を決め、
体の形・顔と手と足・服と髪と持ち物を順に描き、線を清書し、部位ごとに下塗りし、光源を決めて影を 2 段に置き、
光と艶を足し、最後に縮めて見る・反転して見るで崩れを探す。工程ごとに見る物が決まっていて、崩れを見つけたら、
その崩れが決まった工程まで戻って直す。次の工程は、前の工程で決めた物を土台にして壊さずに足す。

設計の決まり（工程の管理の設計は docs/knowledge/drawing-phases.md の「工程の管理の設計」）:
- 12 の工程（PHASES）は人の描き方の段。段の中を、描く工程・確かめる工程（項目ごと、atelier/ai/phase_items.py）・
  直す工程（崩れ 1 つにつき 1 つ）・確かめ直す工程（直した項目だけ）・聞く工程に分け、計画（atelier/ai/phase_plan.py）の表に並べる。
  確かめる工程が崩れを見つけたら、直す工程と確かめ直す工程を表に差し込む。表示・一時停止・聞く所・記録は全部この表から出す
- 描く工程は測らない・直さない。測るのは確かめる工程、直すのは直す工程だけ（前は 1 つの工程の中で描く・測る・直すを全部していた）
- 構図（サムネイル）を選んだあとは、ゼロから描かない。崩れが残っても前の工程へ戻らず、種を替えて描き直すこともしない
- 直しは鉛筆と消しゴムと同じ。今の絵をそのまま土台に、崩れの場所（検品の枠、部位分け、人物の形）だけを囲み、その中だけを描き直す
  （redraw。外は Image.composite で 1 画素も変えない）。囲めない崩れは聞く工程にする。勝手に構図へ戻らない
- 直しの回数に上限は置かない（止めるのは利用者だけ）。絵がほとんど変わらない直し（差の平均が DIFF_MIN 未満）は累計に数えず、
  次の直す工程は囲みを広げ、強さを上げる。MENDS 回手を替えても消えない崩れは聞く工程で利用者に聞く
- 模型に渡す言葉は頼みを訳した言葉だけ。渡した言葉は「模型に渡す言葉:」の知らせにし、進み具合の欄の詳細にだけ置く
- 工程の始めには必ず「工程 i/N「名前」」の知らせを出す（i と N は計画の中の見せる工程の番号と数）。計画が伸びたら「要る工程 a→b」を出す
- 前の工程の絵に描き重ねたら、前の絵の色と明るさに合わせる（phase_tools.guard）
- 確かめ（confirm）を渡すと、12 の工程の 1 つが終わるたびに呼び、「進める」「この工程を描き直す」「言葉を足して描き直す」を受ける
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
NO_PREVIEW = ("目的", "サムネイル", "アタリ")   # キャンバスに途中の絵を出さない工程（アタリを表示しない）

PHASES = [
    ("目的", "何を一番見せるか（主役）", "頼み", "頼みの言葉の数、主役の言葉"),
    ("サムネイル", "構図（小さなラフを何枚か比べて選ぶ）", "白と黒の塊、画面の重さ", "人数、描かれていない物、重さの片寄り（weight_x）"),
    ("アタリ", "頭の大きさ、等身、重心", "立てるか、等身", "重心のずれ（balance）、等身（heads）、人数"),
    ("体の形", "骨格、関節の向き、左右の長さ", "腕と脚の長さ", "骨の長さの比、余分な腕・脚・頭"),
    ("顔・手・足の下描き", "顔の中心、目の高さ、指", "左右の目、指の数", "目の傾き（eye_tilt）、手・指・足・顔の崩れの数"),
    ("服・髪・持ち物", "体に乗る服と髪、持ち物", "頼んだ物があるか", "描かれていない物、頼んでいない物"),
    ("線画の清書", "線の強弱", "輪郭の途切れ、線のメリハリ", "外の輪郭の途切れ（gap）、線の明るさの差（contrast）"),
    ("下塗り", "部位ごとの色", "色の塊、色の数", "色の数（colors）"),
    ("光源", "光の向き 1 つ", "光の来る側", "左右・上下の明るさの差（dx, dy）"),
    ("影 2 段", "影 1 段目・2 段目", "影の向きのそろい、影が光より明るくないか", "影の側の暗い画素の割合（shade_share）、影と光の明るさの差"),
    ("光・艶・目のハイライト", "目の光、髪の艶", "目の中の光", "両目の一番明るい画素（eye_max）"),
    ("仕上げ", "全体の崩れ", "縮めて見る、反転して見る", "手・足・顔・体の崩れの数、縮めた明るさの差、顔の反転の差（asym）"),
]
NAMES = [p[0] for p in PHASES]
THUMBS = 2            # サムネイルの枚数
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


DRAWS = (1, 2, 4, 6, 9)   # 描く工程のある工程（サムネイル、アタリ、下描き、線画の清書、影 2 段）。ほかは測るだけで、描く工程を表に置かない


def draw(painter, prompt: str, seed: int, size, keep: Path, say=lambda m: None, on_step=None, checks=Checks, on_preview=None,
         confirm=None, pause_key: str | None = None, pause_job: dict | None = None, ask=None, answer=None) -> dict:
    """計画（atelier/ai/phase_plan.py の工程の並び）に沿って 1 枚を描く。返り値は {"image": 最後の絵, "phases": 工程ごとの最後の記録,
    "history": 全部の記録, "plan": 工程の並び, "left": [], "checked": True, "complete": True, "backs": 戻った回数,
    "total": 累計の工程の数, "need": 要る工程の数}。
    返るのは全部の工程が検品を通ったときか、利用者に聞いて止まったとき（asked）だけ。止めるのは利用者の「止める」（Stopped）だけ。
    confirm(i, 名前, 絵, 記録) は工程（12 の工程の 1 つ）の最後に呼び、"go"・"redo"・("words", 足す言葉の訳) を返す。
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
        tw, th = (w, h) if THUMB_SCALE >= 1 else (max(256, int(w * THUMB_SCALE) // 8 * 8), max(256, int(h * THUMB_SCALE) // 8 * 8))
        s0 = steps(THUMB_STEPS)
        best, rows, words = None, [], []
        try:
            for k in range(THUMBS):
                stop()
                s = st["seed"] + v * 1000 + k
                say(f"サムネイル {k + 1}/{THUMBS} を描いています（{tw}x{th}）")
                tell(st["prompt"])
                words.append(st["prompt"])
                img = painter.paint(st["prompt"], s, on_step=on_step, size=(tw, th))   # サムネイルは途中の絵もキャンバスに出さない（NO_PREVIEW）
                if THUMB_SCALE >= 1 and THUMB_STEPS >= 1:
                    memo["thumbs"][(st["prompt"], s)] = img
                req = checks.request(img, st["prompt"])   # 構図を選ぶための比べ。選んだ 1 枚の崩れは確かめる工程が項目ごとに出す
                wt = pt.thumb_weight(img)
                flaws = _people(req) + _missing(req) + (["画面の重さが片寄っている"] if wt["weight_x"] > pt.WEIGHT_MOST else [])
                rows.append({"seed": s, **wt, "flaws": len(flaws)})
                score = (len(flaws), wt["weight_x"])
                if best is None or score < best[0]:
                    best = (score, img, s, flaws, req)
                rows[-1]["score"] = list(score)
                del img
                gc.collect()
        finally:
            unsteps(s0)
        _score, img, s, flaws, req = best
        st["thumb"], st["seed_pick"] = img, s
        say(f"サムネイル {THUMBS} 枚のうち、種 {s} の構図を選びました（崩れ {len(flaws)}）")
        out = img.resize((w, h))
        memo["measured"][1] = (out, st["prompt"], {"flaws": flaws, "numbers": {"thumbs": rows, "picked": s},
                                                   "readable": bool(req.get("readable"))})
        return {"image": out, "words": words, "numbers": {"thumbs": rows, "picked": s}}

    def d_atari(v):
        words = []
        s = st.get("seed_pick", st["seed"])
        got = memo["thumbs"].get((st["prompt"], s))
        if got is not None:   # 同じ種・同じ大きさ・同じ工程の数で描いたサムネイルがあれば、それがそのままアタリ（描き直さない）
            say(f"サムネイル（種 {s}）をそのままアタリにします")
            return {"image": got, "words": words}
        s0 = steps(1.0)
        try:
            tell(st["prompt"])
            words.append(st["prompt"])
            return {"image": painter.paint(st["prompt"], s, on_step=on_step, size=(w, h)), "words": words}   # アタリも途中の絵を出さない（NO_PREVIEW）
        finally:
            unsteps(s0)

    def d_draft(v):
        img, words, note = st["image"], [], ""
        s = st["seed"] + v * 1000
        base = img
        if can_refine:   # 描き重ね（絵から絵）を先にする。線に沿って白紙から描き直すと、霞み・枠・色褪せと服の変わりが出た
            say("アタリの絵に描き重ねて、顔・手・足を描き込んでいます")
            tell(st["prompt"])
            words.append(st["prompt"])
            img = keep_tone(painter.refine(st["prompt"], s, img, strength=REFINE, on_step=on_step, **pv), base, "下描き")
        elif can_line:
            say("アタリの線に沿って、顔・手・足を描き込んでいます")
            tell(st["prompt"])
            words.append(st["prompt"])
            img = keep_tone(painter.paint(st["prompt"], s, on_step=on_step, base=img, strength=LINE_STRENGTH, size=(w, h), **pv), base, "下描き")
        else:
            note = "この模型は描き重ねられないので、アタリの絵のまま顔・手・足を確かめます"
        return {"image": img, "words": words, "note": note}

    def d_wear(v):
        """利用者が言葉を足したときだけ置く描く工程。足した言葉を服・髪・持ち物の所だけに描く"""
        img, words = st["image"], []
        if not can_fix:
            return {"image": img, "words": words, "note": "この模型は囲みの中だけを直せないので、足した言葉を描けません"}
        req = checks.request(img, st["prompt"])
        missing = list(req.get("missing", [])) if req.get("readable") else []
        words2 = emphasize(st["prompt"], missing) if missing else st["prompt"]
        say("足した言葉を、服・髪・持ち物の所だけに描き足しています")
        tell(words2)
        words.append(words2)
        protect = [b for b in [pt.face_box(st.get("points") or {})] if b]
        mask, by_parts = pt.wear_mask(img, protect)
        tried = _inside(keep_tone(painter.redraw(words2, st["seed"] + 131 + v * 1000, img, mask, strength=REPAINT), img, "服・髪・持ち物", mask), img, mask)
        return {"image": tried, "words": words, "numbers": {"by_parts": by_parts}}

    def d_lines(v):
        say("線の強弱を付けています（外の輪郭を濃く、内側の線はそのまま）")
        out, hit = pt.weight_lines(st["image"])
        return {"image": out, "numbers": {"pixels": hit}}

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
        return i in DRAWS or (i == 5 and st["prompt"] != prompt)

    drawer = {1: d_thumbs, 2: d_atari, 4: d_draft, 5: d_wear, 6: d_lines, 9: d_shadow}

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
        req = checks.request(img, st["prompt"])
        pts = points(img)
        bal = pt.balance(img)
        hd = pt.heads(pts, bal.get("height", 0)) if bal.get("readable") else None
        flaws = _people(req)
        if bal.get("readable") and bal["balance"] > pt.BALANCE_MOST:
            flaws.append(f"重心が足の上に無い（{bal['balance']}）")
        if hd is not None and not (pt.HEADS[0] <= hd <= pt.HEADS[1]):
            flaws.append(f"等身が外れている（{hd}）")
        st["points"], st["height"] = pts, bal.get("height", 0)
        return {"flaws": flaws, "numbers": {"balance": bal.get("balance"), "heads": hd, "points": len(pts)},
                "readable": bool(req.get("readable")) and bool(bal.get("readable"))}

    def m_body(img):
        pz, bd = checks.pose(img), checks.body(img, st["prompt"])
        flaws = (list(pz.get("bad", [])) if pz.get("readable") else []) + (list(bd.get("bad", [])) if bd.get("readable") else [])
        return {"flaws": flaws, "show": pz.get("map"), "numbers": {"points": pz.get("points")},
                "note": "" if pz.get("readable") else pz.get("reason", "骨組みを読めませんでした"),
                "readable": bool(pz.get("readable")) and bool(bd.get("readable"))}

    def m_draft(img):
        res = checks.hands(img, st["prompt"])
        pc = checks.points(img)
        pts = dict(pc.get("points") or {}) if pc.get("readable") else {}
        tilt = pt.eye_tilt(pts)
        flaws = list(res.get("bad", []))
        regions = list(handcheck.bad_regions(res))
        if tilt is not None and tilt > pt.EYE_TILT:
            flaws.append(f"左右の目の高さがずれている（{tilt}）")
            if pt.face_box(pts):
                regions.append((pt.face_box(pts), "face"))
        st["points"] = pts
        return {"flaws": flaws, "regions": regions, "numbers": {"eye_tilt": tilt, "bad": len(res.get("bad", []))},
                "readable": bool(res.get("readable")) and bool(pc.get("readable"))}

    def m_wear(img):
        req = checks.request(img, st["prompt"])
        flaws = _missing(req) + _extra(req)
        if st["prompt"] != prompt and not can_fix:
            flaws.append("追加指示を反映できません（この模型は描き直し不可）")
        return {"flaws": flaws, "missing": list(req.get("missing", [])) if req.get("readable") else [],
                "numbers": {"missing": len(_missing(req)), "extra": len(_extra(req))}, "readable": bool(req.get("readable"))}

    def m_lines(img):
        m = pt.lines(img)
        return {"flaws": [f"外の輪郭が途切れている（{m['gap']}）"] if m.get("readable") and m["gap"] > pt.LINE_GAP_MOST else [],
                "numbers": m, "readable": bool(m.get("readable"))}

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
        return {"flaws": [f"色が散っている（{colors} 色）"] if colors > COLORS_MOST else [], "readable": True,
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
        # 暗い画素の左右比率は線画・髪・服の色にも左右されるため合否に使わない。影側が光側より明るいかだけを見る
        return {"flaws": [f"影が光より明るい（{sh['shade_minus_lit']}）"] if sh.get("readable") and sh["shade_minus_lit"] > 0 else [],
                "numbers": sh, "readable": bool(sh.get("readable"))}

    def m_shine(img):
        pts = points(img)   # 目の光は今の絵から読んだ座標だけで確かめる（古い目の位置で通さない）
        cl = pt.catchlights(img, pts)
        return {"flaws": [f"目の光が無い（{x}）" for x in cl.get("eye_max", []) if x < pt.CATCHLIGHT],
                "eyes": [(b, "eye") for b in cl.get("boxes", [])], "numbers": {"eye_max": cl.get("eye_max")},
                "readable": bool(cl.get("readable"))}

    def m_finish(img):
        res = checks.hands(img, st["prompt"])
        body = checks.body(img, st["prompt"])
        pts = points(img)
        sv = pt.shrink_view(img)
        face = pt.face_box(pts)
        fv = pt.flip_view(img, face) if face else {"readable": False}
        flaws = list(res.get("bad", [])) + (list(body.get("bad", [])) if body.get("readable") else [])
        if sv.get("readable") and sv["contrast"] < pt.SHRINK_CONTRAST:
            flaws.append(f"縮めると主役が目立たない（{sv['contrast']}）")
        if fv.get("readable") and fv["asym"] > pt.FLIP_MOST:
            flaws.append(f"反転すると顔が片側に歪んで見える（{fv['asym']}）")
        return {"flaws": flaws, "regions": list(handcheck.bad_regions(res)), "numbers": {"shrink": sv.get("contrast"), "asym": fv.get("asym")},
                "readable": bool(res.get("readable")) and bool(body.get("readable")) and bool(pts)
                and bool(sv.get("readable")) and bool(fv.get("readable"))}

    measurer = [m_purpose, m_thumbs, m_atari, m_body, m_draft, m_wear, m_lines, m_base, m_light, m_shadow, m_shine, m_finish]
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
        if on_preview is not None and NAMES[i] not in NO_PREVIEW:   # アタリまでの絵はキャンバスに出さない
            try:
                on_preview(img)
            except Exception:   # noqa: BLE001  見せるだけ。描く流れは止めない
                pass
        return str(path)

    def keep_pause(why_label, extra=None):
        pausekeep.save(pause_key, "phases", why_label, pause_job,
                       {"plan": plan.state(), "st": entry_step, "final": final, "history": history, "entry": entry, "visits": visits,
                        "backs": backs, "total": total, "fixes": fixes, "tries": tries, "passed_over": passed_over, "remaining": remaining,
                        "phase_left": phase_left, "need": plan.need(), **(extra or {})})

    def phase_row(i):
        """今の工程（12 の工程の 1 つ）の記録。工程に入るたびに 1 つ作り、その中の確かめ・直しの結果を積む"""
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
            elif any(k in words for k in ("腕", "脚", "頭", "骨", "重心", "等身", "体", "輪郭", "色", "影", "光", "主役",
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
        目の光は目の囲みで 1 つ、ほかは崩れ 1 つにつき 1 つ"""
        if item in items.REGION_ITEMS and res.get("regions"):
            regs = [[list(b), t] for b, t in res["regions"]]
            if len(regs) == len(flaws) and len(flaws) > 1:
                return [step("mend", i, item, flaws=[f], k=k, how={"mask": "regions", "regions": [r]}) for f, r in zip(flaws, regs)]
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "regions", "regions": regs})]
        if item == "頼んだ物" and i == 5:
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "wear", "missing": list(res.get("missing", []))})]
        if item == "目の光" and res.get("eyes"):
            return [step("mend", i, item, flaws=list(flaws), k=k, how={"mask": "eyes", "regions": [[list(b), t] for b, t in res["eyes"]]})]
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
        """工程（12 の 1 つ）の最後の工程が済んだ。記録をまとめ、確かめ（confirm）を受ける。描き直しを頼まれたら True"""
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
        target = 5 if added and i >= 5 else i
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
                    mask = mend_mask(cur, how) if cur is not None else None
                    if mask is None:
                        s["status"] = "skipped"
                        queue_fix(i, item, s.get("flaws", []), {}, s.get("k", 0), why="囲めない崩れです")
                    else:
                        k = int(s.get("k", 0))
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
                        words = emphasize(st["prompt"], how["missing"]) if how.get("mask") == "wear" and how.get("missing") else st["prompt"]
                        say(f"崩れた所の囲みの中だけを直しています（強さ {strength}）: " + "、".join(s.get("flaws", [])[:3]))
                        tell(words)
                        raw = painter.redraw(words, st["seed"] + 509 * (k + 1) + 31 * i + 7 * len(row["mends"]), cur, m, strength=strength)
                        if how.get("mask") == "wear":
                            raw = keep_tone(raw, cur, "服・髪・持ち物", m)
                        tried = _inside(raw, cur, m)
                        dd = diff(cur, tried, m)
                        s.update({"strength": strength, "diff": dd["mean"], "outside": dd["outside"], "inside": dd["inside"],
                                  "words": [words], "changed": (dd["mean"] or 0) >= DIFF_MIN})
                        mrow = {"phase": NAMES[i], "mend": "赤ペン" if how.get("mask") == "pen" else k + 1, "item": item,
                                "strength": strength, "found": list(s.get("flaws", [])), "diff": dd["mean"], "outside": dd["outside"],
                                "inside": dd["inside"], "words": [words], "readable": True, "image": None, "changed": s["changed"],
                                "visit": visits[i], **({"pen": True} if how.get("mask") == "pen" else {})}
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
