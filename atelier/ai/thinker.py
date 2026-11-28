"""考える役: 思考の模型（言葉の模型）が、工程と直しの手順を考え、「AI の補完の指示」として描く模型に渡す。

描く模型は、頼みの言葉から絵を出すだけで、どこが崩れたかも、何で埋めればよいかも考えない。
そこで、検品の結果（崩れの場所と種類、描かれていない物、部位）を思考の模型に渡し、
直しの手順（囲む所、直し方、補完の言葉、強さ）を決まった形（JSON）で答えさせる。

利用者の指示（頼みの言葉）と AI の補完の指示は別の物として持つ。
- 補完の言葉は、その工程の、その囲みの中の描き直しにだけ足す。頼みの言葉・描くワード・履歴には足さない
- 補完は頼みと食い違ってはいけない。頼みに無い人物・動物、頼みと違う場所、打ち消した物を含む語は捨てる（check_words）
- 思考の模型が無い・答えない・形に合わない答えを返したときは、決まった手順（rules）が代わりを務める
- 思考の模型は間違える前提で扱う。答えは形・値の幅・頼みとの照らし合わせを通った物だけを使う
- 役目は間違いの直しだけ。直す間違い（検品の崩れ、描かれていない物）が 1 つも紐づかない補完は出さない。
  頼みに書いてある物（空の色、時間、天気）を変える語、頼みに無い好み（雰囲気、画風、光の演出）の語は捨てる
- 何も覚えない。答えや結果を次の既定・手本・言葉に積み上げず、同じ絵に寄せない。決まりは間違いの見つけ方と直し方だけ
"""
from __future__ import annotations

import json
import re

HOWS = ("erase_redraw", "move", "rotate", "paste", "none")   # 直し方: 消して描く、移す、回す、切って貼る、直さない
AREAS = ("regions", "background", "person", "shape", "whole")   # 囲む所: 検品の枠、背景、人物、崩れの形、絵の全体
STRENGTH = (0.2, 0.85)   # 強さの幅。これより弱いと変わらず、強いと物が変わった（phases の MEND・FIXES の幅に合わせた。私の推測）
MOST_WORDS = 8           # 補完の言葉の数の上限。多いと頼みの言葉が埋もれる（私の推測）

# 場所ごとに、その場所に当たり前にある物の言葉。頼みにその場所があるときだけ、補完に使ってよい
SCENE = {
    "school": ["school building", "windows"], "学校": ["school building", "windows"],
    "classroom": ["classroom", "desks", "chalkboard", "windows"], "教室": ["classroom", "desks", "chalkboard", "windows"],
    "sky": ["sky"], "空": ["sky"],
    "sunset": ["sunset", "orange sky"], "夕日": ["sunset", "orange sky"],
    "夕暮れ": ["sunset", "orange sky"], "evening": ["evening", "orange sky"],
    "station": ["train station", "platform", "railway tracks"], "駅": ["train station", "platform", "railway tracks"],
    "platform": ["platform", "railway tracks"], "ホーム": ["platform", "railway tracks"],
    "shrine": ["shrine", "torii", "stone path", "lanterns"], "神社": ["shrine", "torii", "stone path", "lanterns"],
    "参道": ["stone path", "torii"], "torii": ["torii"],
    "sea": ["sea", "waves", "horizon"], "海": ["sea", "waves", "horizon"], "ocean": ["ocean", "waves", "horizon"],
    "beach": ["beach", "sand", "waves"], "海辺": ["beach", "sea", "waves"],
    "town": ["town", "houses", "rooftops"], "町": ["town", "houses", "rooftops"], "街": ["city", "buildings", "street"],
    "city": ["city", "buildings", "street"], "street": ["street", "road"], "道": ["path", "road"],
    "forest": ["forest", "trees", "foliage"], "森": ["forest", "trees", "foliage"],
    "path": ["path"], "小道": ["path", "dirt path"],
    "rain": ["rain", "wet ground", "puddles"], "雨": ["rain", "wet ground", "puddles"],
    "shopping street": ["shopping street", "shop signs", "storefronts"], "商店街": ["shopping street", "shop signs", "storefronts"],
    "room": ["room", "wall", "floor"], "部屋": ["room", "wall", "floor"], "indoors": ["indoors", "wall", "floor"],
    "park": ["park", "trees", "grass"], "公園": ["park", "trees", "grass"],
    "mountain": ["mountain", "sky"], "山": ["mountain", "sky"], "river": ["river", "water"], "川": ["river", "water"],
    "night": ["night", "night sky"], "夜": ["night", "night sky"],
}
# 部位や崩れの種類ごとに、形を正す言葉。頼みの中身を変えない（物を足さない）言葉だけを置く
PART = {
    "hand": ["correct hand", "five fingers"], "foot": ["correct foot"], "face": ["correct face", "symmetrical eyes"],
    "eyes": ["detailed eyes", "eye highlights"], "hair": ["neat hair strands"], "wear": ["clean clothing folds"],
    "line": ["clean lines"], "light": [], "shadow": [], "color": ["clean coloring"],
    "detail": ["fine details"], "perspective": ["correct perspective"], "background": [],
}
NEUTRAL = {w for ws in PART.values() for w in ws}   # 雰囲気・画風・光の演出の語（high quality、warm light など）は置かない

# 頼みに書いてある物を変えないための組。同じ組の別の語が頼みにあれば、その語は捨てる（青空の頼みに夕焼けを足さない）
CLASH = [
    {"sunset", "orange sky", "evening", "dusk", "night", "night sky", "day", "daytime", "noon", "morning", "blue sky",
     "starry sky", "dawn", "sunrise", "夕暮れ", "夕日", "夜", "昼", "朝", "青空"},
    {"rain", "wet ground", "puddles", "sunny", "snow", "snowing", "clear sky", "cloudy sky", "overcast", "fog"},
]

PERSON = ("girl", "boy", "woman", "man", "person", "people", "child", "children", "kid", "lady", "male", "female",
          "1girl", "1boy", "2girls", "2boys", "multiple", "crowd", "couple", "人", "少女", "少年", "女性", "男性", "子ども")
ANIMAL = ("dog", "cat", "bird", "horse", "fox", "animal", "犬", "猫", "鳥", "馬", "動物")
PLACES = tuple(SCENE) + ("cafe", "kitchen", "bedroom", "castle", "village", "desert", "snow", "cave", "space",
                         "underwater", "airport", "bridge", "island", "field", "garden", "lake")


def _tags(text) -> list[str]:
    return [t.strip().lower() for t in re.split(r"[,、\n]", str(text)) if t.strip()]


def _has(low: str, word: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(word) + r"s?(?![a-z])", low) is not None


def places(prompt) -> list[str]:
    """頼みにある場所の語（SCENE の鍵）。長い語を先に見る（「shopping street」を「street」より先に）"""
    low = " " + str(prompt).lower() + " "
    out = []
    for k in sorted(SCENE, key=len, reverse=True):
        if _has(low, k.lower()) and not any(k in o for o in out):
            out.append(k)
    return out


def allowed(prompt) -> set[str]:
    """補完に使ってよい言葉: 頼みのタグ、頼みの場所に当たり前にある物、形を正す言葉"""
    ok = set(_tags(prompt)) | NEUTRAL
    for p in places(prompt):
        ok |= set(SCENE[p])
    return ok


def check_words(words, prompt, negative=()) -> tuple[list[str], list[str]]:
    """補完の言葉を頼みと照らす。(使う語, 捨てた語と理由)。
    捨てるのは、頼みに無い人物・動物（新しい人物）、頼みに無い場所（違う場所）、打ち消した物、許す語の表に無い語（頼んでいない物）"""
    low_prompt = str(prompt).lower()
    neg = [n.strip().lower() for n in negative if str(n).strip()]
    ok = allowed(prompt)
    keep, drop = [], []
    asked = set(_tags(prompt))
    for w in _tags(words):
        clash = next((g for g in CLASH if w in g and (asked & g) and w not in asked), None)
        if clash:
            drop.append(f"{w}（頼みにある「{'、'.join(sorted(asked & clash))}」を変える）")
        elif any(_has(w, p) for p in PERSON + ANIMAL) and not any(_has(w, p) and _has(low_prompt, p) for p in PERSON + ANIMAL):
            drop.append(f"{w}（頼みに無い人物・動物）")
        elif any(_has(w, p.lower()) for p in PLACES) and not any(_has(w, p.lower()) and _has(low_prompt, p.lower()) for p in PLACES) \
                and w not in ok:
            drop.append(f"{w}（頼みと違う場所）")
        elif any(n and _has(w, n) for n in neg):
            drop.append(f"{w}（打ち消した物）")
        elif w not in ok:
            drop.append(f"{w}（頼んでいない物）")
        elif w not in keep:
            keep.append(w)
    return keep[:MOST_WORDS], drop


def _kind_of(item: str, regions) -> str:
    """直す項目と枠の種類から、PART の鍵を選ぶ"""
    types = [t for _b, t in (regions or [])]
    for t in ("hand", "foot", "face", "perspective"):
        if t in types:
            return t
    table = {"手": "hand", "足": "foot", "顔": "face", "目の光": "eyes", "頼んだ物": "wear", "線の強弱": "line",
             "線の途切れ": "line", "影": "shadow", "影の締まり": "shadow", "色の差": "color", "塗り残し": "color",
             "ディテール": "detail", "遠近の収束": "perspective", "背景": "background", "光": "light"}
    for k, v in table.items():
        if k in str(item):
            return v
    return ""


def rules(prompt, phase: str, item: str, flaws=(), missing=(), regions=()) -> dict:
    """思考の模型が無いときの決まった手順。描かれていない物・背景の崩れには頼みの場所の言葉、部位の崩れには形を正す言葉"""
    words: list[str] = []
    miss = [str(m).lower() for m in missing]
    scene = places(prompt)
    if item == "背景" or any(any(_has(m, p.lower()) for p in scene) for m in miss):
        area = "background"
        for p in scene:
            words += SCENE[p]
    else:
        area = "regions" if regions else "shape"
    words += [m for m in miss if m in _tags(prompt)]   # 描かれていない頼みの語は、補完ではなく頼みの語として強める
    words += PART.get(_kind_of(item, regions), [])
    keep, _drop = check_words(", ".join(words), prompt)
    return {"area": area, "how": "erase_redraw", "words": ", ".join(keep), "strength": None, "source": "rules"}


SYSTEM = ("You assist an image model that repairs one area of a picture. Reply with one JSON object only: "
          '{"area": one of ' + "|".join(AREAS) + ', "how": one of ' + "|".join(HOWS) +
          ', "words": "short english tags for what should appear inside the repaired area", "strength": 0.2-0.85}. '
          "Use only things the request already contains or that naturally belong to its place. "
          "Never add people, animals, places or objects the request does not contain.")


def ask_model(model, prompt, phase, item, flaws, missing, regions) -> str:
    """思考の模型に問う。model は engine.Words と同じ形（ask を持つ物）"""
    text = json.dumps({"request": str(prompt), "phase": phase, "item": item, "flaws": [str(f) for f in flaws][:6],
                       "missing": [str(m) for m in missing][:6],
                       "regions": [t for _b, t in (regions or [])][:6]}, ensure_ascii=False)
    return model.ask(SYSTEM, text, max_tokens=120, one_line=False)


def parse(reply: str) -> dict | None:
    """答えの JSON を取り出し、形と値の幅を確かめる。合わなければ None"""
    m = re.search(r"\{.*\}", str(reply), re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("area") not in AREAS or d.get("how") not in HOWS or not isinstance(d.get("words", ""), str):
        return None
    s = d.get("strength")
    if s is not None:
        if not isinstance(s, (int, float)) or not STRENGTH[0] <= float(s) <= STRENGTH[1]:
            return None
        s = float(s)
    return {"area": d["area"], "how": d["how"], "words": d.get("words", ""), "strength": s}


def _default_model():
    try:
        from atelier.ai.engine import Words
        w = Words()
        return w if w.ready() else None
    except Exception:   # 言葉の模型の部品が無い機械でも、決まった手順で進める
        return None


def complement(prompt, phase: str, item: str, flaws=(), missing=(), regions=(), negative=(), model="auto") -> dict:
    """直しの手順と AI の補完の指示を返す。
    返す欄: area・how・words（補完の言葉、頼みと照らし済み）・strength・source（thinker か rules）・dropped（捨てた語）・note"""
    if not list(flaws) and not list(missing):
        # 直す間違いが 1 つも無い所には、何も指示しない（好みを足して絵の向きを寄せない）
        return {"area": "", "how": "none", "words": "", "strength": None, "source": "none", "dropped": [],
                "note": "直す間違いが無いので、補完の指示はありません"}
    base = rules(prompt, phase, item, flaws, missing, regions)
    if model == "auto":
        model = _default_model()
    if model is None:
        return {**base, "dropped": [], "note": "思考の模型が無いので、決まった手順で決めました"}
    try:
        ans = parse(ask_model(model, prompt, phase, item, flaws, missing, regions))
    except Exception as e:   # 模型が落ちても描く流れを止めない
        return {**base, "dropped": [], "note": f"思考の模型が答えませんでした（{type(e).__name__}）"}
    if ans is None:
        return {**base, "dropped": [], "note": "思考の模型の答えが決まった形に合わないので捨てました"}
    keep, drop = check_words(ans["words"], prompt, negative)
    if drop and not keep:
        return {**base, "dropped": drop, "note": "思考の模型の言葉が頼みと食い違うので捨てました"}
    # 決まった手順の言葉（場所・部位）を土台にし、思考の模型の言葉は照らし合わせを通った物だけ足す
    words = list(dict.fromkeys(_tags(base["words"]) + keep))[:MOST_WORDS]
    return {"area": ans["area"], "how": ans["how"], "words": ", ".join(words), "strength": ans["strength"],
            "source": "thinker", "dropped": drop, "note": ""}


def merge(user_words: str, extra: str) -> str:
    """描く模型に渡す言葉。利用者の指示を主（先頭）に置き、補完は後ろに足す。利用者の言葉に既にある語は重ねない"""
    have = set(_tags(user_words))
    add = [w for w in _tags(extra) if w not in have]
    return f"{user_words}, {', '.join(add)}" if add and user_words else (user_words or ", ".join(add))
