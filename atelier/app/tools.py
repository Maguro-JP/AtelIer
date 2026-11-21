"""道具の帯に並べる道具と、その説明。"""
from __future__ import annotations

from PySide6.QtWidgets import QDockWidget

# (鍵, 名前, キー)。鍵が None の行は区切り。キーは作画ソフトでよく使う並びに合わせる
TOOLS = (("move", "移動", "V"), ("select", "四角の選択", "M"), ("lasso", "投げなわの選択（なぞって囲む）", "L"),
         ("polygon", "多角形の選択（押して角を置き、ダブルクリックか Enter で閉じる）", "Shift+L"), (None, "", ""),
         ("pen", "ペン", "B"), ("eraser", "消しゴム", "E"), ("blur", "ぼかし", "R"),
         ("spray", "スプレー", "K"), ("smudge", "指先（色を伸ばす）", "W"), (None, "", ""),
         ("fill", "塗りつぶし", "G"), ("gradient", "グラデーション", "J"), (None, "", ""),
         ("line", "直線", "N"), ("rect", "四角", "U"), ("ellipse", "楕円", "O"),
         ("polyshape", "多角形", "Shift+U"), ("regpoly", "正多角形", "Shift+O"), ("text", "文字", "Y"), (None, "", ""),
         ("eyedropper", "スポイト", "I"), ("hand", "手のひら", "H"), ("zoom", "拡大（Shift か右クリックで縮小）", "Z"))

# 図形の道具の説明（ツールチップ）。Shift の働きは押してみないと分からないので、ここに書く
SHAPE_TIPS = {
    "line": "直線（N）。押した所から離した所まで引きます。Shift で 15 度ごとの向きにそろえます。定規を出していれば定規に沿います",
    "rect": "四角（U）。ドラッグした範囲に描きます。Shift で正方形にします",
    "ellipse": "楕円（O）。ドラッグした範囲に描きます。Shift で正円にします",
    "polyshape": "多角形（Shift+U）。押すたびに角を置き、ダブルクリックか Enter か始めの角を押すと閉じて描きます。"
                 "Shift で辺を 15 度ごとの向きにそろえます。Esc でやめます",
    "regpoly": "正多角形（Shift+O）。真ん中から角へドラッグします。辺の数は上の帯で変えます。Shift で向きを 15 度ごとにそろえます",
}
FILLABLE = ("rect", "ellipse", "polyshape", "regpoly")   # 中まで塗れる図形

# 欄は動かせて、外に出せて、閉じられる（作画ソフトと同じ）
PANEL = QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable


def tool_label(key: str) -> str:
    return next(label for k, label, _s in TOOLS if k == key)
