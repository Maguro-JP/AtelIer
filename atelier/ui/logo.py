"""ロゴ「AtelIer」（読みはアトリエ）。A と I（AI）だけを大文字の差し色にして強調する。"""
from __future__ import annotations

from pathlib import Path

NAME = "AtelIer"
ACCENT_LETTERS = ("A", "I")   # 差し色にする字
ASSETS = Path(__file__).resolve().parents[1] / "assets"
LOGO_SVG = ASSETS / "logo.svg"
ICON_SVG = ASSETS / "icon.svg"


def wordmark_html(accent: str, text: str) -> str:
    """ロゴの文字を、色を付けた HTML にする（QLabel などに出す）。accent が AI の色、text がほかの字の色"""
    parts = []
    for ch in NAME:
        color = accent if ch in ACCENT_LETTERS else text
        parts.append(f'<span style="color:{color}">{ch}</span>')
    return '<span style="font-weight:700">' + "".join(parts) + "</span>"
