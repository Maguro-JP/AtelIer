"""描いた結果の受け取り、工程の問い、加工（ちび・線画・ドット絵・拡大）"""
from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from atelier.app.window.image_convert import qimage_from_pil
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.image_convert import qimage_to_pil_rgba
from atelier.app.window.jobs import Job
from atelier.app.window.jobs import Task
from pathlib import Path
import time


class AiResultsMixin:
    """描いた結果の受け取り、工程の問い、加工（ちび・線画・ドット絵・拡大）（Window が継承する）"""

    def on_one(self, prompt: str, path: str):
        """1 枚できるたびに呼ばれる。初めの 1 枚はキャンバスに置き、ほかは履歴に並べて選べるようにする。
        絵を置くのを先にする。前は検品の知らせを先に出していて、そこで落ちると絵が置かれず、途中の絵か何も無いままだった"""
        if self._stale():
            return
        self.canvas.show_overlay(None)
        if self.job_kind == "fix":
            self._on_fixed(path)
            return
        self.images.append(path)
        first = not self.batch
        self.batch.append(path)
        if first and self.job_kind != "chibi":
            self._record_result(path)
        bad = []
        try:
            if self.job_kind == "chibi":
                self.put_result(path, "ちびキャラ")
            elif first and self.pin_action.isChecked() and self.mode.currentIndex() == 0:
                self.say("表示する絵を固定しているので、新しい絵は履歴に入れました（押すと出ます）")
            elif first:
                self.activity.status("キャンバスに置いています")
                self.place(path)
                self._put_phases()
        except (OSError, ValueError) as e:
            self.say(f"絵をキャンバスに置けませんでした（{e}）。履歴から押すと出せます")
        self.batch_items.append(self.activity.add(path, prompt))
        if first and not self.pin_action.isChecked():
            self.history.setCurrentRow(0)   # 選んでいた古い絵ではなく、出した新しい絵を選んだ形にする
        for f in bad:
            self.say(f"崩れ: {f}")
        if prompt:
            # 絵の模型に渡した言葉は会話に毎回出さず、書く欄にカーソルを合わせたときだけ出す（頼みとずれた絵が出たときに見られる）
            self.last_model_prompt = prompt
            self.inspect_prompt = prompt   # 「検品する」で頼んだ物を見る言葉。別の絵を開いたら消す
            self._entry_tip()
        if getattr(self.studio, "last_lost", None) and self.job_kind == "draw":
            self.say("模型に伝わらなかった言葉: " + "、".join(self.studio.last_lost))
        check = getattr(self.studio, "last_check", None)
        if check is not None and self.job_kind == "draw":
            from atelier.qc.hand_check import summary
            try:
                self.say(summary(check))   # 検品の結果は、絵ごとに先に出す（崩れを見落としたまま使わないように）
            except (KeyError, TypeError) as e:
                self.say(f"検品の結果を読めませんでした（{e}）。目で確かめてください")
        self._record()
        item = self.library.add_work(path)
        if item:   # 赤ペンの直しだけの絵は作品にしない（空で返る）
            self.library_panel.add(item)
        # 頼み・種・設定は描いたときに PNG に埋めてある。埋まっていない絵（前の版で描き、隣に .json だけがある物）だけ、
        # 裏の糸で埋める（PNG を書き直すので 1 枚 0.1 秒ほどかかる。別名に書いてから替えるので、読む側は壊れた絵を見ない）
        from atelier.ai import finishers
        self.run_io(lambda: finishers.embedded(path) or finishers.embed(path, finishers.sidecar(path)), lambda _v: None, "ライブラリーへ保存")

    def _pick_way(self, _i=None):
        """描くボタンの横の描き方を設定に残し、今の描き手にすぐ効かせる（模型は読み直さない）"""
        from atelier.app.settings import studio_way
        self.settings.set("draw_way", self.way_pick.currentData())
        if getattr(self, "studio", None) is not None:
            self.studio.way = studio_way(self.settings.get("draw_way"), self.settings.get("ai_way"))

    def ask_phase(self, i: int, name: str, image, row: dict):
        """工程が終わったところで止まり、その工程の絵をキャンバスに見せて、進めるか描き直すかを選んでもらう"""
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        if image is not None:
            self.canvas.show_overlay(qimage_from_pil(image))
        left = row["after"] if row.get("fixed") else row.get("found", [])
        text = (f"工程 {i + 1}「{name}」が終わりました。\n決めた物: {row.get('decides', '')}\n"
                + ("崩れは見つかりませんでした" if not left else "残った崩れ: " + "、".join(left[:4])))
        box = QMessageBox(QMessageBox.Question, "工程ごとに確かめる", text, parent=self)
        box.setObjectName("phase_confirm")
        if image is not None:
            box.setIconPixmap(QPixmap.fromImage(qimage_from_pil(image)).scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        go = box.addButton("進める", QMessageBox.AcceptRole)
        go.setToolTip("この工程の絵を土台にして、次の工程へ進む")
        redo = box.addButton("この工程を描き直す", QMessageBox.ActionRole)
        redo.setToolTip("同じ言葉で、種を変えてこの工程だけを描き直す")
        words = box.addButton("言葉を足して描き直す", QMessageBox.ActionRole)
        words.setToolTip("足したい言葉を書いて、この工程から描き直す（言葉は訳してから模型に渡す）")
        box.setDefaultButton(go)
        box.exec()
        hit = box.clickedButton()
        if hit is redo:
            return "redo"
        if hit is words:
            add, ok = QInputDialog.getText(self, "言葉を足して描き直す", "足す言葉:")
            return ("words", add) if ok and add.strip() else "go"
        return "go"

    def _put_phases(self):
        """工程に分けて描いた回は、工程ごとの絵を描いた絵の下に隠したレイヤーで置き、工程ごとの検品を会話に出す（atelier/ai/phases.py）"""
        rows = getattr(self.studio, "last_phases", None) if self.job_kind == "draw" else None
        if not rows:
            return
        self.canvas.add_phase_layers([(f"工程 {i}: {r['phase']}", r["image"]) for i, r in enumerate(rows, 1) if r.get("image")])
        for r in rows:
            left = r["after"] if r["fixed"] else r["found"]
            self.say(f"「{r['phase']}」{r['seconds']} 秒: " + ("崩れは見つかりませんでした" if not left else "残った崩れ " + "、".join(left[:3]))
                     + ("（1 回直しました）" if r["fixed"] else ""))

    def _put_stopped_phases(self):
        """精度優先で描いている途中に「止める」を押されたら、止めた所までの絵を一番上のレイヤーに、工程ごとの絵を隠したレイヤーに置く。
        裏の糸は止められて返りが無いので、phases.draw が工程ごとに書く progress.json から読む。「描けました」「完成」とは出さない。
        返りは (見出し, 説明)。精度優先の回でなければ None"""
        import json
        if getattr(self, "job_kind", None) != "draw":
            return None
        studio = getattr(self, "job_studio", None) or self.studio
        keep = getattr(studio, "last_phase_keep", None)
        f = Path(keep) / "progress.json" if keep else None
        if f is None or not f.exists():
            return None
        try:
            got = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        studio.last_phase_keep = None   # 同じ回を 2 度置かない
        total, need, left = got.get("total", 0), got.get("need", 0), list(got.get("left") or [])
        head = f"止めました（工程 {total} で止めました）"
        try:
            if got.get("image") and self.canvas.layers:
                self.put_result(got["image"], f"止めた所までの絵（工程 {total}「{got.get('phase', '')}」）")
                self.canvas.add_phase_layers([(f"工程 {k}: {nm}", im) for k, (nm, im) in
                                              enumerate(zip(got.get("names", []), got.get("images", [])), 1)])
                self._refresh_layers()
        except (OSError, ValueError) as e:
            self.say(f"止めた所までの絵をレイヤーに置けませんでした（{e}）")
        self.say(head + f"。要る工程は今 {need}、累計 {total} 工程を描きました")
        self.say("残った崩れ: " + ("、".join(left[:5]) if left else "この工程はまだ検品していません"))
        return head, (f"残った崩れ {len(left)} 件。" if left else "") + "止めた所までの絵を一番上のレイヤーに置きました"

    def _on_fixed(self, path: str):
        """赤ペン・選択範囲の直しの結果は、一番上の新しいレイヤーにだけ置いて選ぶ。描いた絵の履歴・ライブラリーには載せない
        （レイヤーを消せば何も残らない）。崩れが見つかっても隠さずに見せ、崩れは会話に書いて判断を利用者に渡す"""
        self.batch.append(path)
        bad = getattr(getattr(self, "job_studio", None) or self.studio, "last_flaws", [])
        n = getattr(self, "_fix_count", 0) + 1
        self._fix_count = n
        try:
            before = len(self.canvas.layers)
            if self._put_fix(path, f"赤ペンの直し {n}" + ("（崩れあり）" if bad else "")) and len(self.canvas.layers) > before:
                self.canvas.layers[self.canvas.current].redpen = True   # 消したら何も残さない直しのレイヤーの印
        except (OSError, ValueError) as e:
            self.say(f"直しをレイヤーに置けませんでした（{e}）")
        finally:
            if self.settings.get("result_place") != "別ファイル":   # 別ファイルで開くときは、開く側がこの絵を読む
                Path(path).unlink(missing_ok=True)   # 置いたあとは保存先にも残さない（絵はレイヤーの中にある）
        # 直しが済んだら印は消す（残ると、いつまでも絵の上に赤い線が残った）。消した印は元に戻すで戻せる
        only = getattr(self, "_fix_only", 0)
        if only:   # 印 1 つだけを直したときは、その印だけを消してほかの印を戻す
            self.canvas.redpen.remove(only)
            self._end_fix_only(removed=only)
        else:
            for _ in range(len(self.canvas.redpen.marks)):
                self.canvas.redpen.undo()
        self._refresh_layers()
        for f in bad:
            self.say(f"崩れ: {f}")
        whole = getattr(getattr(self, "job_studio", None) or self.studio, "last_whole", {}) or {}
        if whole.get("left"):   # 全体の確かめは 1 回だけ測って知らせる（直し直しには繋げない）
            self.say(whole["note"])

    def show_final(self):
        """描き終えたら、1 枚目の絵をキャンバスに出して履歴で選ぶ。途中の絵（重ねた下描き）は必ず消す。
        途中の絵の知らせが絵の知らせより後に届くと、仕上がった絵の上に途中の絵が残り、出来た絵が見えなかった"""
        self.canvas.show_overlay(None)
        if not self.batch or self.job_kind != "draw" or self.pin_action.isChecked():
            return
        path = self.batch[0]
        if getattr(self, "_placed", None) != path:
            self.place(path)
        for row in range(self.history.count()):
            if self.history.item(row).data(Qt.UserRole) == path:
                self.history.setCurrentRow(row)
                break

    def finish(self):
        if self._stale():
            return
        if getattr(self, "_fix_hid", None):   # 直しが置かれずに終わったときも、隠した印を戻す
            self._end_fix_only()
        self._show_model()   # おまかせで選んだ模型を出す
        self.show_final()
        if self.job_kind == "draw" and self.mode.currentIndex() == 1:
            # ラフから描き終えたら「新規」に戻す。キャンバスはもう AI の絵に置き換わっているので、「ラフから」のままだと
            # 次の頼みが前に描いた絵を下描きにして描かれ、新しい頼みが前の絵に引っ張られた。もう一度ラフから描くときは選び直す
            self.mode.setCurrentIndex(0)
            self.say("次の頼みは「新規」で描きます（今の絵を下描きにするときは「ラフから」を選び直します）")
        n = len(self.batch)
        fixed = self.job_kind in ("fix", "chibi")
        bad = getattr(getattr(self, "job_studio", None) or self.studio, "last_flaws", []) if self.job_kind == "fix" else []
        result = ("直しを重ねました（崩れあり）" if bad else "直しを重ねました") if fixed else \
            f"{n} 枚描きました" if n > 1 else "描けました"
        if bad:   # 崩れがあったときだけ絵の説明に足す（「描けました」は絵を見れば分かる）
            for it in self.batch_items:
                it.setToolTip(f"{result}\n{it.toolTip()}")
        studio = getattr(self, "job_studio", None) or self.studio
        undone = self.job_kind == "draw" and getattr(studio, "last_phases", None) and getattr(studio, "last_passed", None) is False
        if undone:   # 精度優先で検品を通らなかった回は「描けました」と出さない（出来たかは利用者が決める）
            result = "未完成です（崩れが残っています）"
            bad = list(getattr(studio, "last_left", []) or ["検品を通っていません"])
        job = getattr(self, "job", None)
        asked = len(getattr(job, "seeds", ()) or ())
        if not fixed and getattr(job, "reasons", None) and asked > 1:
            # 1 枚が描けなくても残りは描いた。何枚描けたか、描けなかった理由を先に知らせる
            result = f"{asked} 枚のうち {job.drawn} 枚描きました"
            self.say(result + "。描けなかった枚: " + "、".join(job.reasons[:3]))
            self._debug_failure(result, "\n".join(job.reasons), getattr(job, "trace", ""))
        self.activity.end(result, None, record=False)
        if undone:
            self.say("未完成です。残った崩れ: " + "、".join(bad[:5]))
        else:
            self.say(result if fixed else f"{n} 枚描きました。履歴から選べます" if n > 1 else "描きました")
        self.notify(result if fixed or undone else "描けました", "error" if bad else "ok",
                    (f"崩れ {len(bad)} 件。一番上のレイヤーに置きました。見て決めてください" if bad else
                     "新しいレイヤーに重ねました。見て決めてください") if fixed else
                    (f"1 枚目をキャンバスに出しました。ほかの {n - 1} 枚は履歴を押すと出ます" if n > 1
                     else f"崩れ {len(bad)} 件。キャンバスに出しました。見て決めてください" if undone
                     else "キャンバスに出しました（元に戻すで前の絵に戻せます）"),
                    on_click=lambda: (self.panels["history"][0].show(), self.activity.tabs.setCurrentIndex(0)))
        self._end("未完成" if undone else "できました")

    def make_chibi(self):
        """今の絵を、ちびキャラ（頭の大きなデフォルメ）に描き直して、新しいレイヤーに重ねる"""
        from PIL import Image
        from atelier.ai import post_effects as postfx
        if self.busy("ちびキャラ"):
            return
        st = self.check_ai()
        if not st["image"]:
            self.notify("AI が使えません", "error", st["reason"])
            return
        self.feature_tour("chibi")
        base = qimage_to_pil(self.canvas.flatten())
        full = Image.new("L", base.size, 255)
        self._start_job("ちびキャラにする", "chibi", Job(self.studio, postfx.CHIBI_NOTE, self.ai_panel.seeds()[:1], base=base,
                                                       strength=0.7, style=postfx.CHIBI_TAGS,
                                                       regions=[(full, postfx.CHIBI_NOTE)], check=False))

    def make_lineart(self):
        """今の絵から線だけを取り出した線画を、新しいレイヤーに重ねる（元の絵は残す）"""
        from atelier.ai import post_effects as postfx
        self.feature_tour("lineart")
        src = qimage_to_pil(self.canvas.flatten())
        mask = self._region_mask()   # 囲んだときは囲みの中だけを線画にする（囲みの外は 1 画素も変えない）
        out = Path(self.settings.get("output_dir")) / time.strftime("%Y-%m-%d")
        path = out / f"{time.strftime('%Y%m%d-%H%M%S')}-lineart.png"

        def work():   # 線を取り出して書くのは裏の糸（832×1216 で 0.4 秒ほど固まった）
            out.mkdir(parents=True, exist_ok=True)
            line = postfx.lineart(src)
            (line if mask is None else self._clip_to_region(line, mask)).save(path)

        def done(err):
            if isinstance(err, BaseException):
                self.notify("線画にできませんでした", "error", str(err))
                return
            self.put_result(str(path), "線画")
            self.activity.add(str(path), "線画")
            self.notify("線画にしました", "ok", "新しいレイヤーに重ねました。元の絵は下に残っています")
        self.statusBar().showMessage("線画にしています…")
        self.in_background(work, done)

    def make_pixel(self, long: int = 128, colors: int = 24):
        """今の絵をドット絵にして、新しいレイヤーに重ねる。小さいドット絵（1 ドット 1 画素）も出力の置き場に残す"""
        from atelier.ai import post_effects as postfx
        self.feature_tour("pixel")
        img = qimage_to_pil(self.canvas.flatten())
        mask = self._region_mask()   # 囲んだときは囲みの中だけをドット絵にする
        out = Path(self.settings.get("output_dir")) / time.strftime("%Y-%m-%d")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        small = out / f"{stamp}-pixel.png"
        big = out / f"{stamp}-pixel-view.png"

        def work():   # 減色と書き出しは裏の糸（832×1216 で 1.7 秒固まった）
            dots = postfx.pixel_art(img, long=long, colors=colors)
            out.mkdir(parents=True, exist_ok=True)
            dots.save(small)
            view = postfx.enlarge(dots, img.size)
            (view if mask is None else self._clip_to_region(view, mask)).save(big)
            return dots.size

        def done(got):
            if isinstance(got, BaseException):
                self.notify("ドット絵にできませんでした", "error", str(got))
                return
            dw, dh = got
            self.put_result(str(big), "ドット絵")
            self.activity.add(str(small), f"ドット絵 {dw}×{dh}・{colors} 色")
            self.notify("ドット絵にしました", "ok", f"{dw}×{dh} ドット・{colors} 色。元の大きさの絵は履歴にあります")
        self.statusBar().showMessage("ドット絵にしています…")
        self.in_background(work, done)

    def _start_job(self, label: str, kind: str, job):
        self.say(label, "あなた")
        self.button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.activity.begin(label, kind)
        self.batch, self.batch_items, self.job_kind = [], [], kind
        self.before_heavy(getattr(getattr(job, "studio", None), "painter", None))
        self.thread = QThread()
        self.job = self._worker = job
        job.moveToThread(self.thread)
        self.thread.started.connect(job.run)
        job.status.connect(self.on_status)
        job.preview.connect(self.show_preview)
        self._record_job(job)
        job.one.connect(self.on_one)
        job.done.connect(self.finish)
        job.failed.connect(self.fail)
        self.gc_guard()
        self.thread.start()

    def upscale_canvas(self):
        """今の絵を、レイヤーを分けたまま 2 倍の大きさにする（元に戻すの履歴は消えるので、先に保存を勧める）"""
        from atelier.ai import upscale
        if self.busy("2 倍に拡大"):
            return
        from atelier.ui import confirm
        cw, ch = self.canvas.size_px()
        if cw * ch * 4 > confirm.BIG_UPSCALE_PX and confirm.ask(
                self, "upscale_big", "大きな絵の拡大", f"拡大すると {cw * 2}×{ch * 2} になります。時間がかかり、メモリも多く使います。",
                [("go", "拡大する")]) != "go":
            return
        if self.canvas.undo_stack:
            picked = confirm.ask(self, "upscale", "絵を 2 倍に拡大",
                                 "レイヤーはそのままで 2 倍にします。拡大すると「元に戻す」の履歴は消えるので、先に保存しておくと戻れます。",
                                 [("save", "保存してから拡大"), ("go", "拡大")])
            if picked == "save":
                if not self.save_project(wait=True):
                    return
            elif picked != "go":
                return
        layers = [(l.name, l.visible, l.opacity, qimage_to_pil_rgba(l.image)) for l in self.canvas.layers]
        current = self.canvas.current
        self.feature_tour("upscale")
        self.activity.begin("絵を 2 倍に拡大", "拡大")
        self.activity.status("描いています" + ("" if upscale.ready() else "（初めに拡大の部品 2.4MB を取ります）"))

        def work(on_step):
            from PIL import Image
            out = []
            for i, (name, visible, opacity, img) in enumerate(layers, 1):
                size = (img.width * 2, img.height * 2)
                if img.getchannel("A").getbbox() is None:   # 何も描いていないレイヤーは、模型に通さず広げるだけ
                    big = Image.new("RGBA", size, (0, 0, 0, 0))
                else:
                    big = upscale.upscale(img, 2, on_step=lambda a, n, i=i: on_step((i - 1) * 100 + a * 100 // n, len(layers) * 100))
                out.append((name, visible, opacity, big))
            return out, current
        self._run_task(work, self._upscaled)

    def _upscaled(self, result):
        from atelier.paint.canvas import Layer
        made, current = result
        from PySide6.QtGui import QImage
        layers = [Layer(name, qimage_from_pil(big).convertToFormat(QImage.Format_ARGB32_Premultiplied), visible, opacity)
                  for name, visible, opacity, big in made]
        self.canvas._reset(layers, current)
        self.dirty = True
        self.activity.end("拡大しました", None, record=False)
        w, h = self.canvas.size_px()
        self.notify("拡大しました", "ok", f"{w}×{h}・レイヤー {len(layers)} 枚のまま")
        self._end("拡大しました")

    def busy(self, what: str) -> bool:
        """裏で描いている間なら、押した物を始めずに理由を出して True。
        描いている糸を新しい糸で上書きすると、動いている QThread が消されてアプリごと落ちた（綺麗にする・広げる・三面図）"""
        if self.thread is None:
            return False
        self.notify(f"{what}は、今の絵を描き終えてから押してください", "info", "描いている間は、ほかの AI の作業を始めません。止めるなら「止める」を押します")
        return True

    def before_heavy(self, keep=None):
        """AI の重い作業を始める前に、落ちても失わないよう作業を自動保存し、使わない絵の模型をメモリから降ろす。
        描いている途中にアプリごと落ちる報告があった。落ちる前に保存しておけば、次の起動で戻すかを聞ける（offer_restore）。
        今の模型と直しの模型（_fix_cache）が両方メモリに残ると、2 つの模型の分だけメモリを使い、足りなくなった"""
        try:
            self.autosave()
        except Exception:   # noqa: BLE001  保存できなくても描くのは止めない
            pass
        for st in (getattr(self, "studio", None), getattr(self, "_fix_cache", None)):
            p = getattr(st, "painter", None)
            if p is None or p is keep or getattr(p, "model", None) == getattr(keep, "model", object()):
                continue
            loaded = getattr(p, "loaded", None)
            if callable(loaded) and loaded():
                p.unload()

    def _run_task(self, fn, then):
        if self.busy("この作業"):   # 呼び手が見落としても、動いている糸を上書きしない
            return False
        try:
            self.autosave()   # 落ちても失わないように（before_heavy と同じ理由）
        except Exception:   # noqa: BLE001
            pass
        self.thread = QThread()
        self.task = self._worker = Task(fn)
        self.stop_button.setEnabled(True)
        self.task.moveToThread(self.thread)
        self.thread.started.connect(self.task.run)
        self.task.status.connect(self.on_status)
        # lambda をそのままつなぐと、終わりの処理が裏の糸で走って画面を触る。Window の関数を通して画面の糸に戻す
        self._task_then = then
        self.task.done.connect(self._task_done)
        self.task.failed.connect(self.fail)
        self.button.setEnabled(False)
        self.gc_guard()
        self.thread.start()

    def _task_done(self, result):
        if self._stale():
            return
        then, self._task_then = getattr(self, "_task_then", None), None
        if then is not None:
            then(result)
