"""デバッグモードのときだけ、状態の帯の右端に CPU・メモリ・GPU・VRAM を短い 1 行で出す。押すと細かい表の窓を開く。

値は裏の糸で取る（atelier/app/system_usage.py）。前の 1 回が終わっていなければ次を出さないので、取るのが遅い機械でも溜まらない。
デバッグモードが切れたら時計を止め、値も取らない。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHeaderView, QSizePolicy, QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout)

from atelier.app import system_usage

EVERY_MS = 1500


class _Bridge(QObject):
    got = Signal(dict)


class UsageMeter(QToolButton):
    def __init__(self, stage=lambda: "", parent=None):
        super().__init__(parent)
        self.stage = stage            # 描いている間の今の工程を返す関数
        self.setAutoRaise(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)   # 場所があれば全文、狭い窓では最小の幅まで縮む
        self.setMinimumWidth(80)
        self.last: dict | None = None
        self.samples = 0
        self._busy = False
        self._bridge = _Bridge()
        self._bridge.got.connect(self._show)
        self.timer = QTimer(self)
        self.timer.setInterval(EVERY_MS)
        self.timer.timeout.connect(self.tick)
        self.clicked.connect(self.open_table)
        self.box = None
        self.hide()

    def running(self) -> bool:
        return self.timer.isActive()

    def start(self):
        if not self.timer.isActive():
            self.setText("CPU …")
            self.show()
            self.timer.start()
            self.tick()

    def stop(self):
        self.timer.stop()
        self.hide()
        if self.box is not None:
            self.box.hide()

    def tick(self):
        if self._busy:
            return
        self._busy = True
        stage = self.stage() or ""
        threading.Thread(target=self._work, args=(stage,), daemon=True, name="usage-meter").start()

    def _work(self, stage):
        try:
            s = system_usage.sample(stage)
        except Exception as e:   # 取れなくても帯を壊さない
            s = {"why": {"cpu": type(e).__name__, "gpu": type(e).__name__}, "stage": stage, "took": 0}
        self._bridge.got.emit(s)

    def _show(self, s: dict):
        self._busy = False
        if not self.timer.isActive():   # 止めたあとに届いた値は出さない
            return
        self.last, self.samples = s, self.samples + 1
        self.setText(system_usage.line(s))
        self.setToolTip(system_usage.tip(s))
        if self.box is not None and self.box.isVisible():
            self._fill()

    def open_table(self):
        if self.box is None:
            self.box = QDialog(self.window())
            self.box.setWindowTitle("使用率の詳細")
            lay = QVBoxLayout(self.box)
            self.grid = QTableWidget(0, 2)
            self.grid.setHorizontalHeaderLabels(["項目", "値"])
            self.grid.verticalHeader().hide()
            self.grid.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            self.grid.horizontalHeader().setStretchLastSection(True)
            self.grid.setEditTriggers(QTableWidget.NoEditTriggers)
            self.grid.setWordWrap(True)   # 取れない理由は長いので、切らずに折り返す
            self.grid.setTextElideMode(Qt.ElideNone)
            lay.addWidget(self.grid)
            self.box.resize(600, 380)
        self._fill()
        self.box.show()
        self.box.raise_()

    def _fill(self):
        rows = system_usage.table(self.last) if self.last and "cpu" in self.last else [("値", "まだ取れていません")]
        self.grid.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.grid.setItem(i, 0, QTableWidgetItem(k))
            item = QTableWidgetItem(v)
            item.setToolTip(v)   # 長い理由は窓が狭いと切れるので、合わせると全文が出る
            self.grid.setItem(i, 1, item)
        self.grid.resizeRowsToContents()
