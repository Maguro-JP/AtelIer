"""キャンバス全体の縮小図（ナビゲーター）。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel


class Navigator(QLabel):
    """キャンバス全体の縮小図。今見えている所を四角で示し、押した所を真ん中に出す。四角は引いて動かせる。
    描くたびに作り直すと重いので、絵は変わってから少し待って作る（四角はすぐ描き直す）"""

    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(120)
        self.setToolTip("赤い四角が今見えている所です。押すか四角を引くと、表示する場所が動きます")
        self._grab = None   # 四角を引いているとき、押した所と四角の中心のずれ
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.redraw)
        canvas.changed.connect(self.timer.start)
        canvas.history_changed.connect(self.timer.start)
        canvas.horizontalScrollBar().valueChanged.connect(self.update)
        canvas.verticalScrollBar().valueChanged.connect(self.update)
        canvas.zoomed.connect(self.update)

    def redraw(self):
        if not self.isVisible() or not self.canvas.layers:
            return
        img = self.canvas.flatten().scaled(max(1, self.width() - 8), max(1, self.height() - 8), Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(img))

    def showEvent(self, e):
        super().showEvent(e)
        self.redraw()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.timer.start()

    def _frame(self):
        """縮小図の置き場（左上と倍率）。絵がまだ無ければ None"""
        pm = self.pixmap()
        w, h = self.canvas.size_px()
        if pm is None or pm.isNull() or not w or not h:
            return None
        return (self.width() - pm.width()) / 2, (self.height() - pm.height()) / 2, pm.width() / w, pm.height() / h

    def view_rect(self):
        """今キャンバスに見えている所を、縮小図の上の四角で返す"""
        f = self._frame()
        if f is None:
            return None
        x0, y0, sx, sy = f
        r = self.canvas.mapToScene(self.canvas.viewport().rect()).boundingRect() & self.canvas.scene().sceneRect()
        return QRectF(x0 + r.x() * sx, y0 + r.y() * sy, r.width() * sx, r.height() * sy)

    def paintEvent(self, e):
        super().paintEvent(e)
        r = self.view_rect()
        if r is None or r.isEmpty():
            return
        p = QPainter(self)
        p.setPen(QPen(QColor(230, 40, 40), 2))
        p.drawRect(r.adjusted(1, 1, -1, -1))
        p.end()

    def _center_at(self, pos):
        f = self._frame()
        if f is None:
            return
        x0, y0, sx, sy = f
        w, h = self.canvas.size_px()
        self.canvas.centerOn(min(max((pos.x() - x0) / sx, 0), w), min(max((pos.y() - y0) / sy, 0), h))
        self.update()

    def mousePressEvent(self, e):
        r = self.view_rect()
        pos = e.position()
        if r is not None and r.contains(pos):
            self._grab = pos - r.center()   # 四角の中を押したら、押した所がずれないように引く
        else:
            self._grab = pos - pos
            self._center_at(pos)

    def mouseMoveEvent(self, e):
        if self._grab is not None and e.buttons() & Qt.LeftButton:
            self._center_at(e.position() - self._grab)

    def mouseReleaseEvent(self, e):
        self._grab = None

