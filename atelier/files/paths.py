"""アプリのデータ（設定・自動保存・記録）の置き場を 1 か所で決める。

描いた絵や作業ファイルは利用者が選んだ所に保存する。ここで決めるのは、アプリが自分で書く物の置き場だけ。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AtelIer"
ROOT = Path(__file__).resolve().parents[2]
WINDOWS = sys.platform == "win32"


def data_home() -> Path:
    """置き場。ATELIER_HOME > Windows の ProgramData > 開発中の .cache の順に決める"""
    if os.environ.get("ATELIER_HOME"):
        return Path(os.environ["ATELIER_HOME"])
    if WINDOWS:
        return Path(os.environ.get("ProgramData") or "C:\\ProgramData") / APP_NAME
    return ROOT / ".cache"


HOME = data_home()


def keep_broken(path: Path) -> Path | None:
    """読めないファイルを消さずに控えを残す（<名前>.broken-<日時>）。次に書くときに上書きされて失うのを避ける"""
    import shutil
    import time
    try:
        backup = path.with_name(f"{path.name}.broken-{time.strftime('%Y%m%d-%H%M%S')}")
        if not backup.exists():
            shutil.copy2(path, backup)
        return backup
    except OSError:
        return None


def read_json(path: Path, kind: type, default):
    """利用者の設定の JSON を読む。無ければ default。読めない・形が違うときは控えを残してから default を返す"""
    import json
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return default
    try:
        data = json.loads(text)
    except ValueError:
        keep_broken(path)
        return default
    if not isinstance(data, kind):
        keep_broken(path)
        return default
    return data


def write_json(path: Path, data):
    """書きかけで切れても前のファイルが残るよう、別名に書いてから置き換える"""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    part.replace(path)
