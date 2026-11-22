"""通知の出し方を、種類ごとに決める（スマホの通知の設定と同じく、一覧で種類ごとに選ぶ）。

前は知らせのポップアップが種類によって数秒で消えたり、進みのポップアップが × を押すまで残ったりして、
利用者が決められなかった。種類ごとに「出さない / 数秒で消す（秒を選ぶ）/ 押すまで残す」を設定に持つ。
エラーは見落とすと困るので既定で押すまで残し、ほかは数秒で消す。消えた知らせは進み具合の欄の「知らせ」に残る。
"""
from __future__ import annotations

OFF, AUTO, KEEP = "出さない", "数秒で消す", "押すまで残す"
CHOICES = (OFF, AUTO, KEEP)
# (種類, 設定の見出し, 既定の出し方, 既定の秒)。種類は Window.notify の kind と、進みのポップアップの終わり（done）
KINDS = (
    ("info", "知らせ", AUTO, 4),
    ("ok", "できた", AUTO, 4),
    ("warn", "注意・崩れ", AUTO, 6),
    ("error", "エラー", KEEP, 8),
    ("done", "描き終わり（進みのポップアップ）", AUTO, 6),
)


def default(kind: str) -> str:
    for k, _label, how, sec in KINDS:
        if k == kind:
            return f"{how}:{sec}"
    return f"{AUTO}:4"


def parse(value: str) -> tuple[str, int]:
    """設定の値「数秒で消す:4」を (出し方, 秒) にする。読めない値は数秒で消す・4 秒"""
    how, _, sec = str(value or "").partition(":")
    if how not in CHOICES:
        how = AUTO
    try:
        n = max(1, min(120, int(sec)))
    except ValueError:
        n = 4
    return how, n


def rule(settings, kind: str) -> tuple[str, int]:
    """設定から、この種類の (出し方, 秒) を読む。設定が無いとき（試験・設定の前）は既定"""
    kind = kind if any(k == kind for k, *_ in KINDS) else "info"
    try:
        return parse(settings.get(f"notice_{kind}"))
    except Exception:   # noqa: BLE001  設定が読めなくても知らせは出す
        return parse(default(kind))
