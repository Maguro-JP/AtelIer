"""その場で調べて検品する形。題材ごとの検品の表（subject_check）に無い題材（知らない機材、特定の建物）のときに使う。

1. 思考の模型（atelier.ai.thinker.research）が、何を確かめれば正しいかを調べる。まず言葉の模型の知識、足りなければ
   利用者にその場で外へ取りに行く許しを聞き（ask_web）、許されたときだけ参考の説明を取る（fetch）
2. 確かめる項目を決まった形 {"name", "kind": count|shape|ratio|order, "expect"} で受け取る
3. 測れる項目（数・比）はその場で測り、測る道具の無い項目は「測れなかった」として残す（崩れが無いとは返さない）
調べた項目は利用者の置き場に題材ごとに覚え、次からは調べずに使う。覚えるのは確かめる項目だけで、絵も、描く言葉も、
絵の方向を寄せる重みも覚えない（決まり: 実在の物は想像で作らず、先に調べて寸法と形を確かめてから描く）。
思考の模型の部品は別に作っている。呼び出しの形は research(subject, model, ask_web, fetch) -> {subject, checklist, source, note}
で、部品が無い版では空の項目を返す。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

KINDS = ("count", "shape", "ratio", "order")
RATIO_TOLERANCE = 0.25   # 比の項目の許す幅（期待の比に対する割合。私の推測）
# 数の項目の名前から、測る道具を選ぶ語。当たらなければ測れない
COUNT_TOOLS = {"wheel": "wheels", "tire": "wheels", "車輪": "wheels", "タイヤ": "wheels",
               "window": "blobs", "窓": "blobs", "item": "blobs", "個": "blobs", "body": "blobs", "本体": "blobs"}


def _store() -> Path:
    from atelier.files.paths import data_home
    return Path(data_home()) / "qc" / "subject_checks.json"


def _key(subject: str) -> str:
    return re.sub(r"\s+", " ", str(subject).strip().lower())


def load(path: Path | None = None) -> dict:
    p = path or _store()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def valid(item) -> bool:
    """決まった形に合う項目か。thinker.parse_checklist と同じ幅（数は 0〜100 の整数、比は 0 より大きく 100 以下）"""
    if not isinstance(item, dict) or item.get("kind") not in KINDS or not str(item.get("name", "")).strip():
        return False
    e = item.get("expect")
    k = item["kind"]
    if k == "count":
        return isinstance(e, int) and not isinstance(e, bool) and 0 <= e <= 100
    if k == "ratio":
        return isinstance(e, (int, float)) and not isinstance(e, bool) and 0 < float(e) <= 100
    if k == "shape":
        return isinstance(e, str) and bool(e.strip())
    return isinstance(e, list) and len(e) >= 2 and all(isinstance(x, str) for x in e)


def remember(subject: str, checklist, source: str, path: Path | None = None) -> list[dict]:
    """確かめる項目だけを題材ごとに覚える。形に合わない項目は捨てる。覚えた項目を返す"""
    items = [{"name": str(i["name"]).strip(), "kind": i["kind"], "expect": i["expect"]} for i in checklist or [] if valid(i)]
    if not items:
        return []
    p = path or _store()
    table = load(p)
    table[_key(subject)] = {"checklist": items, "source": source}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def _thinker_research():
    try:
        from atelier.ai import thinker
    except Exception:   # noqa: BLE001  思考の模型の部品がまだ無い版
        return None
    return getattr(thinker, "research", None)


def checklist_for(subject: str, research=None, ask_web=None, fetch=None, path: Path | None = None) -> dict:
    """題材の確かめる項目。覚えた物があれば調べずに使い、無ければ思考の模型で調べて覚える。
    返す欄: subject・checklist・source（remembered / words_model / web / none）・note"""
    key = _key(subject)
    got = load(path).get(key)
    if got and got.get("checklist"):
        return {"subject": subject, "checklist": got["checklist"], "source": "remembered", "note": ""}
    fn = research or _thinker_research()
    if fn is None:
        return {"subject": subject, "checklist": [], "source": "none", "note": "思考の模型の部品がありません"}
    try:
        res = fn(subject, ask_web=ask_web, fetch=fetch)
    except Exception as e:   # noqa: BLE001  調べ物が落ちても描く流れを止めない
        return {"subject": subject, "checklist": [], "source": "none", "note": f"調べられませんでした（{type(e).__name__}）"}
    items = remember(subject, res.get("checklist"), res.get("source", "none"), path)
    return {"subject": subject, "checklist": items, "source": res.get("source", "none") if items else "none",
            "note": res.get("note", "")}


def _measure_count(image, tool: str):
    from atelier.qc import subject_check as sc
    if tool == "wheels":
        from atelier.ai import phase_tools as pt
        r = pt.tire_roundness(image)
        return (len(r["tires"]), "") if r.get("readable") else (None, "車輪が読めません")
    r = sc.count_blobs(image)
    return (r["count"], "") if r.get("readable") else (None, r.get("reason", "塊が読めません"))


def _aspect(image):
    import numpy as np
    from atelier.ai import phase_tools as pt
    m = pt.silhouette(image)
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return None
    return (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)


def evaluate(image, checklist) -> dict:
    """確かめる項目で検品する。数は名前の語から道具を選んで数え、比は主役の幅と高さの比で測る。
    形・並びと、道具の無い数は unreadable に残す。返す欄: flaws・unreadable・numbers"""
    flaws, unreadable, numbers = [], [], {}
    for it in checklist or []:
        name, k, e = it["name"], it["kind"], it["expect"]
        if k == "count":
            low = name.lower()
            tool = next((t for w, t in COUNT_TOOLS.items() if w in low), None)
            if tool is None:
                unreadable.append(f"{name}: 数える道具がありません")
                continue
            n, why = _measure_count(image, tool)
            if n is None:
                unreadable.append(f"{name}: {why}")
                continue
            numbers[name] = n
            if n != e:
                flaws.append(f"調べた項目: {name}の数が違う（{n}、調べた数は {e}）")
        elif k == "ratio" and any(w in name.lower() for w in ("width", "aspect", "幅", "縦横")):
            r = _aspect(image)
            if r is None:
                unreadable.append(f"{name}: 主役が読めません")
                continue
            numbers[name] = round(float(r), 3)
            if abs(r - float(e)) > RATIO_TOLERANCE * float(e):
                flaws.append(f"調べた項目: {name}の比が違う（{r:.2f}、調べた比は {e}）")
        else:
            unreadable.append(f"{name}: {k} を測る道具がありません")
    return {"flaws": flaws, "unreadable": unreadable, "numbers": numbers}


def check(image, prompt: str, subject: str | None = None, research=None, ask_web=None, fetch=None, path=None) -> dict:
    """題材が検品の表に無いとき（subject_check.kind が unknown か、subject を明示したとき）、調べて検品する"""
    from atelier.qc import subject_check as sc
    if subject is None:
        if sc.kind(prompt) != "unknown":
            return {"used": False, "flaws": [], "unreadable": [], "numbers": {}, "checklist": [], "source": "table"}
        subject = prompt
    got = checklist_for(subject, research=research, ask_web=ask_web, fetch=fetch, path=path)
    res = evaluate(image, got["checklist"]) if got["checklist"] else {
        "flaws": [], "unreadable": [f"確かめる項目が作れません（{got['note'] or '答えがありません'}）"], "numbers": {}}
    return {"used": True, **res, "checklist": got["checklist"], "source": got["source"]}
