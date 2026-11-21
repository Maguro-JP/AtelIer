"""メインの窓。真ん中にキャンバス、左に道具の帯と色・ブラシの欄、右に全体表示・レイヤー・操作の履歴を並べる。"""
from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (QCheckBox, QDockWidget, QGridLayout, QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QSlider, QSpinBox, QToolBar, QToolButton, QWidget)

from atelier.app.actions import build_shared_actions
from atelier.app.edit_commands import EditCommands
from atelier.app.file_commands import AUTOSAVE_MS, FileCommands
from atelier.app.tools import FILLABLE, PANEL, SHAPE_TIPS, TOOLS, tool_label
from atelier.paint.canvas import SYMMETRY, Canvas
from atelier.paint.drawing_assist import RULERS
from atelier.panels.brush_panel import BrushPanel
from atelier.panels.color_panel import ColorPanel
from atelier.panels.layer_panel import LayerPanel
from atelier.panels.navigator import Navigator
from atelier.panels.operation_history import OperationHistory
from atelier.ui import logo, themes
from atelier.ui.icons import icon

ORGANIZATION, APPLICATION = "AtelIer", "atelier"   # QSettings の置き場
TOOL_COLUMNS = 2   # 道具の帯の列の数


class MainWindow(EditCommands, FileCommands, QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = QSettings(ORGANIZATION, APPLICATION)   # 欄の配置・テーマ・正しく閉じた印
        self.setWindowTitle(logo.NAME)
        self.resize(1400, 900)

        self.canvas = Canvas()
        self.canvas.new_canvas()
        self.setCentralWidget(self.canvas)
        self.canvas.refused.connect(lambda why: self.notify(why, 6000))
        self.canvas.text_wanted.connect(self.ask_text)
        self.canvas.shaped.connect(lambda name: self.notify(f"{name}に整えました（元に戻すで整える前の線に戻ります）"))
        self.canvas.history_changed.connect(lambda: setattr(self, "dirty", True))

        self.shared = build_shared_actions(self)
        self._build_tool_bar()
        self._build_options_bar()
        self._build_panels()
        self._build_menus()
        self._build_status()
        self._tool_changed("pen")

        self.dirty = False
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_MS)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        self._restore_layout()

    # ---- 組み立て ----
    def _build_tool_bar(self):
        """左端: 道具。2 列に並べる（1 列だと窓の高さに収まらず、下の道具に手が届かなかった）"""
        bar = QToolBar("道具", self)
        bar.setObjectName("tools")
        self.addToolBar(Qt.LeftToolBarArea, bar)
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(2)
        group = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}
        self.tool_buttons: dict[str, QToolButton] = {}
        row = col = 0
        for key, label, shortcut in TOOLS:
            if key is None:   # 区切り: 次の組は新しい行から始め、間を空ける
                row += 1 if col else 0
                grid.setRowMinimumHeight(row, 8)
                row, col = row + 1, 0
                continue
            act = QAction(icon(key), label, self, checkable=True, shortcut=shortcut)
            act.setToolTip(SHAPE_TIPS.get(key, f"{label}（{shortcut}）"))
            act.triggered.connect(lambda _=False, k=key: (self.canvas.set_tool(k), self._tool_changed(k)))
            group.addAction(act)
            self.addAction(act)   # 帯を隠してもキーが効くよう、窓にも持たせる
            button = QToolButton()
            button.setDefaultAction(act)
            button.setIconSize(QSize(22, 22))
            button.setAutoRaise(True)
            grid.addWidget(button, row, col)
            self.tool_actions[key], self.tool_buttons[key] = act, button
            row, col = (row + 1, 0) if col == TOOL_COLUMNS - 1 else (row, col + 1)
        grid.setRowStretch(row + 1, 1)
        bar.addWidget(box)
        self.tool_actions["pen"].setChecked(True)
        # 絵の上の R は、押して離すとぼかし、押したままドラッグすると表示を回す（canvas.on_r_tap）
        self.canvas.on_r_tap = self.tool_actions["blur"].trigger
        self.tool_actions["blur"].setToolTip("ぼかし（R）。絵の上で R を押したままドラッグすると表示を回します")
        for text, shortcut, fn in (("描く色と背景の色を入れ替える", "X", self.canvas.swap_colors),
                                   ("色を黒と白に戻す", "D", self.canvas.reset_colors)):
            self.addAction(QAction(text, self, shortcut=shortcut, triggered=fn))

    def _build_options_bar(self):
        """上: 選んだ道具の設定（太さ・濃さ・形の塗り）。絵のすぐ上に置いて手元で変える"""
        bar = QToolBar("道具の設定", self)
        bar.setObjectName("options")
        self.addToolBar(Qt.TopToolBarArea, bar)
        self.tool_name = QLabel("ペン")
        self.tool_name.setObjectName("toolName")
        bar.addWidget(self.tool_name)
        bar.addSeparator()
        bar.addWidget(QLabel(" 太さ "))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(1, 300)
        self.size_slider.setFixedWidth(160)
        self.size_box = QSpinBox()
        self.size_box.setRange(1, 300)
        self.size_box.setSuffix(" px")
        self.size_box.setValue(self.canvas.size)
        self.size_slider.setValue(self.canvas.size)
        self.size_box.valueChanged.connect(lambda v: (setattr(self.canvas, "size", v), self.size_slider.setValue(v)))
        self.size_slider.valueChanged.connect(self.size_box.setValue)
        self.canvas.brush_changed.connect(self.size_box.setValue)
        bar.addWidget(self.size_slider)
        bar.addWidget(self.size_box)
        bar.addSeparator()
        bar.addWidget(QLabel(" 濃さ "))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(120)
        self.opacity_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(
            lambda v: (setattr(self.canvas, "brush_opacity", v / 100), self.opacity_label.setText(f"{v}%")))
        bar.addWidget(self.opacity_slider)
        bar.addWidget(self.opacity_label)
        bar.addSeparator()
        self.fill_shapes = QCheckBox("塗り")
        self.fill_shapes.setToolTip("四角・楕円・多角形・正多角形を、線だけでなく中まで塗る")
        self.fill_shapes.toggled.connect(lambda on: setattr(self.canvas, "fill_shapes", on))
        # 帯に置いた部品は、部品ではなく帯の項目を隠さないと消えない
        self.fill_shapes_act = bar.addWidget(self.fill_shapes)
        self.poly_sides = QSpinBox()
        self.poly_sides.setRange(3, 24)
        self.poly_sides.setValue(self.canvas.poly_sides)
        self.poly_sides.setSuffix(" 角")
        self.poly_sides.setToolTip("正多角形の角（辺）の数")
        self.poly_sides.valueChanged.connect(lambda v: setattr(self.canvas, "poly_sides", v))
        self.poly_sides_act = bar.addWidget(self.poly_sides)

    def _dock(self, name: str, title: str, widget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(PANEL)
        self.addDockWidget(area, dock)
        self.panels[name] = dock
        return dock

    def _build_panels(self):
        self.panels: dict[str, QDockWidget] = {}
        self.color_panel = ColorPanel(self.canvas)
        self.canvas.used_color.connect(self.color_panel.remember)
        self.color_panel.eyedropper_wanted.connect(lambda: self.tool_actions["eyedropper"].trigger())
        self._dock("color", "カラー", self.color_panel, Qt.LeftDockWidgetArea)

        self.brush_panel = BrushPanel(self.canvas)
        self.brush_preview = self.brush_panel.preview
        self.brush_panel.brush_list.currentTextChanged.connect(self._brush_selected)
        for signal in (self.size_box.valueChanged, self.opacity_slider.valueChanged, self.color_panel.color_changed,
                       self.color_panel.mode_changed):
            signal.connect(lambda *_a: self.brush_preview.update())
        self._dock("brushes", "ブラシ", self.brush_panel, Qt.LeftDockWidgetArea)

        self.navigator = Navigator(self.canvas)
        self._dock("view", "全体", self.navigator, Qt.RightDockWidgetArea)
        self.layer_panel = LayerPanel(self.canvas)
        self.layer_panel.shared = self.shared   # 右クリックにメニューと同じ操作（同じキー）を出す
        self._dock("layers", "レイヤー", self.layer_panel, Qt.RightDockWidgetArea)
        self.operation_history = OperationHistory(self.canvas)
        self._dock("history", "操作の履歴", self.operation_history, Qt.RightDockWidgetArea)

    def _build_menus(self):
        S = self.shared
        bar = self.menuBar()

        def menu(title: str, *keys):
            m = bar.addMenu(title)
            m.setToolTipsVisible(True)
            for k in keys:
                if k is None:
                    m.addSeparator()
                else:
                    m.addAction(S[k] if isinstance(k, str) else k)
            return m

        def act(text: str, fn, shortcut: str = "", tip: str = "") -> QAction:
            a = QAction(text, self, triggered=lambda _=False: fn())
            if shortcut:
                a.setShortcut(shortcut)
            if tip:
                a.setToolTip(tip)
            return a

        file = menu("ファイル", "new", "open", "save", act("名前を付けて保存…", lambda: self.save_project(ask=True), "Ctrl+Shift+S"), None)
        out = file.addMenu("書き出す")
        out.addAction(act("PNG（重ねた 1 枚）…", self.export_png, "Ctrl+E"))
        out.addAction(act("PSD（レイヤーごと）…", self.export_psd))
        file.addSeparator()
        file.addAction(act("終了", self.close, "Ctrl+Q"))

        menu("編集", "undo", "redo", None, "cut", "copy", "copy_merged", "paste", "paste_in_place", None,
             "layer_cut", "layer_copy", "layer_paste")

        view = menu("表示", "fit", "actual", "zoom_in", "zoom_out", "zoom_ask", None, "rotate_left", "rotate_right",
                    "rotate_dial", "rotate_reset", "flip_view", "view_reset", None, "grid")
        self._build_symmetry_menu(view.addMenu("対称定規"))
        self._build_ruler_menu(view.addMenu("定規"))
        shapes = view.addMenu("図形")
        shapes.setToolTipsVisible(True)
        for k in ("line", "rect", "ellipse", "polyshape", "regpoly"):
            shapes.addAction(self.tool_actions[k])
        view.addSeparator()
        self.theme_menu = view.addMenu("テーマ")
        self.theme_menu.aboutToShow.connect(self._fill_theme_menu)

        menu("選択範囲", "select_all", "deselect", None, self.tool_actions["select"], self.tool_actions["lasso"],
             self.tool_actions["polygon"], None, "sel_clear", "sel_fill", "copy", "cut")

        menu("レイヤー", "add_layer", "dup_layer", "delete_layer", "clear_layer", None,
             "layer_cut", "layer_copy", "layer_paste", "via_copy", "via_cut", None, "flip_layer_h", "flip_layer_v", None,
             act("画像をレイヤーとして読み込む…", self.import_layer), act("レイヤーを PNG で保存…", self.save_layer_png),
             act("全部のレイヤーを PNG で書き出す…", self.export_layers_png), None, "merge_down", "merge_visible")

        # ロゴはメニューの帯の右端に出す
        self.logo_label = QLabel()
        self.logo_label.setObjectName("logo")
        self.logo_label.setToolTip("AtelIer（アトリエ）")
        self.logo_label.setContentsMargins(0, 0, 12, 0)
        bar.setCornerWidget(self.logo_label, Qt.TopRightCorner)
        self._paint_logo()

        window = bar.addMenu("ウィンドウ")
        for dock in self.panels.values():
            window.addAction(dock.toggleViewAction())
        window.addSeparator()
        window.addAction(act("並びを初めの形に戻す", self.reset_layout))

    def _build_symmetry_menu(self, menu):
        """ブラシの欄の「対称」と同じ設定を、メニューからも切り替えられるようにする"""
        group = QActionGroup(menu)
        box = self.brush_panel.symmetry
        self.symmetry_actions: dict[str, QAction] = {}
        for key, label in (("", "なし"), *SYMMETRY.items()):
            a = QAction(label, menu, checkable=True)
            a.setToolTip("描いた線と図形を、軸の反対側にも同時に描きます" if key else "対称を切ります")
            a.triggered.connect(lambda _=False, k=key: box.setCurrentIndex(box.findData(k)))
            group.addAction(a)
            menu.addAction(a)
            self.symmetry_actions[key] = a
        self.symmetry_actions[""].setChecked(True)
        menu.addSeparator()
        menu.addAction(QAction("軸を真ん中に戻す", menu, triggered=lambda: self.canvas.set_axis_center(None)))
        self.canvas.view_changed.connect(lambda: self.symmetry_actions[self.canvas.symmetry].setChecked(True))

    def _build_ruler_menu(self, menu):
        """ブラシの欄の「定規」「描いて止めると形を整える」と同じ設定"""
        menu.setToolTipsVisible(True)
        group = QActionGroup(menu)
        box = self.brush_panel.ruler
        self.ruler_actions: dict[str, QAction] = {}
        for key, label in (("", "なし"), *RULERS.items()):
            a = QAction(label, menu, checkable=True)
            a.setToolTip("なぞる線と直線を、この定規に沿わせます" if key else "定規を切ります")
            a.triggered.connect(lambda _=False, k=key: box.setCurrentIndex(box.findData(k)))
            group.addAction(a)
            menu.addAction(a)
            self.ruler_actions[key] = a
        self.ruler_actions[""].setChecked(True)
        menu.addSeparator()
        menu.addAction(QAction("定規の点を初めの所に戻す", menu, triggered=lambda: self.canvas.set_ruler_point(0, None)))
        self.quickshape_action = QAction("描いて止めると形を整える", menu, checkable=True)
        self.quickshape_action.toggled.connect(self.brush_panel.quickshape.setChecked)
        self.brush_panel.quickshape.toggled.connect(self.quickshape_action.setChecked)
        menu.addAction(self.quickshape_action)
        self.canvas.view_changed.connect(lambda: self.ruler_actions[self.canvas.ruler].setChecked(True))

    def _build_status(self):
        """下の帯。左に知らせ、右に道具・座標・キャンバスの大きさ・レイヤー・拡大率を並べる"""
        sb = self.statusBar()

        def cell(tip: str, width: int = 0) -> QLabel:
            lb = QLabel()
            lb.setObjectName("statusCell")
            lb.setToolTip(tip)
            if width:
                lb.setMinimumWidth(width)
            sb.addPermanentWidget(lb)
            return lb
        self.st_tool = cell("今の道具", 70)
        self.st_pos = cell("カーソルの位置（画素）", 90)
        self.st_size = cell("キャンバスの大きさ", 90)
        self.st_layer = cell("描いているレイヤー", 90)
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setObjectName("statusButton")
        self.zoom_label.setToolTip("拡大率。押すと全体を表示します")
        self.zoom_label.clicked.connect(self.canvas.fit)
        sb.addPermanentWidget(self.zoom_label)
        self.canvas.zoomed.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f}%"))
        self.canvas.moved.connect(lambda x, y: self.st_pos.setText(f"{x}, {y}"))
        self.canvas.changed.connect(self._status_doc)
        self._status_doc()

    def _paint_logo(self):
        t = themes.current
        html = logo.wordmark_html(t.get("a1", "#ff7a1a"), t.get("bartext", "#e8e8ea"))
        self.logo_label.setText(f'<span style="font-size:15pt">{html}</span>')

    def _status_doc(self):
        w, h = self.canvas.size_px()
        self.st_size.setText(f"{w}×{h}")
        layers = self.canvas.layers
        if layers:   # 消した直後の古い番号でも落ちない
            self.st_layer.setText(layers[max(0, min(self.canvas.current, len(layers) - 1))].name)

    # ---- 道具とブラシ ----
    def _tool_changed(self, key: str):
        """道具の設定の見出しを選んだ道具の名前にし、その道具で使う設定だけを出す"""
        label = tool_label(key)
        self.tool_name.setText(label)
        if hasattr(self, "st_tool"):
            self.st_tool.setText(label)
        self.fill_shapes_act.setVisible(key in FILLABLE)
        self.poly_sides_act.setVisible(key == "regpoly")
        if hasattr(self, "brush_preview"):
            self.brush_preview.update()

    def _brush_selected(self, name: str):
        """ブラシを選ぶと道具も替わる（消しゴムのブラシなら消しゴム、ほかはペン）"""
        key = "eraser" if name == "消しゴム" else "pen"
        self.tool_actions[key].setChecked(True)
        self._tool_changed(key)

    def ask_text(self, pos):
        """文字の道具で押した所に置く文字を聞く。空なら何もしない"""
        text, ok = QInputDialog.getText(self, "文字", "置く文字（描く色・太さの 4 倍の大きさで置きます）")
        if ok and text:
            self.canvas.place_text(pos, text)

    def ask_angle(self):
        v, ok = QInputDialog.getInt(self, "表示の角度", "角度（度。右回りが +）", round(self.canvas.angle), -180, 180, 1)
        if ok:
            self.canvas.set_angle(float(v))

    def ask_zoom(self):
        v, ok = QInputDialog.getInt(self, "拡大率", "拡大率（%）", round(self.canvas.zoom() * 100), 5, 3200, 5)
        if ok:
            self.canvas.set_zoom(v / 100)

    # ---- 知らせ ----
    def notify(self, text: str, msec: int = 4000):
        """下の帯に短い知らせを出す（作業は止めない）"""
        self.statusBar().showMessage(text, msec)

    def notify_error(self, title: str, detail: str = ""):
        """失敗は見落とさないよう、窓で知らせる"""
        self.statusBar().showMessage(title, 8000)
        QMessageBox.warning(self, title, detail or title)

    # ---- テーマと欄の配置 ----
    def _fill_theme_menu(self):
        self.theme_menu.clear()
        now = self.store.value("theme", themes.DEFAULT)
        for name in themes.all_names():
            a = self.theme_menu.addAction(name, lambda n=name: self.set_theme(n))
            a.setCheckable(True)
            a.setChecked(name == now)

    def set_theme(self, name: str):
        from PySide6.QtWidgets import QApplication
        themes.apply(QApplication.instance(), name)
        self.store.setValue("theme", name)
        self._paint_logo()

    def _restore_layout(self):
        self._default_state = self.saveState()
        geometry, state = self.store.value("geometry"), self.store.value("state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def reset_layout(self):
        self.restoreState(self._default_state)
        for dock in self.panels.values():
            dock.setFloating(False)
            dock.show()

    def closeEvent(self, e):
        if not self.confirm_close():
            e.ignore()
            return
        self.dirty = False
        self.autosave_timer.stop()
        self.store.setValue("running", 0)   # 正しく閉じた印（次の起動で戻すかを聞かない）
        self.store.setValue("geometry", self.saveGeometry())
        self.store.setValue("state", self.saveState())
        super().closeEvent(e)
