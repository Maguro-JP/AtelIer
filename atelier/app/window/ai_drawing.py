"""AI に描かせる頼みの送り出しと、描いた絵の取り込み"""
from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QMessageBox
from atelier.ai.engine import Studio
from atelier.ai.engine import check
from atelier.app.window.image_convert import fit_size
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.jobs import Bridge
from atelier.app.window.jobs import Job
from atelier.app.window.jobs import PhaseAsk
from pathlib import Path
import re
import time


class AiDrawingMixin:
    """AI に描かせる頼みの送り出しと、描いた絵の取り込み（Window が継承する）"""

    def export_to(self, folder: str = "") -> Path | None:
        """今の絵を 1 枚の PNG にしてフォルダーへ書き出す。空なら設定の保存先"""
        to = Path(folder).expanduser() if folder else Path(self.settings.get("output_dir"))
        try:
            to.mkdir(parents=True, exist_ok=True)
            path = to / f"{time.strftime('%Y%m%d-%H%M%S')}.png"
            qimage_to_pil(self.canvas.flatten()).save(path)
        except OSError as e:
            self.chat.add("ai", f"書き出せませんでした: {e}")
            return None
        self.chat.add("ai", f"書き出しました: {path}")
        return path

    def favorites(self):
        from atelier.ai.references import Favorites
        if getattr(self, "_favorites", None) is None:
            self._favorites = Favorites(self.settings.store)
        return self._favorites

    def open_favorites(self):
        from atelier.ai.references import FavoritesDialog

        def use(d):
            cur = self.entry.text().strip()
            self.entry.setText(f"{cur}, {d['words']}" if cur else d["words"])
        FavoritesDialog(self.favorites(), self, on_use=use).exec()

    def ask_reference_search(self):
        from PySide6.QtWidgets import QInputDialog
        q, ok = QInputDialog.getText(self, "参考画像を探す", "探す言葉（例: 海 少女 麦わら帽子）", text=self.entry.text().strip())
        if ok and q.strip():
            self.find_reference(q.strip())

    def find_reference(self, query: str):
        """ライブラリーと保存先のフォルダーから参考画像をタグで探し、いちばん合う物を参考画像に置く"""
        from atelier.ai import references as refs
        folders = [self.settings.get("output_dir")] + [str(p) for p in (self.settings.store.value("reference_dirs", []) or [])]
        items = self.library.works() + self.library.docs() if hasattr(self, "library") else []

        def done(got):
            if isinstance(got, BaseException) or not got:
                self.chat.add("ai", f"「{query}」に合う参考画像は見つかりませんでした（ライブラリーと保存先のディレクトリを探しました）")
                return
            self.reference.load(got[0][1])
            self.ai_panel.use_ref.setChecked(True)
            lines = "\n".join(p for _s, p in got[:5])
            self.chat.add("ai", f"「{query}」で {len(got)} 枚見つけました。いちばん合う絵を参考画像に置きました:\n{lines}")
        self.in_background(lambda: refs.find_images(query, items, folders), done, "参考画像を探す")

    def offer_prompt(self, bubble, new: str | None, restored: bool = False):
        """答えの吹き出しに、描く内容の案を AI の欄へ入れるボタンを付ける。読み戻した会話の案にも付ける"""
        if not new:
            return
        if not restored:
            bubble.set_text(bubble.text + f"\n\n描く内容の案: {new}")
        bubble.proposal = new

        def fill():
            self.entry.setText(new)
            dock = self.panels["chat"][0] if hasattr(self, "panels") else None
            if dock is not None:
                dock.show()
                dock.raise_()
            self.ai_panel.sections["描く内容"].set_open(True)
            self.ai_pages.setCurrentIndex(0)
        bubble.add_button("AI の欄に入れる", "この案を AI の欄の「描く内容」に入れます（描きはしません）", fill)
        bubble.add_button("入れて描く", "この案を「描く内容」に入れて、すぐ描きます", lambda: (fill(), self.send()))
        self.chat._fit(bubble)
        if not restored:
            self.chat.save()

    def _show_model(self):
        from atelier.models.catalog import image_model
        from atelier.models.first_setup import AUTO
        from atelier.models.favorites import FAV
        key = self.settings.get("image_model")
        if key == AUTO:   # おまかせで選んだ模型を出す（選ぶ前は、今読んでいる模型）
            chosen = getattr(getattr(self, "studio", None), "chosen", None)
            painter = getattr(getattr(self, "studio", None), "painter", None)
            name = chosen[0] if chosen else image_model(painter.model).name if getattr(painter, "model", "") else ""
            self.model_label.setText("おまかせ" + (f"（{name}）" if name else ""))
            self.model_label.setToolTip(f"おまかせで選んだ理由: {chosen[1]}" if chosen else "描くときに、手元の模型から頼みに合う物を選びます")
        elif key == FAV:
            from atelier.models import favorites as favmodels
            data = favmodels.load()
            self.model_label.setText(favmodels.label(favmodels.active()))
            self.model_label.setToolTip("編成の役目ごとの模型で、工程を分けて描きます\n" + self._set_tip(data))
        else:
            self.model_label.setText(image_model(key).name)
            self.model_label.setToolTip("この模型で描きます。短い頼みは 1 回で速く、細かい頼みとプリセットは工程を分けて描きます。押すと切り替えられます")

    def _fit_features(self):
        """選んだ模型の世代で使えない機能（ラフから、直す、参考画像）のボタンを止め、理由を出す"""
        from atelier.models.catalog import family as fam, image_model
        painter = getattr(getattr(self, "studio", None), "painter", None)
        model = getattr(painter, "model", "") or ""
        if not model or not hasattr(self, "ai_panel"):
            return
        f = fam(image_model(model).family)
        why = f"{f.name} の模型では使えません。SDXL の模型に替えると使えます"
        panel = self.ai_panel
        buttons = panel.mode_buttons[1]   # mode_buttons は（並び、ボタンの一覧）の 2 つ組
        widgets = [(buttons[1], f.sketch), (buttons[2], f.inpaint)]
        if hasattr(panel, "use_ref"):
            widgets.append((panel.use_ref, f.reference))
        for b, ok in widgets:
            if b.property("tip0") is None:
                b.setProperty("tip0", b.toolTip())   # 元の説明は残しておき、使えるときに戻す
            b.setEnabled(ok)
            b.setToolTip(b.property("tip0") if ok else why)
        if not f.sketch and self.mode.currentIndex() == 1 or not f.inpaint and self.mode.currentIndex() == 2:
            self.mode.setCurrentIndex(0)

    def check_ai(self) -> dict:
        """AI が使えるかを確かめて、下の欄に出す。描く前と起動のときに毎回呼ぶ"""
        self._show_model()
        self._fit_features()
        st = check(getattr(self.studio, "painter", None), getattr(self.studio, "words", None)) if isinstance(self.studio, Studio) else \
            {"torch": True, "image": True, "words": True, "reason": ""}
        if st["image"]:
            self.ai_label.setText("AI: 使えます" + ("" if st["words"] else "（言葉の模型なし。日本語は語の表で英語に直します）"))
            self.ai_label.setStyleSheet("color:#8fd18f")
        else:
            self.ai_label.setText("AI: 使えません")
            self.ai_label.setStyleSheet("color:#ff7a5c")
            self.ai_label.setToolTip(st["reason"])
        return st

    def send(self, once: str | None = None):
        """描く。once を渡すと、描くワードの欄を変えずに、この回だけその言葉で描く（チャットの頼み）"""
        if not isinstance(once, str):
            once = None   # ボタンの clicked は押した印（真偽値）を渡す。頼みの文と取り違えないように
        text = (self.entry.text() if once is None else once).strip()
        pen = self.canvas.redpen
        if self.thread and text:   # 描いている間の頼みは受けない。黙って捨てると、押しても何も起きないように見えた
            self.progress_popup.pop()
            self.statusBar().showMessage("描いている途中です。終わってから頼んでください（止めるときは「止める」）", 6000)
            return
        shown = pen.shown()   # 隠した印は直さないので、指示の有無も見ない（隠した印の空の指示で、押しても何も起きなかった）
        if not self.thread and not text and shown and not all(pen.texts[i - 1] for i in shown):
            self.inspect_marks_then_fix()   # 指示の空の囲みは、その中を検品し、見つけた崩れを指示にして 1 回だけ直す
            return
        if self.thread or not text and not (shown and all(pen.texts[i - 1] for i in shown)):   # 絵の上に全部書いてあれば、チャットは空でよい
            return
        if not text:
            text = " / ".join(f"{i}: {pen.texts[i - 1]}" for i in shown)
        from atelier.agent import commands
        words = getattr(getattr(self, "studio", None), "words", None)
        if commands.needs_model(text, words):
            # 言葉の模型に聞くのは裏で行う。画面の糸で聞くと、「赤」「保存」などの操作の言葉を含む頼みで
            # 模型の読み込みと推論の間（数秒〜数十秒）アプリが固まった
            if getattr(self, "asking", False):
                return
            self.asking = True
            self.button.setEnabled(False)

            token = self._ask_token = getattr(self, "_ask_token", 0) + 1

            def got(picked):
                if token != self._ask_token:
                    return   # 止めた回の答え
                self.asking = False
                self.button.setEnabled(True)
                self._send_after(text, None if isinstance(picked, BaseException) else picked, once is not None)
            self.in_background(lambda: commands.by_model(text, words), got, "言葉の模型の答え待ち")
            return
        self._send_after(text, None, once is not None)   # 模型に聞けないときは言葉の決まりで選ぶ

    def in_background(self, work, done, name: str = "裏の処理"):
        """work を裏の糸で動かし、答えを画面の糸の done に渡す。work が例外を出したら、その例外を渡す"""
        import threading
        key = self._bg_register(done, name)

        def run():
            try:
                v = work()
            except BaseException as e:   # noqa: BLE001  裏で落ちても画面の糸に必ず返す
                v = e
            self._bg_emit(key, v)
        threading.Thread(target=run, daemon=True).start()

    def _bg_register(self, done, name: str = "裏の処理") -> int:
        """答えの受け手を画面の糸で覚え、番号を返す。裏の糸には番号だけを渡す。
        前は呼ぶたびに Bridge（QObject）を作って裏の糸に渡していた。裏の糸がその最後の参照を手放すと、
        Python の側の後片付けが裏の糸で走り、画面の糸で落ちた（Shiboken の runDeletionInMainThread で Segmentation fault）"""
        if getattr(self, "_bridge", None) is None:
            self._bridge = Bridge(self)   # 窓と同じだけ生きる 1 つだけの橋。裏の糸で消えることはない
            self._bridge.got.connect(self._bg_done, Qt.QueuedConnection)
            self._waiting: dict[int, object] = {}
            self._next_key = 0
        self._next_key += 1
        self._waiting[self._next_key] = done
        self.activity.bg_begin(self._next_key, name)   # 進みの欄に、裏で動いている物を出す
        self.bg_pending = getattr(self, "bg_pending", 0) + 1
        self.gc_guard()
        return self._next_key

    def gc_guard(self):
        """裏の糸が動いている間は自動の gc を止め、画面の糸で若い世代だけを片付ける。
        裏の糸で gc が走ると、消えた画面の部品の Python 側の後片付けが裏の糸で起き、画面の糸が落ちた
        （Shiboken の runDeletionInMainThread で Segmentation fault。線画を裏で書いている間に再現した）。
        裏の糸が全部終われば、自動の gc に戻す"""
        import gc
        if self.thread is not None or getattr(self, "bg_pending", 0):
            if gc.isenabled():
                gc.disable()
            gc.collect(0)
        elif not gc.isenabled():
            gc.enable()

    def _bg_emit(self, key: int, v):
        try:
            self._bridge.got.emit((key, v))
        except RuntimeError:
            pass   # 窓を閉じたあと

    def _send_after(self, text: str, picked, once: bool = False):
        from atelier.agent import commands
        reply = commands.handle(self, text, picked=picked)   # 操作の頼み（道具・色・欄・配置など）はその場で行い、絵は描かない
        if reply:
            if not once:   # 欄に書いた操作の言葉は欄から消す。チャットから来た言葉では欄に触らない
                self.entry.clear()
            self.say(text, "あなた")
            self.say(reply)
            self.feature_tour("ai_commands")
            return
        self._draw_now(text)

    def _draw_now(self, text: str):
        """頼みを描く（新規・ラフから・直す）。チャットの頼みと、右クリックの指示のショートカットの同じ入口"""
        if self.canvas.redpen.marks and self.mode.currentIndex() != 2:
            self.mode.setCurrentIndex(2)   # 赤ペンの印があるときの頼みは、印の所を直す頼みとして受ける
        if self.mode.currentIndex() == 2 and not self.canvas.redpen.marks and self.canvas.selection_mask() is None:
            self.mode.setCurrentIndex(0)   # 直す所が無いときは、止めずに新しく描く頼みとして受ける（直すのままで止まっていた）
        st = self.check_ai()
        if not st["image"]:
            self.say(st["reason"] or "AI が使えません")
            self.progress_popup.tell("描けません", st["reason"] or "AI が使えません")   # 描く前に止まったことも右下に出す
            return
        text = self._keep_original(text)
        if text is None or not self._ok_batch():
            return
        self.last_text = text
        if self.mode.currentIndex() != 2:   # 赤ペン・選択範囲の直しの指示は、描くワードの履歴に入れない（その絵の 1 か所だけの言葉）
            self._remember_prompt(text)
        self.say(f"描きます: {text}")
        self.button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.feature_tour("draw")
        self.activity.begin(text, self.mode.currentText())
        self.activity.set_sheet(1, 1 if self.mode.currentIndex() == 2 else self.ai_panel.count())
        self.activity.status("AI が使えるかを確かめました")
        m = re.search(r"([124１２４一二四])\s*枚", text)
        if m:   # 「4 枚描いて」のように枚数を書いたら、その枚数で描く
            self.ai_panel.set_count({"１": 1, "一": 1, "２": 2, "二": 2, "４": 4, "四": 4}.get(m.group(1)) or int(m.group(1)))
        if self.ai_panel.reference() is not None and hasattr(self.studio.painter, "reference_ready") \
                and not self.studio.painter.reference_ready():
            from atelier.ai.engine import REFERENCE_GB
            gb = REFERENCE_GB.get(getattr(self.studio.painter, "family", "sdxl"), 3)
            if QMessageBox.question(self, "参考画像に寄せる", f"参考画像を読む部品（約 {gb}GB）を初めに取ります。取りますか。") \
                    != QMessageBox.Yes:
                self.ai_panel.use_ref.setChecked(False)   # 取らないなら、参考画像なしで描く
        self.offer_two_stage_parts()
        mode = self.mode.currentIndex()
        base = qimage_to_pil(self.canvas.flatten()) if mode in (1, 2) else None
        regions = self.fix_regions(text) if mode == 2 else None
        seeds = self.ai_panel.seeds()[:1 if mode == 2 else None]
        self.ai_panel.seed.setValue(seeds[0])   # 使った種を見せる（固定すれば同じ絵を描き直せる）
        self.batch, self.batch_items = [], []
        self.job_kind = "fix" if mode == 2 else "draw"
        meta = dict(mode=self.mode.currentText(), preset=self.ai_panel.preset, style_name=self.ai_panel.style,
                    size=list(self.size_pick.currentData()), strength=self.strength.value())
        if mode == 2:
            meta["source"] = self.fix_source()
        self._apply_avoid()
        self.job_studio = self._fix_studio() if mode == 2 else self.studio
        self._work_layer = None   # 精度優先で描けた工程の絵を置く作業用のレイヤー（回ごとに新しく足す）
        if not hasattr(self, "_phase_ask"):
            self._phase_ask = PhaseAsk(self)
        self.job_studio.phase_confirm = self._phase_ask if self.settings.get("phase_confirm") else None
        self.before_heavy(self.job_studio.painter)
        self.thread = QThread()
        self.job = Job(self.job_studio, text, seeds, base=base, strength=self.strength.value() / 100,
                       style=self.ai_panel.style_tags(), regions=regions, reference=self.ai_panel.reference(),
                       ref_scale=self.ai_panel.ref_scale.value() / 100, meta=meta,
                       size=fit_size(*self.canvas.size_px()) if base is not None else self.size_pick.currentData())
        self._worker = self.job
        self.job.moveToThread(self.thread)
        self.thread.started.connect(self.job.run)
        self.job.status.connect(self.on_status)
        self.job.preview.connect(self.show_preview)
        self._record_job(self.job)
        self.job.one.connect(self.on_one)
        self.job.done.connect(self.finish)
        self.job.failed.connect(self.fail)
        self.gc_guard()
        self.thread.start()

    def _keep_original(self, text: str) -> str | None:
        """直しの頼みが、描いたときの描くワードや赤ペンの指示と食い違えば、確かめてから進める。
        黙って進めると元の指示が無視された。返すのは描く頼み（やめたら None）"""
        if self.mode.currentIndex() != 2:
            return text
        from atelier.ui import confirm
        from atelier.agent import intent
        pen = self.canvas.redpen
        given = set(intent.terms(text))
        old = [getattr(self, "origin_prompt", "") or ""] + [t for t in pen.texts if t and not set(intent.terms(t)) <= given]
        found = intent.conflicts(old, text)
        if not found:
            return text
        lines = "\n".join(f"・元「{a}」 → 今「{b}」" for a, b in found)
        picked = confirm.ask(self, "intent", "元の頼みと食い違います",
                             "今の頼みは、元の頼み（描くワード・赤ペンの指示）と食い違います。\n" + lines,
                             [("keep", "元のまま"), ("new", "新しい頼みにする")],
                             detail="「元のまま」は食い違った所を外して直します。「新しい頼みにする」は今の頼みのとおりに直します。")
        if picked == "cancel":
            self.statusBar().showMessage("直しをやめました。元の絵のままです", 6000)
            return None
        if picked == "keep":
            rest = intent.drop(text, [b for _a, b in found])
            if not rest:
                self.notify("元の頼みのままにしました", "info", "食い違った所を外すと、直す所が残りませんでした")
                return None
            return rest
        gone = {a for a, _b in found}
        kept = [t for t in intent.terms(getattr(self, "origin_prompt", "") or "") if t not in gone]
        self.origin_prompt = "、".join(kept + [b for _a, b in found])   # 次の直しは、新しい頼みを元として見る
        return text

    def _ok_batch(self) -> bool:
        """まとめて描く（枚数が多い）ときは、時間がかかることを先に確かめる"""
        from atelier.ui import confirm
        n = self.ai_panel.count_spin.value()
        if self.mode.currentIndex() == 2 or n < confirm.BATCH_COUNT:
            return True
        return confirm.ask(self, "batch", "まとめて描く", f"{n} 枚をまとめて描きます。1 枚より時間がかかります（描いている間も止められます）。",
                           [("go", f"{n} 枚描く")]) == "go"

    def offer_two_stage_parts(self):
        """2 段で描ける模型がそろっていて、部品（約 2.9GB）だけが無いときに、取るかを聞く。
        取らないと、おまかせでは黙って 1 つの模型で描き、崩れにくい描き方が使われないままになる"""
        if self.studio.way == "one" or self.mode.currentIndex() != 0 or getattr(self, "_two_parts_asked", False):
            return
        from atelier.ai import two_stage as twostage
        try:
            if twostage.pick(self.have_image_models(), self.studio.painter.model) is None or twostage.parts_ready():
                return
        except Exception:
            return
        self._two_parts_asked = True   # 断られたら、この起動の間は聞き直さない
        if QMessageBox.question(self, "構図と仕上げを分けて描く",
                                f"手足や姿勢が崩れにくい描き方（構図と仕上げを分ける）に使う部品（約 {twostage.PARTS_GB}GB）を取りますか。"
                                "取らないときは、1 つの模型で描きます。") == QMessageBox.Yes:
            self.studio.fetch_two_parts = True   # 取るのは描く裏の処理で行う（画面を止めない）

    def save_layer_png(self, path: str | None = None) -> str:
        """選んでいるレイヤーだけを、透明を残したまま PNG で保存する"""
        c = self.canvas
        if not c.layers:
            return ""
        layer = c.layers[c.current]
        if not isinstance(path, (str, Path)):   # メニューからは triggered の真偽（False）が来る。前はそれを道として読み、押すたびに落ちた
            path, _ = QFileDialog.getSaveFileName(self, "レイヤーを PNG で保存", str(Path(self.settings.get("output_dir")) / f"{layer.name}.png"), "PNG (*.png)")
            if not path:
                return ""
        if not layer.image.save(path, "PNG"):
            self.notify("レイヤーを保存できませんでした", "error", f"{path}\n保存先に書き込めるか、ディスクに空きがあるかを確かめて、別の場所を選び直してください")
            return ""
        self.statusBar().showMessage(f"{layer.name} を保存しました: {path}", 6000)
        return path

    def export_layers_png(self, folder: str | None = None) -> list[str]:
        """全部のレイヤーを 1 枚ずつ PNG で書き出す。名前は下からの番号と名前（並びが分かり、同じ名前でも上書きしない）"""
        import re
        c = self.canvas
        if not c.layers:
            return []
        if not isinstance(folder, (str, Path)):   # 同じく triggered の真偽が来る
            folder = QFileDialog.getExistingDirectory(self, "レイヤーを書き出すディレクトリ", str(self.settings.get("output_dir")))
            if not folder:
                return []
        out = []
        for i, layer in enumerate(c.layers, 1):
            safe = re.sub(r'[\\/:*?"<>|]', "_", layer.name).strip() or "layer"
            path = str(Path(folder) / f"{i:02d}-{safe}.png")
            if layer.image.save(path, "PNG"):
                out.append(path)
        self.statusBar().showMessage(f"{len(out)} 枚のレイヤーを書き出しました: {folder}", 6000)
        return out
