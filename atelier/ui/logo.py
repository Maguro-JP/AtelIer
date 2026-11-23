"""ロゴ「AtelIer」（読みはアトリエ）。A と I（AI）だけを大文字の差し色にして強調する。"""
from __future__ import annotations

from pathlib import Path

NAME = "AtelIer"
ACCENT_LETTERS = ("A", "I")   # 差し色にする字
ASSETS = Path(__file__).resolve().parents[1] / "assets"
LOGO_SVG = ASSETS / "logo.svg"
ICON_SVG = ASSETS / "icon.svg"
# ロゴの字は、I に横棒（セリフ）のある書体で組む。横棒の無い書体では大文字の I が小文字の l に見え、
# 「Ateller」と読めてしまったため。上から順に、Windows・macOS・Linux にある物を選ぶ
SERIF_FAMILIES = ("Georgia", "Times New Roman", "DejaVu Serif", "Liberation Serif", "FreeSerif", "serif")


def wordmark_html(accent: str, text: str) -> str:
    """ロゴの文字を、色を付けた HTML にする（QLabel などに出す）。accent が AI の色、text がほかの字の色"""
    parts = []
    for ch in NAME:
        color = accent if ch in ACCENT_LETTERS else text
        parts.append(f'<span style="color:{color}">{ch}</span>')
    families = ", ".join(f"'{f}'" if f != "serif" else f for f in SERIF_FAMILIES)
    return f'<span style="font-weight:700; font-family:{families}">' + "".join(parts) + "</span>"


def wordmark_font(px: float):
    """ロゴの字を QPainter で描くときの書体（wordmark_html と同じ、I に横棒のある書体）"""
    from PySide6.QtGui import QFont
    f = QFont()
    f.setFamilies(list(SERIF_FAMILIES))
    f.setStyleHint(QFont.Serif)
    f.setBold(True)
    f.setPixelSize(max(8, int(px)))
    return f
