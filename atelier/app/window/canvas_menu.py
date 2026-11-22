"""キャンバスと印の右クリックのメニュー、ショートカット、言葉の指示"""
from __future__ import annotations

from atelier.app.window.constants import MARK_OK
from atelier.app.window.constants import REDPEN_SHAPES
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.widgets import exec_once
from pathlib import Path
import os


class CanvasMenuMixin:
    """キャンバスと印の右クリックのメニュー、ショートカット、言葉の指示（Window が継承する）"""

    def canvas_menu(self, gpos):
        """絵の上の右クリック（右ボタンを動かさずに離したとき）。よく使う操作をまとめる"""
        exec_once(self.build_canvas_menu(gpos), gpos)

    def build_canvas_menu(self, gpos=None):
        """右クリックのメニューを作って返す（試験はこれを開かずに押す）"""
        from PySide6.QtWidgets import QMenu
        from atelier.ai import shortcuts
        c = self.canvas
        m = QMenu(self)
        m.setToolTipsVisible(True)
        # よく使う物を上に、1 回で押せる所に置く（赤ペンを「道具」の奥に入れていたら見つからなかった）
        if "redpen" in self.tool_actions:
            m.addAction("赤ペンで直す所を囲む（T）", self.tool_actions["redpen"].trigger).setToolTip(
                "囲んで指示を書き、「描く」を押すと囲んだ所だけを AI が直します")
            here = c.mapToScene(c.viewport().mapFromGlobal(gpos)) if gpos is not None else None
            how = QMenu("赤ペンの囲み方", m)
            how.setToolTipsVisible(True)
            m.addMenu(how)
            for key, _l, _t in REDPEN_SHAPES:
                how.addAction(self.shared[f"redpen_shape:{key}"])
            how.addAction(self.shared["redpen_all"])
            if here is not None and c.layers:
                a = how.addAction("ここを自動選択で印にする", lambda: self.run_autosel((here.x(), here.y()), None, "redpen"))
                a.setToolTip("右クリックした所の物を AI が選び、赤ペンの印にします")
        if c.tool in ("fill", "pen"):
            self.tool_settings_menu(m)   # 今の道具の設定は一番上の段で 1 回で選べるようにする
            m.addSeparator()
        if c.redpen.marks or c.selection is not None:
            # 「描く」を直すにして押すのと同じ道を通す（右クリックから仕上げと同じ手数で直せるように）
            m.addAction("囲んだ所を直す", self.fix_marked).setEnabled(not self.thread)
        m.addAction(self.shared["inspect"])
        if c.redpen.marks:
            m.addAction("赤ペンの印を消す", c.redpen.clear)
        # 番号の丸の上で右クリックしたら、その印だけを直す・消す
        n = c.redpen.number_at(c.mapToScene(c.viewport().mapFromGlobal(gpos)), c.zoom()) if gpos is not None else 0
        if n:
            m.addAction(f"印 {n} の指示を書き直す", lambda: self.edit_note(n))
            m.addAction(f"印 {n} を消す", lambda: c.redpen.remove(n)).setToolTip("元に戻すで戻せます")
            self._mark_menu(m, n)
            self.fill_style_menu(self._submenu(m, f"印 {n} の中の画風の変更"), n)
            m.addSeparator()
        from atelier.ai import fix_menu as fixmenu
        fixmenu.add_to_menu(self, m, n)   # 修正依頼と、模型を使わない整える・揃える・消す（atelier/ai/fix_menu.py の 1 か所）
        # 言葉で指示する。登録した指示は shortcuts.fill_menu が小さなメニューに入れずに上へ並べ、1 回で呼べる
        m.addAction("言葉で指示…", self.open_text_instruction).setToolTip(
            "言葉を書いて、今の絵（囲みがあれば囲みの中）を直す・加工する・描くことができます。書いた言葉は登録できます")
        m.addSeparator()
        can_undo = bool(c.undo_stack) or (c.tool == "redpen" and bool(c.redpen.marks))
        can_redo = bool(c.redo_stack) or (c.tool == "redpen" and bool(c.redpen.undone))
        for label, fn, ok, why in (("元に戻す（Ctrl+Z）", c.undo, can_undo, "戻す操作がありません"),
                                   ("やり直す（Ctrl+Y）", c.redo, can_redo, "やり直す操作がありません")):
            a = m.addAction(label, fn)
            a.setEnabled(ok)
            a.setToolTip("" if ok else why)   # 押せない理由をカーソルを合わせたときに出す
        m.addSeparator()
        # 画風の変更は、隠す設定によらず画風を全部並べる（見本の投稿のように、1 枚の絵を選んだ画風に変える入口）
        self.fill_style_menu(self._submenu(m, "画風の変更"))
        shortcuts.fill_menu(self, m, self.shortcut_store(), skip=("style",))   # ★・よく使う物を上に、残りは処理の種類ごと
        m.addSeparator()
        # 道具・表示・選択は左端の帯やメニューと同じ操作を足す（名前もキーも、今の道具の印もそろう）
        tools = m.addMenu("道具")
        for key in ("pen", "eraser", "eyedropper", "select", "lasso", "polygon", "autosel", "hand", "redpen"):
            if key in self.tool_actions:
                tools.addAction(self.tool_actions[key])
        self.tool_settings_menu(tools)
        shapes = tools.addMenu("図形")
        for key in ("line", "rect", "ellipse", "polyshape", "regpoly"):
            shapes.addAction(self.tool_actions[key])
        view = m.addMenu("表示")
        for k in ("fit", "actual", "rotate_left", "rotate_right", "rotate_reset", "flip_view", "view_reset", "grid"):
            view.addAction(self.shared[k])
        m.addAction(self.shared["add_layer"])
        if c.selection is not None:
            sm = m.addMenu("選択範囲")
            for k in ("sel_clear", "sel_fill", "copy", "cut"):
                sm.addAction(self.shared[k])
            sm.addAction(self.shared["deselect"])
        else:
            m.addAction("絵をコピー", self.copy_image)
        m.addAction(self.shared["paste"])
        here = c.mapToScene(c.viewport().mapFromGlobal(gpos)) if gpos is not None else None
        if here is not None:
            a = m.addAction("色を拾う", lambda: c.pick(here))
            a.setEnabled(bool(c.layers))
            a.setToolTip("右クリックした所の色を描く色にします（スポイト、I）" if c.layers else "絵がありません")
        m.addSeparator()
        a = m.addAction("この絵を AI で描き直す（もう一度描く）", self.draw_again)
        a.setEnabled(bool(self.last_text) and not self.thread)
        a.setToolTip("ほかの処理の途中です。終わってから押してください" if self.thread else
                     ("前の頼みで AI がもう一度描きます" if self.last_text else "まだ AI で描いていません"))
        pin = m.addAction("表示する絵を固定する")
        pin.setCheckable(True)
        pin.setChecked(self.pin_action.isChecked())
        pin.toggled.connect(self.pin_action.setChecked)
        m.addAction("タイムラプスを見る…", self.open_timelapse)
        m.addSeparator()
        m.addAction(self.shared["new"])
        m.addAction("画像を開く…", self.open_image).setToolTip("作業ファイルか絵を開きます")
        m.addAction("この右クリックを編集…", lambda: self.edit_context_menu("キャンバス")).setToolTip(
            "項目を出す・隠す・並べ替える、言葉の指示を項目として足す")
        self.arrange_context("キャンバス", m)
        return m

    FILL_CHOICES = {
        "fill_gap": ("隙間閉じ", ((0, "しない"), (2, "小（2 画素）"), (4, "中（4 画素）"), (8, "大（8 画素）")),
                     "線の切れ目がこの幅までなら、外へ漏れずに止めます"),
        "fill_expand": ("領域拡縮", ((0, "しない"), (1, "1 画素広げる"), (2, "2 画素広げる"), (-1, "1 画素縮める")),
                        "線のふちの薄い画素の下まで塗り、白い塗り残しを出しません"),
        "fill_ref": ("参照するレイヤー", (("all", "見えている絵全部"), ("layer", "今のレイヤーだけ")),
                     "どの絵の色で塗る範囲を決めるか。線画を別のレイヤーにしているときは「見えている絵全部」"),
        "fill_tolerance": ("色の誤差", ((8, "小"), (24, "中"), (64, "大")), "近い色とみなす幅"),
    }
    TAPER_CHOICES = ((0.0, "無し"), (1.5, "短い"), (3.0, "中"), (6.0, "長い"))

    def sync_tool_boxes(self):
        """ブラシの欄の入り抜き・塗りつぶしの選びを、今のブラシとキャンバスの値に合わせる（右クリックで変えたあとも）"""
        c = self.canvas
        for attr, box in getattr(self, "taper_boxes", {}).items():
            vals = [box.itemData(i) for i in range(box.count())]
            now = getattr(c.brush, attr)
            box.setCurrentIndex(min(range(len(vals)), key=lambda i: abs(vals[i] - now)))
        for attr, box in getattr(self, "fill_boxes", {}).items():
            i = box.findData(getattr(c, attr))
            if i >= 0:
                box.setCurrentIndex(i)

    def tool_settings_menu(self, parent):
        """塗りつぶしと入り抜きの設定（今の値に印を付ける）。選んだ値はキャンバスに持ち、次に押したときから効く"""
        from PySide6.QtGui import QActionGroup
        c = self.canvas
        fill = parent.addMenu("塗りつぶしの設定")
        fill.setToolTipsVisible(True)
        for attr, (title, choices, tip) in self.FILL_CHOICES.items():
            sub = fill.addMenu(title)
            sub.setToolTipsVisible(True)
            group = QActionGroup(sub)
            for value, label in choices:
                act = sub.addAction(label, lambda a=attr, v=value: (setattr(c, a, v), self.sync_tool_boxes()))
                act.setCheckable(True)
                act.setChecked(getattr(c, attr) == value)
                act.setToolTip(tip)
                group.addAction(act)
        brush = c.brush
        for attr, title in (("taper_in", "入り"), ("taper_out", "抜き")):
            sub = parent.addMenu(f"{title}（{brush.name}）")
            sub.setToolTipsVisible(True)
            group = QActionGroup(sub)
            for value, label in self.TAPER_CHOICES:
                act = sub.addAction(label, lambda a=attr, v=value: (setattr(c.brush, a, v), self.sync_tool_boxes()))
                act.setCheckable(True)
                act.setChecked(abs(getattr(brush, attr) - value) < 1e-6)
                act.setToolTip("線の始めを細くします" if attr == "taper_in" else "線の終わりを細くします（手を離したときに掛かります）")
                group.addAction(act)

    # ---- どこで右クリックしても出るメニュー ----
    AREA_NAMES = {"color": "色", "brushes": "ブラシ", "library": "ライブラリー", "chat": "AI", "history": "履歴",
                  "layers": "レイヤー", "view": "表示", "talk": "チャット", "progress": "進み"}

    def common_menu(self, m):
        """どの欄の右クリックにも出す操作。新しく描く・開く・ショートカット"""
        from atelier.ai import shortcuts
        m.setToolTipsVisible(True)
        m.addAction("新しく描く（書く欄へ）", self.start_new_drawing).setToolTip("書く欄に移ります。描いてほしい絵を書いて Enter で描きます")
        m.addAction(self.shared["new"])
        m.addAction("画像を開く…", self.open_image).setToolTip("作業ファイルか絵を開きます")
        m.addAction("画像を開いて直す…", self.open_to_edit).setToolTip("手元の絵を開き、赤ペンで囲んで直せる形にします")
        if "redpen" in getattr(self, "tool_actions", {}):
            m.addAction("赤ペンで直す所を囲む（T）", self.tool_actions["redpen"].trigger).setToolTip("絵の上で囲んで指示を書き、「描く」で囲んだ所だけを直します")
        shortcuts.fill_menu(self, m.addMenu("ショートカット"), self.shortcut_store())
        return m

    def area_menu(self, key: str):
        """欄 key の空いた所の右クリックのメニュー。その欄の操作と、どこでも使える操作を出す"""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        if key == "history":
            m.addAction("ごみ箱…", self.open_trash).setToolTip("消した絵を戻す・本当に消す")
        elif key == "layers":
            m.addAction("レイヤーを足す", self.canvas.add_layer)
        elif key == "talk":
            m.addAction("書く欄へ", self.entry.setFocus)
        elif key == "library":
            from atelier.files import folders
            m.addAction("ディレクトリを開く", lambda: folders.open_folder(self.library.root)).setToolTip("ライブラリーの絵と資料の置き場を開きます")
        if m.actions():
            m.addSeparator()
        self.common_menu(m)
        if key in self.AREA_NAMES and hasattr(self, "panels") and key in self.panels:
            m.addSeparator()
            d = self.panels[key][0]
            m.addAction(f"「{self.AREA_NAMES[key]}」の欄を隠す", d.hide).setToolTip("表示メニューからまた出せます")
        return m

    def start_new_drawing(self):
        self.mode.setCurrentIndex(0)
        self.entry.setFocus()

    # ---- 右クリックのショートカット（atelier/ai/shortcuts.py） ----
    def shortcut_store(self):
        from atelier.ai import shortcuts
        if getattr(self, "_shortcut_store", None) is None:
            self._shortcut_store = shortcuts.Store(self.layout_store)   # 利用者の設定（更新で消さない）
        return self._shortcut_store

    def _begin_fix_only(self, n: int):
        """赤ペン n だけを直すため、ほかの見えている印を隠す。隠した印は _end_fix_only で戻す"""
        pen = self.canvas.redpen
        self._fix_only = n
        self._fix_hid = [i for i in range(1, len(pen.marks) + 1) if i != n and i in pen.shown()]
        for i in self._fix_hid:
            pen.set_hidden(i, True)

    def _end_fix_only(self, removed: int = 0):
        """隠したほかの印を戻す。removed は直し終えて消した印の番号（それより後ろの番号は 1 つ前へずれる）"""
        pen = self.canvas.redpen
        for i in getattr(self, "_fix_hid", []):
            j = i - 1 if removed and i > removed else i
            if 1 <= j <= len(pen.marks):
                pen.set_hidden(j, False)
        self._fix_hid, self._fix_only = [], 0
        if hasattr(self, "layer_panel"):
            self._refresh_layers()

    # 赤ペンの印の右クリックに出す加工。全部の加工を印の囲み 1 つに本物の経路で掛けて測り（docs/knowledge/function-check.md の
    # 「赤ペンの印の右クリック」）、囲みの外が 0 画素で、囲みの中が変わり、整える物は目の色の差が 1.5 以下だった物だけを残す
    MARK_SHORTCUTS = None   # None なら下の _mark_ok で選ぶ

    def _mark_items(self):
        from atelier.ai import shortcuts
        keep = self.MARK_SHORTCUTS if self.MARK_SHORTCUTS is not None else MARK_OK
        return [s for s in shortcuts.builtins(self) if s.id in keep]

    def _mark_menu(self, m, n: int):
        """赤ペン n の印の右クリックに、その印の囲みの中だけに掛けて意味のある加工と、登録した言葉の指示を出す"""
        from PySide6.QtWidgets import QMenu
        from atelier.ai import shortcuts
        sub = QMenu(f"赤ペン {n} の中だけ加工", m)
        m.addMenu(sub)
        sub.setToolTipsVisible(True)
        items = self._mark_items()
        for g, label in shortcuts.GROUPS:
            inside = [s for s in items if s.group == g]
            if not inside:
                continue
            gm = QMenu(label, sub)
            sub.addMenu(gm)
            gm.setToolTipsVisible(True)
            for s in inside:
                a = gm.addAction(s.label, lambda sid=s.id: self.run_shortcut_on_mark(n, sid))
                a.setObjectName(f"mark{n}:{s.id}")
                a.setEnabled(s.ready and not self.thread)
                a.setToolTip((f"赤ペン {n} の囲みの中だけに掛けます。囲みの外は変えません。" + s.tip) if s.ready else s.reason)
        # 登録した言葉の指示（右クリックの編集の「言葉の指示を足す…」）。その印の囲みの中だけを、その言葉で直す
        user = [s for s in shortcuts.user_items(self, self.shortcut_store())]
        prompts = {p["id"]: p["text"] for p in self.shortcut_store().prompts()}
        if user:
            sub.addSeparator()
            for s in user:
                a = sub.addAction(s.label, lambda t=prompts.get(s.id, ""): self.mark_instruction(n, t))
                a.setObjectName(f"mark{n}:{s.id}")
                a.setEnabled(s.ready and not self.thread)
                a.setToolTip(f"「{prompts.get(s.id, '')}」で赤ペン {n} の囲みの中だけを直します。囲みの外は変えません" if s.ready else s.reason)
        sub.addSeparator()
        sub.addAction("言葉で指示…", lambda: self.open_text_instruction(n)).setToolTip(
            f"言葉を書いて、赤ペン {n} の囲みの中だけを直す・加工します。書いた言葉は登録できます")

    def run_shortcut_on_mark(self, n: int, sid: str):
        """右クリックの加工を、赤ペン n の囲みの中だけに掛ける。囲み（_region_mask）は押したときに読むので、読み終えたら戻す"""
        self._mark_only = n
        try:
            return self.run_shortcut(sid)
        finally:
            self._mark_only = 0

    def mark_instruction(self, n: int, text: str):
        """赤ペン n の右クリックで選んだ指示を、まずその印の指示の欄に書いて確定し（画面に見えてから）、そのあとで印 n だけを直す"""
        pen = self.canvas.redpen
        if not 1 <= n <= len(pen.marks) or not (text or "").strip():
            return
        self.edit_note(n)                 # 印の横の指示の欄を出し
        self.note_edit.setText(text)      # 指示を入れ
        self.note_ok.click()              # 確定のボタンと同じ道で確定する（欄が閉じ、印とレイヤーの欄に指示が残る）
        self.canvas.viewport().repaint()  # 確定した指示が絵の上に見えてから直しを始める
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.fix_with_text(pen.texts[n - 1] if n <= len(pen.texts) else text, mark=n))

    def run_shortcut(self, sid: str):
        """ショートカットを押したとき。使えなければ理由を出して止めない。使った回数を数えて並びに使う"""
        from atelier.ai import shortcuts
        store = self.shortcut_store()
        s = next((s for s in shortcuts.all_items(self, store) if s.id == sid), None)
        if s is None:
            self.notify("そのショートカットはありません", "info", "消したか、名前が変わりました")
            return None
        if not s.ready:
            self.notify(f"{s.label}は使えません", "info", s.reason)
            return None
        if self.thread:
            self.statusBar().showMessage("ほかの処理の途中です。終わってから押してください", 6000)
            return None
        store.count(sid)
        return s.run()

    def fix_with_text(self, text: str, mark: int = 0):
        """指示の言葉で今の絵を直す。囲み（赤ペン・選択）があれば囲みの中、無ければ絵全体を直す。
        mark（赤ペンの番号）を渡したら、その印の囲みの中だけを直す（ほかの印は直している間だけ隠し、終わったら戻す）。
        描く処理は「直す」で頼んだときと同じ道（_draw_now）を通す"""
        from PySide6.QtCore import QRect
        if self.thread:
            self.statusBar().showMessage("描いている途中です。終わってから頼んでください", 6000)
            return
        if mark:
            self._begin_fix_only(mark)
            try:
                self.mode.setCurrentIndex(2)
                self._draw_now(text)   # 指示の言葉はこの回だけ使い、描くワードの欄は書き換えない
            finally:
                if self.thread is None:   # 始まらなかった（止めた・確かめでやめた）ときはすぐ戻す
                    self._end_fix_only()
            return
        whole = not self.canvas.redpen.marks and self.canvas.selection_mask() is None
        if whole:   # 囲みが無ければ、絵全体を選んだ形で頼み、頼み終えたら選択を戻す
            w, h = self.canvas.size_px()
            self.canvas.set_selection(QRect(0, 0, w, h))
        self.mode.setCurrentIndex(2)
        self.entry.setText(text)
        try:
            self._draw_now(text)
        finally:
            if whole:
                self.canvas.set_selection(None)
        self.entry.clear()

    def add_prompt_shortcut(self, text: str | None = None, name: str | None = None) -> str:
        """書く欄の言葉（空なら尋ねる）を、右クリックから選べる指示として登録する。返すのは id（やめたら空）"""
        from PySide6.QtWidgets import QInputDialog
        if not isinstance(text, str):   # メニューから呼ぶと checked の真偽が来る
            text = self.entry.text().strip()
            if not text:
                text, ok = QInputDialog.getText(self, "指示を登録", "直しの頼みの言葉（例: 目を大きく、背景を夕焼けに）")
                if not ok:
                    return ""
        text = (text or "").strip()
        if not text:
            return ""
        if name is None:
            name, ok = QInputDialog.getText(self, "指示を登録", "右クリックに出す名前", text=text[:20])
            if not ok:
                return ""
        sid = self.shortcut_store().add(name, text)
        self.notify("指示を登録しました", "ok", "絵の上の右クリックの「指示で直す」から選べます")
        return sid

    def open_pick_shortcuts(self):
        """右クリックに出す加工を選ぶ窓"""
        from atelier.ai import shortcuts
        dlg = shortcuts.picker(self, self.shortcut_store())
        dlg.show()
        self._pick_dialog = dlg
        return dlg

    def open_text_instruction(self, mark: int = 0):
        """言葉で指示する窓。書いた言葉で今の絵（囲みがあれば囲みの中）を直す・加工する・描く。名前を付けて登録もできる。
        mark（赤ペンの番号）を渡したら、その印の囲みの中だけを直す"""
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
        from atelier.agent import voice
        from atelier.panels.chat_panel import EnterEdit
        dlg = QDialog(self)
        dlg.setWindowTitle("言葉で指示")
        lay = QVBoxLayout(dlg)
        where = f"赤ペン {mark} の囲みの中" if mark else "囲んだ所" if (self.canvas.redpen.marks or self.canvas.selection is not None) else "絵全体"
        dlg.where = QLabel(f"直す所: {where}")
        dlg.where.setToolTip("赤ペンか四角の選択で囲んでから開くと、囲んだ所だけを直します")
        lay.addWidget(dlg.where)
        row = QHBoxLayout()
        dlg.edit = EnterEdit("例: 目を大きく / 線画にして / 夕焼けの海辺を描いて", lines=2)
        dlg.edit.setToolTip("Enter で行います（Shift+Enter で改行）。日本語でも英語でも書けます")
        dlg.mic = voice.mic_button(dlg.edit, parent=dlg)
        row.addWidget(dlg.edit, 1)
        row.addWidget(dlg.mic)
        lay.addLayout(row)
        buttons = QHBoxLayout()
        dlg.run = QPushButton("行う")
        dlg.run.setObjectName("primary")
        dlg.run.setToolTip("書いた言葉で、今の絵を直す・加工する・描きます。結果は一番上の新しいレイヤーに置きます（Enter）")
        dlg.save = QPushButton("登録…")
        dlg.save.setToolTip("書いた言葉に名前を付けて、右クリックから 1 回で呼べるようにします")
        close = QPushButton("閉じる")
        for b in (dlg.run, dlg.save, close):
            buttons.addWidget(b)
        lay.addLayout(buttons)

        def run():
            text = dlg.edit.text().strip()
            if not text:
                dlg.edit.setFocus()
                return
            dlg.accept()
            self.text_instruction(text, mark=mark)

        def save():
            text = dlg.edit.text().strip()
            if text:
                dlg.saved = self.add_prompt_shortcut(text)
        dlg.edit.returnPressed.connect(run)
        dlg.run.clicked.connect(run)
        dlg.save.clicked.connect(save)
        close.clicked.connect(dlg.reject)
        dlg.resize(460, 160)
        dlg.show()
        dlg.edit.setFocus()
        self._text_dialog = dlg
        return dlg

    def text_instruction(self, text: str, mark: int = 0):
        """言葉の指示を行う。加工の名前があれば加工、「〜を描いて」なら新しく描く、それ以外は今の絵を直す。
        どれも AI の欄・右クリックと同じ関数を通す（日本語は描く処理の中の言葉の直しを通り、そのまま絵の模型に渡らない）"""
        from atelier.agent import chat_plan as chatplan
        from atelier.ai import finishers
        from atelier.agent.assistant import draw_request
        text = (text or "").strip()
        if not text:
            return
        if self.thread:
            self.statusBar().showMessage("描いている途中です。終わってから頼んでください", 6000)
            return
        entries = [{"name": n, "label": f.label} for n, f in finishers.REGISTRY.items()]
        plan = chatplan.parse(text, entries)
        if any(st not in ("draw", "fix") for st in plan.steps) or plan.repeat > 1 or plan.export is not None:
            self._mark_only = mark   # 加工の囲み（_region_mask）は押したときに読む
            try:
                self.run_plan(plan)
            finally:
                self._mark_only = 0
            return
        if mark:   # 赤ペンの印から頼んだときは、新しく描かずに、その印の指示の欄に書いて確定してから、その印の中を直す
            self.mark_instruction(mark, text)
            return
        if draw_request(text) is not None:
            self.mode.setCurrentIndex(0)
            self.entry.setText(plan.body or text)
            self.send()
            return
        self.fix_with_text(text)

    def open_shortcuts(self):
        from atelier.ai import shortcuts
        dlg = shortcuts.dialog(self, self.shortcut_store())
        dlg.show()
        self._shortcut_dialog = dlg
        return dlg

    def make_transparent(self):
        """透過。人物を切り抜いた透明の地の絵を、一番上の新しいレイヤーに置く（元の絵は残す）。
        切り抜きはアニメの切り抜きの模型（tools/gen/layers.anime_cut、isnet-anime）で行う。部品が無いときは、
        四隅から続く地の色を透明にする方法に替えて、替えたことを知らせる"""
        import tempfile
        src = qimage_to_pil(self.canvas.flatten()).convert("RGB")
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        src.save(tmp)
        out = self._finished_path("transparent")

        def work():
            how = "人物を切り抜きました"
            try:
                from atelier.files import paths
                paths.use_tools_gen()
                import layers as gen_layers
                cut = gen_layers.anime_cut(tmp)
            except Exception as e:   # noqa: BLE001
                # 部品が無い（ImportError）だけでなく、模型を読めない・取れないときも、地の色を抜く方法で透過する。
                # 前は ImportError だけを受け、ほかの失敗は「透過できませんでした」で終わっていた
                from atelier.ai import logo_maker as logo
                cut = logo.remove_background(src)
                how = "切り抜きの模型が使えないので、四隅から続く地の色を透明にしました（" + str(e).splitlines()[0][:60] + "）"
            finally:
                Path(tmp).unlink(missing_ok=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            cut.save(out)
            return out, how

        def done(got):
            if isinstance(got, BaseException):
                self.notify("透過できませんでした", "error", str(got))
                return
            path, how = got
            if self.settings.get("result_place") == "別ファイル":
                self.put_result(str(path), "透過")
            else:
                self.canvas.place_result(str(path), "透過", hide_below=True)
                self._refresh_layers()
            self.dirty = True
            self.notify(how, "ok", "下のレイヤーは隠して残しています（目の印で戻せます）。PNG で書き出すと透明のまま保存されます")
        self.statusBar().showMessage("透過しています（初めは切り抜きの模型を取ります）…")
        self.in_background(work, done, "透過")

    def remove_background(self):
        """四隅から続く背景の色を透明にした絵で、キャンバスを置き換える（元に戻すで戻せる）。囲みがあれば囲みの中だけ消す"""
        from atelier.ai import post_effects as postfx
        from PIL import ImageChops
        src = qimage_to_pil(self.canvas.flatten()).convert("RGBA")
        mask = self._region_mask()
        path = self._finished_path("nobg")

        def work():   # 塗りつぶしと書き出しは裏の糸
            out = postfx.paper_to_alpha(src)
            if mask is not None:   # 囲みの外は元の不透明さのまま
                from atelier.ai.finishers import binary
                keep = ImageChops.invert(binary(mask, src.size))
                out.putalpha(ImageChops.lighter(out.getchannel("A"), ImageChops.multiply(keep, src.getchannel("A"))))
            path.parent.mkdir(parents=True, exist_ok=True)
            out.save(path)
            return path

        def done(got):
            if isinstance(got, BaseException):
                self.notify("背景を消せませんでした", "error", str(got))
                return
            self.canvas.replace_with_image(str(got), "背景を消した絵")
            self.dirty = True
            self.notify("背景を消しました", "ok", "元に戻すで戻せます")
        self.statusBar().showMessage("背景を消しています…")
        self.in_background(work, done)

    def redo_from(self, path: str):
        """履歴の絵と同じ頼み・種・画風を、AI の欄とチャットに戻す。押せば同じ設定で描ける"""
        from atelier.ai import finishers
        meta = finishers.sidecar(path)   # PNG に埋めた頼み。前の版の絵は隣の .json
        if not meta:
            self.notify("設定が残っていません", "info", "この絵には描いたときの設定が残っていません")
            return
        self.entry.setText(meta.get("text", ""))
        self.ai_panel.seed.setValue(int(meta.get("seed", 0)))
        # 頼み直しの種は次の 1 回だけ使う。種を固定のままにすると、そのあと何を頼んでも同じ絵になった
        self.ai_panel.next_seed = int(meta.get("seed", 0))
        self.ai_panel.set_style(meta.get("style_name", "おまかせ"))
        self.ai_panel.set_count(1)
        if meta.get("mode") in ("新規", "ラフから"):
            self.mode.setCurrentText(meta["mode"])
        self.entry.setFocus()
        self.notify("同じ設定にしました", "ok", f"種 {meta.get('seed')} を固定しました。「描く」で同じ絵を描きます")
