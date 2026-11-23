"""拡張の置き場に入れたデザイナーが、タイトルの画面のタイルに出て、押すとその画面に入るかを確かめる（Actions の Windows の機械で流す）。

    python -E -s -m atelier.bench.extension_tile <出力の置き場> [拡張の名前]

Setup.exe で入れたアプリの Python で動かし、起動の main() と同じ順で拡張を読む（同梱 → 拡張の置き場 → entry point）。
はじめの「模型を選ぶ」などの確かめの窓は飛ばし、タイトルの画面だけを本物の窓で出す。タイルは本物のボタンを押す。
拡張の Setup が置き場に入れた物を読めているか、読めてもタイルが出ないか、押しても何も開かないかを分けて report.json に残す。
窓の写し（title.png、after.png）を残し、利用者と同じ見た目で出ているかを目で見られるようにする。
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "extension-tile-out")
    name = sys.argv[2] if len(sys.argv) > 2 else "chara"
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"extension": name, "ok": False}
    try:
        _run(out, name, report)
    except Exception:   # noqa: BLE001  落ちた所を report.json に残す
        report["error"] = traceback.format_exc()
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    return 0 if report["ok"] else 1


def _run(out: Path, name: str, report: dict) -> None:
    from PySide6.QtWidgets import QApplication

    from atelier import extensions
    from atelier.app import main_window, title_screen

    app = QApplication.instance() or QApplication(sys.argv)
    main_window.dark(app)
    root = main_window.DATA / "extensions"
    report["dropin_root"] = str(root)
    report["dropins"] = sorted(p.name for p in root.iterdir()) if root.is_dir() else []
    extensions.load_bundled()
    report["loaded"] = extensions.load_dropins(root)
    extensions.load_entry_points()
    report["dropin_info"] = extensions.dropin_info(name)
    if name not in report["loaded"]:
        report["stage"] = "置き場から読めない"
        return
    w = main_window.Window()
    w.resize(1280, 800)
    w.show()
    app.processEvents()
    report["menus"] = [a.text() for a in w.menuBar().actions()]
    seen: dict = {}

    def ask(dlg):
        dlg.show()
        for _ in range(5):
            app.processEvents()
        dlg.grab().save(str(out / "title.png"))
        buttons = [b for b in dlg.findChildren(title_screen.TileButton)]
        seen["tiles"] = [{"key": b.tile.key, "title": b.tile.title, "tagline": b.tile.tagline,
                          "image": bool(b.tile.image), "visible": b.isVisible(),
                          "width": b.width(), "height": b.height()} for b in buttons]
        mine = next((b for b in buttons if b.tile.key == "ext:" + name), None)
        if mine is None:
            return 0
        # 利用者と同じにボタンを押す（_pick が accept して exec が終わるのと同じ形にする）
        mine.click()
        app.processEvents()
        return 1 if dlg.picked == "ext:" + name else 0

    report["entered"] = title_screen.open_title(w, ask=ask)
    report["tiles"] = seen.get("tiles", [])
    if not any(t["key"] == "ext:" + name for t in report["tiles"]):
        report["stage"] = "タイルが出ない"
        return
    # モードを替えた続きの描き直しを済ませてから写す
    for _ in range(10):
        app.processEvents()
    report["mode"] = getattr(w, "app_mode", "")
    menu = getattr(w, "chara_menu", None)
    report["chara_menu"] = {"title": menu.title(), "visible": menu.menuAction().isVisible(),
                            "items": [a.text() for a in menu.actions() if a.text()]} if menu is not None else None
    w.grab().save(str(out / "after.png"))
    if menu is not None and report["chara_menu"]["items"]:
        menu.popup(w.mapToGlobal(w.menuBar().actionGeometry(menu.menuAction()).bottomLeft()))
        for _ in range(5):
            app.processEvents()
        menu.grab().save(str(out / "menu.png"))
        menu.hide()
    report["stage"] = "開いた" if report["entered"] not in ("paint", "none") else "押しても開かない"
    report["ok"] = report["stage"] == "開いた" and bool(report["chara_menu"] and report["chara_menu"]["items"])
    w.layout_store.setValue("running", 0)
    w.close()


if __name__ == "__main__":
    sys.exit(main())
