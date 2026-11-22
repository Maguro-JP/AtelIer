"""まとめた窓。欄（ドック）と帯（ツールバー）を、主の窓から出して自由に組む別ウィンドウ。

Qt の別ウィンドウの欄は 1 枚ずつの窓で、帯は別ウィンドウにできず、帯と欄を 1 つの窓にまとめる手段も無かった。
まとめた窓は小さな QMainWindow なので、中で欄をタブにする・上下左右に並べる・帯をくっつける、が
主の窓と同じドラッグでできる。液タブの画面に、道具の帯と色の欄を 1 つの窓で浮かせるためのもの。
"""
from __future__ import annotations

import base64

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDockWidget, QMainWindow, QMenu, QTabWidget, QToolBar, QWidget


class GroupWindow(QMainWindow):
    def __init__(self, main, number: int):
        super().__init__(main, Qt.Window)   # 主の窓を親にする（主の窓を閉じれば一緒に閉じ、タスクバーに増えない）
        self.main = main
        self.setObjectName(f"group{number}")
        self.setWindowTitle(f"まとめた窓 {number}")
        # 下地を塗る。塗らないと、欄の無い所に前の描画の残りが縞になって見えた
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setDockNestingEnabled(True)
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks | QMainWindow.GroupedDragging)
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)
        # 真ん中は空けない（欄と帯だけの窓にする）。幅 0 の中身を置くと、欄が窓いっぱいに広がる
        empty = QWidget(self)
        empty.setMaximumSize(0, 0)
        self.setCentralWidget(empty)
        # 窓の中で押した F キーや Ctrl+Z も、主の窓と同じに効かせる
        self.addActions(main.shared_actions())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self.menu().exec(self.mapToGlobal(pos)))

    def docks(self) -> list[QDockWidget]:
        return [d for d in self.findChildren(QDockWidget) if d.parent() is self]

    def bars(self) -> list[QToolBar]:
        return [b for b in self.findChildren(QToolBar) if b.parent() is self]

    def menu(self) -> QMenu:
        m = QMenu(self)
        for d in self.docks():
            m.addAction(f"「{d.windowTitle()}」を元の窓に戻す", lambda d=d: self.main.return_panel(d))
        for b in self.bars():
            m.addAction(f"「{b.windowTitle()}」を元の窓に戻す", lambda b=b: self.main.return_bar(b))
        m.addSeparator()
        m.addAction("全部を元の窓に戻して閉じる", self.close)
        return m

    def move_panel(self, dock, area):
        """欄の見出しの「⋯」の「左に置く」などは、主の窓の決まった所へ戻す"""
        self.main.move_panel(dock, area)

    def is_empty(self) -> bool:
        return not self.docks() and not self.bars()

    def closeEvent(self, e):
        """閉じても欄と帯は消さず、主の窓へ戻す（閉じた窓と一緒に見えなくなると、出し方が分からなくなる）"""
        for d in self.docks():
            self.main.return_panel(d, close_empty=False)
        for b in self.bars():
            self.main.return_bar(b, close_empty=False)
        self.main.groups = [g for g in self.main.groups if g is not self]
        super().closeEvent(e)
        self.deleteLater()


class GroupMixin:
    """主の窓の側。欄と帯をまとめた窓へ入れる・戻す、配置に残す"""

    def shared_actions(self) -> list[QAction]:
        """ほかの窓（全画面のキャンバス、まとめた窓）でも効かせるショートカットの付いた操作"""
        return [a for a in self.findChildren(QAction) if not a.shortcut().isEmpty()]

    def all_bars(self) -> dict[str, QToolBar]:
        bars = {}
        for name in ("tools", "options", "ribbon_bar", "quick_bar", "panel_bar", "bottom_bar", "stop_bar"):
            b = getattr(self, name, None)
            if isinstance(b, QToolBar):
                bars[b.objectName() or name] = b
        for b in self.findChildren(QToolBar):
            if b.objectName() and b.objectName() not in bars and b.windowTitle():
                bars[b.objectName()] = b
        return bars

    def _all_docks(self) -> list[QDockWidget]:
        return [d for d in self.findChildren(QDockWidget) if d.objectName()]

    def new_group(self, near=None) -> GroupWindow:
        if not hasattr(self, "groups"):
            self.groups = []
        n = 1 + max([int(g.objectName()[5:]) for g in self.groups] or [0])
        g = GroupWindow(self, n)
        g.resize(380, 480)
        screen = (near or self).screen() if (near or self) is not None else None
        area = (screen or self.screen()).availableGeometry()
        g.move(area.left() + 60 + 30 * (n - 1), area.top() + 60 + 30 * (n - 1))
        self.groups.append(g)
        self.stay_on_top(g, self.fullscreen_on())
        g.show()
        self.feature_tour("group_window")
        return g

    def put_panel_in(self, d: QDockWidget, g: GroupWindow | None = None):
        """欄をまとめた窓へ入れる。g が無ければ新しい窓を作る。既に欄のある窓なら、前の欄とタブにまとめる"""
        g = g or self.new_group()
        old = d.parent()
        d.setFloating(False)
        if isinstance(old, QMainWindow):
            old.removeDockWidget(d)
        others = g.docks()
        g.addDockWidget(Qt.RightDockWidgetArea, d)
        if others:
            g.tabifyDockWidget(others[-1], d)
        d.show()
        d.raise_()
        self._drop_if_empty(old)
        return g

    def put_bar_in(self, b: QToolBar, g: GroupWindow | None = None):
        """帯をまとめた窓へ入れる。帯は窓の上の端に付き、窓の中では上下左右の端へドラッグで動かせる"""
        g = g or self.new_group()
        old = b.parent()
        area = Qt.TopToolBarArea
        if isinstance(old, QMainWindow):
            # 縦の帯（道具）は縦のまま左に付ける。横にすると窓の幅に収まらず、半分が「»」の奥に隠れた
            if old.toolBarArea(b) in (Qt.LeftToolBarArea, Qt.RightToolBarArea):
                area = Qt.LeftToolBarArea
            old.removeToolBar(b)
        b.setParent(g)
        b.setMovable(True)
        g.addToolBar(area, b)
        b.show()
        if g.docks() == []:
            g.resize(max(b.sizeHint().width() + 40, 240), max(b.sizeHint().height() + 40, 80))
        self._drop_if_empty(old)
        return g

    def return_panel(self, d: QDockWidget, close_empty: bool = True):
        old = d.parent()
        area = next((a for dd, a in self.panels.values() if dd is d), Qt.RightDockWidgetArea)
        if isinstance(old, QMainWindow) and old is not self:
            old.removeDockWidget(d)
        d.setFloating(False)
        self.addDockWidget(area, d)
        d.show()
        if close_empty:
            self._drop_if_empty(old)

    def return_bar(self, b: QToolBar, close_empty: bool = True):
        old = b.parent()
        if isinstance(old, QMainWindow) and old is not self:
            old.removeToolBar(b)
        b.setParent(self)
        area = Qt.LeftToolBarArea if b is getattr(self, "tools", None) else Qt.TopToolBarArea
        if b is getattr(self, "panel_bar", None):
            area = Qt.RightToolBarArea
        if b is getattr(self, "bottom_bar", None):
            area = Qt.BottomToolBarArea
        if b is getattr(self, "ribbon_bar", None):
            b.setMovable(False)
        self.addToolBar(area, b)
        b.show()
        if close_empty:
            self._drop_if_empty(old)

    def _drop_if_empty(self, w):
        if isinstance(w, GroupWindow) and w.is_empty():
            w.close()

    def return_all(self):
        for g in list(getattr(self, "groups", [])):
            g.close()

    def build_group_menu(self, menu: QMenu):
        """「ウィンドウ」の「まとめた窓」。開くたびに、今の欄・帯・まとめた窓から作り直す"""
        menu.setToolTipsVisible(True)

        def fill():
            menu.clear()
            groups = list(getattr(self, "groups", []))
            for title, items, put in (("欄を入れる", [(d.windowTitle(), d) for d in self._all_docks()], self.put_panel_in),
                                      ("帯を入れる", [(b.windowTitle(), b) for b in self.all_bars().values()], self.put_bar_in)):
                sub = menu.addMenu(title)
                sub.setToolTipsVisible(True)
                for label, obj in items:
                    s = sub.addMenu(label)
                    a = s.addAction("新しいまとめた窓へ", lambda o=obj, put=put: put(o))
                    a.setToolTip("別ウィンドウにして、ほかの欄や帯と組める窓に入れます")
                    for g in groups:
                        if obj.parent() is not g:
                            s.addAction(f"{g.windowTitle()}へ", lambda o=obj, g=g, put=put: put(o, g))
                    if obj.parent() is not self:
                        back = self.return_panel if put is self.put_panel_in else self.return_bar
                        s.addAction("元の窓に戻す", lambda o=obj, back=back: back(o))
            menu.addSeparator()
            for g in groups:
                menu.addAction(f"{g.windowTitle()}を前に出す", lambda g=g: (g.show(), g.raise_(), g.activateWindow()))
            a = menu.addAction("まとめた窓を全部、元の窓に戻す", self.return_all)
            a.setEnabled(bool(groups))
        menu.aboutToShow.connect(fill)
        fill()

    # ---- 配置の保存 ----
    def groups_snapshot(self) -> list[dict]:
        out = []
        for g in getattr(self, "groups", []):
            out.append({"docks": [d.objectName() for d in g.docks()], "bars": [b.objectName() for b in g.bars()],
                        "state": base64.b64encode(bytes(g.saveState())).decode(),
                        "geometry": base64.b64encode(bytes(g.saveGeometry())).decode()})
        return out

    def groups_restore(self, data: list[dict]):
        """まとめた窓を作り直す。主の窓の restoreState のあとに呼ぶ（先だと主の窓が欄を取り戻した）"""
        self.return_all()
        docks = {d.objectName(): d for d in self._all_docks()}
        bars = self.all_bars()
        for item in data or []:
            g = self.new_group()
            for name in item.get("docks", []):
                if name in docks:
                    self.put_panel_in(docks[name], g)
            for name in item.get("bars", []):
                if name in bars:
                    self.put_bar_in(bars[name], g)
            if g.is_empty():
                g.close()
                continue
            if item.get("state"):
                g.restoreState(QByteArray(base64.b64decode(item["state"])))
            if item.get("geometry"):
                g.restoreGeometry(QByteArray(base64.b64decode(item["geometry"])))
