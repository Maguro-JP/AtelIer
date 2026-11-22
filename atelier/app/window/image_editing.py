"""画像を開いて加工する、仕上げのつなぎ、作風、まとめて描く"""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QFileDialog
from atelier.ai.engine import Painter
from atelier.ai.engine import Studio
from atelier.app.window.image_convert import gray_to_pil
from atelier.app.window.image_convert import qimage_to_pil
from pathlib import Path


class ImageEditingMixin:
    """画像を開いて加工する、仕上げのつなぎ、作風、まとめて描く（Window が継承する）"""

    def _refresh_layers(self):
        self.layer_panel.refresh()

    def import_layer(self):
        path, _ = QFileDialog.getOpenFileName(self, "画像をレイヤーとして読み込む", "", "画像 (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.layer_from_file(path, Path(path).stem)

    def open_image(self):
        if self.tour_first("open", self.open_image):
            return
        from atelier.files import project_file as project
        path, _ = QFileDialog.getOpenFileName(self, "開く", "", "作業ファイルと画像 (" + " ".join(f"*{x}" for x in project.READABLE) + " *.png *.jpg *.jpeg *.webp)")
        if path:
            self.open_path(path)

    # ---- 既存の絵をあとから直す ----
    def open_to_edit(self):
        path, _ = QFileDialog.getOpenFileName(self, "直す絵を開く", "", "画像 (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.edit_image(path)

    def edit_image(self, path: str):
        """手元の絵・ライブラリー・履歴の絵をキャンバスに開き、赤ペンで囲んで直せる形にする。
        キャンバスは置き換える（前の状態は元に戻すで戻せる）。前に描いた絵の .json があれば、頼み・種・模型を戻して続きから直す"""
        from atelier.ai import finishers
        if not Path(path).is_file():
            self.notify("開けませんでした", "error", f"絵が見つかりません: {path}")
            return
        self.work_save()
        if not self.work_open(path):
            self.canvas.replace_with_image(path, Path(path).stem)
            self.work_key = str(path)
        self.project_path = None
        self._fix_from = str(path)
        self.source_path = str(path)   # 「結合して元の画像に上書き保存」で書き戻す先
        self.mode.setCurrentIndex(2)   # 直す
        if "redpen" in self.tool_actions:
            self.tool_actions["redpen"].trigger()
        meta = finishers.sidecar(path)
        self.inspect_prompt = str(meta.get("prompt") or "")   # 絵に埋めた模型の言葉だけを使う。無ければ頼んだ物は見ない
        if meta.get("text"):
            self.entry.setText(meta["text"])
            self.last_text = meta["text"]
        try:
            if "seed" in meta:
                self.ai_panel.seed.setValue(int(meta["seed"]))
        except (TypeError, ValueError):
            pass
        if meta.get("style_name"):
            self.ai_panel.set_style(meta["style_name"])
        if meta.get("model"):
            self.fix_model = meta["model"]   # 描いた模型で続きを直す（取得していなければ今の模型で直す）
        self.edit_meta = meta
        self.notify("直す形で開きました", "ok",
                    "赤ペンで直す所を囲み、指示を書いて「描く」を押してください。囲みの外は変えません"
                    + ("（前の頼みと種を戻しました）" if meta else ""))

    def _fix_studio(self):
        """直しに使う模型を選んでいれば、その模型で直す Studio を作る。おまかせか、使えない模型なら今の Studio"""
        from atelier.ai import finishers
        from atelier.models.catalog import all_images
        key = getattr(self, "fix_model", finishers.AUTO)
        if (not key or key == finishers.AUTO) and getattr(self.studio, "use_favorites", False):
            from atelier.models import favorites as favmodels
            key = favmodels.get("fix") or key   # お気に入りで描いているときは、「直し・加工」のお気に入りで直す
        if not key or key == finishers.AUTO or key == getattr(self.studio.painter, "model", None):
            return self.studio
        every = all_images()
        have = list(self.installed_images(every))
        m = next((m for m in finishers.inpaint_models(every, have) if m.repo == key), None)
        if m is None:
            self.say("直しに選んだ模型が使えないので、今の模型で直します")
            return self.studio
        old = getattr(self, "_fix_cache", None)
        if old is not None and old.painter.model == m.repo:
            return old   # 同じ模型を 2 度読まない
        painter = Painter(m.repo, m.steps, guidance=m.guidance)
        painter.avoid = getattr(self.studio.painter, "avoid", "")
        self._fix_cache = Studio(self.studio.words, painter, Path(self.settings.get("output_dir")))
        return self._fix_cache

    def _fill_fix_menu(self, menu):
        from atelier.ai import finishers
        from atelier.models.catalog import all_images
        menu.clear()
        now = getattr(self, "fix_model", finishers.AUTO)
        group = QActionGroup(menu)
        auto = QAction(finishers.AUTO, menu, checkable=True)
        auto.setToolTip("囲んだ所を、今の絵の模型で直します")
        entries = [(finishers.AUTO, auto)]
        every = all_images()
        for m in finishers.inpaint_models(every, list(self.installed_images(every))):
            act = QAction(m.name, menu, checkable=True)
            act.setToolTip("囲んだ所を、この模型で直します（取得済みで、範囲の直しができる模型だけを出しています）")
            entries.append((m.repo, act))
        for key, act in entries:
            act.setChecked(key == now)
            act.triggered.connect(lambda _=False, k=key: setattr(self, "fix_model", k))
            group.addAction(act)
            menu.addAction(act)

    def finish_with(self, name: str, background: bool = False):
        """仕上げの道具を今の絵に掛け、結果を新しいレイヤーとして重ねる。囲み（赤ペン・選択）があれば囲みの中だけ変える。
        使えないときは止めずに理由を出す。返すのは保存した置き場（出来なければ None）"""
        from atelier.ai import finishers
        base = qimage_to_pil(self.canvas.flatten()).convert("RGB")
        mask = self._region_mask()
        finishers.use_painter(getattr(self.studio, "painter", None))
        finishers.use_source(self.fix_source())   # 加工にも、元の絵を描いたときの言葉を渡す
        if background:   # 模型を使う道具は数十秒かかる。画面の糸で回すと、その間アプリが固まる
            return self.finish_chain([name], finishers.REGISTRY[name].label, base=base, mask=mask)
        try:
            out = finishers.run(name, base, mask)
        except finishers.Unavailable as e:
            self.notify("綺麗にできませんでした", "info", str(e))
            return None
        except Exception as e:  # 道具の中の失敗も、止めずに理由を出す
            from atelier.ai.engine import explain
            self.notify("綺麗にできませんでした", "error", explain(e))
            return None
        if finishers.LAST_QC.get("rejected"):
            self.notify("加工で絵が崩れたので、掛けませんでした", "info", finishers.qc_note())
            return None
        note = finishers.qc_note()   # 元に戻した所（目の色・髪の色・崩れた区画）を知らせる。黙って戻さない
        path = self._place_finished(name, base, out, clip=mask if getattr(self, "_mark_only", 0) else None)
        if note and path is not None:
            self.notify("加工の検品の結果", "info", note + "見比べて、使うか消すかを決めてください")
        return path

    def finish_chain(self, steps, label: str = "", base=None, mask=None):
        """加工を順に裏の糸で掛ける（1 つだけの加工も、まとめて綺麗にするも、自分の組み合わせも同じ道）。
        大きな絵は区画ごとに進みを出し、区画の区切りで「止める」が効く。工程ごとに崩れを検品し、崩れた所は元に戻して知らせる。
        結果は今の絵の一番上の新しいレイヤーに置く。返すのは None（置くのは終わってから）"""
        from atelier.ai import finishers
        from atelier.ai.engine import check_stop
        steps = list(steps or [])
        label = label or (finishers.REGISTRY[steps[0]].label if steps and steps[0] in finishers.REGISTRY else "加工")
        unknown = [n for n in steps if n not in finishers.REGISTRY]
        if not steps or unknown:
            self.notify(f"{label}を掛けられませんでした", "info", "組み合わせの中の加工が見つかりません。組み合わせを作り直してください")
            return None
        if self.busy(label):
            return None
        if base is None:
            base = qimage_to_pil(self.canvas.flatten()).convert("RGB")
            mask = self._region_mask()
        finishers.use_painter(getattr(self.studio, "painter", None))
        finishers.use_source(self.fix_source())
        fetch = []
        for n in steps:
            ok, why = self._finisher_ready(n)
            if not ok:
                if not finishers.fetchable(n):
                    self.notify("綺麗にできませんでした" if len(steps) == 1 else f"{label}を掛けられませんでした", "info", why)
                    return None
                fetch.append(n)
        name = steps[0] if len(steps) == 1 else "chain"
        self.activity.begin(label, "加工")
        path = self._finished_path(name)

        def say(text):   # 区画の区切りごとに呼ばれる。止めるの旗を見てから進みを出す
            check_stop()
            self.task.status.emit(text)

        def work(_step):   # 足りない部品は押したときに取り、取れたら続けて掛ける。書くのも裏の糸
            if fetch:
                finishers.fetch_parts(sorted({m for n in fetch for m in finishers.lacking(n)}),
                                      say=lambda msg, _pct: self.task.status.emit(msg))
                for n in fetch:
                    if not finishers.REGISTRY[n].ready():
                        raise finishers.Unavailable(finishers.REGISTRY[n].why_not())
            out = finishers.run_chain(steps, base, mask, say)
            if all(q.get("rejected") for q in finishers.LAST_CHAIN):
                return None   # どの工程も崩れたので採らない（置かない）
            return self._save_out(out, path)
        # 赤ペンの印の右クリックから掛けたときは、結果を囲みの中だけのレイヤーにする（直した所だけのレイヤー）
        clip = mask if getattr(self, "_mark_only", 0) else None
        self._run_task(work, lambda out: self._chain_done(name, label, base, out, path, clip))
        return None

    def _chain_done(self, name, label, base, out, path, clip=None):
        from atelier.ai import finishers
        note = finishers.chain_note()
        if out is None:
            self._end(f"{label}は掛けませんでした")
            self.notify("加工で絵が崩れたので、掛けませんでした", "info", note + "元の絵のままです")
            return
        self._place_finished(name, base, out, path, clip=clip)
        self._end(f"{label}を掛けました")
        if note:
            self.notify("加工の検品の結果", "info", note + "見比べて、使うか消すかを決めてください")

    def add_chain_shortcut(self, steps=None, name: str | None = None) -> str:
        """加工の組み合わせを、右クリックの「自分の組み合わせ」に登録する。steps が無ければ選ぶ窓を出す。返すのは id（やめたら空）"""
        from atelier.ai import finishers
        from atelier.ai import shortcuts
        if not isinstance(steps, (list, tuple)):   # メニューから呼ぶと checked の真偽が来る
            dlg = shortcuts.chain_picker(self)
            self._chain_picker = dlg
            if not dlg.exec():
                return ""
            steps, name = dlg.picked, dlg.name.text()
        steps = [n for n in steps if n in finishers.REGISTRY]
        if not steps:
            return ""
        sid = self.shortcut_store().add_chain(name or shortcuts.chain_text(steps)[:24], steps)
        self.notify("組み合わせを登録しました", "ok", "絵の上の右クリックの「自分の組み合わせ」から選べます")
        return sid

    @staticmethod
    def _clip_to_region(img, mask):
        """加工の結果 img（PIL）を囲みの中だけのレイヤーにする（囲みの外は透明）。下の元の絵が透けるので、
        囲みの外は 1 画素も変わらない。mask が None か大きさが違えば img のまま（RGBA にして返す）"""
        from atelier.ai.finishers import binary
        from PIL import ImageChops
        out = img.convert("RGBA")
        if mask is None:
            return out
        out.putalpha(ImageChops.multiply(out.getchannel("A"), binary(mask, out.size)))
        return out

    @staticmethod
    def _submenu(m, title):
        """親のメニューが持つ小さなメニュー。Python 側でも親に持たせ、作った関数を抜けても消えないようにする"""
        from PySide6.QtWidgets import QMenu
        sm = QMenu(title, m)
        m.addMenu(sm)
        m.__dict__.setdefault("_kept", []).append(sm)
        return sm

    def fill_style_menu(self, menu, mark: int = 0):
        """画風の一覧（atelier/ai/restyle.py の STYLES の並び）を menu に足す。mark が 1 からの印の番号なら、その囲みの中だけに掛ける"""
        from atelier.ai import finishers
        from atelier.ai.restyle import STYLES
        from PySide6.QtGui import QIcon
        menu.setToolTipsVisible(True)
        # 予想図: 見本の 1 枚を本物の絵の模型でその画風に変えた小さな絵（chatdraw/styleprev/）。名前だけでは仕上がりが分からないので横に出す
        # QMenu は絵の大きさを小さな絵の寸法（16 画素）で描き、スタイルシートの icon-size は効かなかった。その寸法だけを大きくする
        # メニューに独自のスタイル（QProxyStyle）を付けると、右クリックでアプリごと落ちた（0.5.30）。スタイルは付けず、
        # 小さな絵はメニューの絵の欄に、大きな絵はカーソルを合わせたときのツールチップに出す
        prev = Path(__file__).resolve().parents[1] / "styleprev"
        for kind, label, tip, *_ in STYLES:
            name = f"style_{kind}"
            ok, why = self._finisher_ready(name) if name in finishers.REGISTRY else (False, "")
            # 囲み全体（または絵全体）に掛けるときはショートカットと同じ道を通す（使った回数と ★ の並びに入る）
            act = menu.addAction(label, (lambda name=name: self.style_mark(name, mark)) if mark else (lambda name=name: self.run_shortcut("fin:" + name)))
            if not mark:
                act.setObjectName("fin:" + name)
            if (prev / f"{kind}.jpg").is_file():
                act.setIcon(QIcon(str(prev / f"{kind}.jpg")))
            img = prev / f"{kind}.jpg"
            big = f'<br><img src="{img.as_posix()}" width="160">' if img.is_file() else ""
            act.setToolTip(tip + "（絵は見本の絵での例）" + big + ("。囲みの中だけを描き替えます" if mark else "") + ("" if ok or finishers.fetchable(name) else f"（{why}）"))
            act.setEnabled((ok or finishers.fetchable(name)) and not self.thread)
        return menu

    def style_mark(self, name: str, mark: int = 0):
        """画風を掛ける。mark があればその印の囲みだけ（ほかの印と選択範囲は使わない）、無ければ今の囲み（無ければ絵全体）"""
        from atelier.ai import finishers
        if not mark:
            return self.finish_with(name, background=True)
        masks = self.canvas.redpen.masks()
        if not 0 < mark <= len(masks):
            self.notify("その印はありません", "info", "消したか、番号が変わりました")
            return None
        base = qimage_to_pil(self.canvas.flatten()).convert("RGB")
        return self.finish_chain([name], finishers.REGISTRY[name].label, base=base, mask=gray_to_pil(masks[mark - 1]).convert("L"))

    def _region_mask(self):
        """赤ペンの囲みと選択範囲を合わせた囲み（PIL の L）。どちらも無ければ None"""
        from PIL import ImageChops
        masks = [gray_to_pil(m) for m in self.canvas.redpen.masks()]
        only = getattr(self, "_mark_only", 0)
        if only:   # 赤ペンの印の右クリックから掛けるときは、その印の囲みの中だけ（ほかの印と選択は見ない）
            return masks[only - 1].convert("L") if 1 <= only <= len(masks) else None
        sel = self.canvas.selection_mask()
        if sel is not None:
            masks.append(gray_to_pil(sel))
        mask = None
        for m in masks:
            mask = m.convert("L") if mask is None else ImageChops.lighter(mask, m.convert("L"))
        return mask

    def _lines_dialog(self, title: str, hint: str, text: str = "") -> list[dict] | None:
        """「名前: 描く言葉」を 1 行 1 つ書いてもらう窓。返すのは [{"id", "name", "tags"}]（やめたら None）"""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout
        d = QDialog(self)
        d.setWindowTitle(title)
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(hint))
        box = QPlainTextEdit(text)
        box.setMinimumHeight(120)
        lay.addWidget(box)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if d.exec() != QDialog.Accepted:
            return None
        out = []
        for i, line in enumerate(box.toPlainText().splitlines(), 1):
            name, _sep, tags = line.partition(":")
            if not _sep:
                name, _sep, tags = line.partition("：")
            name, tags = name.strip(), tags.strip()
            if name and tags:
                out.append({"id": f"{i}", "name": name, "tags": tags})
        return out

    # ---- 一括生成（atelier/ai/batch.py） ----

    def batch_draw(self, text: str | None = None, count: int = 1, seed: int = 0, as_csv=None, jobs=None, start: int = 0) -> bool:
        """頼みの一覧から順に描き、全部をライブラリーに入れる。1 枚が失敗しても残りを描く。止めるは「止める」"""
        from atelier.ai import batch
        from atelier.ai import engine
        if self.busy("一括生成"):
            return False
        if jobs is not None:   # 一時停止した一括生成を、残した一覧と位置から続ける
            bad = []
        else:
            if not isinstance(text, str):
                got = self._batch_dialog()
                if got is None:
                    return False
                text, count, seed, as_csv = got
            jobs, bad = batch.parse(text, count, seed, as_csv)
        if not jobs:
            self.notify("一括生成できませんでした", "info", "頼みが 1 行もありません。1 行に 1 つ書くか、CSV を読んでください")
            return False
        studio = self.studio
        n = batch.total(jobs)
        self.activity.begin(f"一括生成（{n} 枚）", "一括生成")

        def draw(text, seed, negative):
            p = studio.painter
            old = getattr(p, "avoid", None)
            if negative and old is not None:
                p.avoid = ", ".join(x for x in (old, negative) if x)
            try:
                return studio.draw(text, seed, on_status=self.task.status.emit)[1]
            finally:
                if negative and old is not None:
                    p.avoid = old

        def work(_step):
            import json
            from atelier.files import pause_keep as pausekeep
            res = batch.run(jobs, draw, say=self.task.status.emit, stopped=engine.STOP.is_set, start=start,
                            pause_key=pausekeep.key("batch", json.dumps(jobs, ensure_ascii=False)))
            res["failed"] = [(l, t, w) for l, t, w in bad] + res["failed"]
            return res
        self._run_task(work, self._batch_done)
        return True

    def _batch_dialog(self):
        """一括生成の窓: 頼みの一覧（1 行 1 つ）、ファイルを読む、枚数、種"""
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QPlainTextEdit, QPushButton,
                                       QSpinBox)
        d = QDialog(self)
        d.setWindowTitle("一括生成")
        form = QFormLayout(d)
        box = QPlainTextEdit()
        box.setPlaceholderText("1 行に 1 つ、描く物を書きます。\nCSV なら 1 行目を「頼み,枚数,種」にします")
        box.setMinimumHeight(140)
        form.addRow("頼みの一覧", box)
        state = {"csv": None}

        def load():
            path, _ = QFileDialog.getOpenFileName(d, "頼みの一覧を読む", str(Path.home()), "頼みの一覧 (*.txt *.csv)")
            if not path:
                return
            # Excel が書く CSV は Shift_JIS（cp932）なので、UTF-8 で読めなければそちらで読む。どちらでも読めなければ知らせる
            raw = None
            try:
                data = Path(path).read_bytes()
                for enc in ("utf-8-sig", "cp932"):
                    try:
                        raw = data.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
            except OSError as e:
                self.notify("読めませんでした", "error", str(e))
                return
            if raw is None:
                self.notify("読めませんでした", "error", "文字のファイル（UTF-8 か Shift_JIS の .txt・.csv）を選んでください")
                return
            box.setPlainText(raw)
            state["csv"] = path.lower().endswith(".csv") or None
        read = QPushButton("ファイルを読む…")
        read.setToolTip("1 行 1 つの .txt か、CSV（頼み,枚数,種,禁止ワード）を読みます")
        read.clicked.connect(load)
        form.addRow("", read)
        count = QSpinBox()
        count.setRange(1, 100)
        count.setToolTip("1 行ごとに描く枚数（CSV に枚数があれば、そちらを使います）")
        form.addRow("1 行の枚数", count)
        seed = QSpinBox()
        seed.setRange(0, 999999)
        seed.setToolTip("種の始まり。行ごと・枚ごとに 1 ずつ足します（同じ種なら同じ絵になります）")
        form.addRow("種", seed)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("描く")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return None
        return box.toPlainText(), count.value(), seed.value(), state["csv"]

    def _batch_done(self, res: dict):
        from atelier.ai import batch
        for p in res["done"]:
            self.library_panel.add(self.library.add_work(p))
        self.batch_result = res
        self.activity.end("一括生成を終えました", None, record=False)
        self.notify("一括生成を終えました", "info" if res["failed"] or res["stopped"] else "ok", batch.summary(res))
        self.say(batch.summary(res))
        self._end("一括生成を終えました")
        if res.get("paused") is not None:
            self.offer_paused()   # 残した所から続ける「再開」を出す
