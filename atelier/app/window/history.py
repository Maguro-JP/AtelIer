"""履歴の欄、作業の記録、タイムラプス、3D"""
from __future__ import annotations

from PySide6.QtCore import Qt
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.widgets import exec_once
from pathlib import Path


class HistoryMixin:
    """履歴の欄、作業の記録、タイムラプス、3D（Window が継承する）"""

    def _history_menu(self, pos, run: bool = True):
        from PySide6.QtWidgets import QMenu
        it = self.history.itemAt(pos)
        path = it.data(Qt.UserRole) if it else None
        if not path:   # 絵の無い所でも、使えるメニューを出す
            m = self.area_menu("history")
            if not run:
                return m
            exec_once(m, self.history.mapToGlobal(pos))
            return None
        m = QMenu(self)
        m.addAction("この絵を出す", lambda: self.show_history_image(path))
        m.addAction("この絵を出して固定する", lambda: (self.show_history_image(path), self.pin_action.setChecked(True)))
        if self.pin_action.isChecked():
            m.addAction("固定を外す（最新の絵を出す）", lambda: self.pin_action.setChecked(False))
        m.addAction("今の絵に重ねる", lambda: self.layer_from_file(path, "AI の絵"))
        m.addAction("編集する（囲んで直す）", lambda: self.edit_image(path))
        m.addSeparator()
        m.addAction("この設定で描き直す", lambda: self.redo_from(path))
        m.addAction("頼みの言葉を書く欄に入れる", lambda: self._prompt_from(path))
        m.addAction("頼みの言葉を描くワードに登録する", lambda: self._prompt_from(path, pin=True))
        from atelier.ai import own_style as ownstyle
        m.addAction("★ お気に入りを外す" if ownstyle.is_favorite(path) else "★ お気に入りにする",
                    lambda: (ownstyle.toggle(path), self.library_panel.relabel([path])))
        m.addAction("学習用に集める", self.collect_favorites)
        # 判定（良い・悪い・直した）は学びの記録に付ける（atelier/words/learning.py）。検品より弱く数え、「良い」はタグを強めない
        from atelier.words import learning as wordlearn
        judge = QMenu("判定", m)   # 親をはっきり持たせる（文字だけで足すと、返したメニューから引いたときに消えていた）
        m.addMenu(judge)
        judge.setToolTipsVisible(True)
        now = wordlearn.verdict_of(path)
        for key, label in list(wordlearn.VERDICTS.items()) + [("", "判定を消す")]:
            act = judge.addAction(("● " if key and key == now else "") + label, lambda k=key: self.judge(path, k))
            act.setToolTip("この絵の判定を学びの記録に付けます。次から描くときの通りやすさに弱く数えます")
        m.addSeparator()
        m.addAction("絵をコピー", lambda: self.copy_image(path))
        m.addAction("保存した場所を開く", lambda: self.open_folder(path))
        m.addAction("3D に進む…", lambda: self.open_3d(path)).setToolTip("この絵から骨付きの 3D キャラ（VRM・glTF）や板の模型を作る")
        from atelier.ui import share
        sns = m.addMenu("SNS に送る")
        for name in share.SERVICES:
            act = sns.addAction(f"{name} に送る", lambda n=name: share.post(self, n, path, self._prompt_text(path)))
            act.setEnabled(share.enabled(self.settings, name))
        if not any(share.enabled(self.settings, n) for n in share.SERVICES):
            sns.setToolTip("設定の「SNS 連携」で選ぶと使えます")
            sns.setEnabled(False)
        m.addSeparator()
        m.addAction("消す（ごみ箱へ）…", lambda: self.delete_images([path]))
        self.common_menu(m.addMenu("そのほか"))
        if not run:
            return m
        exec_once(m, self.history.mapToGlobal(pos))

    ENTRY_TIP = "描いてほしい絵を日本語か英語で書き、Enter か「描く」で描きます（Shift+Enter で改行）"

    def _words_changed(self):
        """単語のお気に入り・読めなかった語の直しのあと。目安と段を作り直す"""
        self.word_row.reload()
        self.ai_panel.update_preview()
        self._entry_tip()

    def open_word_dict(self):
        """設定 → 単語辞書…（描くワードの段の「辞書…」と同じ窓）"""
        return self.word_row.open_dialog()

    def _entry_tip(self):
        """書く欄のツールチップ。使い方に、模型に渡る言葉の目安と、前に絵の模型に渡した言葉を足す"""
        if hasattr(self, "lost_row"):   # 読めなかった語は、カーソルを合わせなくても見える段に出す（黙って落とさない）
            from atelier.ai.engine import has_japanese
            from atelier.words.japanese_terms import leftover
            text = self.entry.text().strip()
            self.lost_row.update_words(leftover(text) if text and has_japanese(text) else [])
        lines = [self.ENTRY_TIP]
        guess = self.ai_panel.preview.text().strip()
        if guess:
            lines += ["", guess]
        from atelier.files import sent
        real = sent.tooltip_lines()
        if real:   # 長さの切り詰めと打ち消しを含めた、模型が本当に受け取った文
            lines += [""] + real
        last = getattr(self, "last_model_prompt", "")
        # 記録は工程ごとの共有の帳面なので、前の仕事の行だけが残り、今の絵の言葉が無いことがある（記録しない描き手、別の窓）。
        # そのときも今の絵に渡した言葉を必ず出す
        if last and not any(last in e["prompt"] for e in sent.last(3)):
            lines += ["", "前に絵の模型に渡した言葉: " + last]
        # 長い英語の言葉で横に広がり画面からはみ出さないよう、折り返す形（リッチテキスト）で出す
        import html
        self.entry.setToolTip("<qt>" + "<br>".join(html.escape(t) for t in lines) + "</qt>")
        chat_in = getattr(getattr(self, "chat", None), "input", None)
        if chat_in is not None:   # チャットの欄にも、模型に本当に渡した言葉を出す
            chat_lines = ["AI に話しかける欄です。描く・直す・加工する・設定を変える、を頼めます"] + ([""] + real if real else [])
            chat_in.setToolTip("<qt>" + "<br>".join(html.escape(t) for t in chat_lines) + "</qt>")

    def show_history_image(self, path: str):
        """履歴で選んだ絵をキャンバスに出す。出した絵は「固定」すると、新しく描いても入れ替わらない。
        前の絵の作業（レイヤー・赤ペンの印・表示）を残してから移り、この絵の作業が残っていれば元のとおりに戻す"""
        if not Path(path).is_file():
            self.notify("絵を出せません", "error", f"{path}（消したか、動かした絵です）")
            return
        self.work_save()
        if self.work_open(path):
            self._record()
            return
        try:
            self.canvas.replace_with_image(path, "AI の絵")
        except ValueError as e:
            self.notify("絵を出せません", "error", f"{e}（消したか、動かした絵です）")
            return
        self.canvas.redpen.clear()   # 赤ペンの印は前の絵の物（その絵の作業に残してある）
        self.canvas.redpen.undone.clear()
        self.work_key = str(path)
        self._record()

    # ---- 絵ごとの作業を残す・戻す（atelier/files/work_keep.py） ----
    def work_save(self, wait: bool = False):
        """今の絵の作業を残す。絵を替える前と閉じる前に呼ぶ。使っていない赤ペンの直し（隠した・元に戻した）はここで捨てる。
        書くのは裏の糸（wait なら書き終えるまで待つ）。アプリを開いている間は元に戻すの記録も覚える"""
        from atelier.files import work_keep as workkeep
        key = getattr(self, "work_key", None)
        if not key or not self.canvas.layers:
            return
        workkeep.discard_unused_redpen(self.canvas)
        self._refresh_layers()
        state = workkeep.capture(self.canvas)
        mem = self.__dict__.setdefault("_work_mem", {})
        mem.pop(key, None)
        mem[key] = (state, workkeep.undo_of(self.canvas))
        while len(mem) > workkeep.KEEP_UNDO:
            mem.pop(next(iter(mem)))   # 古い絵から忘れる（レイヤーと印はファイルから戻る。元に戻すの記録だけが無くなる）
        if workkeep.plain(state):
            self.run_io(lambda: workkeep.remove(key), lambda _v: None, "作業の保存")   # 開いただけの絵には作業のファイルを置かない
            return

        def done(v):
            if isinstance(v, BaseException):
                self.notify("作業を残せませんでした", "error", str(v))
        self.run_io(lambda: workkeep.write(state, key), done, "作業の保存")
        if wait:
            self.wait_io()

    def work_open(self, key: str) -> bool:
        """key の絵の作業が残っていれば、キャンバスに戻して True。無ければキャンバスに触らず False"""
        from atelier.files import work_keep as workkeep
        mem = self.__dict__.setdefault("_work_mem", {}).get(str(key))
        state, undo = mem if mem else (None, None)
        if state is None:
            self.wait_io()   # 書いている途中の作業を読まない
            state = workkeep.read(str(key))
            if state is None:
                return False
        workkeep.apply(self.canvas, state, undo)
        self.work_key = str(key)
        self._refresh_layers()
        return True


    def layer_from_file(self, path: str, name: str) -> bool:
        """絵をレイヤーとして重ねる。読めない絵（消した・動かした）は知らせて止める"""
        try:
            self.canvas.add_image_layer(path, name)
        except ValueError as e:
            self.notify("絵を重ねられません", "error", f"{e}（消したか、動かした絵です）")
            return False
        return True

    def _set_pinned(self, on: bool):
        """固定を外したら、いちばん新しい絵を出す（固定の間に描いた絵が出ないままにしない）"""
        self.statusBar().showMessage("表示する絵を固定しました。新しい絵は履歴に入ります" if on else "固定を外しました。最新の絵を出します", 4000)
        if not on and self.images:
            self.show_history_image(self.images[-1])
            self.history.setCurrentRow(0)

    def _record(self):
        if self.recorder.enabled:   # 先に Qt で縮めてから渡す（元の大きさで PIL に移すと 30 ミリ秒ほどかかった）
            from atelier.paint.timelapse import MAX_SIDE
            img = self.canvas.flatten()
            if max(img.width(), img.height()) > MAX_SIDE:
                img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.recorder.add(qimage_to_pil(img))

    def open_userstats(self):
        from atelier.panels import user_stats as userstats
        self._stats_dialog = userstats.open_dialog(self)
        return self._stats_dialog

    def _record_job(self, job):
        """AI が描き始めた。工程に分けて描く仕事が工程の絵（phase）を出すなら、それも順に残す"""
        self.recorder.begin_job()
        self._tl_before = None
        if self.recorder.enabled and self.recorder.frames:
            self._tl_before = self.recorder.frames[-1]
        phase = getattr(job, "phase", None)
        if phase is not None and hasattr(phase, "connect"):
            phase.connect(lambda img: self.recorder.add_strokes(img) if hasattr(img, "convert") else None)

    def _record_result(self, path: str):
        """AI の絵が仕上がった。途中の絵が届かなかった（1 回で描いた）ときは、仕上がった絵から線画→塗り→仕上げを逆算して残す"""
        if not self.recorder.enabled:
            return
        try:
            from PIL import Image
            with Image.open(path) as im:
                self.recorder.end_job(im.convert("RGB"), getattr(self, "_tl_before", None))
        except OSError:
            pass

    def export_timelapse(self, video: bool = False):
        """ファイルのメニューから、タイムラプスを GIF か動画に書き出す"""
        if not self.recorder.frames:
            self.notify("タイムラプスの記録がまだありません", "warn", "線を引くか AI で描くと記録されます（「表示」→「タイムラプス」→「タイムラプスを記録する」）")
            return
        from PySide6.QtWidgets import QFileDialog
        base = Path(self.settings.get("output_dir"))
        if video:
            dst, _ = QFileDialog.getSaveFileName(self, "タイムラプスを動画に書き出す", str(base / "timelapse.mp4"), "MP4 (*.mp4)")
            if dst:
                n, out = self.recorder.export_video(dst)
                self.notify(f"タイムラプスを {out.name} に書き出しました（{n} 枚）", "ok", str(out))
        else:
            dst, _ = QFileDialog.getSaveFileName(self, "タイムラプスを GIF に書き出す", str(base / "timelapse.gif"), "GIF (*.gif)")
            if dst:
                n = self.recorder.export(dst)
                self.notify(f"タイムラプスを GIF に書き出しました（{n} 枚）", "ok", dst)

    def _set_timelapse(self, on: bool):
        self.recorder.enabled = on
        self.settings.set("timelapse", "記録する" if on else "記録しない")

    def open_timelapse(self):
        from atelier.paint.timelapse import TimelapseDialog
        TimelapseDialog(self.recorder, self, Path(self.settings.get("output_dir"))).show()

    def open_player(self):
        from atelier.paint.timelapse import open_player
        open_player(self, Path(self.settings.get("output_dir")))

    def open_3d(self, path: str):
        from atelier.ai.to_3d import To3DDialog
        To3DDialog(path, self).show()

    def chara3d_from_canvas(self):
        """キャラデザのメニューの入口。今の絵を 1 枚に重ねて保存し、3D に進む画面を開く。絵が無ければ選ばせる"""
        import tempfile
        c = self.canvas
        if c.layers:
            out = Path(tempfile.mkdtemp(prefix="chara3d-")) / "chara.png"
            c.flatten().save(str(out))
            self.open_3d(str(out))
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "3D にする絵（三面図か 1 枚絵）", "", "画像 (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.open_3d(path)
