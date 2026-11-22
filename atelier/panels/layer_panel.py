"""レイヤーの欄。縮小図・表示・ロック・名前・選ぶ・並べ替え・消す。

前は名前と表示の印だけの一覧で、どのレイヤーに描いているかが選択の色でしか分からず、
AI の絵のレイヤーに線を描いてしまったり、名前を変えられなかったりした。
上にあるレイヤーを上に並べる（作画ソフトと同じ順）。選んでいるレイヤーは太字と「✎」で示す。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSlider, QVBoxLayout,
                               QWidget)

THUMB = 40
ROLE_INDEX = Qt.UserRole
ROLE_FOLDER = Qt.UserRole + 1   # フォルダーの見出しの行（フォルダーの名前）。この行の ROLE_INDEX は None
INDENT = "　"   # フォルダーの中のレイヤーの字下げ


def thumbnail(image, size: int = THUMB) -> QPixmap:
    """透明の所が分かるよう、市松の上に縮めた絵を置く"""
    pm = QPixmap(size, size)
    pm.fill(QColor("#d0d0d0"))
    p = QPainter(pm)
    s = size // 4
    for y in range(4):
        for x in range(4):
            if (x + y) % 2:
                p.fillRect(x * s, y * s, s, s, QColor("#f4f4f4"))
    if not image.isNull():
        small = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x, y = (size - small.width()) // 2, (size - small.height()) // 2
        p.drawImage(x, y, small)
        # 白い紙（背景）は市松の明るい升と見分けがつかず、縮小図が空に見えた。紙の端に細い枠を引いて、絵の範囲を見せる
        p.setPen(QColor("#7a7a7a"))
        p.drawRect(x, y, small.width() - 1, small.height() - 1)
    p.end()
    return pm


class LayerPanel(QWidget):
    shared: dict = {}   # 窓の共の操作（コピー・貼り付けなど）。窓が渡す。無ければ右クリックは欄の中の操作だけ

    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.list = QListWidget()
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setToolTip("押すと選び、そのレイヤーに描きます。印で表示を切り替え、ダブルクリックで名前を変えます")
        self.list.setEditTriggers(QListWidget.DoubleClicked | QListWidget.EditKeyPressed)
        self.list.itemChanged.connect(self._changed)
        # ドラッグで並べ替える。右クリックで消す・上下へ・名前・結合。Delete キーで消す
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.model().rowsMoved.connect(self._moved)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence.Delete, self.list, activated=self._delete)
        self.list.currentRowChanged.connect(self._selected)
        self.list.itemDoubleClicked.connect(self._double)
        self.active = QLabel()
        self.active.setToolTip("線を描くレイヤー")
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setToolTip("レイヤーの不透明度")
        self.opacity.valueChanged.connect(lambda v: self.canvas.set_opacity(v / 100))
        # よく使う「足す・消す」だけをボタンにし、並べ替え・ロック・名前は「…」のプルダウンにまとめる（欄を狭く保つ）
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QToolButton
        self.buttons = {}
        row = QHBoxLayout()
        row.setSpacing(2)
        for key, label, tip, fn in (
                ("add", "＋", "新しいレイヤーを選んでいるレイヤーの上に足します（Ctrl+Shift+N）", canvas.add_layer),
                ("delete", "－", "選んでいるレイヤーを消します（Delete。元に戻すで戻せます）", self._delete),
                ("up_b", "▲", "選んでいるレイヤーを 1 つ上へ（ドラッグでも並べ替えられます）", lambda: canvas.move_layer(1)),
                ("down_b", "▼", "選んでいるレイヤーを 1 つ下へ", lambda: canvas.move_layer(-1))):
            bt = QPushButton(label)
            bt.setFixedWidth(34)
            bt.setToolTip(tip)
            bt.clicked.connect(fn)
            row.addWidget(bt)
            self.buttons[key] = bt
        self.more = QToolButton()
        self.more.setText("…")
        self.more.setToolTip("並べ替え・ロック・名前を変える")
        self.more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.more)
        for key, label, fn in (("up", "1 つ上へ", lambda: canvas.move_layer(1)),
                               ("down", "1 つ下へ", lambda: canvas.move_layer(-1)),
                               ("lock", "ロックする（描けなくする）", self.toggle_lock),
                               ("rename", "名前を変える", self.rename_current)):
            act = QAction(label, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
            self.buttons[key] = act
        self.buttons["lock"].setCheckable(True)
        self.more.setMenu(menu)
        row.addWidget(self.more)
        row.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.active)
        lay.addWidget(self.list, 1)
        # 合成モード・クリッピング・透明部分の保護。作画ソフトではレイヤーの欄の上に並ぶ毎日の操作なので、メニューの奥に入れない
        from PySide6.QtWidgets import QComboBox
        from atelier.paint.canvas import BLEND_MODES
        props = QHBoxLayout()
        props.setSpacing(2)
        self.blend = QComboBox()
        for key, (label, _psd, _m) in BLEND_MODES.items():
            self.blend.addItem(label, key)
        self.blend.setToolTip("合成モード。乗算は影、スクリーン・加算は光、オーバーレイは色味を重ねるのに使います")
        self.blend.activated.connect(lambda _i: self._set_prop("blend", self.blend.currentData()))
        props.addWidget(self.blend, 1)
        for key, label, tip in (("clip", "クリップ", "下のレイヤーでクリッピングします。下の絵の描いてある所にだけ見え、はみ出しません"),
                                ("alpha_lock", "保護", "透明部分を保護します。描いてある所の上にだけ塗れます（線画の色替え・影）")):
            bt = QToolButton()
            bt.setText(label)
            bt.setCheckable(True)
            bt.setToolTip(tip)
            bt.toggled.connect(lambda on, k=key: self._set_prop(k, on))
            props.addWidget(bt)
            self.buttons[key] = bt
        lay.addLayout(props)
        lay.addWidget(self.opacity)
        lay.addLayout(row)
        # 線を引くたびに縮小図を作り直すと重いので、手を離してから少し待って 1 回だけ作る
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        canvas.changed.connect(self.refresh)
        canvas.stroke_done.connect(self.timer.start)
        canvas.history_changed.connect(self.timer.start)
        self.refresh()

    def row_of(self, index: int) -> int:
        for r in range(self.list.count()):
            if self.list.item(r).data(ROLE_INDEX) == index:
                return r
        pen = getattr(self.canvas, "redpen", None)
        return len(self.canvas.layers) - 1 - index + (len(pen.marks) if pen is not None else 0)

    def folder_row(self, name: str) -> int:
        for r in range(self.list.count()):
            if self.list.item(r).data(ROLE_FOLDER) == name:
                return r
        return -1

    def _folder_item(self, name: str, f) -> QListWidgetItem:
        from atelier.paint.canvas import BLEND_MODES
        mode = "" if f.blend == "pass" else BLEND_MODES.get(f.blend, BLEND_MODES["normal"])[0]
        extra = "・".join(x for x in (mode, f"{round(f.opacity * 100)}%" if f.opacity < 1 else "") if x)
        item = QListWidgetItem(("▶ " if f.collapsed else "▼ ") + name + (f"（{extra}）" if extra else ""))
        item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable & ~Qt.ItemIsDragEnabled)
        item.setCheckState(Qt.Checked if f.visible else Qt.Unchecked)
        item.setData(ROLE_INDEX, None)
        item.setData(ROLE_FOLDER, name)
        fnt = QFont(item.font())
        fnt.setItalic(True)
        item.setFont(fnt)
        item.setToolTip(f"フォルダー「{name}」。ダブルクリックで畳む・開く。チェックで中を全部隠す・出す。右クリックで名前・合成・不透明度")
        return item

    def refresh(self):
        c = self.canvas
        # 赤ペンの行を選んでいたら、作り直したあとも同じ行を選ぶ。前は描くレイヤーの行に戻り、
        # 「－」を押すと選んだ印ではなくレイヤーが消えた
        old = self.list.currentItem()
        keep = old.data(ROLE_INDEX) if old is not None else None
        self.list.blockSignals(True)
        self.list.clear()
        pen = getattr(c, "redpen", None)
        keep_item = None
        # 赤ペンの印は 1 つずつ別の行にし、一番上に置く（隠す・消す・指示を書き直すを印ごとにできるように）。
        # 指示は絵の上に札で出しっぱなしにすると絵が隠れるので、行の名前と説明に持つ
        for n in (reversed(range(1, len(pen.marks) + 1)) if pen is not None else ()):
            note = pen.texts[n - 1] if n - 1 < len(pen.texts) else ""
            item = QListWidgetItem(f"赤ペン {n}" + (f": {note}" if note else ""))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Unchecked if pen.hidden[n - 1] else Qt.Checked)
            item.setData(ROLE_INDEX, -n)
            item.setForeground(QColor("#ff2d2d"))
            item.setToolTip((f"指示: {note}\n" if note else "指示はまだありません。\n") +
                            "ダブルクリックで指示を書き直す。チェックで隠す・出す（隠した印は直しません）。「－」か Delete でこの印を消す。\n"
                            "保存する絵には入りません")
            self.list.addItem(item)
            if keep == -n:
                keep_item = item
        folders = getattr(c, "folders", {})
        shown_folders = set()
        for i in reversed(range(len(c.layers))):
            layer = c.layers[i]
            on = i == c.current
            fo = folders.get(layer.folder) if layer.folder else None
            if fo is not None and layer.folder not in shown_folders:
                shown_folders.add(layer.folder)
                self.list.addItem(self._folder_item(layer.folder, fo))
            from atelier.paint.canvas import BLEND_MODES
            mode = BLEND_MODES.get(layer.blend, BLEND_MODES["normal"])[0] if layer.blend != "normal" else ""
            # クリッピングは CLIP STUDIO PAINT と同じく字下げと印で示し、どの絵に掛かっているかを一目で分かるようにする
            item = QListWidgetItem(QIcon(thumbnail(layer.image)), (INDENT if fo is not None else "")
                                   + ("　┗ " if layer.clip else "") + layer.name
                                   + (f"（{mode}）" if mode else ""))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
            item.setData(ROLE_INDEX, i)
            f = QFont(item.font())
            f.setBold(on)
            item.setFont(f)
            marks = ("✎ " if on else "") + ("ロック中 " if layer.locked else "") + ("透明部分を保護 " if layer.alpha_lock else "")
            item.setToolTip(marks + layer.name + ("（隠しています）" if not layer.visible else ""))
            self.list.addItem(item)
            if fo is not None and fo.collapsed:
                item.setHidden(True)
            if on and keep_item is None:
                self.list.setCurrentItem(item)
        if keep_item is not None:
            self.list.setCurrentItem(keep_item)
        if c.layers:
            layer = c.layers[max(0, min(c.current, len(c.layers) - 1))]   # 消した直後の古い番号でも落ちない
            self.opacity.blockSignals(True)
            self.opacity.setValue(int(layer.opacity * 100))
            self.opacity.blockSignals(False)
            self.buttons["lock"].setChecked(layer.locked)
            self.blend.blockSignals(True)
            self.blend.setCurrentIndex(max(0, self.blend.findData(layer.blend)))
            self.blend.blockSignals(False)
            for k in ("clip", "alpha_lock"):
                self.buttons[k].blockSignals(True)
                self.buttons[k].setChecked(getattr(layer, k))
                self.buttons[k].blockSignals(False)
            self.buttons["clip"].setEnabled(c.current > 0 or layer.clip)
            state = "（ロック中）" if layer.locked else "（隠しています）" if not layer.visible else ""
            self.active.setText(f"✎ 描くレイヤー: {layer.name}{state}")
        self.buttons["delete"].setEnabled(len(c.layers) > 1 or bool(pen is not None and pen.marks))
        self.buttons["up"].setEnabled(c.current < len(c.layers) - 1)
        self.buttons["up_b"].setEnabled(c.current < len(c.layers) - 1)
        self.buttons["down_b"].setEnabled(c.current > 0)
        self.buttons["down"].setEnabled(c.current > 0)
        self.list.blockSignals(False)

    def _selected(self, row: int):
        item = self.list.item(row)
        if item is None:
            return
        i = item.data(ROLE_INDEX)
        pen = getattr(self.canvas, "redpen", None)
        if pen is not None:
            pen.set_focus(-i if i is not None and i < 0 else 0)   # 選んだ印だけ、絵の上に指示を出す
        if i is not None and i >= 0:
            self.canvas.select(i)

    def _changed(self, item: QListWidgetItem):
        name = item.data(ROLE_FOLDER)
        if name is not None:
            on = item.checkState() == Qt.Checked
            QTimer.singleShot(0, lambda: self.canvas.set_folder_prop(name, "visible", on))
            return
        i = item.data(ROLE_INDEX)
        if i is not None and i < 0:
            pen, n = self.canvas.redpen, -i
            pen.set_hidden(n, item.checkState() != Qt.Checked)
            text = item.text()
            head = f"赤ペン {n}"
            note = text[len(head):].lstrip(":： ") if text.startswith(head) else text
            if note.strip() != pen.texts[n - 1]:
                pen.set_text(n, note)
            QTimer.singleShot(0, self.refresh)
            return
        if i is None or not 0 <= i < len(self.canvas.layers):
            return
        layer = self.canvas.layers[i]
        visible = item.checkState() == Qt.Checked
        if visible != layer.visible:
            self.canvas.set_visible(i, visible)
        text = self.plain_name(item.text(), layer)
        if text.strip() and text != layer.name:
            # 一覧の中で一覧を作り直すと、編集中の項目を消して落ちることがあるので、あとで描き直す
            name = text
            QTimer.singleShot(0, lambda: self.canvas.rename_layer(i, name))
        else:
            QTimer.singleShot(0, self.refresh)

    @staticmethod
    def plain_name(text: str, layer) -> str:
        """一覧の見出しから、クリッピングの印と合成モードの添え書きを外した名前（名前を変えたときに印を名前に入れない）"""
        from atelier.paint.canvas import BLEND_MODES
        if layer.folder and text.startswith(INDENT):
            text = text[len(INDENT):]
        if text.startswith("　┗ "):
            text = text[len("　┗ "):]
        mode = BLEND_MODES.get(layer.blend, BLEND_MODES["normal"])[0]
        if layer.blend != "normal" and text.endswith(f"（{mode}）"):
            text = text[:-len(f"（{mode}）")]
        return text

    def _moved(self, _parent, start, _end, _dest, row):
        """ドラッグで並べ替えたとき。一覧の行（上が一番上のレイヤー）をキャンバスの順に直す"""
        item_rows = [self.list.item(r).data(ROLE_INDEX) for r in range(self.list.count())]
        layer_rows = [i for i in item_rows if i is not None and i >= 0]
        n = len(self.canvas.layers)
        moved = self.list.item(row if row < start else row - 1)
        i = moved.data(ROLE_INDEX) if moved is not None else None
        if i is None or i < 0 or i not in layer_rows:
            QTimer.singleShot(0, self.refresh)
            return
        j = n - 1 - layer_rows.index(i)
        # 落とした行のすぐ上がフォルダーの見出しか中のレイヤーなら、そのフォルダーに入れる。ほかは外に出す
        r = self.list.row(moved)
        above = self.list.item(r - 1) if r > 0 else None
        folder = ""
        if above is not None:
            if above.data(ROLE_FOLDER) is not None:
                folder = above.data(ROLE_FOLDER)
            elif isinstance(above.data(ROLE_INDEX), int) and 0 <= above.data(ROLE_INDEX) < n:
                folder = self.canvas.layers[above.data(ROLE_INDEX)].folder
        QTimer.singleShot(0, lambda: self.canvas.move_layer_to(i, j, folder))

    def _double(self, item):
        name = item.data(ROLE_FOLDER)
        if name is not None and name in self.canvas.folders:
            self.canvas.set_folder_collapsed(name, not self.canvas.folders[name].collapsed)

    def folder_menu(self, m, name: str):
        """フォルダーの見出しの右クリック: 畳む・名前・合成・不透明度・解く"""
        from PySide6.QtGui import QActionGroup
        from atelier.paint.canvas import BLEND_MODES
        c = self.canvas
        f = c.folders[name]
        m.addAction("開く" if f.collapsed else "畳む", lambda: c.set_folder_collapsed(name, not f.collapsed))
        m.addAction("フォルダーの名前を変える…", lambda: self._rename_folder(name))
        blend = m.addMenu("フォルダーの合成モード")
        group = QActionGroup(blend)
        for key, label in [("pass", "通過")] + [(k, v[0]) for k, v in BLEND_MODES.items()]:
            act = blend.addAction(label, lambda k=key: c.set_folder_prop(name, "blend", k))
            act.setCheckable(True)
            act.setChecked(f.blend == key)
            group.addAction(act)
        op = m.addMenu("フォルダーの不透明度")
        group2 = QActionGroup(op)
        for v in (100, 75, 50, 25):
            act = op.addAction(f"{v}%", lambda v=v: c.set_folder_prop(name, "opacity", v / 100))
            act.setCheckable(True)
            act.setChecked(round(f.opacity * 100) == v)
            group2.addAction(act)
        m.addAction("選んでいるレイヤーをこのフォルダーに入れる", lambda: c.put_in_folder(name))
        m.addAction("フォルダーを解く（中のレイヤーは残す）", lambda: c.remove_folder(name))

    def _rename_folder(self, name: str):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "フォルダーの名前", "名前", text=name)
        if ok:
            self.canvas.set_folder_prop(name, "name", text)

    def _menu(self, pos):
        from atelier.app.main_window import exec_once
        exec_once(self.context_menu(pos), self.list.viewport().mapToGlobal(pos))

    def context_menu(self, pos):
        """右クリックの窓の中身（試験からも同じ項目を押せるよう、開くのと分ける）"""
        from PySide6.QtWidgets import QMenu
        item = self.list.itemAt(pos)
        m = QMenu(self)
        m.setToolTipsVisible(True)
        m.addAction("新しいレイヤー", self.canvas.add_layer)
        m.addAction("新しいフォルダー（選んでいるレイヤーを入れる）", self.canvas.new_folder)
        if item is not None and item.data(ROLE_FOLDER) is not None:
            m.addSeparator()
            self.folder_menu(m, item.data(ROLE_FOLDER))
        elif item is not None:
            if item.data(ROLE_INDEX) < 0:
                n = -item.data(ROLE_INDEX)
                m.addAction(f"赤ペン {n} の指示を書き直す", lambda: self.list.editItem(item))
                m.addAction(f"赤ペン {n} を消す", lambda: self.canvas.redpen.remove(n))
                m.addAction("赤ペンの印を全部消す", self.canvas.redpen.clear)
            else:
                self.canvas.select(item.data(ROLE_INDEX))
                S = self.shared
                # コピー・切り取り・貼り付け・複製は、メニューと同じ操作（同じキー）を出す
                if S:
                    m.addAction(S["dup_layer"])
                    m.addSeparator()
                    for k in ("layer_cut", "layer_copy", "layer_paste"):
                        m.addAction(S[k])
                    m.addAction(S["via_copy"])
                    m.addSeparator()
                m.addAction("このレイヤーを消す（Delete）", self._delete).setEnabled(len(self.canvas.layers) > 1)
                if S:
                    m.addAction(S["clear_layer"])
                m.addAction("1 つ上へ", lambda: self.canvas.move_layer(1))
                m.addAction("1 つ下へ", lambda: self.canvas.move_layer(-1))
                if S:
                    m.addAction(S["flip_layer_h"])
                    m.addAction(S["flip_layer_v"])
                    m.addAction(S["merge_down"])
                else:
                    m.addAction("下のレイヤーと結合", self.canvas.merge_down)
                m.addAction("名前を変える", self.rename_current)
                if self.canvas.layers[self.canvas.current].folder:
                    m.addAction("フォルダーから出す", self.canvas.take_out_of_folder)
                m.addAction("ロックを切り替える", self.toggle_lock)
        m.addAction("見えているレイヤーを結合", self.canvas.merge_visible)
        w = self.window()   # 欄は窓の中の dock にあるので、上の窓が Window
        if hasattr(w, "edit_context_menu"):   # 項目を出す・隠す・並べ替える（atelier/ui/menu_editor.py）
            m.addAction("この右クリックを編集…", lambda: w.edit_context_menu("レイヤー")).setToolTip("項目を出す・隠す・並べ替える")
            w.arrange_context("レイヤー", m)
        return m

    def _delete(self):
        """「－」。赤ペンの行を選んでいればその印だけを消し、ほかは選んでいるレイヤーを消す"""
        item = self.list.currentItem()
        if item is not None and item.data(ROLE_INDEX) is not None and item.data(ROLE_INDEX) < 0:
            self.canvas.redpen.remove(-item.data(ROLE_INDEX))
            return
        self.canvas.delete_layer()

    def rename_current(self):
        item = self.list.item(self.row_of(self.canvas.current))
        if item is not None:
            self.list.editItem(item)

    def _set_prop(self, key: str, value):
        c = self.canvas
        if c.layers:
            c.set_layer_prop(c.current, key, value)
            self.refresh()

    def toggle_lock(self):
        c = self.canvas
        if c.layers:
            c.set_locked(c.current, not c.layers[c.current].locked)
            self.refresh()
