"""レイヤーとごみ箱、選択範囲、クリップボード、対称と定規"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from pathlib import Path
import os


class LayersAndSelectionMixin:
    """レイヤーとごみ箱、選択範囲、クリップボード、対称と定規（Window が継承する）"""

    # ---- 消す・ごみ箱 ----
    def delete_images(self, paths: list[str], ask: bool = True) -> str | None:
        """絵と付属のファイルをアプリのごみ箱へ移し、履歴とライブラリーから外す。消す前に確かめる。
        すぐには消さない（ごみ箱から戻せる）。移した 1 回分の名前を返す"""
        paths = [str(p) for p in paths if p]
        if not paths:
            return None
        if ask:
            from atelier.ui import confirm
            n = len(paths)
            if confirm.ask(self, "delete_images", "絵を消す",
                           ("この絵" if n == 1 else f"{n} 枚の絵") + "をごみ箱へ移します。付属のファイル（頼みと設定）も一緒に移します。\n"
                           "「ファイル」→「ごみ箱…」から戻せます。", [("yes", "ごみ箱へ移す")]) != "yes":
                return None
        items = self.library.take(paths)
        try:
            key = self.trash.put(paths, items)
        except OSError as e:
            self.library.put_back(items)
            self.notify("消せませんでした", "error", f"{e}\nほかのアプリでその絵を開いていれば閉じてから、もう一度消してください")
            return None
        gone = set(paths)
        for row in reversed(range(self.history.count())):
            if self.history.item(row).data(Qt.UserRole) in gone:
                self.history.takeItem(row)
        self.images = [p for p in self.images if p not in gone]
        self.library_panel.drop(paths)   # 消した絵だけを外す（前は一覧を作り直し、全部の絵を読み直して 1 回 8〜12 秒固まった）
        self._trash_changed()
        self.notify("ごみ箱へ移しました", "ok", "押すと戻します", on_click=lambda: self.restore_trash(key))
        return key

    SWEPT_KEY = "cleanup/redpen_0519"   # 前の版の赤ペンの直しを見終えた出力の置き場（利用者の設定。2 度目からは読まない）

    def sweep_old_redpen(self):
        """0.5.19 までの版は、赤ペンの直しの結果（直した所のほかは透明な絵）を出力の置き場に書き、履歴とライブラリーに足していた。
        レイヤーを消してもその絵が残り、履歴・ライブラリーから押すと透明な絵が出て、ゴミに見えた。
        その絵を履歴・ライブラリーから外し、ファイルは消さずにごみ箱へ移す（本当に消すのは利用者がごみ箱で選んだときだけ）"""
        if getattr(self, "_io_closed", False):
            return
        from atelier.files import redpen_clean as redpenclean
        roots = []
        # 試験（描く仕組みを渡したとき）は、その出力の置き場だけを見る（利用者の本物の置き場に触らない）
        own = getattr(self, "_own_studio", True)
        for r in (getattr(self.studio, "out", None), self.settings.get("output_dir") if own else None):
            if r and str(Path(r).resolve()) not in [str(Path(x).resolve()) for x in roots]:
                roots.append(r)
        done_roots = set(filter(None, str(self.settings.store.value(self.SWEPT_KEY) or "").split("\n")))
        todo = [r for r in roots if str(Path(r).resolve()) not in done_roots]
        dropped = list(getattr(self.library, "dropped_redpen", []))
        self.library.dropped_redpen = []
        if not todo and not dropped:
            return

        def work():
            found = [str(p) for p in redpenclean.old_redpen_files(todo)]
            return found + [p for p in dropped if p not in found and Path(p).is_file()]

        def done(found):
            if isinstance(found, BaseException):
                return
            self.settings.store.setValue(self.SWEPT_KEY, "\n".join(sorted(done_roots | {str(Path(r).resolve()) for r in todo})))
            if not found:
                return
            items = self.library.take(found)
            try:
                self.trash.put(found, items, label="前の版の赤ペンの直し")
            except OSError:
                self.library.put_back(items)
                return
            gone = set(found)
            for row in reversed(range(self.history.count())):
                if self.history.item(row).data(Qt.UserRole) in gone:
                    self.history.takeItem(row)
            self.images = [p for p in self.images if p not in gone]
            self.library_panel.refresh()
            self._trash_changed()
            self.statusBar().showMessage(f"前の版の赤ペンの直しの絵 {len(found)} 枚を、履歴とライブラリーから外してごみ箱へ移しました", 8000)
        self.run_io(work, done, "前の版の赤ペンの直しを片付け")

    def trash_layer_file(self, path: str):
        """AI の結果のレイヤーを消したら、その画像ファイルもごみ箱へ移し、履歴とライブラリーから外す（聞かない。ごみ箱から戻せる）。
        今の絵そのもの（作業の土台の絵）と、出力の置き場の外のファイル（手元の絵・仮の置き場）には触らない"""
        p = Path(path)
        if not p.is_file() or str(p) == str(getattr(self, "work_key", "") or "") or str(p) == str(getattr(self, "source_path", "") or ""):
            return
        roots = [Path(r).resolve() for r in (getattr(self.studio, "out", None), self.settings.get("output_dir")) if r]
        if not any(str(p.resolve()).startswith(str(r) + os.sep) for r in roots):
            return
        items = self.library.take([str(p)])
        try:
            key = self.trash.put([str(p)], items, label="消したレイヤーの絵")
        except OSError as e:
            self.library.put_back(items)
            self.notify("レイヤーの絵をごみ箱へ移せませんでした", "error", str(e))
            return
        for row in reversed(range(self.history.count())):
            if self.history.item(row).data(Qt.UserRole) == str(p):
                self.history.takeItem(row)
        self.images = [x for x in self.images if x != str(p)]
        self.library_panel.drop([str(p)])
        self._trash_changed()
        if key:
            self.statusBar().showMessage("消したレイヤーの絵をごみ箱へ移しました（「ファイル」→「ごみ箱…」から戻せます）", 8000)

    def restore_trash(self, key: str) -> bool:
        """ごみ箱から元の場所へ戻し、履歴とライブラリーにも戻す"""
        m = self.trash.restore(key)
        if m is None:
            return False
        if m.get("library"):
            self.library.put_back(m["library"])
            self.library_panel.refresh()
        for p in m["images"]:
            if Path(p).exists() and not any(it.get("kind") == "doc" and it["path"] == p for it in m.get("library", [])):
                self.activity.add(p, "")
                if p not in self.images:
                    self.images.append(p)
        self.statusBar().showMessage("ごみ箱から戻しました", 4000)
        self._trash_changed()
        return True

    def _trash_changed(self):
        """ごみ箱の画面を開いたままなら並べ直す"""
        dlg = getattr(self, "_trash_dialog", None)
        if dlg is not None and dlg.isVisible() and not getattr(dlg, "_filling", False):
            dlg._filling = True
            try:
                dlg.fill()
            finally:
                dlg._filling = False

    def open_trash(self):
        from atelier.files.trash import open_dialog
        open_dialog(self)

    def _prompt_text(self, path: str) -> str:
        from atelier.ai import finishers
        return str(finishers.sidecar(path).get("text", ""))

    def _prompt_from(self, path: str, pin: bool = False):
        text = self._prompt_text(path)
        if not text:
            self.notify("頼みの言葉が残っていません", "info", "この絵の .json がありません")
            return
        self.entry.setText(text)
        if pin:
            self.pin_prompt(text)

    def _need_selection(self) -> bool:
        if self.canvas.selection is None:
            self.notify("選択範囲がありません", "info", "四角・投げなわ・多角形の選択で範囲を選んでから使ってください")
            return False
        return True

    def selection_clear(self):
        if self._need_selection():
            self.canvas.clear_selection_area()
            self.statusBar().showMessage("選択範囲の中を消しました（Ctrl+Z で戻せます）", 3000)

    def selection_fill(self):
        if self._need_selection() and self.canvas.fill_selection():
            self.statusBar().showMessage("選択範囲を塗りました（Ctrl+Z で戻せます）", 3000)

    def selection_copy(self) -> bool:
        """選択があればその中を、無ければ見えている絵全体をコピーする"""
        from PySide6.QtWidgets import QApplication
        img = self.canvas.selection_image()
        if img is None:
            self.copy_image()
            self._copied_at = None
            return True
        QApplication.clipboard().setImage(img)
        self._copied_at = self.canvas.selection.topLeft()   # 「同じ位置に貼り付け」で使う
        self.statusBar().showMessage("選択範囲をコピーしました", 3000)
        return True

    def selection_cut(self):
        if not self._need_selection():
            return
        from PySide6.QtWidgets import QApplication
        if not self.canvas.editable():
            return   # ロックした・隠したレイヤーは切り取らない（前はロックしたレイヤーの絵が消えた）
        QApplication.clipboard().setImage(self.canvas.selection_image())
        self._copied_at = self.canvas.selection.topLeft()
        self.canvas.clear_selection_area()
        self.statusBar().showMessage("選択範囲を切り取りました（Ctrl+Z で戻せます）", 3000)

    def paste_clipboard(self):
        """コピーした絵を一番上の新しいレイヤーに貼る（利用者が気づけるよう、貼ったレイヤーを選んだ状態にする）"""
        from PySide6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            self.notify("貼り付ける絵がありません", "info", "絵をコピーしてから貼り付けてください")
            return
        if not self.canvas.layers:
            self.canvas.new_canvas(img.width(), img.height())
        if self.canvas.paste_image(img):
            self.statusBar().showMessage("一番上の新しいレイヤーに貼りました（Ctrl+Z で戻せます）", 3000)

    def layer_copy(self):
        from PySide6.QtWidgets import QApplication
        layer = self.canvas.copy_layer()
        if layer is not None:
            QApplication.clipboard().setImage(layer.image)   # ほかのアプリにも絵として貼れるようにする
            self._copied_at = None
            self.statusBar().showMessage(f"レイヤー「{layer.name}」をコピーしました", 3000)

    def layer_cut(self):
        from PySide6.QtWidgets import QApplication
        layer = self.canvas.cut_layer()
        if layer is not None:
            QApplication.clipboard().setImage(layer.image)
            self.statusBar().showMessage(f"レイヤー「{layer.name}」を切り取りました（Ctrl+Z で戻せます）", 3000)

    def layer_paste(self):
        if self.canvas.copied_layer is None:
            self.notify("貼り付けるレイヤーがありません", "info", "「レイヤーをコピー」か「レイヤーを切り取り」をしてから貼り付けてください")
            return
        if self.canvas.paste_layer():
            self.statusBar().showMessage("レイヤーを貼り付けました（Ctrl+Z で戻せます）", 3000)

    def copy_merged(self):
        from PySide6.QtWidgets import QApplication
        if not self.canvas.layers:
            return
        QApplication.clipboard().setImage(self.canvas.merged_image())
        sel = self.canvas.selection
        self._copied_at = sel.topLeft() if sel is not None else None
        self.statusBar().showMessage("見えている絵を結合してコピーしました", 3000)

    def paste_in_place(self):
        """コピーした所と同じ位置に貼る。位置の分からない絵（ほかのアプリでコピーした絵）は左上に貼る"""
        from PySide6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            self.notify("貼り付ける絵がありません", "info", "絵をコピーしてから貼り付けてください")
            return
        if not self.canvas.layers:
            self.canvas.new_canvas(img.width(), img.height())
        from PySide6.QtCore import QPoint
        at = getattr(self, "_copied_at", None)
        if self.canvas.paste_image(img, "貼り付け", at if at is not None else QPoint(0, 0)):
            self.statusBar().showMessage("同じ位置の新しいレイヤーに貼りました（Ctrl+Z で戻せます）", 3000)

    def build_symmetry_menu(self, menu):
        """表示のメニューの「対称定規」。ブラシの設定の「対称」と同じ設定を、どの道具からでも切り替えられるようにする"""
        from PySide6.QtGui import QActionGroup
        from atelier.paint.canvas import SYMMETRY
        group = QActionGroup(menu)
        self.symmetry_actions = {}
        for key, label in (("", "なし"),) + tuple(SYMMETRY.items()):
            a = QAction(label, menu, checkable=True)
            a.setToolTip("描いた線と図形を、軸の反対側にも同時に描きます" if key else "対称を切ります")
            a.triggered.connect(lambda _=False, k=key: self.symmetry.setCurrentIndex(self.symmetry.findData(k)))
            group.addAction(a)
            menu.addAction(a)
            self.symmetry_actions[key] = a
        self.symmetry_actions[""].setChecked(True)
        menu.addSeparator()
        menu.addAction(QAction("軸を真ん中に戻す", menu, triggered=lambda: self.canvas.set_axis_center(None),
                               toolTip="対称の軸を絵の真ん中に戻します"))
        self.canvas.view_changed.connect(lambda: self.symmetry_actions[self.canvas.symmetry].setChecked(True))

    def build_ruler_menu(self, menu):
        """表示のメニューの「定規」と「形を整える」。ブラシの設定の「定規」「描いて止めると形を整える」と同じ設定"""
        from PySide6.QtGui import QActionGroup
        from atelier.paint.drawing_assist import RULERS
        menu.setToolTipsVisible(True)
        group = QActionGroup(menu)
        self.ruler_actions = {}
        for key, label in (("", "なし"),) + tuple(RULERS.items()):
            a = QAction(label, menu, checkable=True)
            a.setToolTip("なぞる線と直線を、この定規に沿わせます" if key else "定規を切ります")
            a.triggered.connect(lambda _=False, k=key: self.ruler.setCurrentIndex(self.ruler.findData(k)))
            group.addAction(a)
            menu.addAction(a)
            self.ruler_actions[key] = a
        self.ruler_actions[""].setChecked(True)
        menu.addSeparator()
        menu.addAction(QAction("定規の点を初めの所に戻す", menu, triggered=lambda: self.canvas.set_ruler_point(0, None),
                               toolTip="定規の中心・消失点・平行線の向きを、初めの所に戻します"))
        self.quickshape_action = QAction("描いて止めると形を整える", menu, checkable=True,
                                         toolTip="ペンで描き終えて少し止めると、直線・円・楕円・四角・三角に整えます")
        self.quickshape_action.toggled.connect(self.quickshape.setChecked)
        self.quickshape.toggled.connect(self.quickshape_action.setChecked)
        menu.addAction(self.quickshape_action)
        self.canvas.view_changed.connect(lambda: self.ruler_actions[self.canvas.ruler].setChecked(True))
        self.canvas.shaped.connect(lambda name: self.statusBar().showMessage(f"{name}に整えました（元に戻すで整える前の線に戻ります）", 4000))

    def copy_image(self, path: str | None = None):
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setImage(QImage(path) if path else self.canvas.flatten())
        self.statusBar().showMessage("絵をコピーしました", 3000)

    def open_crashlog(self):
        """落ちたときの記録（crash.log）を開く。無ければ無いと知らせる"""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from atelier.app import crash_log as crashlog
        p = crashlog.path()
        if not p.exists():
            self.notify("落ちた記録はありません", "info", str(p))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def open_folder(self, path: str):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
