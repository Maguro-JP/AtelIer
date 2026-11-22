"""「CharacterDesigner から引き継ぐ」窓と、「前の版が写した物の片付け」窓。

どちらも利用者が中身を見て選んでから動く。引き継ぎは選んだ組だけを写し、片付けは消す物をアプリのごみ箱へ移す
（ごみ箱の「戻す」で元の場所へ戻せる）。初めての起動では、置き場や印が見つかったときだけ 1 回出し、
「あとで」を選んだら次の起動でまた出す。メニューからはいつでも開ける。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from atelier.app import migrate

OFFER_KEY = "migrate/offer"       # "" はまだ聞いていない・あとで、"done" は引き継いだ、"never" は引き継がない
CLEANUP_KEY = "migrate/cleanup"   # 同じく片付けの窓


class ImportDialog(QDialog):
    def __init__(self, parent, src: Path, home: Path, gguf: Path):
        super().__init__(parent)
        self.src, self.home, self.gguf = src, home, gguf
        self.result_text = ""
        self.setWindowTitle("CharacterDesigner から引き継ぐ")
        lay = QVBoxLayout(self)
        head = QLabel("この機械に CharacterDesigner の置き場が見つかりました。\n引き継ぐ物を選んでください。"
                      "AtelIer に既にある物は上書きしません。CharacterDesigner の側は消しません（言葉の模型だけは共通の置き場へ移します）。")
        head.setWordWrap(True)
        lay.addWidget(head)
        sizes = migrate.survey(src)
        self.boxes: dict[str, QCheckBox] = {}
        for kind in migrate.KINDS:
            n, size = sizes[kind]
            text = f"{migrate.LABELS[kind]}　{n} 件・{migrate.human_size(size)}"
            if kind == "settings":
                text = f"{migrate.LABELS[kind]}　画面の並びとファイル {n} 件"
            box = QCheckBox(text)
            box.setChecked(kind == "settings" or n > 0)
            box.setEnabled(kind == "settings" or n > 0)
            self.boxes[kind] = box
            lay.addWidget(box)
        self.bar = QProgressBar()
        self.bar.hide()
        lay.addWidget(self.bar)
        self.status = QLabel("あとからでも「ファイル」→「ほかのアプリから引き継ぐ…」で同じ窓を開けます。")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.never = QPushButton("引き継がない")
        self.never.setToolTip("この窓を次から出しません。メニューからはいつでも開けます")
        self.later = QPushButton("あとで")
        self.later.setToolTip("今は何もしません。次の起動でもう一度聞きます")
        self.go = QPushButton("引き継ぐ")
        self.go.setDefault(True)
        row.addWidget(self.never)
        row.addStretch(1)
        row.addWidget(self.later)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.never.clicked.connect(lambda: self.done_with("never"))
        self.later.clicked.connect(lambda: self.done_with(""))
        self.go.clicked.connect(self.run)
        self.resize(560, self.sizeHint().height())

    def done_with(self, state: str):
        QSettings("AtelIer", "atelier").setValue(OFFER_KEY, state)
        self.accept() if state else self.reject()

    def run(self):
        kinds = [k for k, b in self.boxes.items() if b.isChecked()]
        if not kinds:
            self.status.setText("引き継ぐ物を 1 つ以上選んでください。")
            return
        for b in (self.go, self.later, self.never, *self.boxes.values()):
            b.setEnabled(False)
        self.bar.show()

        def progress(i, total, name):
            self.bar.setMaximum(max(total, 1))
            self.bar.setValue(i)
            self.status.setText(f"{i}/{total} 件　{name}")
            QApplication.processEvents()

        file_kinds = [k for k in kinds if k != "settings"] + (["settings"] if "settings" in kinds else [])
        counts = migrate.integrate_files(self.src, self.home, self.gguf, file_kinds, progress)
        lines = [f"{migrate.LABELS[k]}: {counts.get(k, 0)} 件" for k in kinds]
        if "settings" in kinds:
            lines.append(f"画面の設定: {migrate.integrate_settings(QSettings)} 項目")
        if counts["skipped"]:
            lines.append(f"既にあったので写さなかった物: {counts['skipped']} 件")
        if counts["failed"]:
            lines.append(f"写せなかった物: {counts['failed']} 件（記録は migrate.log）")
        if "parts" in kinds:
            import sys
            for lib in (self.home / "simple" / "lib", self.home / "gen" / "lib", self.home / "llm" / "lib"):
                if lib.exists() and str(lib) not in sys.path:
                    sys.path.insert(0, str(lib))
        self.result_text = "\n".join(lines)
        QSettings("AtelIer", "atelier").setValue(OFFER_KEY, "done")
        self.status.setText("引き継ぎました。\n" + self.result_text + "\n画面の並びは次の起動から使われます。")
        self.go.setText("閉じる")
        self.go.setEnabled(True)
        self.go.clicked.disconnect()
        self.go.clicked.connect(self.accept)


class CleanupDialog(QDialog):
    def __init__(self, parent, home: Path, trash, src: Path | None):
        super().__init__(parent)
        self.home, self.trash = home, trash
        self.setWindowTitle("前の版が CharacterDesigner から写した物の片付け")
        lay = QVBoxLayout(self)
        head = QLabel("AtelIer 0.1.1〜0.1.4 は、CharacterDesigner の置き場を丸ごと AtelIer の置き場へ写していました。"
                      "下の物は AtelIer が使わない物です。消す物に印を付けて「ごみ箱へ移す」を押してください。\n"
                      "消した物はすぐには消えず、AtelIer のごみ箱（「ファイル」→「ごみ箱…」）に入ります。"
                      "要る物だったときは、ごみ箱で選んで「戻す」を押せば元の場所へ戻ります。"
                      "設定・★・描く部品など AtelIer が使っている物は、一覧に出さず消しません。")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["消す物", "大きさ", "理由"])
        self.tree.setRootIsDecorated(False)
        total = 0
        for path, size, why in migrate.cleanup_candidates(home, src):
            it = QTreeWidgetItem([path.name, migrate.human_size(size), why])
            it.setCheckState(0, Qt.Checked)
            it.setData(0, Qt.UserRole, str(path))
            it.setToolTip(0, str(path))
            self.tree.addTopLevelItem(it)
            total += size
        for c in range(3):
            self.tree.resizeColumnToContents(c)
        lay.addWidget(self.tree)
        self.status = QLabel(f"{self.tree.topLevelItemCount()} 件、あわせて {migrate.human_size(total)}"
                             if self.tree.topLevelItemCount() else "片付ける物は見つかりませんでした。")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        later = QPushButton("あとで")
        later.setToolTip("今は何もしません。次の起動でもう一度出します")
        keep = QPushButton("消さずに残す")
        keep.setToolTip("何も消さず、この窓を次から出しません。「ヘルプ」のメニューからはいつでも開けます")
        self.go = QPushButton("ごみ箱へ移す")
        self.go.setEnabled(self.tree.topLevelItemCount() > 0)
        row.addWidget(keep)
        row.addStretch(1)
        row.addWidget(later)
        row.addWidget(self.go)
        lay.addLayout(row)
        later.clicked.connect(self.reject)
        keep.clicked.connect(lambda: (QSettings("AtelIer", "atelier").setValue(CLEANUP_KEY, "done"), self.accept()))
        self.go.clicked.connect(self.run)
        self.resize(760, 420)

    def run(self):
        paths = [self.tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(self.tree.topLevelItemCount())
                 if self.tree.topLevelItem(i).checkState(0) == Qt.Checked]
        if not paths:
            self.status.setText("消す物に印を付けてください。")
            return
        key = self.trash.put(paths, label="CharacterDesigner から写した物の片付け")
        QSettings("AtelIer", "atelier").setValue(CLEANUP_KEY, "done")
        QMessageBox.information(self, self.windowTitle(),
                                f"{len(paths)} 件をごみ箱へ移しました。\n戻すときは「ファイル」→「ごみ箱…」で選んで「戻す」を押してください。"
                                if key else "移せる物がありませんでした。")
        self.accept()


def open_import(w) -> None:
    from atelier.files.paths import GGUF, HOME
    src = migrate.source_home()
    if src is None:
        QMessageBox.information(w, "ほかのアプリから引き継ぐ", "この機械には CharacterDesigner の置き場が見つかりませんでした。")
        return
    ImportDialog(w, src, HOME, GGUF).exec()


def open_cleanup(w) -> None:
    from atelier.files.paths import HOME
    CleanupDialog(w, HOME, w.trash, migrate.source_home()).exec()


def offer_on_start(w) -> None:
    """初めての起動で、見つかったときだけ窓を出す。片付けを先に出す（写しすぎた物を引き継ぎの前に見せる）"""
    from atelier.files.paths import HOME
    store = QSettings("AtelIer", "atelier")
    if migrate.was_bulk_copied(HOME) and not store.value(CLEANUP_KEY, "") and migrate.cleanup_candidates(HOME, migrate.source_home()):
        open_cleanup(w)
    if migrate.source_home() is not None and not store.value(OFFER_KEY, "") and not migrate.was_bulk_copied(HOME):
        open_import(w)
