"""キャンバスの全画面。液タブなど選んだ画面いっぱいに、キャンバスだけを出して描く。

キャンバスそのものを全画面の窓へ移す（写しを作らない）。絵・拡大率・レイヤー・元に戻すの履歴は同じ物のままで、
戻すと主の窓の真ん中へ帰る。主の窓と欄は別の画面に残せる。
別ウィンドウの欄・帯・まとめた窓は、全画面のあいだ上に重ねる（全画面の窓の後ろに隠れると、液タブで色も道具も選べなかった）。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import QDockWidget, QLabel, QMenu, QToolBar, QVBoxLayout, QWidget

SHORTCUT = "Ctrl+Shift+F"   # F11 は前から「進み」の欄に使っている
SCREEN_KEY = "fullscreen/screen"


class _Hold(QLabel):
    """全画面のあいだ主の窓の真ん中に置く札。キャンバスと同じ大きさを望み、欄の並びを動かさない"""

    def __init__(self, size: QSize, text: str):
        super().__init__(text)
        self._size = size
        self.setAlignment(Qt.AlignCenter)

    def sizeHint(self):
        return self._size


class FullscreenCanvas(QWidget):
    def __init__(self, main):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.main = main
        self.setObjectName("fullscreen_canvas")
        self.setWindowTitle("AtelIer 全画面")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # 主の窓のショートカット（ペン、消しゴム、拡大、元に戻す、欄の F キー）を、この窓でも同じに効かせる
        self.addActions(main.shared_actions())
        # 抜け方を最初の数秒だけ上の端に出す（枠もメニューも無いので、出さないと戻り方が分からない）
        self.hint = QLabel(f"Esc か {SHORTCUT} で元の窓に戻ります", self)
        self.hint.setToolTip(f"全画面をやめるには Esc か {SHORTCUT} を押します")
        self.hint.setStyleSheet("background: rgba(0,0,0,170); color: white; padding: 8px 14px; border-radius: 6px;")
        self.hint.adjustSize()

    def showEvent(self, e):
        super().showEvent(e)
        from PySide6.QtCore import QTimer
        self.hint.move(max(0, (self.width() - self.hint.width()) // 2), 16)
        self.hint.raise_()
        self.hint.show()
        QTimer.singleShot(4000, self.hint.hide)

    def keyPressEvent(self, e):
        # キャンバスが使わなかった Esc（図形の途中でなければ）で戻る
        if e.key() == Qt.Key_Escape:
            self.main.leave_fullscreen()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.main.fullscreen_on():
            self.main.leave_fullscreen()
        super().closeEvent(e)


class FullscreenMixin:
    def fullscreen_on(self) -> bool:
        return getattr(self, "_fullscreen", None) is not None

    def fullscreen_screen(self):
        """全画面に使う画面。前に選んだ画面があればそれ、無ければ主の窓の画面"""
        name = self.layout_store.value(SCREEN_KEY, "")
        for s in QGuiApplication.screens():
            if s.name() == name:
                return s
        return self.screen() or QGuiApplication.primaryScreen()

    def choose_fullscreen_screen(self, name: str):
        self.layout_store.setValue(SCREEN_KEY, name)
        if self.fullscreen_on():   # 全画面のまま選び直したら、その画面へ移す
            self.leave_fullscreen()
            self.enter_fullscreen()

    def toggle_fullscreen(self):
        self.leave_fullscreen() if self.fullscreen_on() else self.enter_fullscreen()

    def enter_fullscreen(self):
        if self.fullscreen_on():
            return
        canvas = self.takeCentralWidget()   # 消さずに取り出す（setCentralWidget で替えると前の物が消えた）
        if canvas is None:
            return
        # 真ん中を空けたままにすると下と横の欄が広がり、戻したときにキャンバスが細い帯になった。
        # 同じ所に札を置いて、主の窓の並びを動かさない
        hold = _Hold(canvas.rect().size(), f"キャンバスは全画面に出しています。\nEsc か {SHORTCUT} で戻ります")
        sizes = self._dock_sizes()
        self.setCentralWidget(hold)
        self._fullscreen_sizes = sizes
        self._put_dock_sizes(sizes)
        win = FullscreenCanvas(self)
        win.layout().addWidget(canvas)
        canvas.show()
        self._fullscreen = win
        screen = self.fullscreen_screen()
        win.setScreen(screen)
        win.setGeometry(screen.geometry())
        win.showFullScreen()
        win.activateWindow()
        canvas.setFocus()
        self._float_on_top(True)
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(True)
        self.statusBar().showMessage(f"全画面で描いています。Esc か {SHORTCUT} で戻ります", 6000)
        self.feature_tour("fullscreen")

    def leave_fullscreen(self):
        win = getattr(self, "_fullscreen", None)
        if win is None:
            return
        self._fullscreen = None
        canvas = self.canvas
        win.layout().removeWidget(canvas)
        self.setCentralWidget(canvas)
        canvas.show()
        self._put_dock_sizes(getattr(self, "_fullscreen_sizes", {}))
        win.hide()
        win.deleteLater()
        self._float_on_top(False)
        if hasattr(self, "fullscreen_action"):
            self.fullscreen_action.setChecked(False)
        self.activateWindow()
        canvas.setFocus()

    def _dock_sizes(self) -> dict:
        return {d: d.size() for d in self.findChildren(QDockWidget)
                if d.parent() is self and d.isVisible() and not d.isFloating()}

    def _put_dock_sizes(self, sizes: dict):
        """真ん中の中身を替えると、下の欄（チャット）が空いた所へ広がり、キャンバスが細い帯になった。
        替える前の欄の大きさに戻す（あとで戻すのも、イベントを流してから）"""
        from PySide6.QtCore import QTimer

        def put():
            docks = [d for d in sizes if d.parent() is self and not d.isFloating() and d.isVisible()]
            # 上下の欄は高さ、左右の欄は幅だけを戻す（両方を当てると、右の欄が細くなった）
            tb = [d for d in docks if self.dockWidgetArea(d) in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea)]
            lr = [d for d in docks if d not in tb]
            if tb:
                self.resizeDocks(tb, [sizes[d].height() for d in tb], Qt.Vertical)
            if lr:
                self.resizeDocks(lr, [sizes[d].width() for d in lr], Qt.Horizontal)
        put()
        QTimer.singleShot(0, put)

    # ---- 別ウィンドウを全画面の上に出す ----
    def floating_windows(self) -> list[QWidget]:
        out = []
        for d in self.findChildren(QDockWidget):
            if d.isFloating():
                out.append(d)
        for b in self.findChildren(QToolBar):
            if b.isFloating():
                out.append(b)
        out += list(getattr(self, "groups", []))
        return out

    def stay_on_top(self, w: QWidget, on: bool):
        if bool(w.windowFlags() & Qt.WindowStaysOnTopHint) == on:
            return
        shown = w.isVisible()
        w.setWindowFlag(Qt.WindowStaysOnTopHint, on)   # 旗を替えると窓が隠れるので、出ていた物は出し直す
        if shown:
            w.show()

    def _float_on_top(self, on: bool):
        for w in self.floating_windows():
            self.stay_on_top(w, on)

    def floated_now(self, w: QWidget, floating: bool):
        """全画面のあいだに別ウィンドウにした欄も、上に出す"""
        if floating and self.fullscreen_on():
            self.stay_on_top(w, True)

    def build_fullscreen_menu(self, view: QMenu):
        self.fullscreen_action = QAction("全画面で描く", self, checkable=True, shortcut=SHORTCUT,
                                         triggered=lambda _on=False: self.toggle_fullscreen())
        self.fullscreen_action.setToolTip(f"キャンバスだけを選んだ画面いっぱいに出します（{SHORTCUT}。Esc で戻ります）")
        view.addAction(self.fullscreen_action)
        where = view.addMenu("全画面にする画面")
        where.setToolTipsVisible(True)

        def fill():
            where.clear()
            current = self.fullscreen_screen()
            for i, s in enumerate(QGuiApplication.screens(), 1):
                g = s.geometry()
                a = where.addAction(f"画面 {i}（{g.width()}×{g.height()}）", lambda n=s.name(): self.choose_fullscreen_screen(n))
                a.setCheckable(True)
                a.setChecked(s is current)
                a.setToolTip(s.name() or f"画面 {i}")
        where.aboutToShow.connect(fill)
        fill()

    # ---- 配置の保存 ----
    def fullscreen_snapshot(self) -> dict:
        return {"on": self.fullscreen_on(), "screen": self.layout_store.value(SCREEN_KEY, "")}

    def fullscreen_restore(self, data: dict | None):
        if not data:
            return
        if data.get("screen"):
            self.layout_store.setValue(SCREEN_KEY, data["screen"])
        if data.get("on"):
            self.enter_fullscreen()
        else:
            self.leave_fullscreen()
