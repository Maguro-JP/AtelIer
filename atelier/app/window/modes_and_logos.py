"""モード、参考の組、ロゴとスタンプ、仕上げのメニュー"""
from __future__ import annotations

from PySide6.QtGui import QAction
from atelier.app.window.image_convert import qimage_to_pil
from pathlib import Path
import time


class ModesAndLogosMixin:
    """モード、参考の組、ロゴとスタンプ、仕上げのメニュー（Window が継承する）"""

    # ---- モード（atelier/app/modes.py） ----

    def set_mode(self, key: str, tour: bool = True):
        """モードを替える。メニュー・欄・プリセットだけを出し分け、キャンバスとレイヤーはそのまま"""
        from atelier.app import modes
        modes.apply(self, key)
        modes.remember(self.layout_store, self.app_mode)
        if tour:
            modes.show_tour(self, self.app_mode)

    def choose_mode(self) -> str:
        """「表示」の「モード」の「モードを選ぶ…」。起動のときと同じ窓を開き、閉じたら今のモードのまま"""
        from atelier.app import modes
        dlg = modes.ModeDialog(self, getattr(self, "app_mode", ""))
        picked = dlg.exec()
        if picked:
            self.set_mode(picked)
        return picked

    def start_mode(self, ask=None) -> str:
        """起動したときのモード。覚えたモードがあり「次から聞かない」なら窓を出さない"""
        from atelier.app import modes
        key, dont_ask = modes.stored(self.layout_store)
        if not dont_ask:   # 「起動したときにモードを聞く」を利用者が入れたときだけ聞く
            dlg = modes.ModeDialog(self, key)
            picked = ask(dlg) if ask else dlg.exec()
            # 閉じたときは「今は選ばない」。前のモード（無ければ既定）で開き、聞くかどうかの設定は変えない
            if picked:
                modes.remember(self.layout_store, picked, dlg.dont_ask.isChecked())
                self.mode_ask_action.setChecked(not dlg.dont_ask.isChecked())
            key = picked or key or modes.DEFAULT
        self.set_mode(key or modes.DEFAULT)
        return key

    def add_mode(self, key: str):
        """モードを「表示」の「モード」に足す。並びは modes.MODES の順（拡張があとから足したモードも、決めた位置に入る）"""
        from atelier.app import modes
        if key in self.mode_actions:
            return self.mode_actions[key]
        m = modes.MODES[key]
        act = QAction(m["name"], self, triggered=lambda _=False, k=key: self.set_mode(k))
        act.setCheckable(True)
        act.setToolTip(m["tip"])
        later = list(modes.MODES)[list(modes.MODES).index(key) + 1:]
        before = next((self.mode_actions[k] for k in later if k in self.mode_actions), self.mode_menu_end)
        self.mode_menu.insertAction(before, act)
        self.mode_actions[key] = act
        return act

    def _ready_painter(self):
        """読み込める絵のモデル。まだ無ければ知らせて None を返す"""
        painter = getattr(self.studio, "painter", None)
        if painter is None or not getattr(painter, "ready", lambda: False)():
            self.notify("絵の模型がまだありません", "info", "AI のメニューで模型を取ってください")
            return None
        return painter

    def open_refsets(self):
        from atelier.ai import references as refs
        kind, target = ("character", getattr(self, "chara_id", "")) if getattr(self, "chara_id", "") else \
            ("model", str(self.settings.get("image_model") or ""))

        def use(path, d):
            self.reference.load(path)
            if hasattr(self.ai_panel, "use_ref"):
                self.ai_panel.use_ref.setChecked(True)
        self.refset_dialog = refs.RefSetDialog(refs.RefSets(), self, on_use=use, target=target, kind=kind)
        self.refset_dialog.exec()

    # ---- ロゴ・スタンプ（atelier/ai/logo_maker.py）。項目は logo.menu_items が返し、メニューバーと右クリックで同じ物を使う ----

    def _fill_logo_menu(self, m=None):
        from atelier.ai import logo_maker as logo
        m = m if m is not None else self.logo_menu
        m.clear()
        m.setToolTipsVisible(True)
        busy = getattr(self, "thread", None) is not None
        for label, fn, tip in logo.menu_items(self):
            act = m.addAction(label, fn)
            act.setToolTip(tip)
            act.setEnabled(not busy)
        return m

    def _logo_folder(self, kind: str) -> Path:
        return Path(self.settings.get("output_dir")) / time.strftime("%Y-%m-%d") / kind / time.strftime("%Y%m%d-%H%M%S")

    def logo_make(self, name=None, mood: str = "", colors: str = ""):
        """頼み（名前、雰囲気、色）からロゴのマークを AI に描かせ、整えた版を書き出す"""
        from atelier.ai import logo_maker as logo
        if not isinstance(name, str):
            from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit
            d = QDialog(self)
            d.setWindowTitle("ロゴ・マークを作る")
            form = QFormLayout(d)
            fields = []
            for label, tip in (("名前", "ロゴに重ねる文字。文字は AI に描かせず、フォントで書きます"),
                               ("雰囲気", "例: かわいい、和風、猫"), ("色", "例: 青と白")):
                e = QLineEdit()
                e.setToolTip(tip)
                form.addRow(label, e)
                fields.append(e)
            box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            box.accepted.connect(d.accept)
            box.rejected.connect(d.reject)
            form.addRow(box)
            if d.exec() != QDialog.Accepted:
                return
            name, mood, colors = (e.text().strip() for e in fields)
        painter = self._ready_painter()
        if painter is None:
            return
        words = getattr(self.studio, "words", None)
        folder, seed = self._logo_folder("logo"), int(time.time()) % 100000
        self.activity.begin("ロゴ・マークを描く", "ロゴ・スタンプ")

        def work(_step):
            mark = logo.draw_logo(painter, name, mood, colors, seed, words=words, say=self.task.status.emit)
            return logo.export_logo(mark, folder, text=name)
        self._run_task(work, lambda out: self._logo_done("ロゴを書き出しました", out))

    def logo_from_canvas(self, text=None):
        from atelier.ai import logo_maker as logo
        if not isinstance(text, str):
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(self, "今の絵をロゴに整える", "横長の版に重ねる文字（空なら文字なし）")
            if not ok:
                return
        image, folder = qimage_to_pil(self.canvas.flatten()), self._logo_folder("logo")
        self.activity.begin("ロゴに整える", "ロゴ・スタンプ")
        self._run_task(lambda _step: logo.export_logo(logo.remove_background(image), folder, text=text),
                       lambda out: self._logo_done("ロゴを書き出しました", out))

    def _pick_spec(self, spec):
        from atelier.ai import logo_maker as logo
        if isinstance(spec, str) and spec in logo.SPECS:
            return spec
        from PySide6.QtWidgets import QInputDialog
        keys = ("line", "telegram")
        names = [logo.SPECS[k]["name"] for k in keys]
        got, ok = QInputDialog.getItem(self, "スタンプ", "形", names, 0, False)
        return keys[names.index(got)] if ok else None

    def stamp_from_canvas(self, spec=None):
        from atelier.ai import logo_maker as logo
        spec = self._pick_spec(spec)
        if spec is None:
            return
        image, folder = qimage_to_pil(self.canvas.flatten()), self._logo_folder("stamp")
        self.activity.begin("スタンプにする", "ロゴ・スタンプ")
        self._run_task(lambda _step: logo.export_stamps([image], folder, spec),
                       lambda out: self._logo_done("スタンプを書き出しました", out))

    def logo_export(self, opts: dict | None = None) -> bool:
        """書き出しの形を選んで、今の絵を書き出す。opts は logo.FORM_DEFAULT の形（試験から渡す。無ければ窓で聞く）"""
        from atelier.ai import logo_maker as logo
        if self.busy("書き出し"):
            return False
        if not isinstance(opts, dict):
            from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox
            d = QDialog(self)
            d.setWindowTitle("書き出しの形")
            form = QFormLayout(d)
            boxes = {}
            for key, label, tip in (("transparent", "透過", "背景を抜いて透明にします"),
                                    ("mono", "単色", "黒 1 色にします（はんこ・刺しゅう・刷り物向け）"),
                                    ("square", "正方形", "余白を付けて正方形に収めます"),
                                    ("line_stamp", "LINE スタンプの大きさ", "370×320・メイン 240×240・タブ 96×74 も書き、zip にまとめます")):
                b = QCheckBox(label)
                b.setToolTip(tip)
                b.setChecked(bool(logo.FORM_DEFAULT[key]))
                form.addRow(b)
                boxes[key] = b
            line = QSpinBox()
            line.setRange(0, 40)
            line.setSuffix(" 画素")
            line.setToolTip("形の外に付ける縁取りの太さ。0 で付けません")
            form.addRow("線の太さ", line)
            size = QSpinBox()
            size.setRange(64, 4096)
            size.setValue(logo.FORM_DEFAULT["size"])
            size.setToolTip("正方形の一辺の画素")
            form.addRow("正方形の大きさ", size)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.button(QDialogButtonBox.Ok).setText("書き出す")
            bb.accepted.connect(d.accept)
            bb.rejected.connect(d.reject)
            form.addRow(bb)
            if d.exec() != QDialog.Accepted:
                return False
            opts = {k: b.isChecked() for k, b in boxes.items()} | {"line": line.value(), "size": size.value()}
        o = dict(logo.FORM_DEFAULT, **opts)
        image, folder = qimage_to_pil(self.canvas.flatten()), self._logo_folder("export")
        self.activity.begin("書き出す", "ロゴ・スタンプ")
        self._run_task(lambda _step: logo.export_forms(image, folder, "mark", o["transparent"], o["mono"], o["line"], o["square"],
                                                        o["line_stamp"], o["size"]),
                       lambda out: self._logo_done("書き出しました", out))
        return True

    def stamp_from_expressions(self, spec=None):
        from atelier.ai import logo_maker as logo
        ident, files = "", []
        for source in self.expression_sources:   # 表情差分を持っているのは拡張（本体は置き場を知らない）
            ident, files = source()
            if files:
                break
        if not files:
            self.notify("スタンプにできませんでした", "info",
                        "表情差分がまだありません。キャラクターデザインのメニューで「表情差分を描く」を先に押してください")
            return
        spec = self._pick_spec(spec)
        if spec is None:
            return
        folder = self._logo_folder("stamp")
        self.activity.begin("表情差分をスタンプにする", "ロゴ・スタンプ")
        self._run_task(lambda _step: logo.export_stamps(files, folder, spec, stem=ident),
                       lambda out: self._logo_done("スタンプを書き出しました", out))

    def _logo_done(self, msg: str, out: list):
        self.activity.end(msg, None, record=False)
        self.logo_out = out
        where = str(Path(out[0]).parent) if out else ""
        self.notify(msg, "ok", f"{len(out)} 個のファイルを {where} に置きました")
        self._end(msg)   # 終えないと糸が残り、ほかの AI の作業（キャラクターデザインのメニューなど）が「描いている間」のまま押せなかった

    def _fill_finish_menu(self):
        """メニューバーの「加工」。項目は右クリックのショートカットと同じ物（shortcuts.builtins）で、押すと同じ関数を呼ぶ"""
        from PySide6.QtWidgets import QMenu
        from atelier.ai import shortcuts
        m = self.finish_menu
        for sub in getattr(self, "_finish_subs", []):   # 開くたびに作り直すので、前の小さなメニューは消す
            sub.deleteLater()
        m.clear()
        m.setToolTipsVisible(True)
        items = shortcuts.builtins(self)
        # 小さなメニューは窓の側で持つ。addMenu(文字) の返りだけを持つと、Python の側の参照が消えたときに中身ごと消えた
        self._finish_subs = []
        for g, label in shortcuts.GROUPS:
            inside = [s for s in items if s.group == g]
            if not inside:
                continue
            sub = QMenu(label, m)
            m.addMenu(sub)
            self._finish_subs.append(sub)
            sub.setToolTipsVisible(True)
            for s in inside:
                act = sub.addAction(s.label, lambda sid=s.id: self.run_shortcut(sid))
                act.setObjectName("menu-" + s.id)
                act.setToolTip(s.tip if s.ready else s.reason)
                act.setEnabled(s.ready)

    def _finisher_ready(self, name: str):
        from atelier.ai import finishers
        for f in finishers.available():
            if f.get("name") == name:
                return bool(f.get("ready")), f.get("reason", "")
        return False, "その道具はありません"

    def _finished_path(self, name: str) -> Path:
        # 日付ごとのフォルダに分ける（1 つのフォルダに絵が溜まり続け、探せなくなった）。前に保存した絵は動かさない
        day = Path(self.settings.get("output_dir")) / time.strftime("%Y-%m-%d")
        day.mkdir(parents=True, exist_ok=True)
        return day / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}.png"

    @staticmethod
    def _save_out(out, path: Path, meta: dict | None = None):
        """出来た絵を書く（裏の糸で呼んでよい）。返すのは out のまま"""
        from atelier.paint.canvas import preload
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(path)
        if meta is not None:
            from atelier.ai import finishers
            finishers.embed(path, meta)
        preload(path)
        return out

    def _place_finished(self, name: str, base, out, path: Path | None = None, clip=None):
        """仕上げた絵を保存し、同じ大きさなら新しいレイヤー、拡大なら置き換えで置く。path を渡したら書き済み。
        clip（囲み）を渡したら、同じ大きさの結果は囲みの中だけのレイヤーにする（囲みの外は透明で、下の元の絵のまま）"""
        from atelier.ai import finishers as _f
        effect = _f.REGISTRY.get(name) is not None and _f.REGISTRY[name].extra.get("effect")
        if clip is not None and out.size == base.size and not effect:   # エフェクトは下で変わった画素だけのレイヤーにする
            out = self._clip_to_region(out, clip)
            path = path or self._finished_path(name)
            self._save_out(out, path)
        if path is None:
            path = self._finished_path(name)
            self._save_out(out, path)
        from atelier.ai import finishers
        f = finishers.REGISTRY.get(name)
        if f is not None and f.extra.get("effect") and out.size == base.size:
            # エフェクトは変わった画素だけのレイヤーに置く。元の絵の画素は変えず、表示の切り替え・不透明度・消すで扱える
            layer = finishers.effect_layer(base, out)
            if clip is not None:   # 赤ペンの印から掛けたエフェクトも、囲みの外は 1 画素も変えない
                layer = self._clip_to_region(layer, clip)
            layer.save(path)
            from atelier.paint.canvas import preload
            preload(path)
            self.canvas.place_result(str(path), f"エフェクト: {f.label}")   # エフェクトはいつも今の絵の一番上のレイヤー
            s = finishers.LAST_STRENGTH.get("strength")
            self.notify("エフェクトを新しいレイヤーに置きました", "ok",
                        (f"この絵に合わせた強さ {s}。" if s else "") + "レイヤーの欄で表示・不透明度を変えたり、消したりできます")
            return path
        if f is not None and f.group == "style" and out.size == base.size:
            from atelier.ai import restyle
            self.put_result(str(path), f"画風: {f.label}")   # 一番上の新しいレイヤーに置いて選ぶ。元の絵は下に残す
            self.notify(f"{f.label}に描き替えました（新しいレイヤー）", "ok", restyle.note() + "見比べて、使うか消すかを決めてください")
            return path
        if out.size == base.size:
            self.put_result(str(path), "綺麗にした絵")   # 元の絵は下に残す
            self.canvas.fit()   # 結果は全体表示で見せる
        else:
            self.put_result(str(path), "綺麗にした絵（拡大）", replace=True)   # 拡大した絵（元に戻すで戻せる）
        self.notify("綺麗にしました（新しいレイヤー）", "ok", "見比べて、使うか消すかを決めてください")
        return path
