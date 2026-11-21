"""ブラシの欄。種類を選び、硬さ・流量・間隔・筆圧の効き方・手ぶれ補正・対称・定規を変える。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QListWidget, QSlider, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)

from atelier.paint.canvas import STABILIZER_MAX, SYMMETRY
from atelier.paint.drawing_assist import RULERS
from atelier.panels.brush_preview import BrushPreview


class BrushPanel(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.brush_list = QListWidget()
        for b in canvas.brushes.values():
            self.brush_list.addItem(b.name)
        self.brush_list.currentTextChanged.connect(self.select_brush)

        self.hardness = self._slider(0, 100, "縁のくっきりさ")
        self.flow = self._slider(1, 100, "1 回に置く絵の具の量")
        self.spacing = self._slider(2, 100, "筆の跡の間隔")
        self.size_pressure = QCheckBox("筆圧→太さ")
        self.size_pressure.setToolTip("ペンタブレットの筆圧で線の太さを変える")
        self.opacity_pressure = QCheckBox("筆圧→濃さ")
        self.opacity_pressure.setToolTip("ペンタブレットの筆圧で線の濃さを変える")
        self.hardness.valueChanged.connect(lambda v: setattr(canvas.brush, "hardness", v / 100))
        self.flow.valueChanged.connect(lambda v: setattr(canvas.brush, "flow", v / 100))
        self.spacing.valueChanged.connect(lambda v: setattr(canvas.brush, "spacing", v / 100))
        self.size_pressure.toggled.connect(lambda on: setattr(canvas.brush, "size_pressure", on))
        self.opacity_pressure.toggled.connect(lambda on: setattr(canvas.brush, "opacity_pressure", on))

        # 手ぶれ補正と対称は、ペン・消しゴム・ぼかし・スプレー・指先のなぞる道具すべてに効く
        self.stabilizer = QSpinBox()
        self.stabilizer.setRange(0, STABILIZER_MAX)
        self.stabilizer.setSingleStep(5)
        self.stabilizer.setToolTip(f"手ぶれ補正の強さ（0〜{STABILIZER_MAX}）。大きいほど線がカーソルに遅れてついてきて、"
                                   "なめらかになる（0 で切る）")
        self.stabilizer.valueChanged.connect(lambda v: setattr(canvas, "stabilizer", v))
        self.symmetry = self._choice(SYMMETRY, "描いた線と図形を、軸の反対側にも同時に描きます。軸の丸をドラッグすると軸を動かせます")
        self.symmetry.currentIndexChanged.connect(lambda _i: canvas.set_symmetry(self.symmetry.currentData()))
        self.ruler = self._choice(RULERS, "なぞる線と直線を定規に沿わせます。緑の丸をドラッグすると、中心・消失点・平行線の向きを動かせます")
        self.ruler.currentIndexChanged.connect(lambda _i: canvas.set_ruler(self.ruler.currentData()))
        self.quickshape = QCheckBox("描いて止めると形を整える")
        self.quickshape.setToolTip("ペンで描き終えて少し止めると、直線・円・楕円・四角・三角に整えます。元に戻すで整える前の線に戻ります")
        self.quickshape.toggled.connect(lambda on: setattr(canvas, "quickshape", on))

        form = QFormLayout()
        form.addRow("硬さ", self.hardness)
        form.addRow("流量", self.flow)
        form.addRow("間隔", self.spacing)
        form.addRow(self.size_pressure)
        form.addRow(self.opacity_pressure)
        form.addRow("手ぶれ補正", self.stabilizer)
        form.addRow("対称", self.symmetry)
        form.addRow("定規", self.ruler)
        form.addRow(self.quickshape)
        settings = QWidget()
        settings.setLayout(form)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.brush_list, "ブラシ")
        self.tabs.addTab(settings, "設定")

        # 見本の線。ブラシと設定を変えるたびに描き直す（色・太さ・濃さは窓がつなぐ）
        self.preview = BrushPreview(canvas)
        for signal in (self.hardness.valueChanged, self.flow.valueChanged, self.spacing.valueChanged,
                       self.size_pressure.toggled, self.opacity_pressure.toggled, self.brush_list.currentTextChanged,
                       canvas.brush_changed, canvas.color_picked):
            signal.connect(lambda *_a: self.preview.update())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)
        lay.addWidget(self.preview)
        lay.addWidget(self.tabs, 1)
        self.brush_list.setCurrentRow(0)

    @staticmethod
    def _slider(low: int, high: int, tip: str) -> QSlider:
        s = QSlider(Qt.Horizontal)
        s.setRange(low, high)
        s.setToolTip(tip)
        return s

    @staticmethod
    def _choice(items: dict[str, str], tip: str) -> QComboBox:
        box = QComboBox()
        box.addItem("なし", "")
        for key, label in items.items():
            box.addItem(label, key)
        box.setToolTip(tip)
        return box

    def select_brush(self, name: str):
        """ブラシを替え、そのブラシの設定を欄に出す"""
        if name not in self.canvas.brushes:
            return
        self.canvas.set_brush(name)
        b = self.canvas.brush
        for w, v in ((self.hardness, b.hardness), (self.flow, b.flow), (self.spacing, b.spacing)):
            w.blockSignals(True)
            w.setValue(int(v * 100))
            w.blockSignals(False)
        for w, v in ((self.size_pressure, b.size_pressure), (self.opacity_pressure, b.opacity_pressure)):
            w.blockSignals(True)
            w.setChecked(v)
            w.blockSignals(False)
