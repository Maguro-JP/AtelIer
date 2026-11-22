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

from atelier.ui import screens, touch


class GroupWindow(QMainWindow):
    def __init__(self, main, number: int):
        # 親を持たない独立したウィンドウにする。主の窓を親にすると、Windows ではタスクバーに出ず、
        # 最小化すると主の窓と一緒に隠れ、液タブとタッチモニターに分けて置いたときに 1 枚ずつ扱えなかった。
        # 主の窓を閉じるときは closeEvent で一緒に閉じる（GroupMixin.close_groups）
        super().__init__(None, Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WA_QuitOnClose, False)
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
        top = m.addAction("前面に固定する")
        top.setCheckable(True)
        top.setChecked(self.pinned())
        top.setToolTip("ほかの窓（全画面のキャンバスも）の後ろに隠れないようにします")
        top.toggled.connect(self.set_pinned)
        for d in self.docks():
            t = m.addAction(f"「{d.windowTitle()}」をタッチ向けにする")
            t.setCheckable(True)
            t.setChecked(touch.is_on(d))
            t.setToolTip("ボタンと欄の中の部品を、指で押しやすい大きさにします")
            t.toggled.connect(lambda on, d=d: self.main.set_touch(d, on))
        m.addAction("最小化", self.showMinimized)
        m.addSeparator()
        m.addAction("全部を元の窓に戻して閉じる", self.close)
        return m

    def pinned(self) -> bool:
        return bool(getattr(self, "_pinned", False))

    def set_pinned(self, on: bool):
        """前面に固定する。全画面のあいだは固定していなくても上に出す（FullscreenMixin._float_on_top）"""
        self._pinned = bool(on)
        self.main.stay_on_top(self, self._pinned or self.main.fullscreen_on())

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
        # まとめた窓は親を持たないので、そこへ入れた帯は主の窓の子から探せない。窓ごとに探す
        found = self.findChildren(QToolBar)
        for g in getattr(self, "groups", []):
            found += g.bars()
        for b in found:
            if b.objectName() and b.objectName() not in bars and b.windowTitle():
                bars[b.objectName()] = b
        return bars

    def _all_docks(self) -> list[QDockWidget]:
        docks = [d for d in self.findChildren(QDockWidget) if d.objectName()]
        for g in getattr(self, "groups", []):
            docks += [d for d in g.docks() if d.objectName() and d not in docks]
        return docks

    def new_group(self, near=None) -> GroupWindow:
        if not hasattr(self, "groups"):
            self.groups = []
        n = 1 + max([int(g.objectName()[5:]) for g in self.groups] or [0])
        g = GroupWindow(self, n)
        g.setWindowIcon(self.windowIcon())
        g.addActions(self.shared_actions())
        g.resize(380, 480)
        screen = (near or self).screen() if (near or self) is not None else None
        area = (screen or self.screen()).availableGeometry()
        g.move(area.left() + 60 + 30 * ((n - 1) % 12), area.top() + 60 + 30 * ((n - 1) % 12))
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
                        "geometry": base64.b64encode(bytes(g.saveGeometry())).decode(),
                        **window_place(g), "title": g.windowTitle()})
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
            if item.get("title"):
                g.setWindowTitle(item["title"])
            if "rect" in item:
                put_window_place(self, g, item)
            elif item.get("geometry"):   # 前の版の保存（位置の数字が無い）
                g.restoreGeometry(QByteArray(base64.b64decode(item["geometry"])))
                self.keep_window_on_screen(g)


def window_place(win: QWidget) -> dict:
    """窓の置き場所を数字で残す。saveGeometry は枠の大きさを足した位置を持ち、OS とモニターの拡大率で
    枠の厚さが変わると戻すたびにずれた。中身の位置（geometry）とモニターの名前・拡大率を別に持つ"""
    s = win.screen()
    r = win.normalGeometry() if (win.isMaximized() or win.isFullScreen()) and win.normalGeometry().isValid() else win.geometry()
    return {"screen": s.name() if s else "", "scale": s.devicePixelRatio() if s else 1.0,
            "rect": [r.x(), r.y(), r.width(), r.height()],
            "maximized": win.isMaximized(), "fullscreen": win.isFullScreen(), "minimized": win.isMinimized(),
            "visible": win.isVisible(), "pinned": bool(getattr(win, "pinned", lambda: False)())}


def put_window_place(main, win: QWidget, item: dict):
    """window_place で残した所へ戻す。見せる前と見せた後の両方で同じ数字を当てる（見せると OS が枠の分を動かした）。
    保存したモニターが無ければ、今の画面の中へ収める"""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication
    x, y, w, h = item["rect"]
    rect = QRect(x, y, w, h)
    named = next((s for s in QGuiApplication.screens() if s.name() and s.name() == item.get("screen")), None)
    if named is None or not named.geometry().intersects(rect):
        rect = screens.fit_into(rect, [s.availableGeometry() for s in QGuiApplication.screens()])
    if named is not None and win.windowHandle() is not None:
        win.windowHandle().setScreen(named)
    win.setGeometry(rect)
    if item.get("pinned") and hasattr(win, "set_pinned"):
        win.set_pinned(True)
    if not item.get("visible", True):
        win.hide()
        return
    if item.get("fullscreen"):
        win.showFullScreen()
    elif item.get("maximized"):
        win.showMaximized()
    elif item.get("minimized"):
        win.showMinimized()
    else:
        win.show()
        if win.geometry() != rect:
            win.setGeometry(rect)


class DetachMixin:
    """全部の欄と帯を、1 つずつ独立したウィンドウにする。液タブを描く所だけにし、色や設定はタッチモニターに置くため"""

    def detach(self, obj) -> GroupWindow:
        """欄か帯を、それだけの独立したウィンドウに出す。今いる窓の画面に出す（別のモニターへはタイトルをドラッグして動かす）"""
        g = self.new_group(near=obj.window())
        if isinstance(obj, QToolBar):
            self.put_bar_in(obj, g)
        else:
            self.put_panel_in(obj, g)
            g.resize(max(g.width(), 320), max(g.height(), 420))
        g.setWindowTitle(f"{obj.windowTitle()} - AtelIer")
        self.feature_tour("detach")
        return g

    def detach_all(self):
        """見えている欄と帯を全部、独立したウィンドウにする。同じ画面の中に、重ならないようにずらして並べる"""
        self.remember_layout()
        items = [d for d, _a in self.panels.values() if not d.isHidden()]
        items += [b for b in self.all_bars().values() if not b.isHidden()]
        area = (self.screen() or self.windowHandle().screen()).availableGeometry()
        made = []
        for obj in items:
            if isinstance(obj.window(), GroupWindow) and len(obj.window().docks()) + len(obj.window().bars()) == 1:
                continue   # 既に 1 つだけの窓に入っている
            made.append(self.detach(obj))
        for i, (rect, g) in enumerate(zip(screens.cascade(area, [g.size() for g in made]), made)):
            g.setGeometry(rect)
        return made

    def _maybe_hand_placed(self):
        """欄をマウスでドラッグして動かしたら、手で置いた配置として扱い、自動で整えない"""
        from PySide6.QtWidgets import QApplication
        if QApplication.mouseButtons() != Qt.NoButton:
            self.__dict__["_hand_placed"] = True

    def keep_window_on_screen(self, w: QWidget):
        """窓を今あるモニターのどれかの中に収める。保存したモニターが外されていたら、主の画面へ戻す"""
        from PySide6.QtGui import QGuiApplication
        rects = [s.availableGeometry() for s in QGuiApplication.screens()]
        if not rects:
            return
        g = w.frameGeometry()
        r = screens.fit_into(g, rects)
        if r.size() != g.size():
            w.resize(r.size() - (g.size() - w.size()))
        if r.topLeft() != g.topLeft():
            w.move(r.topLeft())

    def set_touch(self, dock: QDockWidget, on: bool):
        """欄ごとのタッチ向けの見た目。選んだ欄は覚えておき、次の起動でも同じにする"""
        touch.apply(dock, on)
        win = dock.window()
        if on and win is not self and dock.widget() is not None:
            # 部品が大きくなった分だけ窓を広げる。広げないと、右の端の欄（色の番号）が切れて横に流す棒が出た
            inner = dock.widget().widget() if hasattr(dock.widget(), "widget") and dock.widget().widget() else dock.widget()
            win.resize(max(win.width(), inner.minimumSizeHint().width() + 32), win.height())
        names = set(self.touch_panels())
        (names.add if on else names.discard)(dock.objectName())
        self.layout_store.setValue("touch/panels", ",".join(sorted(n for n in names if n)))

    def touch_panels(self) -> list[str]:
        raw = self.layout_store.value("touch/panels", "") or ""
        return [n for n in str(raw).split(",") if n]

    def restore_touch(self, names=None):
        names = self.touch_panels() if names is None else names
        if names is not None and names is not self.touch_panels():
            self.layout_store.setValue("touch/panels", ",".join(sorted(names)))
        for d in self._all_docks():
            touch.apply(d, d.objectName() in names)

    def close_groups(self):
        """主の窓を閉じるとき、独立したウィンドウも閉じる（親を持たないので、残すとアプリが終わらない）。
        次の起動で同じ所へ出せるように、先に並びを残す"""
        import json
        groups = list(getattr(self, "groups", []))
        self.layout_store.setValue("groups9", json.dumps(self.groups_snapshot()) if groups else "")
        self.layout_store.setValue("floats9", json.dumps(self.floats_snapshot()))
        self.return_all()

    def floats_snapshot(self) -> dict:
        """別ウィンドウにした欄（まとめた窓に入れていない物）の置き場所"""
        return {d.objectName(): window_place(d) for d, _a in self.panels.values() if d.isFloating()}

    def floats_restore(self, data: dict):
        for d, _a in self.panels.values():
            item = (data or {}).get(d.objectName())
            if item and d.isFloating():
                put_window_place(self, d, item)

    def restore_groups_at_start(self):
        import json
        try:
            self.floats_restore(json.loads(self.layout_store.value("floats9", "") or "{}"))
        except (ValueError, TypeError, KeyError):
            pass
        raw = self.layout_store.value("groups9", "")
        if not raw:
            return
        try:
            self.groups_restore(json.loads(raw))
        except (ValueError, TypeError, KeyError):
            self.layout_store.setValue("groups9", "")   # 読めない並びは捨てる（起動を止めない）

    def build_detach_menu(self, menu: QMenu):
        """「ウィンドウ」の「独立したウィンドウ」。欄と帯を 1 つずつ外に出す・戻す・モニターの組ごとの配置"""
        from PySide6.QtWidgets import QInputDialog
        from atelier.ui import layouts as L
        menu.setToolTipsVisible(True)

        def fill():
            menu.clear()
            a = menu.addAction("すべての欄と帯を独立したウィンドウにする", self.detach_all)
            a.setToolTip("見えている欄と帯を 1 つずつ別の窓にします。タイトルをドラッグして液タブやタッチモニターへ動かせます")
            for title, items in (("欄", [(d.windowTitle(), d) for d, _a in self.panels.values()]),
                                 ("帯", [(b.windowTitle(), b) for b in self.all_bars().values()])):
                sub = menu.addMenu(f"{title}を 1 つ外に出す")
                for label, obj in items:
                    sub.addAction(label, lambda o=obj: self.detach(o))
            a = menu.addAction("全部を元の窓に戻す", self.return_all)
            a.setEnabled(bool(getattr(self, "groups", [])))
            menu.addSeparator()
            now = L.current_screens()
            mine = L.saved_names(self.layout_store)
            fit = [n for n in mine if L.screens_of(self.layout_store, n) == now]
            sub = menu.addMenu(f"今のモニターの組（{now}）の配置")
            sub.setToolTipsVisible(True)
            for n in fit:
                sub.addAction(n, lambda n=n: (self.remember_layout(), L.load(self, self.layout_store, n), self.notify(f"「{n}」の配置にしました", "ok")))
            if not fit:
                sub.addAction("まだ保存した配置はありません").setEnabled(False)
            others = [n for n in mine if n not in fit]
            if others:
                o = menu.addMenu("ほかのモニターの組の配置")
                o.setToolTipsVisible(True)
                for n in others:
                    act = o.addAction(f"{n}（{L.screens_of(self.layout_store, n) or '組の記録なし'}）",
                                      lambda n=n: (self.remember_layout(), L.load(self, self.layout_store, n),
                                                   self.notify(f"「{n}」の配置にしました。無いモニターの窓は今の画面に戻しました", "ok")))
                    act.setToolTip("保存したときのモニターが無い窓は、今の画面の中へ戻します")

            def save():
                count = now.split(" ")[0]
                name, ok = QInputDialog.getText(self, "今のモニターの組で配置を保存", f"配置の名前（{now}）",
                                                text=f"液タブ {count} 台")
                if ok and name.strip():
                    L.save(self, self.layout_store, name.strip())
                    self.notify(f"「{name.strip()}」として保存しました", "ok", now)
            a = menu.addAction("今のモニターの組で配置を保存…", save)
            a.setToolTip("独立したウィンドウの位置、前面に固定、全画面にする画面も一緒に残します")
            menu.addSeparator()
            t = menu.addMenu("タッチ向けにする欄")
            for d, _a in self.panels.values():
                act = t.addAction(d.windowTitle())
                act.setCheckable(True)
                act.setChecked(touch.is_on(d))
                act.toggled.connect(lambda on, d=d: self.set_touch(d, on))
        menu.aboutToShow.connect(fill)
        fill()

    def build_bar_shown_menu(self, menu: QMenu):
        """全部の帯を出す・隠す。前は道具・欄の帯・道具の設定・よく使う帯しか選べず、リボンや下の帯は隠せなかった"""
        def fill():
            menu.clear()
            for b in self.all_bars().values():
                a = menu.addAction(b.windowTitle())
                a.setCheckable(True)
                a.setChecked(not b.isHidden())
                a.toggled.connect(lambda on, b=b: b.setVisible(on))
        menu.aboutToShow.connect(fill)
        fill()

    def remember_layout(self):
        """配置を大きく変える前（決まった配置を選ぶ、保存した配置を呼ぶ、全部を外に出す）の形を 1 つ残す"""
        from atelier.ui import layouts as L
        self._prev_layout = L.snapshot(self)

    def undo_layout(self) -> bool:
        """前の配置に戻す。戻す前の形を残すので、もう一度押すと戻す前に帰れる"""
        from atelier.ui import layouts as L
        prev = getattr(self, "_prev_layout", None)
        if not prev:
            self.notify("戻せる前の配置はまだありません", "info")
            return False
        now = L.snapshot(self)
        ok = L.restore(self, prev)
        self._prev_layout = now
        self.notify("前の配置に戻しました", "ok")
        return ok
