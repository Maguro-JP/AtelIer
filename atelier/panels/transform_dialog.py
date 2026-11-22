"""自由変形の窓。拡大・縮小、回転、反転、ゆがみを数で決め、絵の上で見ながら確定か取り消しを選ぶ。

値を変えるたびにキャンバスに見え方を出し、「確定」で 1 回の操作として履歴に入れる。
「取り消し」と Esc は、絵と選択範囲を変形の前に戻す（途中の見え方を履歴に残さないため）。
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QVBoxLayout)


class TransformDialog(QDialog):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setWindowTitle("自由変形")
        form = QFormLayout()
        self.boxes = {}
        for key, label, lo, hi, val, step, suffix, tip in (
                ("scale_x", "横の大きさ", 1, 1000, 100, 5, " %", "横の拡大・縮小"),
                ("scale_y", "縦の大きさ", 1, 1000, 100, 5, " %", "縦の拡大・縮小"),
                ("angle", "回転", -360, 360, 0, 5, " 度", "右回りが正"),
                ("shear_x", "横のゆがみ", -200, 200, 0, 5, " %", "上を右へ、下を左へずらす"),
                ("shear_y", "縦のゆがみ", -200, 200, 0, 5, " %", "右を下へ、左を上へずらす")):
            b = QDoubleSpinBox()
            b.setRange(lo, hi)
            b.setValue(val)
            b.setSingleStep(step)
            b.setSuffix(suffix)
            b.setToolTip(tip)
            b.valueChanged.connect(self.preview)
            form.addRow(label, b)
            self.boxes[key] = b
        self.keep = QCheckBox("縦横の比を保つ")
        self.keep.setChecked(True)
        self.keep.setToolTip("横の大きさを変えると、縦も同じ割合にします")
        self.boxes["scale_x"].valueChanged.connect(self._follow)
        form.addRow(self.keep)
        flips = QHBoxLayout()
        self.flip_h = QCheckBox("左右反転")
        self.flip_v = QCheckBox("上下反転")
        for b in (self.flip_h, self.flip_v):
            b.toggled.connect(self.preview)
            flips.addWidget(b)
        form.addRow(flips)
        buttons = QDialogButtonBox()
        ok = buttons.addButton("確定", QDialogButtonBox.AcceptRole)
        ok.setToolTip("変形を絵に決めます（Enter。元に戻すで戻せます）")
        no = buttons.addButton("取り消し", QDialogButtonBox.RejectRole)
        no.setToolTip("変形の前に戻します（Esc）")
        ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _follow(self, v):
        if self.keep.isChecked():
            self.boxes["scale_y"].setValue(v)

    def params(self) -> dict:
        b = self.boxes
        return {"scale_x": b["scale_x"].value() / 100, "scale_y": b["scale_y"].value() / 100, "angle": b["angle"].value(),
                "shear_x": b["shear_x"].value() / 100, "shear_y": b["shear_y"].value() / 100,
                "flip_h": self.flip_h.isChecked(), "flip_v": self.flip_v.isChecked()}

    def preview(self, *_a):
        self.canvas.set_transform(**self.params())

    def accept(self):
        self.preview()
        self.canvas.commit_transform()
        super().accept()

    def reject(self):
        self.canvas.cancel_transform()
        super().reject()
