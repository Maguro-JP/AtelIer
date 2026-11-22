"""CharacterDesigner から AtelIer へ、利用者のファイルと設定を 1 回だけ引き継いで統合する。

AtelIer は動くときに CharacterDesigner の置き場や設定を読まない（2 つのアプリを別の物にする）。
そのかわり、CharacterDesigner を使っていた人が AtelIer を入れたときに、次を AtelIer の置き場へ写して統合する。
- データの置き場の中身（設定のファイル、★・非表示・学んだ基準、ライブラリー、記録、描く部品）: C:\\ProgramData\\AtelIer へ写す
  CharacterDesigner の前の版がずれて書いた「cd」の下の物も、cd を作らずに同じ所へ合わせる
- 言葉の模型（.gguf）: 写さずに、自作アプリ共通の置き場（C:\\LLM\\gguf）へ移す（数 GB を 2 か所に持たない。CharacterDesigner も共通の置き場を読む）
- 画面の設定（QSettings）: AtelIer の設定へ写す
AtelIer の側に既にある物は上書きしない。CharacterDesigner を使っていない人には何もしない（初めて入れた人の置き場は空のまま）。
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

SOURCE_APP = "CharacterDesigner"
DONE = "integrated-from-CharacterDesigner.txt"   # 統合済みの印（AtelIer のデータの置き場の下）。2 回目からは何もしない
STRAY = "cd"                                     # CharacterDesigner の前の版が設定をずれて書いた所
MODELS = (".gguf",)
SKIP = (".part", ".lock")                        # 取りかけの物は写さない


def source_home() -> Path | None:
    """CharacterDesigner のデータの置き場。統合のときだけ読む。無ければ None"""
    if os.environ.get("CD_HOME"):
        d = Path(os.environ["CD_HOME"])
    elif os.name == "nt":
        d = Path(os.environ.get("ProgramData") or "C:\\ProgramData") / SOURCE_APP
    else:
        return None
    return d if d.is_dir() else None


def _target(rel: Path) -> Path:
    """cd の下の物は cd を外した所へ合わせる"""
    parts = rel.parts
    return Path(*parts[1:]) if parts and parts[0] == STRAY else rel


def integrate_files(src: Path, dst: Path, gguf: Path) -> list[str]:
    """src（CharacterDesigner の置き場）の中身を dst（AtelIer の置き場）へ写し、言葉の模型は gguf へ移す。返すのは記録の行"""
    log = [time.strftime("%Y-%m-%d %H:%M:%S"), f"CharacterDesigner から統合する: {src} -> {dst}"]
    copied = moved = skipped = failed = 0
    # cd の外の物を先に写す（cd の下は前の版がずれて書いた古い写しなので、同じ名前があれば外の物を残す）
    files = sorted((p for p in src.rglob("*") if p.is_file()), key=lambda p: p.relative_to(src).parts[:1] == (STRAY,))
    for path in files:
        if path.name == DONE or path.suffix.lower() in SKIP:
            continue
        try:
            if path.suffix.lower() in MODELS:
                if path.is_symlink():
                    continue
                target = gguf / path.name
                if target.exists():
                    skipped += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target))
                moved += 1
                continue
            target = dst / _target(path.relative_to(src))
            if target.exists():
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
        except OSError as e:
            failed += 1
            log.append(f"統合できなかった: {path} ({e})")
    log.append(f"写した {copied} 件、模型を移した {moved} 件、既にあった {skipped} 件、できなかった {failed} 件")
    if failed == 0:
        dst.mkdir(parents=True, exist_ok=True)
        (dst / DONE).write_text("\n".join(log) + "\n", encoding="utf-8")
    return log


def integrate_settings(QSettings) -> int:
    """CharacterDesigner の画面の設定を AtelIer の設定へ写す。AtelIer に既にある鍵は上書きしない。写した鍵の数を返す"""
    count = 0
    for old_name, new_name in (("chatdraw", "atelier"), ("chatdraw-settings", "atelier-settings")):
        old, new = QSettings(SOURCE_APP, old_name), QSettings("AtelIer", new_name)
        for key in old.allKeys():
            if not new.contains(key):
                new.setValue(key, old.value(key))
                count += 1
        new.sync()
    return count


def integrate_once(home: Path, gguf: Path, QSettings=None, src: Path | None = None) -> bool:
    """1 回だけ統合する。ファイル（置き場の印）と画面の設定（QSettings の印）は別に見る
    （インストーラーは管理者として動き、利用者の画面の設定に届かないので、画面の設定は初めての起動で写す）。何か統合したら True"""
    src = src or source_home()
    if src is None:
        return False
    log: list[str] = []
    if not (home / DONE).exists():
        log += integrate_files(src, home, gguf)
    if QSettings is not None:
        mark = QSettings("AtelIer", "atelier")
        if not mark.value("integrated_from_character_designer", False, type=bool):
            log.append(f"画面の設定を {integrate_settings(QSettings)} 件写した")
            mark.setValue("integrated_from_character_designer", True)
            mark.sync()
    if not log:
        return False
    home.mkdir(parents=True, exist_ok=True)
    with open(home / "migrate.log", "a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    return True


def main(argv: list[str]) -> int:
    """インストーラーから呼ぶ入口（人は使わない）。ファイルだけを統合する"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from atelier.files.paths import GGUF, HOME, ensure_shared
    ensure_shared()
    integrate_once(HOME, GGUF)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
