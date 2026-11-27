"""設定、ヘルプ、デバッグモードと記録"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from atelier.ai.engine import Painter
from atelier.ai.engine import Studio
from atelier.ai.engine import Words
from atelier.app.settings import SettingsDialog
from atelier.files.paths import HOME as DATA
from pathlib import Path


def faded_base(image, alpha: float):
    """土台の絵を、指定の薄さ（0〜1）で重ねられる RGBA の絵にする（デバッグ表示用）"""
    rgba = image.convert("RGBA")
    a = rgba.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, alpha))))
    rgba.putalpha(a)
    return rgba


class SettingsAndDebugMixin:
    """設定、ヘルプ、デバッグモードと記録（Window が継承する）"""

    def _studio_from_settings(self) -> Studio:
        """設定の模型で描く仕組みを作る。前と同じ絵の模型なら、読んだ物をそのまま使う（7GB を読み直さない）"""
        from atelier.models.catalog import IMAGES
        from atelier.models.first_setup import AUTO
        g = self.settings.get
        image, words = g("image_model"), g("words_model")
        from atelier.models.ratings import is_blocked
        if is_blocked(image):   # ブロックした模型は、設定に残っていても使わない
            image = AUTO
        from atelier.models import favorites as favmodels
        if image == favmodels.FAV:   # お気に入り: 初めに読むのは仕上げ（無ければ構図）のお気に入り
            have = self.have_image_models()
            first = favmodels.resolve("finish", have) or favmodels.resolve("compose", have)
            if first is None:
                from atelier.ai.choose import choose_image
                first = choose_image("", "", have=have)[0] or IMAGES[0]
            image, steps, guidance = first.repo, first.steps, first.guidance
        elif image == AUTO:
            from atelier.ai.choose import choose_image
            first = choose_image("", "", have=self.have_image_models())[0] or IMAGES[0]
            image, steps, guidance = first.repo, first.steps, first.guidance
        else:
            steps, guidance = g("steps"), g("guidance")
        old = getattr(self, "studio", None)
        if old is not None and getattr(old.painter, "model", None) != image and not getattr(self, "thread", None) \
                and callable(getattr(old.painter, "unload", None)):
            old.painter.unload()   # 模型を替えたら、前の模型を降ろしてから次を読む（2 つを同時にメモリに置かない）
        painter = old.painter if old is not None and getattr(old.painter, "model", None) == image else Painter(image)
        painter.steps, painter.guidance = steps, guidance
        painter.lora = str(self.layout_store.value("lora", "") or "")
        painter.lora_scale = int(self.layout_store.value("lora_scale", 80)) / 100
        studio = Studio(Words(None if words == AUTO else Path(words)), painter, Path(g("output_dir")))
        studio.image_auto, studio.words_auto = g("image_model") == AUTO, words == AUTO
        studio.use_favorites = g("image_model") == favmodels.FAV
        from atelier.app.settings import studio_way
        studio.way = studio_way(g("draw_way"), g("ai_way"))
        for hook in self.studio_hooks:   # 拡張が、作り直した仕組みに自分の物を入れ直す（開いている人物など）
            hook(studio)
        return studio

    def open_help(self, key: str):
        from atelier.ui.help_view import HelpDialog
        HelpDialog(key, self).show()

    def open_logs(self):
        """記録（atelier.log、setup.log）の置き場を開く。困ったときに中を見たり、渡したりするため"""
        from atelier.files.folders import open_folder
        open_folder(DATA)

    def open_keys(self):
        from atelier.app.key_bindings import KeyDialog
        if KeyDialog(self, self.layout_store).exec():
            self.statusBar().showMessage("キーの設定を保存しました", 4000)

    def reset_layout(self):
        """欄と帯を初めの並びに戻し、ウィンドウを画面に収める（並びが崩れて操作できなくなったときの戻り道）"""
        from atelier.ui.window_fit import fit
        self._all_hidden = False
        if getattr(self, "ai_tabs", None) is not None:
            self.ai_tabs.reset()   # 外へ出した AI の欄のタブも戻し、タブの順も初めの形にする
        self._show_all(True)
        for d, _area in self.panels.values():
            d.setFloating(False)
        self.arrange()
        self.showNormal()
        area = self.screen().availableGeometry()
        self.resize(min(1400, area.width() - 40), min(900, area.height() - 60))
        fit(self)

    def reset_confirms(self):
        from atelier.ui import confirm
        n = confirm.forget(self)
        self.notify("確かめの窓をまた出します" if n else "聞かないにした窓はありません", "ok")

    def open_settings(self):
        """設定ウィンドウを開き、保存されたら描く仕組みに当てる。絵の模型を替えたときだけ読み直す"""
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            g = self.settings.get
            from atelier.ai import memory_budget as membudget
            membudget.set_mode(g("mem_mode"))   # 次に描く 1 枚から効く
            self.studio = self._studio_from_settings()
            self.strength.setValue(int(g("rough_follow") * 100))
            self.check_ai()
            self.canvas.set_cursor_style(g("cursor"))
            self.apply_debug_mode()
            from atelier.app.settings import PRECISE
            self.way_pick.blockSignals(True)   # 設定で替えた描き方を、描くボタンの横の欄にも出す
            self.way_pick.setCurrentIndex(1 if g("draw_way") == PRECISE else 0)
            self.way_pick.blockSignals(False)
            self.statusBar().showMessage("設定を保存しました")

    # ---- デバッグモード（atelier/app/debug_log.py） ----
    def apply_debug_mode(self):
        """設定のデバッグモードを当てる。オンなら下に「記録」の欄を出し、裏の記録を流す"""
        from atelier.app import debug_log as debuglog
        from atelier.app.settings import apply_debug
        apply_debug(self.settings)
        if debuglog.on():
            self._debug_dock().show()
        elif getattr(self, "_dbg_dock", None) is not None:
            self._dbg_dock.hide()
            btn = getattr(self, "base_overlay_btn", None)
            if btn is not None and btn.isChecked():
                btn.setChecked(False)   # デバッグを切ったら、土台の重ね表示も消す

    def _toggle_base_overlay(self, on):
        self._base_overlay_on = bool(on)
        self._refresh_base_overlay()

    def _stash_base(self, img):
        """土台の絵を受け取って取っておく（Job の base_thumb から届く）。出すのは重ね表示が
        オンのときだけ。通常の見せ方には出さない"""
        self._base_thumb = img
        if getattr(self, "_base_overlay_on", False):
            self._refresh_base_overlay()

    def _refresh_base_overlay(self):
        """土台の絵を薄くしてキャンバスに重ねる。オフなら消す。土台がまだ届いていなければ、
        届いたときに show_preview がもう一度呼ぶ"""
        try:
            if not getattr(self, "_base_overlay_on", False):
                self.canvas.show_overlay(None)
                return
            base = getattr(self, "_base_thumb", None)
            if base is None:
                return
            slider = getattr(self, "base_overlay_slider", None)
            alpha = (slider.value() / 100.0) if slider is not None else 0.35
            from atelier.app.window.image_convert import qimage_from_pil
            self.canvas.show_overlay(qimage_from_pil(faded_base(base, alpha)))
        except Exception:   # noqa: BLE001  デバッグ表示の失敗で描く処理を止めない
            pass

    def _debug_dock(self):
        from PySide6.QtCore import QObject, QTimer, Signal
        from PySide6.QtWidgets import QDockWidget, QLabel, QPlainTextEdit
        from atelier.app import debug_log as debuglog
        from atelier.app import usage
        if getattr(self, "_dbg_dock", None) is not None:
            return self._dbg_dock

        class Bridge(QObject):   # 裏の糸の記録を、画面の糸で欄に足す
            line = Signal(str)
        self._dbg_bridge = Bridge()
        dock = QDockWidget("記録", self)
        dock.setObjectName("debug_log")
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        # 使用率（CPU・メモリ）。デバッグのときタスクマネージャーで見ていた物。
        # 欄が見えている間だけ、1 秒ごとに測る
        self.debug_usage_label = QLabel("使用率 計測中")
        self._usage_meter = usage.CpuMeter()
        self._usage_timer = QTimer(self)
        self._usage_timer.setInterval(1000)
        self._usage_timer.timeout.connect(self._update_usage_label)
        dock.visibilityChanged.connect(
            lambda v: self._usage_timer.start() if v else self._usage_timer.stop())
        lay.addWidget(self.debug_usage_label)
        # 土台の絵の重ね表示（デバッグ専用）: 精度優先の基準にした土台の絵を、今の絵に
        # 薄く重ねて、何を直そうとしているのかを見られるようにする。通常の見せ方では出さない
        from PySide6.QtWidgets import QSlider
        base_row = QHBoxLayout()
        self.base_overlay_btn = QPushButton("土台の絵を薄く重ねる")
        self.base_overlay_btn.setCheckable(True)
        self.base_overlay_btn.setToolTip("精度優先の基準にした土台の絵（80 点の一発の絵）を、今描いている絵に薄く重ねます")
        self.base_overlay_btn.toggled.connect(self._toggle_base_overlay)
        self.base_overlay_slider = QSlider(Qt.Horizontal)
        self.base_overlay_slider.setRange(10, 80)
        self.base_overlay_slider.setValue(35)
        self.base_overlay_slider.setToolTip("土台の絵の濃さ")
        self.base_overlay_slider.valueChanged.connect(lambda _v: self._refresh_base_overlay())
        base_row.addWidget(self.base_overlay_btn)
        base_row.addWidget(self.base_overlay_slider)
        lay.addLayout(base_row)
        self.debug_view = QPlainTextEdit()
        self.debug_view.setReadOnly(True)
        self.debug_view.setMaximumBlockCount(debuglog.RING)
        self.debug_view.setPlainText("\n".join(debuglog.lines()))
        row = QHBoxLayout()
        open_btn = QPushButton("記録のファイルを開く")
        open_btn.setToolTip(f"今日の記録のファイルを開きます（{debuglog.KEEP_DAYS} 日より古い記録は自動で消えます）")
        open_btn.clicked.connect(self.open_debug_log)
        row.addWidget(open_btn)
        row.addStretch(1)
        lay.addWidget(self.debug_view)
        lay.addLayout(row)
        dock.setWidget(box)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        talk = getattr(self, "panels", {}).get("talk")
        if talk is not None:
            # 既定は下の「チャット」の欄とタブで重ねる（利用者の希望。記録はシステムの知らせの
            # 置き場なので、会話の欄と一緒が合う）。保存した並びがあるときは、このあとの
            # 復元（restoreState）がそちらを当てるので、ここは初めの置き場でしかない
            self.tabifyDockWidget(talk[0], dock)
        self._dbg_bridge.line.connect(self.debug_view.appendPlainText)
        debuglog.listen(self._dbg_bridge.line.emit)
        self._dbg_dock = dock
        return dock

    def _update_usage_label(self):
        """使用率の表示を今の値にする。測れなくても記録の欄は壊さない"""
        try:
            from atelier.app import usage
            self.debug_usage_label.setText(usage.format_line(usage.sample(self._usage_meter)))
        except Exception:   # noqa: BLE001
            pass

    def open_debug_log(self):
        from atelier.app import debug_log as debuglog
        f = debuglog.file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.touch()
        except OSError:
            pass
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(f)))

    def _debug_failure(self, title: str, why: str, trace: str = ""):
        """デバッグモードなら、描けなかった・落ちた理由の全文を窓で出す（記録のファイルを開ける）"""
        from atelier.app import debug_log as debuglog
        if not debuglog.on():
            return
        debuglog.log("描けなかった", why)
        box = QMessageBox(QMessageBox.Warning, title, why, parent=self)
        box.setDetailedText(trace or why)
        opener = box.addButton("記録のファイルを開く", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        opener.clicked.connect(self.open_debug_log)
        box.setModal(False)
        self.debug_box = box
        box.show()
