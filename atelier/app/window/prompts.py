"""描く言葉と禁止の言葉の履歴・お気に入り・候補"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton


class PromptsMixin:
    """描く言葉と禁止の言葉の履歴・お気に入り・候補（Window が継承する）"""

    PROMPT_KEY, FAV_KEY, PROMPT_MAX = "prompts/history", "prompts/favorites", 20
    EXAMPLES = ("赤いマフラーの女の子", "鎧の騎士 全身", "猫耳の少女 笑顔", "夕暮れの街", "レイヤーを足して")

    def _list(self, key: str) -> list[str]:
        saved = self.settings.store.value(key, []) or []
        return [str(t) for t in ([saved] if isinstance(saved, str) else list(saved))]

    def recent_prompts(self) -> list[str]:
        return self._list(self.PROMPT_KEY)

    def favorite_prompts(self) -> list[str]:
        return self._list(self.FAV_KEY)

    def _load_prompts(self):
        """書く欄の下のボタンを作り直す。登録した言葉、直近の言葉の順。どちらも無いときだけ頼みの例を出す"""
        while self.tips.count():
            it = self.tips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        favs = self.favorite_prompts()
        recent = [t for t in self.recent_prompts() if t not in favs]
        self.chip_texts = favs + recent   # ↑↓ で呼び出す順
        rows = [(t, True) for t in favs] + [(t, False) for t in recent] or [(t, None) for t in self.EXAMPLES]
        for text, fav in rows:
            chip = QPushButton(("★ " if fav else "") + (text if len(text) <= 24 else text[:23] + "…"))
            chip.setObjectName("suggest")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setProperty("prompt", text)
            chip.setToolTip(text + ("\n押すと書く欄に入り、ダブルクリックでもう一度描きます。右クリックで登録・外す・消す" if fav is not None else ""))
            chip.clicked.connect(lambda _=False, t=text: (self.entry.setText(t), self.entry.setFocus()))
            if fav is not None:
                chip.setContextMenuPolicy(Qt.CustomContextMenu)
                chip.customContextMenuRequested.connect(lambda pos, c=chip, t=text, f=fav: self._chip_menu(c, pos, t, f))
                chip.installEventFilter(self)
            self.tips.addWidget(chip)
        self.fav_button.setText("★" if self.entry.text().strip() in favs and self.entry.text().strip() else "☆")
        self._prompt_pos = -1

    def _chip_menu(self, chip, pos, text: str, fav: bool):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("登録から外す" if fav else "描くワードに登録する", lambda: (self.unpin_prompt(text) if fav else self.pin_prompt(text)))
        m.addAction("この言葉ですぐ描く", lambda: (self.entry.setText(text), self.send()))
        m.addAction("この言葉でプリセットを作る…", lambda: self.preset_from_words(text)).setToolTip(
            "今の描き方・大きさ・画風とこの描くワードを、自分の AI プリセットに固定します")
        m.addAction("一覧から消す", lambda: self.forget_prompt(text))
        m.exec(chip.mapToGlobal(pos))

    def preset_from_words(self, text: str, run: bool = True):
        """描くワードをプリセットに固定する窓を開く（中身は今の設定とこの言葉）"""
        p = self.ai_panel
        dlg = p.edit_preset(run=False)
        dlg.words.setPlainText(text)
        dlg.name.setText(text[:16])
        if run and dlg.exec():
            p.finish_edit(dlg)
        return dlg

    def _save(self, key: str, items: list[str], limit: int | None = None):
        self.settings.store.setValue(key, items[:limit] if limit else items)
        self._load_prompts()

    def ask_forget(self, text: str, then) -> bool:
        """一覧・辞書・プリセットから消す前の確かめの窓（「次から聞かない」で出さなくできる）"""
        from atelier.ui import confirm
        if confirm.ask(self, "forget", "一覧から消す", text, [("yes", "消す")]) != "yes":
            return False
        then()
        return True

    def _remember_prompt(self, text: str):
        """頼んだ言葉を、新しい順に残す（同じ言葉は 1 つにまとめて先頭へ）"""
        self._save(self.PROMPT_KEY, [text] + [t for t in self.recent_prompts() if t != text], self.PROMPT_MAX)

    def pin_prompt(self, text: str):
        """描くワードに登録する。登録は数を限らず、外すまで残す"""
        if not text:
            self.notify("登録する言葉がありません", "info", "書く欄に言葉を書いてから ☆ を押します")
            return
        favs = self.favorite_prompts()
        if text not in favs:
            self._save(self.FAV_KEY, favs + [text])
            self.statusBar().showMessage(f"描くワードに登録しました: {text}", 4000)

    def select_tool(self, key: str):
        """道具を持ち替える（初めの道具や配置を変えたとき）。利用者が押したときと違い、初めて使うときの案内は出さない"""
        if getattr(self, "_start_tool_pending", False):
            key = self.start_tool(key)
        act = self.tool_actions.get(key)
        if act is None:
            return
        act.setChecked(True)
        self.canvas.set_tool(key)
        self._tool_changed(key)

    def start_tool(self, asked: str) -> str:
        """起動したときの道具。初めはペン（手のひらだと、初めての人がなぞっても線が出なかった）。
        次からは前に使った道具。設定の「起動したときの道具」で手かペンに決めておける"""
        self._start_tool_pending = False
        self._start_tool_done = True
        fixed = self.settings.get("first_tool")
        if fixed == "手":
            return "hand"
        if fixed == "ペン":
            return "pen"
        last = str(self.layout_store.value("last_tool", "") or "")
        return last if last in self.tool_actions else "pen"

    def voice_input(self):
        """描くワードの欄のマイクを押すのと同じ"""
        self.mic_button.press()

    def _toggle_fav(self):
        text = self.entry.text().strip() or self.last_text
        if text and text in self.favorite_prompts():
            self.unpin_prompt(text)
        else:
            self.pin_prompt(text)
        self.fav_button.setText("★" if text in self.favorite_prompts() else "☆")

    def unpin_prompt(self, text: str):
        self._save(self.FAV_KEY, [t for t in self.favorite_prompts() if t != text])

    def forget_prompt(self, text: str):
        self.settings.store.setValue(self.FAV_KEY, [t for t in self.favorite_prompts() if t != text])
        self._save(self.PROMPT_KEY, [t for t in self.recent_prompts() if t != text])

    def _entry_keys(self, obj, e) -> bool:
        """書く欄で ↑ を押すと前に頼んだ言葉、↓ で新しい方へ戻る"""
        from PySide6.QtCore import QEvent
        if obj is getattr(self, "entry", None) and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Up, Qt.Key_Down) \
                and "\n" not in self.entry.text():   # 複数行のときは、↑↓ で行を動かす
            texts = getattr(self, "chip_texts", [])
            if texts:
                self._prompt_pos = min(self._prompt_pos + 1, len(texts) - 1) if e.key() == Qt.Key_Up else self._prompt_pos - 1
                if self._prompt_pos < 0:
                    self._prompt_pos = -1
                    self.entry.clear()
                else:
                    self.entry.setText(texts[self._prompt_pos])
                return True
        if e.type() == QEvent.MouseButtonDblClick and isinstance(obj, QPushButton) and obj.property("prompt"):
            self.entry.setText(obj.property("prompt"))   # ボタンをダブルクリックで、その言葉ですぐ描く
            self.send()
            return True
        return False

    NEG_KEY = "prompts/negatives"

    def negative_presets(self) -> list[str]:
        return self._list(self.NEG_KEY)

    def _load_negatives(self):
        """禁止ワードの欄の下のボタン（登録した禁止ワード）を作り直す"""
        while self.neg_tips.count():
            it = self.neg_tips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for text in self.negative_presets():
            chip = QPushButton("★ " + (text if len(text) <= 24 else text[:23] + "…"))
            chip.setObjectName("suggest")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setProperty("negative", text)
            chip.setToolTip(text + "\n押すと禁止ワードの欄に足します。右クリックで外す・この言葉だけにする")
            chip.clicked.connect(lambda _=False, t=text: self._use_negative(t))
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.customContextMenuRequested.connect(lambda pos, c=chip, t=text: self._neg_chip_menu(c, pos, t))
            self.neg_tips.addWidget(chip)
        self.neg_tips_box.setVisible(bool(self.negative_presets()))
        t = self.ai_panel.negative.text().strip()
        self.neg_fav_button.setText("★" if t and t in self.negative_presets() else "☆")

    def _use_negative(self, text: str):
        """登録した禁止ワードを欄に足す。もう入っている言葉は重ねない"""
        cur = self.ai_panel.negative.text().strip()
        if not cur:
            self.ai_panel.negative.setText(text)
        elif text not in cur:
            self.ai_panel.negative.setText(cur + "、" + text)
        self.ai_panel.negative.setFocus()

    def _neg_chip_menu(self, chip, pos, text: str):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("禁止ワードの欄に足す", lambda: self._use_negative(text))
        m.addAction("この言葉だけにする", lambda: self.ai_panel.negative.setText(text))
        m.addAction("登録から外す", lambda: self.unpin_negative(text))
        m.exec(chip.mapToGlobal(pos))

    def pin_negative(self, text: str):
        """禁止ワードを登録する。数を限らず、外すまで残す"""
        if not text:
            self.notify("登録する禁止ワードがありません", "info", "禁止ワードの欄に言葉を書いてから ☆ を押します")
            return
        presets = self.negative_presets()
        if text not in presets:
            self.settings.store.setValue(self.NEG_KEY, presets + [text])
            self.statusBar().showMessage(f"禁止ワードを登録しました: {text}", 4000)
        self._load_negatives()

    def unpin_negative(self, text: str):
        self.settings.store.setValue(self.NEG_KEY, [t for t in self.negative_presets() if t != text])
        self._load_negatives()

    def _toggle_neg_fav(self):
        text = self.ai_panel.negative.text().strip()
        if text and text in self.negative_presets():
            self.unpin_negative(text)
        else:
            self.pin_negative(text)

    def _apply_avoid(self):
        """AI の欄の禁止ワードを絵の模型に渡す。描く・直す・ちびキャラ・広げる・綺麗にするのどの経路も painter.avoid を読む。
        描くときだけ渡すと、書き換えたあとに描かずに広げた・ちびキャラにしたときに前の禁止ワードのままだった"""
        painter = getattr(getattr(self, "studio", None), "painter", None)
        if painter is None:
            return
        avoid = list(self.ai_panel.taste()["avoid"])
        avoid += [a for a in self.ai_panel.avoid_words() if a not in avoid]   # 模型の決まりと「〜なし」には engine が足す
        painter.avoid = ", ".join(avoid)

    def draw_again(self):
        """前と同じ頼みを、別の種で描き直す"""
        if not self.last_text:
            self.notify("まだ描いていません", "info", "チャットに描きたい絵を書いて「描く」を押します")
            return
        self.entry.setText(self.last_text)
        self.send()
