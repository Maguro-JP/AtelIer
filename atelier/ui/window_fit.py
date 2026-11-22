"""ウィンドウを画面の中に収める。

前の起動で残した大きさ・位置や、中身の多い欄・別ウィンドウにした欄・設定の窓が、画面より縦に長くなったり、
タスクバーの下に潜ったりして、閉じる・動かす所に手が届かず操作できなくなった。
表に出る窓（メインウィンドウ、別ウィンドウの欄、窓）はすべて、出たときと大きさが変わったときに、
画面の使える範囲（タスクバーを除く）に収める。大きすぎるときは縮め、はみ出したときは中へ動かす。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget


def available(w: QWidget) -> QRect:
    screen = w.screen() or QGuiApplication.screenAt(w.frameGeometry().center()) or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def fit(w: QWidget):
    """w を画面の使える範囲に収める。最大化・全画面のときは OS に任せる（その大きさは OS が使える範囲で決める）"""
    if not w.isWindow() or w.isMaximized() or w.isFullScreen() or w.isMinimized():
        return
    if w.windowType() in (Qt.Popup, Qt.ToolTip, Qt.SplashScreen):
        return   # メニュー、一覧の開き、ツールチップは Qt が画面に合わせて出すので触らない
    area = available(w)
    frame = w.frameGeometry()
    extra_w = frame.width() - w.width()     # 枠と見出しの分
    extra_h = frame.height() - w.height()
    max_w, max_h = area.width() - extra_w, area.height() - extra_h
    # 元の最小の大きさを覚えておき、画面に収まる分だけ使う。下げたままにすると、広い画面に戻しても戻らなかった
    orig = w.property("fit_min0")
    if orig is None:
        orig = (w.minimumWidth(), w.minimumHeight())
        w.setProperty("fit_min0", orig)
    want = (min(orig[0], max_w), min(orig[1], max_h))
    if want != (w.minimumWidth(), w.minimumHeight()):
        w.setMinimumSize(*want)
    width, height = min(w.width(), max_w), min(w.height(), max_h)
    if (width, height) != (w.width(), w.height()):
        w.resize(width, height)
    frame = w.frameGeometry()
    x = min(max(frame.x(), area.left()), area.right() - frame.width() + 1)
    y = min(max(frame.y(), area.top()), area.bottom() - frame.height() + 1)
    if (x, y) != (frame.x(), frame.y()):
        w.move(x, y)


class ScreenFit(QObject):
    """アプリ全体の窓を見張り、出たとき・大きさが変わったとき・画面を移ったときに収める。動かしている途中は引き戻さない"""

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.Show, QEvent.Resize, QEvent.WindowStateChange, QEvent.ScreenChangeInternal) and isinstance(obj, QWidget) and obj.isWindow():
            if not getattr(obj, "_fit_pending", False):
                obj._fit_pending = True

                def later(o=obj):
                    try:
                        o._fit_pending = False
                        fit(o)
                    except RuntimeError:   # 窓が先に消えた
                        pass
                # 動かしている途中（見出しのドラッグ）に引き戻さないよう、少し待ってから収める
                QTimer.singleShot(0 if t == QEvent.Show else 300, later)
        return False


_FILTER: ScreenFit | None = None


def install(app: QApplication):
    global _FILTER
    if _FILTER is None:
        _FILTER = ScreenFit(app)
        app.installEventFilter(_FILTER)


def fit_dock_height(dock: QWidget, height: int):
    """欄を中身の高さ（height）にそろえる。進みの欄のように、中身が状態で増え減りする欄に使う。
    欄の外側（流す枠）の高さを決めないと、Qt の欄の場所は前の高さのまま残り、描いている間は文が切れ、
    描いていない間は空きが大きく残った。流す枠の高さの上限を中身の高さにし、欄の場所をその高さに合わせる"""
    box = dock.widget()
    if box is None:
        return
    box.setMinimumHeight(0)
    # 上限は付けない。上限を中身の高さにすると欄の高さが固定になり、利用者が手で広げられなくなった
    box.setMaximumHeight(16777215)
    _watch_hand_resize(dock)
    # 欄の外枠の最小・最大は、中身が固定の高さのとき Qt が中身から決めて持ち続ける。隠れている間に中身の高さを変えると
    # 前の高さ（起動したときの 114 など）のまま残ったので、毎回組み直させる
    if dock.layout() is not None:
        dock.layout().invalidate()
        dock.layout().activate()
    dock.updateGeometry()
    if dock.isFloating():
        dock.adjustSize()
        return
    from PySide6.QtWidgets import QMainWindow
    main = dock.parentWidget()
    if isinstance(main, QMainWindow) and dock.isVisible():
        bar = dock.titleBarWidget()
        head = bar.sizeHint().height() if bar is not None and bar.isVisible() else 0
        want = height + head
        hand = dock.property("fit_hand_height")
        if hand:
            want = max(want, int(hand))   # 手で決めた大きさを尊重する。中身が増えて足りないときだけ広げる
        dock._fit_busy = True
        try:
            main.resizeDocks([dock], [want], Qt.Vertical)
        finally:
            dock._fit_busy = False


class _HandResize(QObject):
    """欄の境目をマウスで動かして変えた高さを覚える。自動で合わせた高さや窓の大きさの変化では覚えない"""

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize and not getattr(obj, "_fit_busy", False) and not obj.isFloating() \
                and QApplication.mouseButtons() & Qt.LeftButton and e.size().height() != e.oldSize().height():
            obj.setProperty("fit_hand_height", e.size().height())
        return False


def _watch_hand_resize(dock: QWidget):
    if getattr(dock, "_hand_watch", None) is None:
        dock._hand_watch = _HandResize(dock)
        dock.installEventFilter(dock._hand_watch)
