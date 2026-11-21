"""操作の履歴の欄。元に戻すの積み重ねを並べ、選んだ操作のあとまで戻る。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class OperationHistory(QListWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.setToolTip("選ぶと、その操作のあとまで戻ります")
        canvas.history_changed.connect(self.refresh)
        self.currentRowChanged.connect(lambda row: row >= 0 and canvas.go_to(row))
        self.refresh()

    def refresh(self):
        """先頭は「始め」、済んだ操作のあとに戻した操作を薄く並べ、今いる所を選んでおく"""
        self.blockSignals(True)
        self.clear()
        self.addItem("始め")
        for name in self.canvas.undo_names:
            self.addItem(name)
        for name in reversed(self.canvas.redo_names):
            item = QListWidgetItem(name)
            item.setForeground(Qt.gray)
            self.addItem(item)
        self.setCurrentRow(len(self.canvas.undo_names))
        self.blockSignals(False)
