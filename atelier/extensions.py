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


def attach_all(window) -> None:
    """登録した拡張を、窓に 1 つずつ付ける。窓のメニューと欄を作り終えたあとに呼ぶ"""
    load_bundled()
    for extension in registered():
        try:
            extension.attach(window)
        except Exception:   # noqa: BLE001  拡張が付かなくても、本体の窓は開く
            _warn(f"拡張 {extension.name} を窓に付けられませんでした")
