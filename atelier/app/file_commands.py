"""ファイルの操作（開く・保存・書き出し・自動保存）。窓（MainWindow）に混ぜて使う。"""
from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from atelier.files import project_file

IMAGE_FILTER = "画像 (*.png *.jpg *.jpeg *.webp)"
AUTOSAVE_MS = 120_000   # 変わってから 2 分ごとに書く


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


class FileCommands:
    project_path: str | None = None   # 今の絵の作業ファイル。無ければ、保存のときに置き場を聞く
    dirty = False                     # 保存していない変更があるか

    # ---- 開く ----
    def open_image(self):
        suffixes = " ".join(f"*{s}" for s in project_file.READABLE)
        path, _ = QFileDialog.getOpenFileName(self, "開く", "", f"作業ファイルと画像 ({suffixes} *.png *.jpg *.jpeg *.webp)")
        if path:
            self.open_path(path)

    def open_path(self, path: str, restore: bool = False) -> bool:
        """作業ファイルか絵を開く。restore は自動保存から戻すとき（自動保存の場所に上書き保存させない）"""
        try:
            if str(path).endswith(project_file.READABLE):
                project_file.load(self.canvas, path)
                own = str(path).endswith(project_file.SUFFIX) and not restore
                self.project_path = str(path) if own else None   # 前の形（.cdproj）と自動保存は、保存のときに置き場を聞く
            else:
                self.canvas.show_image(str(path))
                self.project_path = None
        except (OSError, ValueError, KeyError) as e:
            self.notify_error("開けませんでした", f"{path}\n{e}")
            return False
        self.dirty = restore
        return True

    def import_layer(self):
        path, _ = QFileDialog.getOpenFileName(self, "画像をレイヤーとして読み込む", "", IMAGE_FILTER)
        if not path:
            return
        try:
            self.canvas.add_image_layer(path, Path(path).stem)
        except ValueError as e:
            self.notify_error("絵を重ねられません", str(e))

    # ---- 保存 ----
    def save_project(self, ask: bool = False) -> bool:
        """作業ファイル（レイヤーごと）に保存する。初めてか ask なら置き場を聞く。保存できたら True"""
        path = self.project_path
        if ask or not path:
            path, _ = QFileDialog.getSaveFileName(self, "作業ファイルを保存", "drawing" + project_file.SUFFIX,
                                                  f"作業ファイル (*{project_file.SUFFIX})")
            if not path:
                return False
            if not path.endswith(project_file.SUFFIX):
                path += project_file.SUFFIX
        try:
            project_file.save(self.canvas, path)
        except OSError as e:
            self.notify_error("保存できませんでした", f"{e}\n保存先に書き込めるか、ディスクに空きがあるかを確かめてください")
            return False
        self.project_path, self.dirty = path, False
        self.notify(f"保存しました: {Path(path).name}")
        return True

    def export_png(self) -> bool:
        """見えているレイヤーを重ねた 1 枚を PNG に書き出す"""
        if not self.canvas.layers:
            return False
        dst, _ = QFileDialog.getSaveFileName(self, "PNG で書き出す", "drawing.png", "PNG (*.png)")
        if not dst:
            return False
        if not self.canvas.flatten().save(dst, "PNG"):
            self.notify_error("書き出せませんでした", f"{dst}\n書き出す先に書き込めるかを確かめてください")
            return False
        self.notify(f"書き出しました: {Path(dst).name}")
        return True

    def export_psd(self) -> bool:
        dst, _ = QFileDialog.getSaveFileName(self, "PSD で書き出す", "drawing.psd", "PSD (*.psd)")
        if not dst:
            return False
        try:
            project_file.export_psd(self.canvas, dst)
        except OSError as e:
            self.notify_error("書き出せませんでした", f"{e}\n書き出す先に書き込めるかを確かめてください")
            return False
        self.notify(f"書き出しました: {Path(dst).name}（レイヤー {len(self.canvas.layers)} 枚）")
        return True

    def save_layer_png(self, path: str | None = None) -> str:
        """選んでいるレイヤーだけを、透明を残したまま PNG で保存する"""
        c = self.canvas
        if not c.layers:
            return ""
        layer = c.layers[c.current]
        if not isinstance(path, (str, Path)):   # メニューからは triggered の真偽（False）が来る
            path, _ = QFileDialog.getSaveFileName(self, "レイヤーを PNG で保存", f"{layer.name}.png", "PNG (*.png)")
            if not path:
                return ""
        if not layer.image.save(str(path), "PNG"):
            self.notify_error("レイヤーを保存できませんでした", f"{path}\n保存先に書き込めるかを確かめて、別の場所を選び直してください")
            return ""
        self.notify(f"{layer.name} を保存しました: {path}")
        return str(path)

    def export_layers_png(self, folder: str | None = None) -> list[str]:
        """全部のレイヤーを 1 枚ずつ PNG で書き出す。名前は下からの番号と名前（並びが分かり、同じ名前でも上書きしない）"""
        c = self.canvas
        if not c.layers:
            return []
        if not isinstance(folder, (str, Path)):
            folder = QFileDialog.getExistingDirectory(self, "レイヤーを書き出すディレクトリ")
            if not folder:
                return []
        out = []
        for i, layer in enumerate(c.layers, 1):
            safe = re.sub(r'[\\/:*?"<>|]', "_", layer.name).strip() or "layer"
            path = str(Path(folder) / f"{i:02d}-{safe}.png")
            if layer.image.save(path, "PNG"):
                out.append(path)
        self.notify(f"{len(out)} 枚のレイヤーを書き出しました: {folder}")
        return out

    # ---- 自動保存 ----
    def autosave(self) -> bool:
        """変わっていれば、決まった置き場に作業ファイルを書く。落ちたときに次の起動で戻せるように"""
        if not self.dirty or not self.canvas.layers:
            return False
        path = project_file.autosave_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            project_file.save(self.canvas, path)
        except OSError:
            return False   # 自動保存が書けなくても、描く邪魔はしない
        return True

    def offer_restore(self) -> bool:
        """前に閉じずに終わっていて、自動保存が残っていれば、戻すかを聞く（自動保存は消さない）"""
        try:
            before = int(self.store.value("running", 0) or 0)
        except (TypeError, ValueError):
            before = 0
        crashed = bool(before) and before != os.getpid() and not pid_alive(before)
        self.store.setValue("running", os.getpid())
        path = project_file.autosave_path()
        if not crashed or not path.exists():
            return False
        answer = self.ask_choice("前の絵を戻す", "前回は正しく閉じられませんでした。自動保存した絵を開きますか。",
                                 (("open", "開く", QMessageBox.AcceptRole), ("skip", "開かない", QMessageBox.RejectRole)))
        return answer == "open" and self.open_path(str(path), restore=True)

    def confirm_close(self) -> bool:
        """保存していない変更があれば、閉じる前に聞く。閉じてよければ True"""
        if not self.dirty or not self.isVisible():
            return True
        answer = self.ask_choice("閉じる前に", "作業ファイルに保存していない変更があります。保存しますか。",
                                 (("save", "保存", QMessageBox.AcceptRole), ("drop", "保存しない", QMessageBox.DestructiveRole),
                                  ("cancel", "やめる", QMessageBox.RejectRole)))
        if answer == "save":
            return self.save_project()
        return answer == "drop"

    def ask_choice(self, title: str, text: str, choices) -> str | None:
        """ボタンで選ばせる窓を出し、選んだボタンの鍵を返す。choices は（鍵, 見出し, 役目）の並び。窓を閉じたら None"""
        box = QMessageBox(QMessageBox.Question, title, text, parent=self)
        buttons = {box.addButton(label, role): key for key, label, role in choices}
        box.exec()
        return buttons.get(box.clickedButton())
