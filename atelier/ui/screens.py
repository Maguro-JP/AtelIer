"""モニターの組を数える・窓を画面の中へ収める。Qt の画面を直接読まず、四角の一覧で受けるので、
1 台しか無い試験の環境でも、台数と大きさを変えて確かめられる。
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize


def signature(rects: list[QRect]) -> str:
    """モニターの組の名前。並び（左から）と大きさで決める。同じ組なら同じ名前になり、配置を組ごとに分けて残せる"""
    rs = sorted(rects, key=lambda r: (r.x(), r.y()))
    return f"{len(rs)} 台 " + " + ".join(f"{r.width()}×{r.height()}" for r in rs)


def fit_into(rect: QRect, screens: list[QRect]) -> QRect:
    """rect を、いちばん多く重なっている画面の中へ収める。どの画面とも重ならなければ最初の画面（主の画面）へ。
    主の窓の画面だけで収めると、2 台目のモニターに置いた窓まで 1 台目へ引き戻した"""
    if not screens:
        return QRect(rect)
    best = max(screens, key=lambda s: _overlap(rect, s))
    if _overlap(rect, best) == 0:
        best = screens[0]
    w = min(max(rect.width(), 160), best.width())
    h = min(max(rect.height(), 80), best.height())
    x = min(max(rect.x(), best.left()), best.left() + best.width() - w)
    y = min(max(rect.y(), best.top()), best.top() + best.height() - h)
    return QRect(x, y, w, h)


def _overlap(a: QRect, b: QRect) -> int:
    i = a.intersected(b)
    return 0 if i.isEmpty() else i.width() * i.height()


def cascade(area: QRect, sizes: list[QSize], step: int = 36) -> list[QRect]:
    """窓を左上から右へ並べ、はみ出したら次の段へ。画面の外へ出さない"""
    out, x, y, row = [], area.left() + 20, area.top() + 20, 0
    for s in sizes:
        w, h = min(s.width(), area.width() - 40), min(s.height(), area.height() - 40)
        if x + w > area.right() - 20 and x > area.left() + 20:
            x, y = area.left() + 20, y + row + step
            row = 0
        if y + h > area.bottom() - 20:
            y = area.top() + 20 + (len(out) % 8) * step   # 段が尽きたら少しずつずらして重ねる
        out.append(fit_into(QRect(x, y, w, h), [area]))
        x += w + 12
        row = max(row, h)
    return out
