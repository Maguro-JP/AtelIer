"""模型（LoRA を含む）の選び方・入れ替え・管理と、学習と判定"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMessageBox
from pathlib import Path


class ModelsMixin:
    """模型（LoRA を含む）の選び方・入れ替え・管理と、学習と判定（Window が継承する）"""

    def _lora_row(self):
        """AI の欄の「模型」に、LoRA を選ぶ欄と強さ（0〜1.5）を足す。初めは「なし」"""
        from PySide6.QtWidgets import QComboBox, QSlider
        from atelier.ai import own_style as ownstyle
        self.lora_pick = QComboBox()
        self.lora_pick.setToolTip("LoRA を絵の模型に重ねます。足すのは「模型の管理」の「LoRA…」から。置き場は " + str(ownstyle.lora_dir()))
        ModelsMixin._lora_fill(self)
        self.lora_strength = QSlider(Qt.Horizontal)
        self.lora_strength.setRange(0, 150)
        self.lora_strength.setValue(int(self.layout_store.value("lora_scale", 80)))
        self.lora_strength.setToolTip("LoRA の強さ（0〜1.5）。大きいほど LoRA の作風に寄せます")
        self.lora_pick.currentIndexChanged.connect(lambda _i: self._lora_changed())
        self.lora_strength.valueChanged.connect(lambda _v: self._lora_changed())
        body = self.ai_panel.sections["模型"].body
        body.addWidget(self.lora_pick)
        body.addWidget(self.lora_strength)
        ModelsMixin._lora_shown(self)   # 試験は名前空間で呼ぶので、窓の側の関数を直接呼ぶ

    def _lora_fill(self, model_family: str | None = None):
        """置き場の LoRA を並べ直す。今の模型と系統の合わない物は選べなくし、理由をツールチップに出す"""
        from PySide6.QtCore import Qt as _Qt
        from atelier.ai import lora as loralib
        if model_family is None:
            try:
                from atelier.models.catalog import image_model
                model_family = image_model(getattr(getattr(getattr(self, "studio", None), "painter", None), "model", "") or "").family
            except Exception:
                model_family = ""
        keep = str(self.layout_store.value("lora", "") or "")
        self.lora_pick.blockSignals(True)
        self.lora_pick.clear()
        self.lora_pick.addItem("LoRA なし", "")
        for p in loralib.loras():
            ok, why = loralib.compatible(loralib.family_of(p), model_family) if model_family else (True, "")
            words = ", ".join(loralib.trigger_words(p))
            self.lora_pick.addItem(loralib.label(p), str(p))
            i = self.lora_pick.count() - 1
            tip = "\n".join(x for x in (why, f"きっかけの言葉: {words}（効かせるときは描くワードに書いてください。自動では足しません）" if words else "") if x)
            self.lora_pick.setItemData(i, tip or loralib.FAMILY_JA.get(loralib.family_of(p), ""), _Qt.ToolTipRole)
            if not ok:
                item = self.lora_pick.model().item(i)
                item.setEnabled(False)
        i = self.lora_pick.findData(keep)
        if i > 0 and not self.lora_pick.model().item(i).isEnabled():
            i = 0
        self.lora_pick.setCurrentIndex(max(0, i))
        self.lora_pick.blockSignals(False)

    def _lora_shown(self):
        """LoRA を置いていなければ選ぶ欄を出さず、「なし」のときは強さを出さない（動かしても何も変わらない部品を並べない）。
        選んだ値と設定の鍵（lora、lora_scale）はそのまま残す"""
        self.lora_pick.setVisible(self.lora_pick.count() > 1)
        self.lora_strength.setVisible(bool(self.lora_pick.currentData()))

    def _lora_changed(self):
        ModelsMixin._lora_shown(self)   # 試験は名前空間で呼ぶので、窓の側の関数を直接呼ぶ
        path, scale = self.lora_pick.currentData() or "", self.lora_strength.value()
        self.layout_store.setValue("lora", path)
        self.layout_store.setValue("lora_scale", scale)
        painter = getattr(getattr(self, "studio", None), "painter", None)
        if painter is not None:
            painter.lora, painter.lora_scale = path, scale / 100

    def collect_favorites(self):
        """★ の絵を学習用のデータ（絵と説明の .txt）に書き出し、置き場を知らせる"""
        from atelier.ai import own_style as ownstyle
        if not ownstyle.favorites():
            self.statusBar().showMessage("★ の絵がありません。履歴かライブラリーの絵を右クリックして ★ を付けてください", 8000)
            return None
        res = ownstyle.collect()
        self.statusBar().showMessage(f"学習用に {len(res['images'])} 枚を集めました: {res['dir']}"
                                     + (f"（見つからない絵 {len(res['missing'])} 枚）" if res["missing"] else ""), 12000)
        return res

    def _learn_runner(self):
        """★ から学び直す裏の処理を、この窓の裏の処理（動いている間は自動の gc を止める）で動かす。
        窓が閉じたら ownstyle は自前の糸に戻る。窓を強く持たない（閉じた窓を残さない）"""
        import weakref
        from atelier.ai import own_style as ownstyle
        me = weakref.ref(self)

        def run(work):
            w = me()
            if w is None or getattr(w, "_io_closed", False):
                raise RuntimeError("窓が閉じています")
            from PySide6.QtCore import QThread
            if QThread.currentThread() is not w.thread_main:
                raise RuntimeError("画面の糸からだけ渡す")
            w.in_background(work, lambda _v: None, "★ から学ぶ")
        ownstyle.RUNNER = run

    def judge(self, path: str, verdict: str) -> bool:
        """履歴の右クリック → 判定。記録の無い絵（前の版で描いた絵）は知らせる"""
        from atelier.words import learning as wordlearn
        from atelier.panels import user_stats as userstats

        def work():
            return wordlearn.set_verdict(path, verdict)

        def done(ok):
            # 判定が変わったので、模型の並べ方を測り直す（測るのは次に並べるとき。ここでは覚えを捨てるだけ）
            userstats.refresh()
            if isinstance(ok, BaseException):
                ok = False
            self.statusBar().showMessage((f"判定を付けました: {wordlearn.VERDICTS.get(verdict, '消しました')}" if ok else
                                          "この絵は学びの記録がありません（前の版で描いた絵です）"), 4000)
        # 記録（数千行）を読み直して書き直すのは裏の列で行う。画面の糸で書くと 1 回 0.4 秒固まった。
        # 書く列は 1 本なので、続けて押しても同じファイルに重ねて書かない
        self.run_io(work, done, "判定を付ける")
        return True

    def ask_models(self, force: bool = False):
        """初めての起動か、絵の模型が足りなければ、候補を見せて選んでもらう。force なら入れ替えと更新の画面を開く"""
        from atelier.models.first_setup import SetupDialog, missing
        store = self.settings.store
        # 閉じても「今は選ばない」として 1 回だけ聞く。前は閉じると次の起動でまた出て、模型が無い間は毎回出た
        first = not int(store.value("setup_done", 0)) and not int(store.value("setup_asked", 0))
        if not (force or first):
            if missing()["image"] and hasattr(self, "notify"):
                self.statusBar().showMessage("絵の模型がまだありません。「AI」の「模型の管理」から取れます", 8000)
            return
        store.setValue("setup_asked", 1)
        if SetupDialog(self.settings, self, first=not force).exec():
            self.studio = self._studio_from_settings()   # 選んだ模型で描き直す
            self.check_ai()

    def upgrade_models(self):
        """使っている言葉の模型を、完全に上回る新しい模型があれば裏で取って乗り換える。古いファイルは消さない"""
        from atelier.models.catalog import SUPERSEDED, WORDS, offered_words
        from atelier.models.first_setup import Fetcher, has_words, words_path
        # 言葉の模型は利用者に選ばせず、確かめていちばん点の高い物を使う。利用者が自分で置いた模型（一覧に無い物）はそのまま
        from atelier.models.manager import words_chosen
        if words_chosen(self.settings):   # 利用者が選んだ物（「使わない」を含む）は勝手に替えない
            return
        now = self.settings.get("words_model")
        best = offered_words()
        new = best[0] if best else None
        known = {m.file for m in WORDS} | set(SUPERSEDED)
        if new is None or Path(now).name == new.file or (now not in ("", "auto") and Path(now).name not in known):
            return

        def switch(err: str = ""):
            if err:
                self.statusBar().showMessage(f"{new.name} に乗り換えられませんでした", 6000)
                return
            self.settings.set("words_model", str(words_path(new)))
            self.studio = self._studio_from_settings()
            self.notify(f"言葉の模型を {new.name} に乗り換えました", "ok")
        if has_words(new):
            switch()
            return
        import threading
        self.upgrader = Fetcher()
        self.upgrader.finished.connect(switch, Qt.QueuedConnection)
        self.watch_fetch(self.upgrader, "言葉の模型")
        self.statusBar().showMessage(f"新しい言葉の模型 {new.name} を裏で取っています", 6000)
        threading.Thread(target=self.upgrader.run, args=(None, new), daemon=True).start()

    def ask_words_once(self, pick=None, force: bool = False):
        """言葉の模型を選んでもらう。起動のときは聞かない（初めての起動で確かめの窓が 3 枚続いたため。
        選ぶまでは点のいちばん高い物を使う。upgrade_models）。「設定」の「言葉の模型を選ぶ…」と試験（pick）から開く。
        閉じたときは「今は選ばない」で、「使わない」とは覚えない。
        pick は試験で窓の代わりに答えを返す関数（items を受けて 1 つ返す。None はやめた）"""
        from atelier.models.manager import choose_words, words_chosen
        from atelier.models.catalog import offered_words
        from atelier.models.first_setup import has_words, words_path
        if pick is None and not force:
            return
        if words_chosen(self.settings) and not force:
            return
        offered = offered_words()
        if not offered:
            return   # 選べる物が無いうちは聞かない（聞いても「使わない」しか無い）
        labels = [f"{m.name}（{m.gb:.1f}GB{'・取得済み' if has_words(m) else ''}）" for m in offered] + ["使わない"]
        now = Path(self.settings.get("words_model") or "").name
        first = next((i for i, m in enumerate(offered) if m.file == now), 0)
        if pick is None:
            from PySide6.QtWidgets import QInputDialog
            got, ok = QInputDialog.getItem(self, "言葉の模型", "日本語の頼みとチャットに使う模型を選んでください。\n"
                                           "選んだ物を覚え、次からは聞きません。あとで「模型の管理」から変えられます。",
                                           labels, first, False)
            got = got if ok else None
        else:
            got = pick(labels)
        if got is None:
            return   # 閉じた・やめた。何も決めず、前の模型のまま
        if got == "使わない":
            choose_words(self.settings, "")
            self.statusBar().showMessage("言葉の模型を使いません。使うときは「模型の管理」から選びます", 6000)
        else:
            m = offered[labels.index(got)]
            choose_words(self.settings, str(words_path(m)))
            if not has_words(m):
                import threading
                from atelier.models.first_setup import Fetcher
                self.words_fetcher = Fetcher()
                self.words_fetcher.finished.connect(lambda _err="": (setattr(self, "studio", self._studio_from_settings()),
                                                                   self.check_ai()), Qt.QueuedConnection)
                self.watch_fetch(self.words_fetcher, "言葉の模型")
                threading.Thread(target=self.words_fetcher.run, args=(None, m), daemon=True).start()
        self.studio = self._studio_from_settings()

    # ---- AI のメニュー: 模型の切り替え ----
    def rescan_models(self):
        """手元にある絵の模型を裏の糸で数え直す。模型 1 つごとに置き場を見に行くので、100 余りの模型で
        画面の糸が 50 ミリ秒以上（Windows の大きな置き場ではもっと）止まり、メニューを開くたびに引っかかった"""
        if getattr(self, "_scanning", False):
            self._rescan_again = True
            return
        self._scanning, self._rescan_again = True, False
        from atelier.models.catalog import all_images
        from atelier.models.first_setup import has_image
        every = all_images()

        def done(have):
            self._scanning = False
            if isinstance(have, BaseException):
                return
            changed = have != self._have_images
            self._have_images = have
            if changed:
                self._refresh_ai_menu()
            if self._rescan_again:
                self.rescan_models()
        self.in_background(lambda: {m.repo for m in every if has_image(m)}, done, "模型を調べる")

    def installed_images(self, models) -> set[str]:
        """models のうち手元にある物。まだ一度も数えていなければ（起動の初めだけ）その場で数える"""
        if getattr(self, "_have_images", None) is None:
            from atelier.models.catalog import all_images
            from atelier.models.first_setup import has_image
            self._have_images = {m.repo for m in all_images() if has_image(m)}
        return {m.repo for m in models if m.repo in self._have_images}

    def have_image_models(self) -> list:
        """手元にある絵の模型（裏で数えて覚えた物を使う）"""
        from atelier.models.catalog import all_images
        every = all_images()
        have = self.installed_images(every)
        return [m for m in every if m.repo in have]

    def _fill_ai_menu(self):
        """模型の一覧を作り直す。開くときと、取った・消した・点・★・非表示が変わったとき（ratings.changed）に呼ぶ"""
        from atelier.models.catalog import catalog_images, manual_images, pick
        from atelier.models.ratings import is_blocked, is_favorite, rating_text, set_favorite
        from atelier.models.first_setup import AUTO
        menu = self.ai_menu
        menu.clear()
        now_image = self.settings.get("image_model")
        # 出すのは、推奨に届いた模型と手元にある模型（手元の物と ★ が先）。非表示にした物は出さない
        catalog = catalog_images()
        have = self.installed_images(catalog)
        listed = pick(catalog, "推奨（確かめ済み）", have=have)
        listed = pick(catalog, "取得済み", have=have) + [m for m in listed if m.repo not in have]   # メニューには手元の物も出す
        images = listed + [m for m in manual_images() if not is_blocked(m.repo)]
        menu.addSection("絵の模型")
        group = QActionGroup(menu)
        auto = QAction("おまかせ", menu, checkable=True)
        auto.setToolTip("描くときに、手元の模型から頼みに合い点の高い物を選びます")
        from atelier.models import favorites as favmodels
        from atelier.models.favorites import FAV
        entries = [(AUTO, auto)]
        # 編成した物を模型の選択に 1 つずつ出す。選ぶと、その編成の役目ごとの模型で描く（作る・直すは「模型の編成」のメニュー）
        active_set = favmodels.active()
        for name in favmodels.sets():
            data = favmodels.get_set(name)
            act = QAction(favmodels.label(name), menu, checkable=True)
            act.setToolTip(self._set_tip(data))
            entries.append((("set", name), act))
        now_key = ("set", active_set) if now_image == FAV else now_image
        for m in images:
            label = ("★ " if is_favorite(m.repo) else "") + m.name + (f"　{rating_text(m)}" if m in listed else "")
            ok = m.repo in have or m not in listed
            entries.append((m.repo, QAction(label if ok else f"{label}（未取得）", menu, checkable=True)))
        for key, act in entries:
            act.setChecked(key == now_key)
            if isinstance(key, tuple):
                act.triggered.connect(lambda _=False, n=key[1]: self.use_model_set(n))
            else:
                act.triggered.connect(lambda _=False, k=key: self.switch_model("絵の模型", k))
            group.addAction(act)
            menu.addAction(act)
        stars = menu.addMenu("★ お気に入り")
        stars.setToolTipsVisible(True)
        for m in listed:
            a = QAction(m.name, menu, checkable=True)   # 親はメニュー（作り直すと一緒に消える）
            stars.addAction(a)
            a.setChecked(is_favorite(m.repo))
            a.setToolTip("★ を付けた模型は一覧の先頭に出て、おまかせでも選ばれやすくなります")
            a.toggled.connect(lambda on, r=m.repo: set_favorite(r, on))
        menu.addAction(QAction("Civitai から探す…", self, triggered=self.open_civitai,
                               toolTip="Civitai の模型と LoRA を見本の絵で探して取ります"))
        sets_menu = menu.addMenu("模型の編成")
        sets_menu.setToolTipsVisible(True)
        for text, tip, fn in (("編成を作る…", "構図・仕上げ・背景・顔・身体・髪と加工に使う模型の組を、名前を付けて作ります", self.new_model_set),
                              ("今の編成を直す…", "今の編成の役目ごとの模型を選び直します", self.open_role_models),
                              ("今の編成の名前を変える…", "今の編成の名前を変えます", self.rename_model_set),
                              ("今の編成を消す…", "今の編成を消します（模型そのものは消しません）", self.delete_model_set)):
            sets_menu.addAction(QAction(text, menu, triggered=lambda _=False, f=fn: f(), toolTip=tip))
        menu.addSeparator()
        fix_menu = menu.addMenu("直しに使う模型")
        fix_menu.setToolTipsVisible(True)
        fix_menu.aboutToShow.connect(lambda: self._fill_fix_menu(fix_menu))
        self._fill_fix_menu(fix_menu)
        menu.addAction(QAction("模型の管理…", self, triggered=self.manage_models))
        qc = QAction("検品の部品を取り直す", self, triggered=lambda: __import__("atelier.models.first_setup", fromlist=["x"]).refetch_qc_parts(self))
        qc.setToolTip("手・足・顔・部位分け・人の枠の検品に使う部品のうち、無い物を取ります")
        menu.addAction(qc)

    def _open_ai_menu(self):
        """AI のメニューを開くとき。取った・消した直後でも古い一覧を出さないよう、手元の模型をその場で数え直す"""
        self._have_images = None
        self._ai_menu_stale = False
        self._fill_ai_menu()

    def _refresh_ai_menu(self):
        """模型の一覧を作り直す。開いているメニューの中身は押している最中に消さず、閉じたあとに作り直す"""
        if self.ai_menu.isVisible():
            self._ai_menu_stale = True
        else:
            self._fill_ai_menu()

    def _ai_menu_hidden(self):
        if getattr(self, "_ai_menu_stale", False):
            self._ai_menu_stale = False
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._fill_ai_menu)

    def _models_changed(self):
        """模型の一覧が変わったら（取得・削除・ブロック・非表示・評価・★）、AI のメニューと模型の表示を作り直す"""
        self._refresh_ai_menu()
        self._show_model()
        self.rescan_models()   # 取った・消したあとの手元の模型は裏で数え直し、変わっていればメニューを作り直す

    def manage_models(self):
        if self.tour_first("manager", self.manage_models):
            return
        from atelier.models.manager import ModelManager
        ModelManager(self.settings, self).exec()
        self._have_images = None   # 取った・消した物があるかもしれないので、数え直すまで覚えを使わない
        self.studio = self._studio_from_settings()
        if hasattr(self, "lora_pick"):   # 足した LoRA と、替えた模型の系統に合わせて並べ直す
            ModelsMixin._lora_fill(self)
            ModelsMixin._lora_changed(self)
        self.check_ai()
        self._fill_ai_menu()
        self.rescan_models()

    def open_civitai(self):
        """Civitai から模型と LoRA を探して取る窓（atelier/panels/civitai_panel.py）。取った物はすぐ一覧に出す"""
        from atelier.panels.civitai_panel import CivitaiDialog
        dlg = CivitaiDialog(self.layout_store, self)
        dlg.exec()
        if dlg.got is not None:
            self.reload_loras()
            self._have_images = None
            self._refresh_ai_menu()

    def reload_loras(self):
        """LoRA の欄を置き場から数え直す（取ったばかりの LoRA をすぐ選べるように）。選んでいた物は残す"""
        from atelier.ai import own_style as ownstyle
        now = self.lora_pick.currentData()
        self.lora_pick.blockSignals(True)
        self.lora_pick.clear()
        self.lora_pick.addItem("LoRA なし", "")
        for p in ownstyle.loras():
            self.lora_pick.addItem(p.stem, str(p))
        self.lora_pick.setCurrentIndex(max(0, self.lora_pick.findData(now)))
        self.lora_pick.blockSignals(False)
        ModelsMixin._lora_shown(self)

    def _set_tip(self, data: dict) -> str:
        from atelier.models import favorites as favmodels
        from atelier.models.catalog import image_model
        return "\n".join(f"{label}: {image_model(data[r]).name if r in data else 'おまかせ'}"
                         for r, (label, _t) in favmodels.ROLES.items())

    def use_model_set(self, name: str):
        """模型の選択で編成を選んだとき。その編成を今の編成にして、役目ごとの模型で描く"""
        from atelier.models import favorites as favmodels
        favmodels.use_set(name)
        self.switch_model("絵の模型", favmodels.FAV)
        self._fill_ai_menu()

    def open_role_models(self, name: str | None = None):
        """編成の役目ごとの模型を選ぶ窓（atelier/models/favorites.py）。保存したらその編成で描くように替える"""
        from atelier.models import favorites as favmodels
        from atelier.panels.favorite_models_panel import RoleModelsDialog
        name = name or favmodels.active()
        dlg = RoleModelsDialog(self.have_image_models(), self, data=favmodels.get_set(name), title=f"編成「{name}」")
        if not dlg.exec():
            return False
        favmodels.save_set(name, dlg.values(), use=True)
        self.use_model_set(name)
        return True

    def new_model_set(self, name: str | None = None):
        from atelier.models import favorites as favmodels
        if name is None:
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "編成を作る", "編成の名前（例: アニメの立ち絵、背景つき）")
            if not ok:
                return
        name = name.strip()
        if not name or name in favmodels.sets():
            self.notify("その名前は使えません", "warn", "空か、ほかの編成と同じ名前です")
            return
        self.open_role_models(name)

    def rename_model_set(self, new: str | None = None):
        from atelier.models import favorites as favmodels
        old = favmodels.active()
        if new is None:
            from PySide6.QtWidgets import QInputDialog
            new, ok = QInputDialog.getText(self, "編成の名前", "新しい名前", text=old)
            if not ok:
                return
        try:
            favmodels.rename_set(old, new)
        except (KeyError, ValueError) as e:
            self.notify("名前を変えられません", "warn", str(e).strip("'"))
            return
        self._fill_ai_menu()
        self._show_model()

    def delete_model_set(self, confirm: bool = True):
        from atelier.models import favorites as favmodels
        name = favmodels.active()
        if confirm and QMessageBox.question(self, "編成を消す", f"編成「{name}」を消しますか？（模型そのものは消しません）") != QMessageBox.Yes:
            return
        favmodels.delete_set(name)
        self._fill_ai_menu()
        self._show_model()

    def switch_model(self, kind: str, key: str):
        self.feature_tour("model")
        """メニューで選んだ模型に替える。取っていなければ取ってから替える。消すことはしない"""
        from atelier.models.catalog import WORDS
        from atelier.models.first_setup import AUTO, SetupDialog, has_image, has_words, words_path
        if kind == "絵の模型":
            from atelier.models.catalog import all_images
            m = next((m for m in all_images() if m.repo == key), None)
            need = m is not None and not has_image(m) or key == AUTO and not any(has_image(x) for x in all_images())
        else:
            m = next((m for m in WORDS if m.file == key), None)
            need = m is not None and not has_words(m) or key == AUTO and not any(has_words(x) for x in WORDS)
            if m is None and key not in (AUTO, ""):
                from atelier.files.paths import find_gguf
                from atelier.models.manager import choose_words
                choose_words(self.settings, str(find_gguf(key) or key))   # 利用者が自分で置いた模型
                self.studio = self._studio_from_settings()
                self.check_ai()
                return
        if need:
            dlg = SetupDialog(self.settings, self, first=False)
            dlg.select(**({"image": key} if kind == "絵の模型" else {"words": key}))
            dlg.start(update=False)
            if not dlg.exec():
                return
            self._have_images = None   # 取ったばかりの模型を、おまかせの選びに入れる
        elif kind == "絵の模型":
            self.settings.set("image_model", key)
            if m is not None:
                self.settings.set("steps", m.steps)
                self.settings.set("guidance", m.guidance)
        else:
            from atelier.models.manager import choose_words
            choose_words(self.settings, key if key in (AUTO, "") else str(words_path(m)))
        self.studio = self._studio_from_settings()
        if hasattr(self, "lora_pick"):   # 足した LoRA と、替えた模型の系統に合わせて並べ直す
            ModelsMixin._lora_fill(self)
            ModelsMixin._lora_changed(self)
        self.check_ai()
        self._fill_ai_menu()
        self.rescan_models()
        self.notify(f"{kind}を替えました", "ok")
