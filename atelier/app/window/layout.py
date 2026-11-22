"""テーマ、欄と帯の配置、ツールバー、欄の出し入れ"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtGui import QActionGroup
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDockWidget
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QToolBar
from atelier.app.window.constants import PANEL
from atelier.app.window.constants import PANEL_ORDER
from atelier.app.window.widgets import PanelTitle
from atelier.ui import i18n
from atelier.ui.icons import icon
from pathlib import Path


class LayoutMixin:
    """テーマ、欄と帯の配置、ツールバー、欄の出し入れ（Window が継承する）"""

    def _fill_theme_menu(self):
        """決まったテーマ、自分のテーマ、テーマを作る・消す"""
        from atelier.ui import themes
        m = self.theme_menu
        m.clear()
        group = QActionGroup(m)
        for name in themes.all_names():
            if name == next(iter(themes.CUSTOM), None):
                m.addSeparator()
            a = QAction(name, m, checkable=True, triggered=lambda _=False, n=name: self.set_theme(n))
            a.setChecked(name == themes.current["name"])
            group.addAction(a)
            m.addAction(a)
        m.addSeparator()
        m.addAction(QAction("テーマを作る…", m, triggered=self.edit_theme))
        if themes.CUSTOM:
            gone = m.addMenu("自分のテーマを消す")
            for name in themes.CUSTOM:
                gone.addAction(QAction(name, gone, triggered=lambda _=False, n=name: self.remove_theme(n)))

    def _look(self, t: dict):
        self.canvas.setBackgroundBrush(QColor(t["canvas"]))
        self.look.apply(t)

    def set_theme(self, name: str):
        """テーマ（色・模様・演出）を替えて覚える。アイコン・絵の周り・欄の色がそろって替わる"""
        from atelier.ui import look
        from atelier.ui import themes

        def change():
            t = themes.apply(QApplication.instance(), name)
            self._look(t)
            self.layout_store.setValue("theme", t["name"])
        look.crossfade(self, change)
        self.feature_tour("theme")
        return themes.current

    def preview_theme(self, t: dict):
        """テーマを作る窓で替えている途中の色を、保存せずに当てる"""
        from atelier.ui import themes
        self._look(themes.apply(QApplication.instance(), t))

    def edit_theme(self):
        from atelier.ui.theme_editor import ThemeEditor
        self.feature_tour("theme_edit", lambda: ThemeEditor(self).exec())

    def remove_theme(self, name: str):
        from atelier.ui import themes
        if QMessageBox.question(self, "自分のテーマを消す", f"「{name}」を消します。よろしいですか") != QMessageBox.Yes:
            return
        if themes.current["name"] == name:
            self.set_theme(themes.DEFAULT)
        themes.remove_custom(self.layout_store, name)

    def arrange(self):
        """初期の配置。左に道具・色・ブラシ、右に AI・描いた絵と進み・レイヤー、真ん中を広く絵に使う"""
        for key in ("brushes", "color", "chat", "history", "layers"):
            self.panels[key][0]   # 欄がそろっているかを確かめる（足りなければ前と同じく KeyError）
        for d, _area in self.panels.values():
            d.setFloating(False)
            d.show()
        self.addToolBar(Qt.LeftToolBarArea, self.tools)
        self.tools.show()
        self.addToolBar(Qt.TopToolBarArea, self.ribbon_bar)
        self.ribbon_bar.show()
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, self.options)
        self.options.show()
        if hasattr(self, "quick_bar"):
            self.addToolBar(Qt.TopToolBarArea, self.quick_bar)
            self.quick_bar.show()
        self.addToolBar(Qt.RightToolBarArea, self.panel_bar)
        self.panel_bar.show()
        self.addToolBar(Qt.BottomToolBarArea, self.bottom_bar)
        self.bottom_bar.show()
        from PySide6.QtCore import QTimer
        from atelier.ui.layouts import recommended, settle
        recommended(self)
        QTimer.singleShot(0, lambda: settle(self))

    def apply_layout(self, fn, *args):
        """配置を当て、絵を新しい大きさに合わせる"""
        self._all_hidden = False   # Tab で隠したあとに配置を選んだとき、次の Tab で出したばかりの欄が隠れないように
        self.remember_layout()
        fn(self, *args)
        from PySide6.QtCore import QTimer
        from atelier.ui.layouts import settle
        QTimer.singleShot(0, lambda: settle(self))
        QTimer.singleShot(0, self.canvas.fit)

    def build_layout_menu(self):
        """「配置」メニュー。決まった配置・寄せ・等分・自分の配置の保存と読み出し・書き出しと読み込み"""
        from PySide6.QtWidgets import QInputDialog
        from atelier.ui import layouts as L
        menu = self.menuBar().addMenu("配置")
        self.layout_menu = menu

        def fill():
            menu.clear()
            for name in L.PRESETS:
                menu.addAction(self.shared[f"layout:{name}"])   # リボンの「おすすめ」と同じ操作
            menu.addSeparator()
            for label, where in (("左に寄せる", "left"), ("右に寄せる", "right"), ("真ん中に寄せる（絵を中央に）", "center")):
                menu.addAction(QAction(label, self, triggered=lambda _=False, w=where: self.apply_layout(L.align, w)))
            for n in (3, 5):
                menu.addAction(QAction(f"{n} 等分にする", self, triggered=lambda _=False, n=n: self.apply_layout(L.split, n)))
            menu.addSeparator()
            menu.addAction(QAction("前の配置に戻す", self, triggered=self.undo_layout))
            mine = L.saved_names(self.layout_store)
            if mine:
                sub = menu.addMenu("自分の配置")
                for name in mine:
                    sub.addAction(QAction(name, self, triggered=lambda _=False, n=name: (
                        self.remember_layout(), L.load(self, self.layout_store, n), self.notify(f"「{n}」の配置にしました", "ok"))))
                rm = menu.addMenu("自分の配置を消す")
                for name in mine:
                    rm.addAction(QAction(name, self, triggered=lambda _=False, n=name: (
                        L.remove(self.layout_store, n), self.notify(f"「{n}」を消しました", "info"))))

            def save():
                name, ok = QInputDialog.getText(self, "今の配置を保存", "配置の名前")
                if ok and name.strip():
                    L.save(self, self.layout_store, name.strip())
                    self.notify(f"「{name.strip()}」として保存しました", "ok")
            menu.addAction(QAction("今の配置を保存…", self, triggered=lambda: self.feature_tour("layout_save", save)))
            menu.addSeparator()

            def export():
                path, _ = QFileDialog.getSaveFileName(self, "配置を書き出す", "layout.cdlayout.json", "配置 (*.json)")
                if path:
                    L.export(self, path)
                    self.notify("配置を書き出しました", "ok", Path(path).name)

            def import_():
                path, _ = QFileDialog.getOpenFileName(self, "配置を読み込む", "", "配置 (*.json)")
                if path:
                    name = L.import_(self, path)
                    self.notify(f"「{name}」の配置にしました" if name else "読み込めませんでした", "ok" if name else "error")
            menu.addAction(QAction("配置を書き出す…", self, triggered=lambda: self.feature_tour("layout_export", export)))
            menu.addAction(QAction("配置を読み込む…", self, triggered=lambda: self.feature_tour("layout_export", import_)))
        menu.aboutToShow.connect(fill)
        fill()

    def build_status(self):
        """下のステータスバー。左に知らせ、右に道具・座標・キャンバスの大きさ・レイヤー・AI の状態・拡大率を並べる。
        拡大率は押すと全体表示に戻る"""
        sb = self.statusBar()
        sb.setSizeGripEnabled(True)

        def cell(tip, w=0):
            lb = QLabel()
            lb.setObjectName("statusCell")
            lb.setToolTip(tip)
            if w:
                lb.setMinimumWidth(w)
            sb.addPermanentWidget(lb)
            return lb
        self.st_tool = cell("今の道具", 70)
        self.st_pos = cell("カーソルの位置（画素）", 90)
        self.st_size = cell("キャンバスの大きさ", 90)
        self.st_layer = cell("描いているレイヤー", 90)
        self.ai_label = cell("AI の状態")
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setObjectName("statusButton")
        self.zoom_label.setToolTip("拡大率。押すと全体を表示します")
        self.zoom_label.clicked.connect(self.canvas.fit)
        sb.addPermanentWidget(self.zoom_label)
        self.canvas.zoomed.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f}%"))
        self.canvas.moved.connect(lambda x, y: self.st_pos.setText(f"{x}, {y}"))
        self.canvas.changed.connect(self._status_doc)
        self._status_doc()
        self.st_tool.setText(self.tool_name.text())

    def _status_doc(self):
        w, h = self.canvas.size_px()
        self.st_size.setText(f"{w}×{h}")
        layers = self.canvas.layers
        if layers:   # 消した直後の古い番号でも落ちない
            self.st_layer.setText(layers[max(0, min(self.canvas.current, len(layers) - 1))].name)

    def build_bottom(self):
        """下の帯。表示と元に戻すの操作を、手の届く下に並べる。「ウィンドウ」から隠せ、上にも移せる"""
        from PySide6.QtWidgets import QSlider as _S
        bar = QToolBar("下の帯", self)
        bar.setObjectName("bottombar")
        bar.setIconSize(QSize(18, 18))
        S = self.shared
        bar.addAction(S["undo"])
        bar.addAction(S["redo"])
        bar.addSeparator()
        bar.addAction(S["fit"])
        self.zoom_slider = _S(Qt.Horizontal)
        self.zoom_slider.setRange(5, 800)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(180)
        self.zoom_slider.setToolTip("拡大率")
        self.zoom_slider.valueChanged.connect(lambda v: self.canvas.set_zoom(v / 100))
        self.canvas.zoomed.connect(lambda z: (self.zoom_slider.blockSignals(True), self.zoom_slider.setValue(int(z * 100)),
                                              self.zoom_slider.blockSignals(False)))
        from PySide6.QtWidgets import QWidgetAction
        zoom = QWidgetAction(self)   # 帯の編集で外して戻せるよう、操作として持つ
        zoom.setText("拡大率")
        zoom.setDefaultWidget(self.zoom_slider)
        S["zoom_slider"] = zoom
        bar.addAction(zoom)
        # 拡大率は数字でも見て入れられる（つまみだけだと今が何 % か分からなかった）
        from PySide6.QtWidgets import QSpinBox
        self.zoom_box = QSpinBox()
        self.zoom_box.setRange(5, 3200)
        self.zoom_box.setSuffix(" %")
        self.zoom_box.setValue(100)
        self.zoom_box.setToolTip("拡大率。数字を入れて Enter で変わります")
        self.zoom_box.setKeyboardTracking(False)
        self.zoom_box.valueChanged.connect(lambda v: abs(self.canvas.zoom() * 100 - v) >= 0.5 and self.canvas.set_zoom(v / 100))
        self.canvas.zoomed.connect(lambda z: (self.zoom_box.blockSignals(True), self.zoom_box.setValue(round(z * 100)),
                                              self.zoom_box.blockSignals(False)))
        zbox = QWidgetAction(self)
        zbox.setText("拡大率の数字")
        zbox.setDefaultWidget(self.zoom_box)
        S["zoom_box"] = zbox
        bar.addAction(zbox)
        bar.addAction(S["rotate_left"])
        bar.addAction(S["rotate_right"])
        # 角度のつまみ（-180〜180 度）。R を押しながら絵の上をドラッグしても回せる
        self.angle_slider = _S(Qt.Horizontal)
        self.angle_slider.setRange(-180, 180)
        self.angle_slider.setFixedWidth(120)
        self.angle_slider.setToolTip("表示の角度（0 度）。R を押しながら絵の上をドラッグしても回せます")
        self.angle_slider.valueChanged.connect(lambda v: self.canvas.set_angle(float(v)))

        def sync_angle():
            v = round(self.canvas.angle)
            self.angle_slider.blockSignals(True)
            self.angle_slider.setValue(v)
            self.angle_slider.blockSignals(False)
            self.angle_slider.setToolTip(f"表示の角度（{v} 度）。R を押しながら絵の上をドラッグしても回せます")
        self.canvas.view_changed.connect(sync_angle)
        ang = QWidgetAction(self)
        ang.setText("角度")
        ang.setDefaultWidget(self.angle_slider)
        S["angle_slider"] = ang
        bar.addAction(ang)
        bar.addAction(S["rotate_reset"])
        bar.addAction(S["flip_view"])
        bar.addAction(S["view_reset"])
        self.addToolBar(Qt.BottomToolBarArea, bar)
        self.bottom_bar = bar

    def build_shared_actions(self):
        """メニュー・リボン・帯・右クリックで共に使う操作。1 つの QAction を、出す所ごとに足す"""
        c = self.canvas
        rows = (("new", "new", "新規キャンバス", self.new_blank, "Ctrl+N", "白い新しいキャンバスにします（元に戻すで戻せます）"),
                ("open", "open", "開く…", self.open_image, "Ctrl+O", "作業ファイルか絵を開きます"),
                ("save", "save", "保存", self.save_project, "Ctrl+S", "作業ファイルに保存します"),
                ("trash", "trash", "ごみ箱…", self.open_trash, "", "消した絵を見て、元に戻すか本当に消します"),
                ("undo", "undo", "元に戻す", c.undo, "Ctrl+Z", ""),
                ("redo", "redo", "やり直す", c.redo, "Ctrl+Y", ""),
                ("redpen_clear", "", "赤ペンの印を全部消す", c.redpen.clear, "Ctrl+Shift+Backspace", ""),
                ("inspect", "", "検品する", self.inspect_now, "",
                 "今の絵の手・足・顔を検品し、崩れた所を赤ペンで囲みます。直しはしません（直すのは「囲んだ所を直す」）"),
                ("select_all", "select", "すべてを選択", c.select_all, "Ctrl+A", ""),
                ("deselect", "", "選択を解除", lambda: c.set_selection(None), "Ctrl+D", ""),
                ("sel_clear", "eraser", "選択範囲の中を消す", self.selection_clear, "", "選んだレイヤーの、選択範囲の中を消します（絵の上で Delete でも消せます。元に戻すで戻せます）"),
                ("sel_fill", "fill", "選択範囲を塗る", self.selection_fill, "Alt+Backspace", "選択範囲の中を描く色で塗ります"),
                ("copy", "", "コピー", self.selection_copy, "Ctrl+C", "選択範囲の中をコピーします。選択が無いときは見えている絵全体をコピーします"),
                ("cut", "", "切り取り", self.selection_cut, "Ctrl+X", "選択範囲の中をコピーして消します"),
                ("paste", "", "貼り付け", self.paste_clipboard, "Ctrl+V", "コピーした絵を一番上の新しいレイヤーに貼ります"),
                ("fit", "fit", "全体を表示", c.fit, "Ctrl+0", ""),
                ("actual", "zoom", "100%", c.actual, "Ctrl+1", "等倍で表示"),
                ("rotate_left", "", "左に回す", lambda: c.rotate_view(-15), "Ctrl+[", ""),
                ("rotate_right", "rotate", "右に回す", lambda: c.rotate_view(15), "Ctrl+]", ""),
                ("rotate_reset", "", "回転を戻す", c.reset_rotation, "Ctrl+\\", "表示の角度を 0 度に戻します"),
                ("view_reset", "fit", "表示をリセット", c.reset_view, "Ctrl+Alt+0",
                 "回転・左右反転・拡大・位置を初めに戻し、絵の全体を出します（絵は変えません）"),
                ("rotate_dial", "rotate", "角度を指定…", self.ask_angle, "",
                 "表示の角度を数字で決めます（R を押しながらドラッグでも回せます）"),
                ("zoom_in", "zoom", "拡大", lambda: c.set_zoom(c.zoom() * 1.25), "Ctrl+=", ""),
                ("zoom_out", "", "縮小", lambda: c.set_zoom(c.zoom() / 1.25), "Ctrl+-", ""),
                ("zoom_ask", "", "拡大率を指定…", self.ask_zoom, "", "拡大率を % の数字で決めます"),
                ("flip_view", "", "左右反転で表示", lambda: c.flip_view(), "Shift+H",
                 "絵を左右反転して見ます（絵は変えません）。崩れを見つけやすくなります"),
                ("grid", "", "グリッド", lambda: c.set_grid(not c.grid), "Ctrl+'", "絵の上に方眼を出します（保存する絵には入りません）"),
                ("op_history", "history", "操作の履歴…", self.show_op_history, "Ctrl+Alt+Z",
                 "元に戻すの履歴を出します。選ぶとその操作のあとまで戻ります"),
                ("add_layer", "layers", "新しいレイヤー", c.add_layer, "Ctrl+Shift+N", ""),
                ("delete_layer", "", "レイヤーを消す", c.delete_layer, "", "選んでいるレイヤーを消します（元に戻すで戻せます）"),
                ("dup_layer", "", "レイヤーを複製", c.duplicate_layer, "", "選んでいるレイヤーを、すぐ上に同じ絵で複製します"),
                ("layer_copy", "", "レイヤーをコピー", self.layer_copy, "Ctrl+Alt+C", "選んでいるレイヤーを、名前と不透明度ごとコピーします"),
                ("layer_cut", "", "レイヤーを切り取り", self.layer_cut, "Ctrl+Alt+X", "選んでいるレイヤーをコピーしてから消します"),
                ("layer_paste", "", "レイヤーを貼り付け", self.layer_paste, "Ctrl+Alt+V",
                 "コピーしたレイヤーを、選んでいるレイヤーのすぐ上に新しいレイヤーとして貼ります"),
                ("paste_in_place", "", "同じ位置に貼り付け", self.paste_in_place, "Ctrl+Shift+V",
                 "コピーした絵を、コピーした所と同じ位置の新しいレイヤーに貼ります"),
                ("copy_merged", "", "結合してコピー", self.copy_merged, "Ctrl+Shift+C",
                 "見えているレイヤーを重ねた絵の、選択範囲の中をコピーします（選択が無いときは全体）"),
                ("via_copy", "", "選択範囲をコピーして新しいレイヤーへ", lambda: c.layer_via(False), "Ctrl+J",
                 "選択範囲の中を同じ位置の新しいレイヤーに写します。選択が無いときはレイヤーを複製します"),
                ("via_cut", "", "選択範囲を切り取って新しいレイヤーへ", lambda: c.layer_via(True), "Ctrl+Shift+J",
                 "選択範囲の中を元のレイヤーから切り取り、同じ位置の新しいレイヤーに移します"),
                ("merge_down", "", "下のレイヤーと結合", c.merge_down, "", "選んでいるレイヤーを、すぐ下のレイヤーに結合します"),
                ("clear_layer", "", "レイヤーの中を消す", c.clear_layer, "", "選んでいるレイヤーの絵を全部消します（レイヤーは残ります）"),
                ("flip_layer_h", "", "レイヤーを左右反転", lambda: c.flip_layer(True), "", "選んでいるレイヤーの絵そのものを左右に反転します"),
                ("flip_layer_v", "", "レイヤーを上下反転", lambda: c.flip_layer(False), "", "選んでいるレイヤーの絵そのものを上下に反転します"),
                ("tour", "help", "使い方ツアー", self.start_tour, "F1", ""),
                ("draw", "ai", "描く", self.send, "", "書いた内容で AI に描かせます"))
        self.shared: dict[str, QAction] = {}
        for key, ic, label, fn, short, tip in rows:
            a = QAction(label, self)
            if ic:
                a.setIcon(icon(ic))
            if short:
                a.setShortcut(short)
            a.triggered.connect(lambda _=False, fn=fn: fn())
            a.setToolTip((tip or label) + (f"（{short}）" if short else ""))
            self.shared[key] = a
        for k in ("flip_view", "grid"):
            self.shared[k].setCheckable(True)
        c.view_changed.connect(lambda: (self.shared["flip_view"].setChecked(c.flipped), self.shared["grid"].setChecked(c.grid)))
        self.shared["stop"] = self.emergency_stop
        from atelier.ui import layouts as L
        for name, fn in L.PRESETS.items():
            a = QAction(name, self, triggered=lambda _=False, fn=fn: self.feature_tour("layout", lambda fn=fn: self.apply_layout(fn)))
            a.setToolTip(f"「{name}」の配置にします")
            if name == "おすすめ":
                a.setIcon(icon("layout"))
            self.shared[f"layout:{name}"] = a

    def build_quick_bar(self):
        """よく使う帯。元に戻す・やり直す・赤ペン・描く・止める を、絵のすぐ上の手の届く所に小さく並べる"""
        bar = QToolBar("よく使う帯", self)
        bar.setObjectName("quickbar")
        bar.setIconSize(QSize(18, 18))
        S = self.shared
        for k in ("undo", "redo"):
            bar.addAction(S[k])
        bar.addSeparator()
        if "redpen" in self.tool_actions:
            bar.addAction(self.tool_actions["redpen"])
        bar.addAction(S["draw"])
        # 止めるは置かない。緊急停止の帯がいつも上にあり、ここにも置くと狭い窓で「緊急停止」が 2 つ並んだ
        self.addToolBar(Qt.TopToolBarArea, bar)
        self.quick_bar = bar

    def all_actions(self) -> dict[str, QAction]:
        """帯に置ける操作の一覧。帯の並びはこの名前で覚える"""
        out = dict(self.shared)
        out.update({f"tool:{k}": a for k, a in self.tool_actions.items()})
        out.update({f"panel:{k}": a for k, a in self.panel_actions.items()})
        return out

    def setup_customizing(self):
        """メニューと帯の並べ替え・出し入れ・固定を、覚えた形で当てる（版を上げても利用者の形を残す）"""
        from atelier.ui import menu_editor as menuedit
        self.bars_editor = menuedit.Bars(self, self.layout_store, {
            "よく使う帯": self.quick_bar, "道具の帯": self.tools, "欄の帯": self.panel_bar, "下の帯": self.bottom_bar},
            self.all_actions())
        self.menus_editor = menuedit.Menus(self, self.layout_store)

    def edit_menus(self):
        from atelier.ui.menu_editor import MenuEditor
        return MenuEditor(self, self.menus_editor)

    def context_builders(self) -> dict:
        """編集できる右クリック。名前 → 作る関数（編集の窓が中身を見るために作る）"""
        from PySide6.QtCore import QPoint
        lp = self.layer_panel
        return {"キャンバス": lambda: self.build_canvas_menu(),
                "レイヤー": lambda: lp.context_menu(lp.list.visualItemRect(lp.list.item(lp.row_of(self.canvas.current))).center())
                if lp.list.count() else lp.context_menu(QPoint(-5, -5))}

    def arrange_context(self, name: str, m):
        ed = getattr(self, "menus_editor", None)
        if ed is not None:
            ed.arrange_context(name, m)
        return m

    def edit_context_menu(self, name: str):
        dlg = self.edit_menus()
        dlg.pick.setCurrentText("右クリック: " + name)
        dlg.exec()
        return dlg

    FIX_TEXT_HINT = ("どう直すかが書かれていません。印を右クリックして「言葉で指示…」で印に指示を書くか、"
                     "AI の欄の「指示」に書いてから、もう一度押してください")

    def edit_bars(self):
        from atelier.ui.menu_editor import BarEditor
        return BarEditor(self, self.bars_editor)

    def createPopupMenu(self):
        """帯やメニューの帯の右クリック。出し入れの一覧に、帯とメニューの編集と固定を足す"""
        m = super().createPopupMenu() or __import__("PySide6.QtWidgets", fromlist=["QMenu"]).QMenu(self)
        m.addSeparator()
        m.addAction(self.edit_bars_action)
        m.addAction(self.edit_menus_action)
        m.addAction(self.lock_bars_action)
        return m

    def notify(self, text: str, kind: str = "info", detail: str = "", on_click=None):
        """右下に知らせを出す（作業は止めない）。出すか・何秒で消すか・押すまで残すかは設定の「通知」で種類ごとに決める。
        出さない種類も、進み具合の欄の「知らせ」には必ず残す（あとから見返せるように）"""
        from atelier.ui.notice import Notice
        from atelier.ui.notice_rules import KEEP, OFF, rule
        act = getattr(self, "activity", None)
        if act is not None and hasattr(act, "note"):
            act.note(text + (f"　{detail}" if detail else ""), kind)
        how, sec = rule(getattr(self, "settings", None), kind)
        if how == OFF:
            return None
        return Notice(self, text, kind, ms=None if how == KEEP else sec * 1000, detail=detail, on_click=on_click)

    def build_ribbon(self):
        """上部のリボン。メニューと同じ操作を、タブごとに大きなアイコンで並べる"""
        from atelier.ui import ribbon as ribbon_mod
        from atelier.ui.ribbon import Ribbon

        def act(key, label, fn, tip=""):
            a = QAction(icon(key), label, self, triggered=fn)
            a.setToolTip(tip or label)
            return a
        p = self.panels
        S = self.shared
        r = Ribbon()
        r.add_page("ホーム", [
            ("ファイル", [S["new"], S["open"], S["save"]]),
            ("編集", [S["undo"], S["redo"]]),
            ("選択", [S["select_all"], S["deselect"]]),
        ])
        t = self.tool_actions
        # 同じ系統の道具は 1 つのボタンにまとめる（▼か長押しで中を選ぶ）。系統は CLIP STUDIO PAINT の道具と
        # Photoshop の道具のグループに合わせた（docs/knowledge/ribbon-families.md）。道具を 1 つずつ並べると、
        # 似た物が横に並んで帯が窓の幅を超え、どれが同じ働きの仲間かも見えなかった
        F = ribbon_mod.Family

        def tools(*keys):
            return [t[k] for k in keys]
        r.add_page("描く", [
            ("選択", [F("移動", tools("move")), F("選択", tools("select", "lasso", "polygon", "autosel"), "選択の道具（四角・投げなわ・多角形・自動選択）")]),
            ("描く", [F("ペン", tools("pen", "spray"), "ペン系（ペン・スプレー）"),
                     F("消しゴム", tools("eraser")),
                     F("色を混ぜる", tools("blur", "smudge"), "色を混ぜる道具（ぼかし・指先）")]),
            ("塗り", [F("塗り", tools("fill", "gradient"), "塗りの道具（塗りつぶし・グラデーション）")]),
            ("図形・文字", [F("図形", tools("line", "rect", "ellipse", "polyshape", "regpoly"),
                            "図形の道具（直線・四角・楕円・多角形・正多角形）"), F("文字", tools("text"))]),
            ("定規・対称", [F("定規", list(self.ruler_actions.values()), "定規（平行線・同心円・放射・パース）", icon("line")),
                         F("対称", list(self.symmetry_actions.values()), "対称定規（左右・上下・点対称）", icon("regpoly"))]),
            ("色", [t["eyedropper"], act("palette", "入れ替え", self.canvas.swap_colors, "描く色と背景色を入れ替える（X）")]),
            ("表示の道具", [F("手のひら・拡大", tools("hand", "zoom"), "表示を動かす道具（手のひら・拡大）")]),
            ("AI", [F("赤ペン", tools("redpen"))]),
        ])

        def ai(mode):
            p["chat"][0].show()
            p["chat"][0].raise_()
            self.mode.setCurrentIndex(mode)
            self.ai_panel.sections["描く内容"].set_open(True)
            self.entry.setFocus()
        r.add_page("AI", [
            ("描く", [S["draw"], act("ai", "頼んで描く", lambda: ai(0), "描きたい絵を書いて AI に描かせる"),
                     act("rough", "ラフから", lambda: ai(1), "キャンバスの線に沿って AI に描かせる")]),
            ("模型", [act("models", "絵の模型", lambda: self.ai_menu.exec(self.cursor().pos()), "絵の模型を切り替える"),
                     act("settings", "管理", self.manage_models, "模型の一覧・取得・更新・削除")]),
        ])
        r.add_page("表示", [
            ("キャンバス", [F("拡大率", [S["fit"], S["actual"], S["zoom_ask"]], "表示の大きさ（全体・100%・倍率を入れる）")]),
            ("回転・反転", [F("回転", [S["rotate_left"], S["rotate_right"], S["rotate_dial"]], "表示の回転（左・右・角度を回す）"),
                         S["flip_view"], S["view_reset"]]),
            ("補助", [S["grid"], S["op_history"]]),
            ("欄", [self.panel_actions[k] for k in PANEL_ORDER]),
            ("配置", [S["layout:おすすめ"],
                     act("layout", "配置…", lambda: self.layout_menu.exec(self.cursor().pos()), "決まった配置・寄せ・等分・保存")]),
            ("ヘルプ", [S["tour"]]),
        ])
        # タブはドラッグで並べ替えられ、並びを覚える（「帯を固定する」で動かなくなる）
        r.tabBar().setMovable(True)
        order = self.layout_store.value("ribbon/order")
        if order:
            names = str(order).split("\t")
            for i, name in enumerate(names):
                j = next((k for k in range(r.count()) if i18n.ja(r.tabText(k)) == name), -1)
                if j >= 0 and j != i and i < r.count():
                    r.tabBar().moveTab(j, i)
        r.tabBar().tabMoved.connect(lambda *_: self.layout_store.setValue(
            "ribbon/order", "\t".join(i18n.ja(r.tabText(k)) for k in range(r.count()))))   # 英語の画面でも日本語の名前で残す
        r.setCurrentIndex(next((k for k in range(r.count()) if r.tabText(k) == "描く"), 0))   # 初めは「描く」を開いておく
        # タブを右クリックすると、並びを変える窓を出す（ドラッグのほかに、上へ・下へでも並べ替えられる）
        r.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        r.tabBar().customContextMenuRequested.connect(
            lambda pos: self._ribbon_menu().exec(r.tabBar().mapToGlobal(pos)))
        bar = QToolBar("リボン", self)
        bar.setObjectName("ribbonbar")
        # リボンも上下左右の端や別ウィンドウへ動かせる（前は動かせなかった）。「帯を固定する」で止められる
        bar.addWidget(r)
        self.insertToolBar(self.options, bar)     # リボンを道具の設定の帯の前に入れ、
        self.insertToolBarBreak(self.options)     # 道具の設定の帯はリボンの下の段に置く
        self.ribbon, self.ribbon_bar = r, bar

    def move_panel(self, dock: QDockWidget, area):
        """欄を左・右・下・上のどこかへ移す。移した先で中身をふわっと出す"""
        from atelier.ui.motion import fade_in
        self.feature_tour("panel_place")
        dock.titleBarWidget().expand()
        dock.setFloating(False)
        self.addDockWidget(area, dock)
        dock.show()
        if dock.widget() is not None:
            fade_in(dock.widget())

    def place_bar(self, bar: QToolBar, area):
        self.feature_tour("bars")
        self.addToolBar(area, bar)
        bar.show()

    def panel_in_front(self, key: str) -> bool:
        """欄が出ていて、タブの裏に隠れていないか"""
        d = self.panels[key][0]
        if d.isHidden():
            return False
        if d.isFloating():
            return d.isVisible()
        return d.isVisible() and not d.visibleRegion().isEmpty()

    def toggle_panel(self, key: str):
        """欄の帯・ウィンドウのメニュー・F キーで押したとき。隠れていれば出して前に出し、前に出ていれば隠す"""
        d = self.panels[key][0]
        if self.panel_in_front(key):
            d.hide()
        else:
            was_hidden = d.isHidden()
            d.show()
            d.raise_()
            title = d.titleBarWidget()
            if getattr(title, "collapsed", False):
                title.toggle()   # 畳んだままだと出しても中身が見えない
            if was_hidden:
                self.feature_tour(key)
        self.panel_actions[key].setChecked(not d.isHidden())

    def _appear(self, d: QDockWidget, on: bool):
        """隠していた欄を出したときだけ、中身をふわっと出す（タブの切り替えでは動かさない）"""
        from atelier.ui.motion import fade_in
        if on and getattr(d, "_was_hidden", False) and d.widget() is not None:
            fade_in(d.widget())
        d._was_hidden = not on and d.isHidden()

    def _as_window(self, d: QDockWidget, floating: bool):
        """別ウィンドウにした欄を、ふつうのウィンドウの枠にする。上下左右と四隅の端をつかんで大きさを変えられ、最大化もできる"""
        title = d.titleBarWidget()
        if isinstance(title, PanelTitle):
            title.expand()
        if floating:
            d.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
            d.show()
            self.keep_on_screen(d)

    def keep_on_screen(self, d: QDockWidget):
        """別ウィンドウの欄を画面の中に収める。保存した配置を別の画面の大きさで読んだときや、
        すべて別ウィンドウにして並べたときに、画面の外に出て見えなくなった"""
        # 主の窓の画面だけに収めると、2 台目のモニターへ置いた欄まで 1 台目へ引き戻した。重なる画面の中へ収める
        self.keep_window_on_screen(d)

    def _collapse_all(self, on: bool):
        for d, _area in self.panels.values():
            title = d.titleBarWidget()
            if isinstance(title, PanelTitle) and title.collapsed != on:
                title.toggle()

    def _ribbon_menu(self):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("リボンの並びを変える…", self.edit_ribbon_order)
        return m

    def edit_ribbon_order(self):
        from atelier.ui.ribbon import OrderDialog
        self.ribbon_order_dialog = OrderDialog(self.ribbon, self)
        self.ribbon_order_dialog.exec()

    def ask_angle(self):
        from PySide6.QtWidgets import QInputDialog
        v, ok = QInputDialog.getInt(self, "表示の角度", "角度（度。右回りが +）", round(self.canvas.angle), -180, 180, 1)
        if ok:
            self.canvas.set_angle(float(v))

    def ask_zoom(self):
        from PySide6.QtWidgets import QInputDialog
        v, ok = QInputDialog.getInt(self, "拡大率", "拡大率（%）", round(self.canvas.zoom() * 100), 5, 3200, 5)
        if ok:
            self.canvas.set_zoom(v / 100)

    def show_op_history(self):
        """操作の履歴（履歴の欄の「操作」のタブ）を出す"""
        dock = self.panels["history"][0]
        dock.show()
        dock.raise_()
        tabs = self.activity.tabs
        tabs.setCurrentIndex(tabs.indexOf(self.activity.ops))

    def toggle_all(self):
        # 文字の欄（チャット、描く内容、赤ペンの指示、名前の書き換え）で打った Tab は、欄を隠さずに次の欄へ移る。
        # 前は文字を打っている途中の Tab で欄が全部消え、打っていた欄も見えなくなった
        from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox)) or (
                isinstance(fw, QComboBox) and fw.isEditable()):
            nxt = fw.nextInFocusChain()
            while nxt is not None and nxt is not fw and not (
                    nxt.isVisible() and nxt.isEnabled() and nxt.focusPolicy() & Qt.TabFocus):
                nxt = nxt.nextInFocusChain()
            if nxt is not None and nxt is not fw:
                nxt.setFocus(Qt.TabFocusReason)
            return
        on = not getattr(self, "_all_hidden", False)
        if on:
            # 隠す前に見えていた欄と帯だけを覚え、次の Tab でそれだけを出す（前は閉じていた欄まで全部出た）
            self._shown_before = [w for w in self._all_bars() if w.isVisible()]
            for w in self._shown_before:
                w.setVisible(False)
        else:
            for w in getattr(self, "_shown_before", None) or self._all_bars():
                w.setVisible(True)
            self._shown_before = []
        self._all_hidden = on
        if on:
            self.statusBar().showMessage("欄を隠しました。Tab でまた出します", 6000)

    def _all_bars(self):
        return [d for d, _area in self.panels.values()] + [self.tools, self.options, self.panel_bar,
                                                           self.bottom_bar, self.ribbon_bar]

    def _show_all(self, on: bool):
        for d, _area in self.panels.values():
            d.setVisible(on)
        self.tools.setVisible(on)
        self.options.setVisible(on)
        self.panel_bar.setVisible(on)
        self.bottom_bar.setVisible(on)
        self.ribbon_bar.setVisible(on)

    def float_all(self):
        """欄をすべて別のウィンドウにして、少しずつずらして並べる"""
        x, y = self.geometry().right() - 380, self.geometry().top() + 40
        for i, (d, _area) in enumerate(self.panels.values()):
            d.show()
            d.setFloating(True)
            self._as_window(d, True)   # 前の並びで既に外に出ていると topLevelChanged が来ず、窓の枠にならなかった
            d.resize(360, 520)
            d.move(x - i * 40, y + i * 40)
            self.keep_on_screen(d)

    def free_layout(self):
        """欄の見出しをドラッグすると、左右上下のどこにでも置け、重ねるとタブになる"""
        for d, _area in self.panels.values():
            d.show()
            d.setFeatures(PANEL)
        self.tools.setMovable(True)
        self.statusBar().showMessage("欄をドラッグして配置できます", 4000)

    def closeEvent(self, e):
        if getattr(self, "dirty", False) and self.isVisible() and not getattr(self, "closing_checked", False):
            box = QMessageBox(QMessageBox.Question, "閉じる前に", "作業ファイルに保存していない変更があります。保存しますか。", parent=self)
            save = box.addButton("保存", QMessageBox.AcceptRole)
            drop = box.addButton("保存しない", QMessageBox.DestructiveRole)
            box.addButton("やめる", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is save and not self.save_project(wait=True) or box.clickedButton() not in (save, drop):
                e.ignore()
                return
        if not self.finish_threads_before_close():
            e.ignore()
            return
        self.work_save()   # 今の絵の作業を残す（開き直して同じ絵を出せば元のとおりに戻る）
        self.wait_io()   # 裏で書いている保存を書き終えてから閉じる（書きかけの作業ファイルを残さない）
        # アプリ全体で効くキー（緊急停止、操作を探す）は、閉じた窓の分を外す。残すと、閉じた窓の動作が
        # キーの一覧に残り続け、窓を何度も開け閉めしたあとにキーを押すとアプリごと落ちた
        from PySide6.QtGui import QKeySequence
        for a in (getattr(self, "emergency_stop", None), getattr(self, "palette_action", None)):
            if a is not None:
                a.setShortcut(QKeySequence())
                a.setEnabled(False)
        if getattr(self, "_io_queue", None) is not None:   # 保存の糸を終える（窓ごとに残ると増え続けた）
            self._io_closed = True
            self._io_queue.put(None)
            self._io_queue = None
        self.layout_store.setValue("running", 0)   # 正しく閉じた印（次の起動で戻すかを聞かない）
        self.close_groups()   # 独立したウィンドウは親を持たないので、ここで並びを残して閉じる
        # 次に開いたときも同じ並びにする
        self.layout_store.setValue("geometry9", self.saveGeometry())
        self.layout_store.setValue("state9", self.saveState())
        if getattr(self, "ai_tabs", None) is not None:
            self.ai_tabs.save()
        from atelier.models import ratings
        ratings.off_change(self._models_changed)   # 閉じた窓を模型の一覧の知らせ先から外す
        super().closeEvent(e)
