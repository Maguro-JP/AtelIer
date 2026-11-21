"""アプリを起動する。

  python -m atelier [--open <作業ファイルか絵>]
"""
from __future__ import annotations

import sys


def apply_theme(app):
    """前に選んだテーマの色を当てる（初めはナイト: 暗い灰色の地に赤とオレンジの差し色）"""
    from PySide6.QtCore import QSettings
    from atelier.app.main_window import APPLICATION, ORGANIZATION
    from atelier.ui import themes
    store = QSettings(ORGANIZATION, APPLICATION)
    themes.load_custom(store)
    return themes.apply(app, store.value("theme", themes.DEFAULT))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    from atelier.app import crash_log
    crash_log.install()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    app = QApplication(argv)
    from atelier.ui import logo, type_guard, wheel_guard, window_fit
    app.setApplicationName(logo.NAME)
    app.setWindowIcon(QIcon(str(logo.ICON_SVG)))
    apply_theme(app)
    window_fit.install(app)
    wheel_guard.install()   # 欄のスクロールで数が変わらないようにする
    type_guard.install()    # 打っている欄のキーをショートカットに取られないようにする
    from atelier.app.main_window import MainWindow
    w = MainWindow()
    w.show()
    opened = argv[argv.index("--open") + 1] if "--open" in argv[:-1] else None
    if opened:
        w.open_path(opened)
    else:
        w.offer_restore()
    app.aboutToQuit.connect(lambda: (w.store.setValue("running", 0), w.store.sync()))
    return app.exec()
