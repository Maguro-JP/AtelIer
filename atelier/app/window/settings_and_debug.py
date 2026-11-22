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

    def open_palette(self):
        """操作を探す窓（Ctrl+K）"""
        from atelier.ui.command_palette import CommandPalette
        self.cmd_palette = CommandPalette(self)
        self.cmd_palette.open()
        return self.cmd_palette

    def compare_images(self):
        """履歴で選んだ絵を並べる。1 枚以下なら新しい順に 4 枚まで"""
        from PySide6.QtCore import Qt
        from atelier.ui.command_palette import CompareDialog
        items = [it for it in self.history.selectedItems() if it.data(Qt.UserRole)]
        if len(items) < 2:
            items = [self.history.item(r) for r in range(min(4, self.history.count()))]
            items = [it for it in items if it.data(Qt.UserRole)]
        if len(items) < 2:
            self.statusBar().showMessage("比べる絵が 2 枚以上ありません。描くと履歴に並びます", 6000)
            return None
        self.compare = CompareDialog(self, [(it.data(Qt.UserRole), it.toolTip()) for it in items[:8]])
        self.compare.open()
        return self.compare

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

    def _debug_dock(self):
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import QDockWidget, QPlainTextEdit
        from atelier.app import debug_log as debuglog
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
        self._dbg_bridge.line.connect(self.debug_view.appendPlainText)
        debuglog.listen(self._dbg_bridge.line.emit)
        self._dbg_dock = dock
        return dock

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
