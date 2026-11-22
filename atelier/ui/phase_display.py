"""精度優先の工程を、利用者に見せる番号と名前に直す。

工程の中には何も描かない工程（目的: 頼みの言葉を数えるだけ）がある。そのまま「工程 1「目的」」と出すと、
利用者には何をしているのか分からず、描く工程の番号も 1 つずれて見えた。
描く流れ（atelier/ai/phases.py）は変えずに、見せる側（進みの欄・ポップアップ・会話・レイヤーの名前）でここを通し、
描く工程だけを 1 から数える。N も描く工程の数にする。
"""
from __future__ import annotations

import re

from atelier.ai.phases import NAMES

HIDDEN = ("目的",)   # 描かない工程。利用者に見せる番号と名前から外す
SHOWN = [n for n in NAMES if n not in HIDDEN]
_PHASE = re.compile(r"工程 (\d+)/(\d+)「([^」]+)」")


def hidden(name: str) -> bool:
    """name は工程の名前か、計画の工程の名前（「体の形／確かめる 骨組みの比」）"""
    return name.split("／")[0] in HIDDEN


def number(i: int, name: str) -> int | None:
    """描く流れの工程の番号 i（1 から）を、見せる番号にする。描かない工程は None"""
    if hidden(name):
        return None
    return max(1, i - sum(1 for n in NAMES[:max(0, i - 1)] if n in HIDDEN))


def total(n: int) -> int:
    """要る工程の数 n を、描く工程の数にする"""
    return max(1, n - len(HIDDEN))


def relabel(msg: str) -> str | None:
    """描かない工程の知らせは None（出さない）。計画（atelier/ai/phase_plan.py）の「工程 i/n」と「要る工程 a→b」は、
    描く流れが描かない工程を外して数えてあるので、番号は直さない（直すと 2 度引いてずれる）"""
    m = _PHASE.search(msg or "")
    if m and hidden(m.group(3)):
        return None
    return msg


def drawn(rows: list[dict]) -> list[dict]:
    """工程ごとの結果から、描かない工程を外す（レイヤーの名前と会話の番号をそろえる）"""
    return [r for r in rows if not hidden(r.get("phase", ""))]
