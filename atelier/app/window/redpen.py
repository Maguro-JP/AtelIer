"""赤ペンの印、自動選択、検品の印と指示の欄"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QWidget
from atelier.app.window.constants import REDPEN_SHAPES
from atelier.app.window.image_convert import gray_to_pil
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.widgets import NoteEdit
import re


class RedpenMixin:
    """赤ペンの印、自動選択、検品の印と指示の欄（Window が継承する）"""

    # ---- 赤ペンの囲み方と自動選択 ----
    def set_redpen_shape(self, key: str):
        """赤ペンの印の取り方を替え、赤ペンに持ち替える"""
        self.canvas.set_redpen_shape(key)
        a = self.shared.get(f"redpen_shape:{key}")
        if a is not None and not a.isChecked():
            a.setChecked(True)
        if self.canvas.tool != "redpen" and "redpen" in self.tool_actions:
            self.tool_actions["redpen"].trigger()
        label = next((lb for k, lb, _t in REDPEN_SHAPES if k == key), key)
        self.statusBar().showMessage(f"赤ペンの囲み方: {label}", 4000)

    def redpen_all(self):
        if not self.canvas.layers:
            self.statusBar().showMessage("絵がありません", 4000)
            return
        if self.canvas.tool != "redpen" and "redpen" in self.tool_actions:
            self.tool_actions["redpen"].trigger()
        self.canvas.redpen_all()

    def run_autosel(self, point, box, target: str):
        """自動選択を裏の糸で回す（模型は 1 回で十数秒かかる）。答えは autosel_done で画面の糸に返す"""
        if getattr(self, "_autosel_busy", False):
            self.statusBar().showMessage("自動選択の途中です。終わってから押してください", 4000)
            return
        if not self.canvas.layers:
            return
        self._autosel_busy = True
        image = qimage_to_pil(self.canvas.flatten())
        self.statusBar().showMessage("自動選択: 押した所の物を選んでいます…")
        self._autosel_last = (point, box, target)

        def work():
            from atelier.ai import auto_select as autosel
            return autosel.pick(image, point, box)
        # 裏の糸から窓へ直に返さず、in_background の橋を通す（裏の糸で画面の部品が片付くと落ちた）
        self.in_background(work, lambda v: self._autosel_done(v, target), "自動選択")

    def _autosel_done(self, picked, target: str):
        from atelier.ai import auto_select as autosel
        self._autosel_busy = False
        if isinstance(picked, BaseException):
            self.notify("自動選択できませんでした", "error", str(picked) or type(picked).__name__)
            return
        n = self.canvas.apply_pick(picked.mask, target)
        self.last_autosel = picked
        msg = autosel.describe(picked) if n else "自動選択: 何も選べませんでした。少しずらして押すか、四角で囲んでください"
        self.statusBar().showMessage(msg, 8000)
        if picked.how != "sam" and n:
            self.say(msg)

    def fix_marked(self):
        """赤ペンで囲んだ所を直す。AI の欄を「直す」にして「描く」と同じ send() を呼ぶ"""
        self.mode.setCurrentIndex(2)
        self.send()

    # ---- 手で呼ぶ検品（atelier/qc/manual_check.py）。検品は印と指示を置くだけで、直すのは利用者が押したときだけ ----
    def _picture(self):
        """今の絵を平らにした絵。白一色などの何も描いていない絵なら None"""
        img = qimage_to_pil(self.canvas.flatten()).convert("RGB")
        return img if any(lo != hi for lo, hi in img.getextrema()) else None

    def _busy_inspect(self) -> bool:
        if self.thread or getattr(self, "inspecting", False):
            self.statusBar().showMessage("描いているか検品している途中です。終わってから押してください", 6000)
            return True
        return False

    def add_flaw_mark(self, box, note: str) -> int:
        """崩れの枠を囲む赤ペンの印を足し、指示の欄に崩れの中身を書く。足した印の番号を返す"""
        import math
        from PySide6.QtCore import QPointF
        pen = self.canvas.redpen
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = max(12.0, (x1 - x0) * 0.6), max(12.0, (y1 - y0) * 0.6)
        pts = [QPointF(cx + rx * math.cos(t * math.pi / 16), cy + ry * math.sin(t * math.pi / 16)) for t in range(33)]
        pen.begin(pts[0])
        for q in pts[1:]:
            pen.add(q)
        pen.end()
        n = len(pen.marks)
        pen.set_text(n, note)
        return n

    def inspect_now(self):
        """今の絵（AI が描いていない絵も）を検品し、崩れた所を赤ペンで囲む。直しはしない"""
        if self._busy_inspect():
            return
        img = self._picture()
        if img is None:
            self.notify("検品する絵がありません", "info", "絵を描くか開いてから押します")
            return
        from atelier.qc import manual_check as qcmanual
        self.inspecting = True
        self.statusBar().showMessage("検品しています（手・足・顔）", 6000)

        def done(res):
            self.inspecting = False
            self.statusBar().clearMessage()
            if isinstance(res, BaseException):
                self.notify("検品で止まりました", "error", str(res))
                return
            found, rest, lost = qcmanual.flaws(res), qcmanual.unplaced(res), qcmanual.missed(res)
            for box, note in found:
                self.add_flaw_mark(box, note)
            if found:
                self.mode.setCurrentIndex(2)   # 「描く」を「囲んだ所を直す」にして、そのまま押せるようにする
                if hasattr(self, "layer_panel"):
                    self._refresh_layers()
            tail = "。".join(([f"場所の分からない崩れ: {'、'.join(rest)}"] if rest else [])
                             + ([f"検品できなかった所: {'、'.join(lost)}"] if lost else []))
            if found:
                self.notify(f"検品: 崩れ {len(found)} か所を赤ペンで囲みました", "info",
                            "印の指示を見て「囲んだ所を直す」で直せます" + (f"。{tail}" if tail else ""))
            elif rest:
                self.notify(f"検品: 崩れ {len(rest)} 件（場所は分かりません）", "info", tail)
            else:
                self.notify("検品: 崩れは見つかりませんでした" + ("（検品できなかった所があります）" if lost else ""),
                            "ok" if not lost else "info", tail)
        # 最後に描いた絵の模型の言葉があれば渡し、頼んだ物が描かれたか・頼んでいない物が無いかも見る
        # 開いた別の絵に、前に描いた絵の言葉を渡さない（open_path・edit_image で消す）
        asked = getattr(self, "inspect_prompt", "") or ""
        self.in_background(lambda: qcmanual.inspect(img, asked=asked), done, "検品")

    def inspect_marks_then_fix(self):
        """指示の空の囲みの中だけを検品し、見つけた崩れを指示にして 1 回だけ直す。崩れが無ければ何もしない。
        直したあとは検品し直さない（描く・検品・直しを繋げて回すと止まらなかった）"""
        if self._busy_inspect():
            return
        img = self._picture()
        pen = self.canvas.redpen
        if img is None:
            self.notify("検品する絵がありません", "info", "絵を描くか開いてから押します")
            return
        masks = pen.masks()
        jobs = []
        for i in pen.shown():
            if pen.texts[i - 1]:
                continue
            box = gray_to_pil(masks[i - 1]).resize(img.size).getbbox()
            if box:
                jobs.append((i, box, img.crop(box)))
        if not jobs:
            return
        from atelier.qc import manual_check as qcmanual
        self.inspecting = True
        self.statusBar().showMessage(f"囲みの中を検品しています（{len(jobs)} か所）", 6000)
        marks = list(pen.marks)

        def done(got):
            self.inspecting = False
            self.statusBar().clearMessage()
            if isinstance(got, BaseException):
                self.notify("検品で止まりました", "error", str(got))
                return
            if list(pen.marks) != marks:   # 検品の間に印を消した・足した。古い番号に指示を書かない
                self.notify("検品の間に赤ペンの印が変わったので、直しませんでした", "info")
                return
            clean, lost = [], []
            for i, (x0, y0, _x1, _y1), res in got:
                notes = [t for _b, t in qcmanual.flaws(res, (x0, y0))] + qcmanual.unplaced(res)
                lost += [f"印 {i} の{w}" for w in qcmanual.missed(res)]
                if notes:
                    pen.set_text(i, "、".join(notes))
                else:
                    clean.append(i)
            more = f"検品できなかった所: {'、'.join(lost)}" if lost else ""
            if len(clean) == len(got):
                self.notify("囲みの中に崩れは見つからなかったので、直しませんでした", "info", more)
                return
            for i in clean:   # 崩れの無い囲みは隠して直さない（レイヤーの欄で出し直せる）
                pen.set_hidden(i, True)
            if hasattr(self, "layer_panel"):
                self._refresh_layers()
            self.notify(f"囲みの中の崩れを指示にして直します（{len(got) - len(clean)} か所）", "info",
                        "。".join(x for x in ([f"崩れの無い印 {'・'.join(map(str, clean))} は隠しました"] if clean else []) + [more] if x))
            self.send()   # 指示が全部そろったので、普段の直しを 1 回だけ通す
        self.in_background(lambda: [(i, box, qcmanual.inspect(crop)) for i, box, crop in jobs], done, "囲みの中の検品")

    def edit_note(self, n: int):
        """赤ペンの n 番の印の横に、指示を書く欄を出す。Enter で絵の上に残し、Esc でやめる"""
        from PySide6.QtCore import QPoint
        pen = self.canvas.redpen
        if not 1 <= n <= len(pen.marks):
            return
        if getattr(self, "note_edit", None) is None:
            # 指示の欄の横にマイクを置き、声でも指示を入れられるようにする（atelier/agent/voice.py。描くワードの欄と同じ仕組み）
            from atelier.agent import voice
            self.note_box = QWidget(self.canvas.viewport())
            self.note_box.setObjectName("noteBox")
            row = QHBoxLayout(self.note_box)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            self.note_edit = NoteEdit(self.note_box)   # 打った文字をキャンバスとショートカットに取られない欄
            self.note_edit.setObjectName("noteEdit")
            self.note_edit.setPlaceholderText("この所をどう直すか（例: 笑顔に）Enter で残す")
            self.note_edit.setMinimumWidth(260)
            self.note_edit.returnPressed.connect(self._note_done)
            self.note_edit.installEventFilter(self)
            self.note_mic = voice.mic_button(self.note_edit, parent=self.note_box)
            from PySide6.QtWidgets import QPushButton
            self.note_ok = QPushButton("確定", self.note_box)   # Enter を知らない人でも、押せば指示が入って欄が閉じる
            self.note_ok.setObjectName("noteOk")
            self.note_ok.setToolTip("書いた指示をこの印に残して欄を閉じます（Enter と同じ）。直すのは「描く」か右クリックの「囲んだ所を直す」で")
            self.note_ok.setFocusPolicy(Qt.NoFocus)   # 押しても欄から打つ所を奪わない
            self.note_ok.clicked.connect(self._note_done)
            row.addWidget(self.note_edit, 1)
            row.addWidget(self.note_mic)
            row.addWidget(self.note_ok)
        self.note_n = n
        at = self.canvas.mapFromScene(pen.marks[n - 1][0]) + QPoint(18, -14)
        self.note_edit.setText(pen.texts[n - 1])
        self.note_box.move(at)
        self.note_box.adjustSize()
        self.note_box.show()
        self.note_edit.setFocus()
        self.feature_tour("redpen_note")

    def _note_done(self):
        pen = self.canvas.redpen
        if 1 <= self.note_n <= len(pen.texts):
            pen.set_text(self.note_n, self.note_edit.text())
            if hasattr(self, "layer_panel"):   # 指示はレイヤーの欄の「赤ペン n」の行にも出す
                self._refresh_layers()
        self.note_box.hide()
        self.canvas.setFocus()

    def on_mouse_back(self):
        """マウスの戻るボタン。打っている欄があればその欄の元に戻す、無ければ絵の元に戻す"""
        self._mouse_step("undo")

    def on_mouse_forward(self):
        self._mouse_step("redo")

    def _mouse_step(self, key: str):
        from atelier.ui.type_guard import is_text_input
        f = QApplication.focusWidget()
        if is_text_input(f) and hasattr(f, key):
            getattr(f, key)()
            return
        a = self.shared.get(key)
        if a is not None and a.isEnabled():
            a.trigger()

    def _tip_watch(self):
        """模型に本当に渡した言葉をツールチップに出す欄（頼みの欄とチャットの欄）と、その中の表示面"""
        out = []
        for w in (getattr(self, "entry", None), getattr(getattr(self, "chat", None), "input", None)):
            if w is not None:
                out.append(w)
                if hasattr(w, "viewport"):
                    out.append(w.viewport())
        return out

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.ToolTip and obj in self._tip_watch():
            self._entry_tip()   # カーソルを合わせたときに作り直す（直す・加工のあとにも、最後に渡した言葉を出す）
        if self._entry_keys(obj, e):
            return True
        if obj is getattr(self, "note_edit", None) and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
            self.note_box.hide()
            return True
        return super().eventFilter(obj, e)

    def fix_source(self) -> str:
        """今の絵を描いたときの言葉（記録の prompt）。直した絵なら、その元の絵の言葉。記録が無ければ空（直すときに絵からタグを読む）"""
        from atelier.ai import finishers
        path = getattr(self, "_fix_from", None)
        if not path:
            return ""
        try:
            meta = finishers.sidecar(path)
        except Exception:
            return ""
        return str(meta.get("source", "") if meta.get("mode") == "直す" else meta.get("prompt", "") or "")

    def fix_regions(self, text: str):
        """直す所と指示の並び。赤ペンの印は絵の上に書いた指示か番号ごとの指示、四角の選択は文全体を指示にする"""
        from atelier.paint.redpen import merge
        marks = self.canvas.redpen.masks()
        shown = self.canvas.redpen.shown()   # 欄で隠した印は直さない
        regions = [(gray_to_pil(m), n) for i, (m, n) in enumerate(zip(marks, merge(self.canvas.redpen.texts, text)), 1) if i in shown]
        sel = self.canvas.selection_mask()
        if sel is not None:
            regions.append((gray_to_pil(sel), text))
        return regions

    def on_status(self, msg: str):
        if self._stale():
            return
        m = re.search(r"（(\d+)/(\d+)）", msg)
        self.activity.status(msg, *(int(m.group(1)), int(m.group(2))) if m else (None, None))
