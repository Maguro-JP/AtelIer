"""拡張の登録口。本体（atelier/）に、外の部品がメニュー・モード・欄・ファイルの種類を足すための入口。

本体は拡張の中身を知らない。拡張は `name` と `attach(window)` を持つ物で、窓ができたあとに 1 回ずつ呼ばれ、
窓の公開している口（メニューバー、`file_menu` と `file_extension_anchor`、`studio_hooks`、`expression_sources`、
`add_mode`、ライブラリーの欄の `tabs` と `refresh_hooks`）に自分の物を足す。
依存の向きは「拡張 → 本体」だけにする。本体が拡張を読むと、拡張を別のリポジトリへ移せなくなる。

拡張は別のパッケージに置き、entry points の `atelier.extensions` の組に拡張の物（かそのクラス）を書いて入れる。
キャラクターデザインは CharacterDesigner のリポジトリの `character_designer` パッケージで、この形で入る。
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Protocol, runtime_checkable

GROUP = "atelier.extensions"                       # entry points の組の名前
NO_BUNDLED_ENV = "ATELIER_NO_BUNDLED_EXTENSIONS"   # 1 にすると同梱の拡張を読まない（本体だけで動くかを確かめる）
# 同梱の拡張（モジュールの名前を文字で持つ）。いまは無い。キャラクターデザインは CharacterDesigner へ移り、entry points で入る。
# 口は残す: 配る版に拡張を同梱したくなったとき、本体のほかの所を直さずに足せるようにするため
BUNDLED: tuple[str, ...] = ()


@runtime_checkable
class Extension(Protocol):
    """拡張の形。`unload()` を持っていれば、登録を外すときに呼ぶ（モードなど、窓の外に足した物を戻すため）"""

    name: str

    def attach(self, window) -> None: ...


_registered: list[Extension] = []
_bundled_loaded = False
# 置き場から読めた拡張の見せ方（タイルの画面が読む）。名前 → {"title", "tagline", "image", "folder", "dropin"}
_dropin_info: dict[str, dict] = {}


def _warn(what: str) -> None:
    """拡張 1 つの失敗で本体を止めない。理由は捨てずに stderr へ出す"""
    print(f"[extensions] {what}\n{traceback.format_exc()}", file=sys.stderr)


def register(extension: Extension) -> None:
    """拡張を足す。同じ名前の拡張があれば入れ替える（同梱と entry points の両方から同じ物が来ても 2 回付けない）"""
    for old in [e for e in _registered if e is extension or e.name == extension.name]:
        _registered.remove(old)
    _registered.append(extension)


def unregister(extension: Extension) -> None:
    """拡張を外す。次に作る窓から付かない。すでに開いている窓からは外さない"""
    if extension in _registered:
        _registered.remove(extension)
        unload = getattr(extension, "unload", None)
        if callable(unload):
            unload()


def registered() -> tuple[Extension, ...]:
    return tuple(_registered)


def load_bundled(again: bool = False) -> None:
    """同梱の拡張を 1 回だけ登録する。外した拡張を次の窓で勝手に戻さないよう、2 回目からは何もしない（again で読み直す）"""
    global _bundled_loaded
    if os.environ.get(NO_BUNDLED_ENV, "") == "1" or (_bundled_loaded and not again):
        return
    _bundled_loaded = True
    import importlib
    for module in BUNDLED:
        try:
            register(importlib.import_module(module).EXTENSION)
        except ImportError:
            pass   # 同梱の拡張が無い配り方（本体だけ）でも動く
        except Exception:   # noqa: BLE001
            _warn(f"同梱の拡張 {module} を読めませんでした")


def load_entry_points() -> list[str]:
    """入っているパッケージの拡張（entry points）を登録する。返すのは登録した拡張の名前"""
    from importlib.metadata import entry_points
    names = []
    try:
        found = list(entry_points(group=GROUP))
    except Exception:   # noqa: BLE001  パッケージの情報が壊れていても起動は続ける
        _warn("拡張の一覧を読めませんでした")
        return names
    for point in found:
        try:
            extension = point.load()
            if isinstance(extension, type):
                extension = extension()
            if not isinstance(extension, Extension):
                raise TypeError(f"{point.value} は name と attach(window) を持っていません")
            register(extension)
            names.append(extension.name)
        except Exception:   # noqa: BLE001  1 つの拡張の失敗で、ほかの拡張と本体を止めない
            _warn(f"拡張 {point.name} を読めませんでした")
    return names


MANIFEST = "extension.json"   # 拡張の置き場の 1 つの拡張の印: {"module": "...", "attr": "EXTENSION", "path": "."}


def load_dropins(root) -> list[str]:
    """拡張の置き場（C:\\ProgramData\\AtelIer\\extensions\\<名前>\\）の拡張を登録する。
    ほかのアプリのインストーラーは AtelIer の Python に pip で入れられないので、ここへパッケージを置く。
    <名前>（か extension.json の path）を sys.path の後ろに足し、module の attr を読む。返すのは登録した拡張の名前"""
    import importlib
    import json
    from pathlib import Path
    names: list[str] = []
    root = Path(root)
    if not root.is_dir():
        return names
    for folder in sorted(p for p in root.iterdir() if (p / MANIFEST).is_file()):
        try:
            spec = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
            where = str((folder / spec.get("path", ".")).resolve())
            if where not in sys.path:
                # 後ろに足す。拡張に AtelIer と同じ名前の物（tools/gen の台本など）があっても、AtelIer の物を先に読む
                sys.path.append(where)
            extension = getattr(importlib.import_module(spec["module"]), spec.get("attr", "EXTENSION"))
            if isinstance(extension, type):
                extension = extension()
            if not isinstance(extension, Extension):
                raise TypeError(f"{spec['module']} は name と attach(window) を持っていません")
            register(extension)
            names.append(extension.name)
            image = spec.get("image")
            _dropin_info[extension.name] = {
                "title": str(spec.get("title") or extension.name), "tagline": str(spec.get("tagline") or ""),
                "image": str((folder / image).resolve()) if image else "", "folder": str(folder), "dropin": folder.name}
        except Exception:   # noqa: BLE001  1 つの拡張の失敗で、ほかの拡張と本体を止めない
            _warn(f"拡張の置き場の {folder.name} を読めませんでした")
    return names


def dropin_info(name: str) -> dict:
    """置き場の extension.json に書かれた見せ方（title・tagline・image）。置き場から読んでいない拡張は空"""
    return dict(_dropin_info.get(name, {}))


def _parts(window) -> dict:
    """拡張を付ける前と後で比べるための、窓の目に見える部品（メニュー・欄・モード）"""
    from PySide6.QtWidgets import QDockWidget
    bar = window.menuBar() if hasattr(window, "menuBar") else None
    # QAction.menu() は呼ばない。PySide6 6.9 では呼ぶと別の包みが作られ、窓が持っていたメニューが「消えた」扱いになり、
    # 拡張を入れた Windows の AtelIer が窓を作る途中で落ちた（i18n.translate_menus と同じ避け方）。見出しの操作からメニューを引く
    from PySide6.QtWidgets import QApplication, QMenu
    subs = {m.menuAction(): m for m in QApplication.allWidgets() if isinstance(m, QMenu)}
    return {"menus": [subs[a] for a in bar.actions() if a in subs] if bar is not None else [],
            "docks": window.findChildren(QDockWidget) if hasattr(window, "findChildren") else [],
            "modes": list(getattr(window, "mode_actions", {}) or {})}


def attach_all(window) -> None:
    """登録した拡張を、窓に 1 つずつ付ける。窓のメニューと欄を作り終えたあとに呼ぶ。
    付けた前後で増えたメニュー・欄・モードを window.extension_parts に覚える。タイルの画面がデザイナーに入るとき、
    拡張に open(window) が無ければ、ここで覚えた物を開く（拡張にどの物が自分の入口かを書かせなくて済む）"""
    load_bundled()
    parts = getattr(window, "extension_parts", None)
    if parts is None:
        parts = {}
        try:
            window.extension_parts = parts
        except Exception:   # noqa: BLE001  属性を持てない窓（試験の見本）でも付ける
            parts = {}
    for extension in registered():
        try:
            before = _parts(window)
        except Exception:   # noqa: BLE001
            before = {"menus": [], "docks": [], "modes": []}
        try:
            extension.attach(window)
        except Exception:   # noqa: BLE001  拡張が付かなくても、本体の窓は開く
            _warn(f"拡張 {extension.name} を窓に付けられませんでした")
            continue
        try:
            after = _parts(window)
            parts[extension.name] = {k: [x for x in after[k] if x not in before[k]] for k in after}
        except Exception:   # noqa: BLE001
            pass
