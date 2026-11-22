"""欄ごとのタッチ向けの見た目。指で押せるように、ボタン・欄の中の部品・帯のアイコンを大きくする。
アプリ全体の見た目は変えない（タッチモニターに置いた欄だけを大きくし、液タブの側は細かいままにするため）。
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QToolBar, QWidget

MIN = 44   # 指で押せる大きさの目安（ピクセル）
# 数の欄と文字の欄には当てない。高さを足すとテーマの枠と上下の矢印が消え、数字が読めなくなった
STYLE = (f"QPushButton, QComboBox {{ min-height: {MIN}px; }}"
         f" QPushButton {{ min-width: {MIN}px; }}"
         " QSlider { min-height: 36px; }"
         " QCheckBox::indicator, QRadioButton::indicator { width: 26px; height: 26px; }")


def is_on(w: QWidget) -> bool:
    return bool(w.property("touch"))


def apply(w: QWidget, on: bool):
    w.setProperty("touch", bool(on))
    body = w.widget() if hasattr(w, "widget") and callable(w.widget) else w
    if body is not None:
        body.setStyleSheet(STYLE if on else "")
    for bar in ([w] if isinstance(w, QToolBar) else []) + w.findChildren(QToolBar):
        if on and bar.property("touch_old_icon") is None:
            bar.setProperty("touch_old_icon", bar.iconSize())
        if on:
            bar.setIconSize(QSize(36, 36))
        elif bar.property("touch_old_icon") is not None:
            bar.setIconSize(bar.property("touch_old_icon"))
            bar.setProperty("touch_old_icon", None)
