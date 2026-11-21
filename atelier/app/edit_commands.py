"""編集の操作（選択範囲・コピー・貼り付け・レイヤーのコピー）。窓（MainWindow）に混ぜて使う。"""
from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication


class EditCommands:
    _copied_at: QPoint | None = None   # コピーした所の左上（「同じ位置に貼り付け」で使う）

    def _need_selection(self) -> bool:
        if self.canvas.selection is None:
            self.notify("選択範囲がありません。四角・投げなわ・多角形の選択で範囲を選んでから使ってください")
            return False
        return True

    def selection_clear(self):
        if self._need_selection():
            self.canvas.clear_selection_area()
            self.notify("選択範囲の中を消しました（Ctrl+Z で戻せます）")

    def selection_fill(self):
        if self._need_selection() and self.canvas.fill_selection():
            self.notify("選択範囲を塗りました（Ctrl+Z で戻せます）")

    def selection_copy(self) -> bool:
        """選択があればその中を、無ければ見えている絵全体をコピーする"""
        img = self.canvas.selection_image()
        if img is None:
            QApplication.clipboard().setImage(self.canvas.flatten())
            self._copied_at = None
            self.notify("絵をコピーしました")
            return True
        QApplication.clipboard().setImage(img)
        self._copied_at = self.canvas.selection.topLeft()
        self.notify("選択範囲をコピーしました")
        return True

    def selection_cut(self):
        if not self._need_selection():
            return
        if not self.canvas.editable():
            return   # ロックした・隠したレイヤーは切り取らない
        QApplication.clipboard().setImage(self.canvas.selection_image())
        self._copied_at = self.canvas.selection.topLeft()
        self.canvas.clear_selection_area()
        self.notify("選択範囲を切り取りました（Ctrl+Z で戻せます）")

    def _clipboard_image(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            self.notify("貼り付ける絵がありません。絵をコピーしてから貼り付けてください")
            return None
        if not self.canvas.layers:
            self.canvas.new_canvas(img.width(), img.height())
        return img

    def paste_clipboard(self):
        """コピーした絵を一番上の新しいレイヤーに貼る（気づけるよう、貼ったレイヤーを選んだ状態にする）"""
        img = self._clipboard_image()
        if img is not None and self.canvas.paste_image(img):
            self.notify("一番上の新しいレイヤーに貼りました（Ctrl+Z で戻せます）")

    def paste_in_place(self):
        """コピーした所と同じ位置に貼る。位置の分からない絵（ほかのアプリでコピーした絵）は左上に貼る"""
        img = self._clipboard_image()
        at = self._copied_at if self._copied_at is not None else QPoint(0, 0)
        if img is not None and self.canvas.paste_image(img, "貼り付け", at):
            self.notify("同じ位置の新しいレイヤーに貼りました（Ctrl+Z で戻せます）")

    def copy_merged(self):
        if not self.canvas.layers:
            return
        QApplication.clipboard().setImage(self.canvas.merged_image())
        sel = self.canvas.selection
        self._copied_at = sel.topLeft() if sel is not None else None
        self.notify("見えている絵を結合してコピーしました")

    def layer_copy(self):
        layer = self.canvas.copy_layer()
        if layer is not None:
            QApplication.clipboard().setImage(layer.image)   # ほかのアプリにも絵として貼れるようにする
            self._copied_at = None
            self.notify(f"レイヤー「{layer.name}」をコピーしました")

    def layer_cut(self):
        layer = self.canvas.cut_layer()
        if layer is not None:
            QApplication.clipboard().setImage(layer.image)
            self.notify(f"レイヤー「{layer.name}」を切り取りました（Ctrl+Z で戻せます）")

    def layer_paste(self):
        if self.canvas.copied_layer is None:
            self.notify("貼り付けるレイヤーがありません。「レイヤーをコピー」か「レイヤーを切り取り」をしてから貼り付けてください")
            return
        if self.canvas.paste_layer():
            self.notify("レイヤーを貼り付けました（Ctrl+Z で戻せます）")
