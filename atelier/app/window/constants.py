"""道具の並び、赤ペンの印の取り方、欄の並びなどの決まった値"""
from __future__ import annotations

from PySide6.QtWidgets import QDockWidget
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]



# 左端の道具。None は区切り
TOOLS = (("move", "移動", "V"), ("select", "四角の選択", "M"), ("lasso", "投げなわの選択（なぞって囲む）", "L"),
         ("polygon", "多角形の選択（押して角を置き、ダブルクリックか Enter で閉じる）", "Shift+L"),
         ("autosel", "自動選択（押した所の物を AI が選ぶ。合わないときは四角で囲むと合いやすい）", "A"), (None, "", ""),
         ("pen", "ペン", "B"), ("eraser", "消しゴム", "E"), ("blur", "ぼかし", "R"),
         ("spray", "スプレー", "K"), ("smudge", "指先（色を伸ばす）", "W"), (None, "", ""),
         ("fill", "塗りつぶし", "G"), ("gradient", "グラデーション", "J"), (None, "", ""),
         ("line", "直線", "N"), ("rect", "四角", "U"), ("ellipse", "楕円", "O"),
         ("polyshape", "多角形", "Shift+U"), ("regpoly", "正多角形", "Shift+O"), ("text", "文字", "Y"), (None, "", ""),
         ("eyedropper", "スポイト", "I"), ("hand", "手のひら", "H"), ("zoom", "拡大（Shift か右クリックで縮小）", "Z"), (None, "", ""),
         ("redpen", "赤ペン（AI に直す所を囲む）", "T"))

# 図形の道具の説明（ツールチップ）。Shift の働きは押してみないと分からないので、ここに書く
SHAPE_TIPS = {
    "line": "直線（N）。押した所から離した所まで引きます。Shift で 15 度ごとの向きにそろえます。定規を出していれば定規に沿います",
    "rect": "四角（U）。ドラッグした範囲に描きます。Shift で正方形にします",
    "ellipse": "楕円（O）。ドラッグした範囲に描きます。Shift で正円にします",
    "polyshape": "多角形（Shift+U）。押すたびに角を置き、ダブルクリックか Enter か始めの角を押すと閉じて描きます。Shift で辺を 15 度ごとの向きにそろえます。Esc でやめます",
    "regpoly": "正多角形（Shift+O）。真ん中から角へドラッグします。辺の数は上の帯で変えます。Shift で向きを 15 度ごとにそろえます",
}

# 欄の帯とメニューに並べる順（よく使う順）
# 赤ペンの印の右クリックに出す加工（印の囲み 1 つに本物の経路で掛けて、囲みの外 0 画素・囲みの中が変わる・目の色の差 1.5 以下だった物。
# 表は docs/knowledge/function-check.md の「赤ペンの印の右クリック」、測り方は test_function_check.MarkMenuCheck）
MARK_OK = frozenset(("fin:retouch", "fin:clean", "fin:retouch_full", "fin:face", "fin:around", "combo:tidy_color",
                     "fin:detail", "fin:mat_gem", "fin:air_haze",
                     # 線画とドット絵は目の色を変えるのが仕事なので、目の色では外さない（囲みの外 0 画素は確かめた）
                     "app:lineart", "app:pixel"))
# 赤ペンの印の取り方（帯・右クリック・道具の設定で選ぶ）
REDPEN_SHAPES = (("free", "手で描く", "なぞって囲んだ所を印にします"), ("ellipse", "丸", "引いた丸の中を印にします"),
                 ("rect", "四角", "引いた四角の中を印にします"),
                 ("auto", "自動選択", "押した所の物（髪・顔・服・持ち物・背景）を AI が選んで印にします。四角で囲んでもよい"))
PANEL_ORDER = ("talk", "chat", "view", "history", "library", "progress", "layers", "color", "brushes")

# 欄は動かせて、外に出せて、閉じられる（作画ソフトと同じ）
PANEL = QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
