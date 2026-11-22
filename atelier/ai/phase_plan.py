"""精度優先の計画（工程の並び）。描く工程・確かめる工程・直す工程・確かめ直す工程・聞く工程を 1 つの表で持つ。

前は 12 の工程のそれぞれが「描く → 測る → 崩れがあれば囲みの中を直す（手を替えて 3 回まで）→ 測り直す」を 1 つの塊で回し、
工程の数え方・表示・一時停止・止まって聞く所がこの塊に縛られていた（直しの途中で止めると、どこまで済んだかを別の旗で持っていた）。
ここでは工程を細かく分けて表に並べ、確かめる工程が崩れを見つけたら、その崩れを直す工程と、その項目だけを確かめ直す工程を表に差し込む。
今の工程・済んだ工程・残りがこの表 1 つで分かるので、一時停止と再開（表と位置を残す）、止まって聞く所（聞く工程）、
表示（「工程 i/N 名前」と要る工程の数）、記録（工程ごとの絵と差）が同じ表から出る。

工程の種類:
- draw: 描く工程。模型で描くか、処理で描き足す（線の強弱、影の 2 段目）。描かない工程（測るだけの工程）は表に置かない
- check: 確かめる工程。1 つの項目（人数、手、線の途切れなど。phase_items）を測る
- mend: 直す工程。崩れ 1 つにつき 1 つ（同じ囲みで直す崩れはまとめて 1 つ）。囲み・直し方・強さの段（k）を持つ
- recheck: 確かめ直す工程。直した項目だけを測り直す
- ask: 聞く工程。囲めない崩れと、手を替えて直しても消えない崩れを利用者に聞く
"""
from __future__ import annotations

from atelier.ai.phase_items import PHASE_ITEMS

KIND_WORDS = {"draw": "描く", "check": "確かめる", "mend": "直す", "recheck": "確かめ直す", "ask": "聞く"}
SEP = "／"   # 工程の名前と工程の中身の区切り（工程の名前「影 2 段」に空白があるので空白では区切らない）


def step(kind: str, phase: int, item: str = "", **more) -> dict:
    return {"kind": kind, "phase": phase, "item": item, "status": "todo", **more}


def phase_steps(phase: int, draws: bool, items=None) -> list[dict]:
    """1 つの工程の初めの並び。描く工程（描く工程だけ）と、確かめる項目ごとの確かめる工程"""
    out = [step("draw", phase)] if draws else []
    return out + [step("check", phase, it) for it in (items if items is not None else PHASE_ITEMS[phase])]


class Plan:
    """工程の並びと今の位置。steps は JSON に書ける dict の並び（一時停止で残し、再開で読み直す）"""

    def __init__(self, names: list[str], hidden=(), steps=None, pos: int = 0):
        self.names = list(names)
        self.hidden = tuple(hidden)
        self.steps: list[dict] = list(steps or [])
        self.pos = pos

    @classmethod
    def initial(cls, names, draws, hidden=(), start: int = 0):
        """draws(phase) は、その工程が描くか"""
        p = cls(names, hidden)
        for i in range(start, len(names)):
            p.steps += phase_steps(i, draws(i))
        return p

    # 位置
    def current(self) -> dict | None:
        return self.steps[self.pos] if self.pos < len(self.steps) else None

    def done(self) -> bool:
        return self.pos >= len(self.steps)

    def advance(self):
        self.pos += 1

    def next_phase(self) -> int | None:
        nxt = self.steps[self.pos + 1] if self.pos + 1 < len(self.steps) else None
        return None if nxt is None else nxt["phase"]

    # 名前と番号
    def label(self, s: dict) -> str:
        head = self.names[s["phase"]]
        if s["kind"] == "draw":
            return f"{head}{SEP}描く"
        return f"{head}{SEP}{KIND_WORDS[s['kind']]} {s.get('item', '')}".rstrip()

    def shown(self, s: dict) -> bool:
        """利用者に見せる工程か（描かない工程「目的」は見せない）"""
        return self.names[s["phase"]] not in self.hidden

    def number(self, pos: int | None = None) -> tuple[int, int]:
        """(見せる番号, 見せる工程の数)。見せない工程の番号は 0"""
        pos = self.pos if pos is None else pos
        shown = [k for k, s in enumerate(self.steps) if self.shown(s)]
        j = shown.index(pos) + 1 if pos in shown else 0
        return j, len(shown)

    def need(self) -> int:
        return self.number()[1]

    # 差し込み
    def insert(self, steps: list[dict], at: int | None = None) -> int:
        """今の工程のすぐあと（at があればそこ）に差し込む。差し込んだ数を返す"""
        at = self.pos + 1 if at is None else at
        self.steps[at:at] = steps
        return len(steps)

    def end_of_phase(self, phase: int) -> int:
        """今の位置から先で、その工程の最後の工程のあとの位置"""
        at = self.pos + 1
        k = self.pos + 1
        while k < len(self.steps) and self.steps[k]["phase"] == phase:
            k += 1
            at = k
        return at

    def pending(self, kind: str, phase: int, item: str) -> int | None:
        """今の位置から先に、同じ工程・同じ項目・同じ種類の工程が待っていればその位置"""
        for k in range(self.pos + 1, len(self.steps)):
            s = self.steps[k]
            if s["phase"] != phase:
                break
            if s["kind"] == kind and s.get("item") == item and s["status"] == "todo":
                return k
        return None

    def last_pending(self, kinds, phase: int, item: str) -> int | None:
        last = None
        for k in range(self.pos + 1, len(self.steps)):
            s = self.steps[k]
            if s["phase"] != phase:
                break
            if s["kind"] in kinds and s.get("item") == item and s["status"] == "todo":
                last = k
        return last

    def restart(self, phase: int, draws):
        """今の工程のあとの残りを捨て、phase の工程から先を初めの並びで積み直す（利用者が選んだ描き直し）"""
        for s in self.steps[self.pos + 1:]:
            s["status"] = "dropped"
        kept = self.steps[:self.pos + 1]
        dropped = self.steps[self.pos + 1:]
        self.steps = kept
        for i in range(phase, len(self.names)):
            self.steps += phase_steps(i, draws(i))
        return dropped

    def rows(self) -> list[dict]:
        """記録と窓に渡す表（番号・名前・種類・状態と、済んだ工程の結果）"""
        out = []
        for k, s in enumerate(self.steps):
            j, _n = self.number(k)
            row = {"no": j, "name": self.label(s), **{x: v for x, v in s.items() if x not in ("before_image",)}}
            out.append(row)
        return out

    def state(self) -> dict:
        return {"steps": self.steps, "pos": self.pos}

    @classmethod
    def load(cls, names, hidden, state: dict):
        return cls(names, hidden, state.get("steps"), int(state.get("pos", 0)))
