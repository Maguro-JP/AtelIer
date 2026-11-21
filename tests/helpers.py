"""試験で共に使う部品。窓を開き、絵の上をマウスで押して動かして離す（本物と同じ経路）。"""
from __future__ import annotations


def application():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def window(width: int = 200, height: int = 200):
    """200×200 の等倍のキャンバスを出した窓"""
    application()
    from atelier.app.main_window import MainWindow
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    w.canvas.new_canvas(width, height)
    w.canvas.set_zoom(1.0)
    w.dirty = False
    return w


def close(w):
    """保存の確かめを出さずに閉じる"""
    w.dirty = False
    w.close()


def drag(c, pts):
    """絵の座標の点の列を、ビューの上のマウスの押す・動かす・離すにして流す"""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    vp = c.viewport()
    at = [c.mapFromScene(x, y) for x, y in pts]
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, at[0])
    for p in at[1:]:
        ev = QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(vp, ev)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at[-1] if at else QPoint())


def changed(before, after) -> int:
    """2 枚の絵で、色が違う画素の数（1 つ飛ばしで数える）"""
    return sum(1 for y in range(0, after.height(), 2) for x in range(0, after.width(), 2)
               if before.pixelColor(x, y) != after.pixelColor(x, y))
