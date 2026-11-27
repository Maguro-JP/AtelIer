"""チャットの欄と、チャットの文から組む頼みの実行"""
from __future__ import annotations

from PySide6.QtCore import Qt
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.jobs import Bridge
from pathlib import Path
import re
import time


class ChatMixin:
    """チャットの欄と、チャットの文から組む頼みの実行（Window が継承する）"""

    def say(self, text: str, who: str = "AtelIer"):
        """進み具合の知らせ（描いた・検品の結果・工程・取れなかった物など）を進み具合の欄に書く。
        前はチャットに吹き出しで出していて、チャットが進み具合の履歴になり、会話が埋もれて読み返せなかった。
        チャットは利用者と AI の会話だけにする（知らせは進み具合の欄の「知らせ」と下の帯で見る）"""
        if who == "あなた":
            return None   # 欄に書いた頼みの写しは、進み具合には要らない
        self.progress_notes = (getattr(self, "progress_notes", []) + [f"{time.strftime('%H:%M')} {text}"])[-40:]
        act = getattr(self, "activity", None)
        if act is not None:
            act.detail.setText(text)
            # 模型に渡した言葉（activity の words_log）も詳細に残す。知らせだけで上書きすると、渡した言葉が見られなくなった
            act.detail.setToolTip("\n".join(self.progress_notes[-15:] + list(getattr(act, "words_log", []) or [])[-12:]))
        self.statusBar().showMessage(text, 8000)
        return None

    # ---- チャットの相談相手（言葉の模型。atelier/agent/assistant.py の converse） ----
    def chat_state(self) -> str:
        """言葉の模型に見せる、今の絵・レイヤー・履歴の様子。短く（数行）まとめる"""
        lines = []
        c = getattr(self, "canvas", None)
        if c is not None and c.layers:
            w, h = c.size_px()
            names = []
            for i, layer in reversed(list(enumerate(c.layers))):
                tag = ("赤ペン" if layer.redpen else "") + ("・隠す" if not layer.visible else "") + ("・選択中" if i == c.current else "")
                names.append(layer.name + (f"（{tag.strip('・')}）" if tag else ""))
            lines.append(f"キャンバス: {w}×{h}、レイヤー {len(c.layers)} 枚（上から: {'、'.join(names[:6])}）")
            marks = len(getattr(getattr(c, "redpen", None), "marks", []) or [])
            lines.append(f"赤ペンの印: {marks} 個" + ("（「赤ペンで直す」で囲んだ所だけ直せる）" if marks else ""))
        else:
            lines.append("キャンバス: まだ絵がない")
        neg = getattr(getattr(self, "ai_panel", None), "negative", None)
        if neg is not None and neg.text().strip():
            lines.append(f"禁止ワード: {neg.text().strip()[:80]}")
        try:
            painter = getattr(getattr(self, "studio", None), "painter", None)
            if getattr(painter, "model", ""):
                from atelier.models.catalog import image_model
                lines.append(f"絵の模型: {image_model(painter.model).name}")
        except Exception:   # noqa: BLE001  様子が取れなくても会話は続ける
            pass
        hist = getattr(self, "history", None)
        if hist is not None and hist.count():
            done = [hist.item(i).text().strip() for i in range(max(0, hist.count() - 3), hist.count())]
            done = [d[:40] for d in done if d]
            if done:
                lines.append("最近描いた絵: " + " ／ ".join(done))
        try:
            from atelier.ai import finishers
            names = [f.label for f in list(finishers.REGISTRY.values())[:14]]
            lines.append("加工の名前: " + "、".join(names))
        except Exception:   # noqa: BLE001
            pass
        return "\n".join(lines)

    def chat_action_line(self, act: tuple[str, str]) -> str:
        kind, arg = act
        return {"描く": f"この回だけ「{arg}」で描きます（描くワードの欄は変えません）",
                "赤ペンで直す": "赤ペンで囲んだ所だけを直します",
                "加工": f"今の絵に「{arg}」を掛けます（新しいレイヤーに置きます）",
                "模型": f"絵の模型を「{arg}」に替えます",
                "描くワード": f"描くワードを「{arg}」に書き換えます"}.get(kind, f"{kind} {arg}")

    def offer_chat_action(self, act: tuple[str, str], delay_ms: int = 1500):
        """操作をする前に、何をするかを 1 行で見せ、少し待ってからする（「やめる」で止められる）"""
        from PySide6.QtCore import QTimer
        b = self.chat.add("ai", "する: " + self.chat_action_line(act), remember=False)
        b.action = act
        state = {"cancelled": False}

        def stop():
            state["cancelled"] = True
            b.set_text(b.text + "\n（やめました）")
            cancel.setEnabled(False)
            self.chat._fit(b)
        cancel = b.add_button("やめる", "この操作をしません", stop)
        self.chat._fit(b)

        def go():
            if state["cancelled"]:
                return
            cancel.setEnabled(False)
            done = self.run_chat_action(act)
            if done:
                self.chat.add("ai", done, remember=False)
        QTimer.singleShot(delay_ms, go)
        return b

    def run_chat_action(self, act: tuple[str, str]) -> str | None:
        """チャットで頼まれた操作をする。返すのは結果を伝える 1 文（無ければ None）"""
        from atelier.agent import assistant
        kind, arg = act
        if kind == "描く":
            self.watch_chat_result()
            self.send(arg)
            return None
        if kind == "赤ペンで直す":
            if not getattr(self.canvas.redpen, "marks", None):
                if "redpen" in self.tool_actions and self.canvas.tool != "redpen":
                    self.tool_actions["redpen"].trigger()
                return "赤ペンの印がありません。赤ペンにしたので、直す所を囲んでからもう一度頼んでください"
            self.watch_chat_result()
            self.fix_marked()
            return None
        if kind == "加工":
            from atelier.ai import finishers
            key = arg.strip()
            name = next((n for n, f in finishers.REGISTRY.items() if key in (n, f.label)), None) or next(
                (n for n, f in finishers.REGISTRY.items() if key and (key in f.label or f.label in key)), None)
            if name is None:
                return f"「{arg}」という加工が見つかりませんでした。右クリックの「加工」から選べます"
            if not self.canvas.layers:
                return "加工する絵がありません"
            self.watch_chat_result()
            self.finish_with(name, background=True)
            return None
        if kind == "模型":
            from atelier.models.catalog import all_images
            key = arg.strip().lower()
            m = next((m for m in all_images() if key and (key in m.name.lower() or key in m.repo.lower())), None)
            if m is None:
                return f"「{arg}」という絵の模型が見つかりませんでした。「AI」のメニューの「模型の管理」で探せます"
            self.switch_model("絵の模型", m.repo)
            return f"絵の模型を「{m.name}」にしました"
        if kind == "描くワード" and arg:
            self.entry.setText(arg)
            return f"描くワードを「{arg}」にしました（元に戻すときは Ctrl+Z）"
        return assistant.NO_MODEL if kind is None else None

    def _chat_stream_bridge(self):
        """裏の糸で流れてくる答えを、画面の糸の吹き出しに渡す橋（窓と同じだけ生きる）"""
        if getattr(self, "_chat_stream", None) is None:
            self._chat_stream = Bridge(self)
            self._chat_stream.got.connect(self._chat_piece, Qt.QueuedConnection)
        return self._chat_stream

    def _chat_piece(self, text: str):
        b = getattr(self, "_chat_live", None)
        if b is None:
            self.chat.set_busy(False)
            b = self._chat_live = self.chat.add("ai", text, remember=False, save=False)
        else:
            b.set_text(text)
            self.chat._fit(b)

    def chat_send(self, text: str):
        """チャットに書かれた一言に答える。操作ならして、「〜を描いて」なら描く内容に入れて描き、
        それ以外は言葉の模型に裏で聞く（画面の糸で聞くと、読み込みと推論の間アプリが固まる）"""
        from atelier.agent import assistant
        from atelier.agent import commands
        self.chat.add("user", text)
        self.watch_chat_result()   # 絵が変わったら、終わったときに縮小した絵を返す
        if getattr(self, "asking", False):
            self.chat.add("ai", "前の答えを待っています。少し待ってからもう一度送ってください", remember=False)
            return
        from atelier.words import chat_words as chatwords
        changed = chatwords.parse(text, self.entry.text())
        if changed is not None:   # 描くワードを変えるのは、チャットでそう頼まれたときだけ（何をどう変えたかを 1 行で返す）
            self.entry.setText(changed[0])
            self.chat.add("ai", changed[1])
            return
        if self.chat_plan(text):   # 文の頼み（繰り返し・予約・書き出し・加工の並び・参考画像・お気に入り）は段取りにして行う
            return
        words = getattr(getattr(self, "studio", None), "words", None)
        self.asking = True
        self.chat.set_busy(True)

        def picked(p):
            p = None if isinstance(p, BaseException) else p
            reply = commands.handle(self, text, picked=p)
            if reply:
                self.asking = False
                self.chat.set_busy(False)
                self.chat.add("ai", reply)
                self.feature_tour("ai_commands")
                return
            body = assistant.draw_request(text)
            if body is None and re.fullmatch(r"\s*(今の(描くワード|描く内容)で)?\s*(描いて|描く|かいて|描け)(ください|下さい)?\s*[。！!]*\s*", text):
                body = self.entry.text().strip() or self.last_text   # 「描いて」だけなら、今の描くワードで描く
            if body:
                body = self.favorites().apply(body)[0]   # 「お気に入りの水彩で描いて」は、残した言葉を足して描く
                self.asking = False
                self.chat.set_busy(False)
                # チャットの文は言語の模型への指示で、描くワードの欄（描画の模型への設定）は書き換えない。
                # 文に描く内容があればこの回だけ使い、無ければ今の描くワードで描く
                if body == self.entry.text().strip():
                    self.chat.add("ai", f"今の描くワード「{body}」で描きます")
                else:
                    self.chat.add("ai", f"この回だけ「{body}」で描きます（描くワードの欄は変えません）")
                self.send(body)
                return
            if self.thread is not None and getattr(words, "ready", lambda: False)():
                self.asking = False   # 描いている間は言葉の模型を描く側が使う。同時に使うと落ちることがある
                self.chat.set_busy(False)
                self.chat.add("ai", "描いている間は答えられません。描き終わってからもう一度送ってください")
                return
            turns, prompt, state = list(self.chat.turns[:-1]), self.entry.text().strip(), self.chat_state()
            self._chat_live = None
            bridge = self._chat_stream_bridge()
            self.in_background(lambda: assistant.converse(words, turns, text, prompt, state, on_piece=bridge.got.emit),
                               answered, "言葉の模型の答え待ち")

        def answered(got):
            self.asking = False
            self.chat.set_busy(False)
            live, self._chat_live = getattr(self, "_chat_live", None), None
            if isinstance(got, BaseException):
                if live is not None:
                    self.chat.list.removeWidget(live)
                    live.hide()
                    live.deleteLater()
                self.chat.add("ai", f"答えられませんでした: {got}")
                return
            reply, new, act = got
            if live is not None:   # 流しながら出した吹き出しを、仕上がった答えにして会話に入れる
                self.chat.list.removeWidget(live)
                live.hide()
                live.deleteLater()
            b = self.chat.add("ai", reply) if reply else None
            if reply == assistant.NO_MODEL and b is not None:
                b.add_button("言葉の模型を取る", assistant.NO_MODEL_HOW, self.manage_models)
                self.chat._fit(b)
            if b is not None:
                self.offer_prompt(b, new)
            if act is not None:
                self.offer_chat_action(act)

        if commands.needs_model(text, words):
            self.in_background(lambda: commands.by_model(text, words), picked, "言葉の模型の答え待ち")
        else:
            picked(None)

    # ---- チャットの文の頼み（atelier/agent/chat_plan.py） ----
    _FIND_REF = re.compile(r"参考(画像|資料|の絵)を?.{0,4}(探|検索|見つけ)|find\s+reference", re.I)
    _FAV_ADD = re.compile(r"お気に入り(の作風)?(に|へ|として)\s*(保存|登録|足|追加|残)")

    def chat_plan(self, text: str) -> bool:
        """チャットの文を段取りに読んで行う。普通の 1 回の頼み・操作・質問なら False（今までの流れに任せる）"""
        from atelier.agent import chat_plan as chatplan
        from atelier.ai import finishers
        if self._FIND_REF.search(text):
            q = self._FIND_REF.sub(" ", text)
            q = re.sub(r"(を|の|して|ください|[、。])", " ", q).strip()
            self.find_reference(q or self.entry.text().strip())
            return True
        if self._FAV_ADD.search(text):
            m = re.search(r"「([^」]+)」\s*[:：=＝は]?\s*(.+)?", text)
            if not m:
                self.chat.add("ai", "「名前」と言葉を書いてください。例: お気に入りに保存「水彩」: watercolor, soft colors")
                return True
            words = (m.group(2) or "").strip(" 、。") or self.entry.text().strip()
            words = self._FAV_ADD.sub(" ", words).strip(" 、。して")
            self.favorites().put(m.group(1), words)
            self.chat.add("ai", f"登録した作風「{m.group(1)}」に「{words}」を残しました。「{m.group(1)}で描いて」で使えます")
            return True
        try:
            # 一覧の見出しだけを使う。available() は使えるかを確かめるので 1 秒余りかかり、画面の糸で呼ぶとチャットが固まった
            entries = [{"name": n, "label": f.label} for n, f in finishers.REGISTRY.items()]
        except Exception:   # noqa: BLE001  仕上げの一覧が読めなくても、ほかの段取りは読む
            entries = []
        from atelier.panels import ai_panel as aipanel
        prompts = self.shortcut_store().prompts()
        asked = chatplan.clarify(text, entries, [n for n, *_ in aipanel.STYLES], prompts)
        if asked is not None:
            self.offer_choices(*asked)
            return True
        called = chatplan.find_prompts(text, prompts)
        if len(called) == 1:
            p = called[0]
            self.chat.add("ai", f"登録した指示「{p['name']}」（{p['text']}）で直します")
            self.run_shortcut(p["id"])
            return True
        plan = chatplan.parse(text, entries)
        if not plan.special:
            return False
        if plan.scheduled:
            later = re.sub(r"\s+", " ", chatplan._SCHEDULE_WORDS.sub(" ", text)).strip()
            self.scheduler.add(later, plan.after_min, plan.daily)
            self.chat.add("ai", f"予約しました: {chatplan.describe(plan)}。アプリを開いている間に行います（設定 → 予約の一覧で見る・消す）")
            return True
        self.run_plan(plan)
        return True

    def offer_choices(self, question: str, choices):
        """曖昧な頼みに、候補をボタンで出す。押すと、その文をチャットに送ったのと同じに行う"""
        b = self.chat.add("ai", question)
        for label, send in choices:
            b.add_button(label, f"「{send}」と頼みます", lambda _c=False, t=send: self.chat_send(t))
        self.chat._fit(b)
        return b

    def watch_chat_result(self):
        """チャットの頼みで絵が変わったら、処理が終わったときに縮小した絵をチャットに返す。
        終わりは画面の糸の時計で見る（描く・加工は裏で動き、終わりの知らせの形が処理ごとに違うため）"""
        from PySide6.QtCore import QTimer
        if getattr(self, "_chat_watch", None) is not None:
            return   # 前の頼みを見ている途中。その前の絵と比べる
        self._chat_watch = self._canvas_key()
        QTimer.singleShot(400, self._chat_watch_tick)

    def _canvas_key(self) -> str:
        import hashlib
        img = self.canvas.flatten()
        return f"{img.width()}x{img.height()}:" + hashlib.blake2b(bytes(img.constBits()), digest_size=16).hexdigest()

    def _chat_watch_tick(self):
        from PySide6.QtCore import QTimer
        if not self._plan_idle() or getattr(self, "_plan_queue", []):
            QTimer.singleShot(400, self._chat_watch_tick)
            return
        before, self._chat_watch = self._chat_watch, None
        if before is None or self._canvas_key() == before:
            return
        folder = Path(self.settings.get("output_dir")) / "chat"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.png"
            qimage_to_pil(self.canvas.flatten()).save(path)
        except OSError as e:
            self.chat.add("ai", f"結果の絵を残せませんでした: {e}", remember=False)
            return
        self.chat.add_image("できました。絵を押すと元の大きさで開きます", str(path))

    def open_chat_image(self, path: str):
        """チャットの結果の絵を元の大きさで見る。キャンバスに開くこともできる"""
        return self.chat.view_image(path, ("キャンバスに開く", "この絵をキャンバスに開きます（元に戻すで戻せます）", self.edit_image))

    def _scheduled(self, text: str):
        self.chat.add("ai", f"予約の時刻になりました: {text}")
        self.chat_send(text)

    def run_plan(self, plan):
        """段取りを 1 つずつ、前の作業が終わってから行う。描く・加工は裏で動くので、空いたのを見てから次を始める"""
        from atelier.agent import chat_plan as chatplan
        body = plan.body
        if body:
            fav = self.favorites().apply(body)
            body = fav[0]
        acts = {"upscale": self.upscale_canvas, "transparent": self.make_transparent, "chibi": self.make_chibi,
                "lineart": self.make_lineart, "pixel": self.make_pixel}
        queue = []
        for step in plan.steps:
            if step in ("draw", "fix"):
                for _ in range(plan.repeat):
                    queue.append(lambda st=step: self._plan_draw(body, fix=st == "fix"))
            elif step.startswith("finisher:"):
                queue.append(lambda n=step.split(":", 1)[1]: self.finish_with(n, background=True))
            elif step in acts:
                queue.append(acts[step])
        if plan.export is not None:
            queue.append(lambda: self.export_to(plan.export))
        if plan.keep_best and plan.repeat > 1:
            # どれが良いかは利用者が決める（AI が自分で出来を判定しない）。描いた絵は全部履歴に残し、選んでもらう
            queue.append(lambda: self.chat.add("ai", f"{plan.repeat} 枚描きました。履歴の欄で見比べて、残す絵を選んでください"
                                                     "（気に入った絵は「この絵が好き」で覚えます）"))
        self.chat.add("ai", f"段取り: {chatplan.describe(plan)}")
        self._plan_queue = getattr(self, "_plan_queue", []) + queue
        self._plan_pump()

    def _plan_idle(self) -> bool:
        return self.thread is None and not getattr(self, "bg_pending", 0) and not getattr(self, "asking", False)

    def _plan_pump(self):
        from PySide6.QtCore import QTimer
        q = getattr(self, "_plan_queue", [])
        if not q:
            return
        if self._plan_idle():
            q.pop(0)()
        if q:
            QTimer.singleShot(1000, self._plan_pump)   # 前の作業が終わるのを、画面を止めずに待つ

    def _plan_draw(self, body: str, fix: bool = False):
        if fix:
            self.mode.setCurrentIndex(2)
        # 描くのは、この段取りの本文だけ。前の頼み（last_text）で埋めない。
        # 前は本文が読めなかった段取りが、前の頼みの題材を黙って描いていた
        # （利用者の指摘、2026-11-27: 指示と全く関係ない絵を描いている）。
        # 本文が無ければ、下の「何を描くかが分かりませんでした」で止める
        self.entry.setText(body)
        if not self.entry.text().strip():
            self.chat.add("ai", "何を描くかが分かりませんでした。描く内容を書いてください")
            self._plan_queue = []
            return
        self.send()
