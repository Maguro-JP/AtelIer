"""前の版（%LOCALAPPDATA%\\Programs\\AtelIer に入れた版）から、新しい置き場へ移す。インストーラーが 1 回だけ呼ぶ。

前の版は、プログラムも模型も描いた物も、入れた場所 1 か所に置いていた。新しい版はこう分ける。
- 模型: C:\\LLM（自作アプリで共有。atelier/files/paths.py）
- 描いた物・保存したキャラクター: ピクチャの AtelIer\\previous-version
- 部品と設定: C:\\ProgramData\\AtelIer
移す物を移し終えてから、前の版の場所を丸ごと消す（残るのはプログラムと、取り直せる部品だけ）。
1 つでも移せなかったら、前の版の場所は消さずに残し、理由を記録に書く。
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

# 利用者の作った物が入る場所（前の版の build.sh の DATA から、部品と模型の .cache と models を除いた物）
WORKS = ("library", "bible", "characters", "designs", "config", "out")


def old_install() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    d = Path(base) / "Programs" / "AtelIer" if base else None
    return d if d is not None and d.is_dir() else None


def pictures() -> Path:
    return Path.home() / "Pictures" / "AtelIer"


def _move(src: Path, dst: Path, log: list[str]) -> bool:
    """src を dst へ移す。dst に同じ名前の物があれば、同じ物とみなして src を移さない（あとで前の場所ごと消える）"""
    if dst.exists():
        log.append(f"既にある: {dst}")
        return True
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        log.append(f"移した: {src} -> {dst}")
        return True
    except OSError as e:
        log.append(f"移せなかった: {src} ({e})")
        return False


def migrate(old: Path, hub: Path, gguf: Path, works: Path, log_path: Path) -> bool:
    """前の版の場所 old から移す。全部移せたら old を消して True を返す"""
    log: list[str] = [time.strftime("%Y-%m-%d %H:%M:%S"), f"前の版: {old}"]
    ok = True
    old_hub = old / ".cache" / "gen" / "hf" / "hub"
    if old_hub.is_dir():
        for d in sorted(old_hub.glob("models--*")):
            ok &= _move(d, hub / d.name, log)
    old_llm = old / ".cache" / "llm"
    if old_llm.is_dir():
        for f in sorted(old_llm.glob("*.gguf")):
            if f.is_symlink():
                continue   # 別名（model.gguf）は中身ではない
            ok &= _move(f, gguf / f.name, log)
    for name in WORKS:
        d = old / name
        if d.is_dir() and any(d.iterdir()):
            ok &= _move(d, works / "previous-version" / name, log)
    if ok:
        shutil.rmtree(old, ignore_errors=True)
        log.append("前の版の場所を消した" if not old.exists() else f"消せずに残った: {old}")
    else:
        log.append("移せなかった物があるので、前の版の場所は残した")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    return ok and not old.exists()


CD_APP = "CharacterDesigner"   # キャラクターデザイン以外を AtelIer に移す前に、描く・直すを担っていたアプリ
IMPORTED = "imported-from-CharacterDesigner.txt"   # 引き継ぎ済みの印（data_home の下）。2 回目からは何もしない


MODEL_SUFFIXES = (".gguf", ".part")   # 模型の本体（数 GB）と取りかけ。写さずに元の場所から読む（paths.legacy_gguf_dirs）


def character_designer_home() -> Path | None:
    """CharacterDesigner のデータの置き場（CD_HOME > C:\\ProgramData\\CharacterDesigner）。無ければ None"""
    from atelier.files.paths import character_designer_home as home
    return home()


def import_character_designer(src: Path, dst: Path) -> list[str]:
    """CharacterDesigner の置き場 src から、AtelIer の置き場 dst へ、部品（torch など）・設定・記録を写す。
    移さずに写すのは、CharacterDesigner もそのまま使い続けられるようにするため。
    dst に既にある物は上書きしない（AtelIer で変えた設定を前の値に戻さない）。返すのは記録の行"""
    log = [time.strftime("%Y-%m-%d %H:%M:%S"), f"CharacterDesigner から引き継ぐ: {src} -> {dst}"]
    copied = skipped = failed = 0
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.name == IMPORTED:
            continue
        if path.suffix.lower() in MODEL_SUFFIXES:   # 言葉の模型を 2 か所に持たない（写すと数 GB ずつ増えた）
            continue
        target = dst / path.relative_to(src)
        if target.exists():
            skipped += 1
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
        except OSError as e:
            failed += 1
            log.append(f"写せなかった: {path} ({e})")
    log.append(f"写した {copied} 件、既にあった {skipped} 件、写せなかった {failed} 件")
    if failed == 0:
        dst.mkdir(parents=True, exist_ok=True)
        (dst / IMPORTED).write_text("\n".join(log) + "\n", encoding="utf-8")
    return log


def import_character_designer_settings(QSettings) -> int:
    """CharacterDesigner の画面の設定（配置・テーマ・模型の選び・描く言葉など）を、AtelIer の設定に写す。
    AtelIer の側に既にある鍵は上書きしない。写した鍵の数を返す"""
    count = 0
    for old_name, new_name in (("chatdraw", "atelier"), ("chatdraw-settings", "atelier-settings")):
        old, new = QSettings(CD_APP, old_name), QSettings("AtelIer", new_name)
        for key in old.allKeys():
            if not new.contains(key):
                new.setValue(key, old.value(key))
                count += 1
        new.sync()
    return count


def import_once(home: Path, QSettings=None, src: Path | None = None) -> bool:
    """1 回だけ、CharacterDesigner から引き継ぐ。ファイル（data_home の印）と画面の設定（QSettings の印）は別に見る。
    インストーラーは管理者として動き、利用者の画面の設定（HKCU）に届かないので、画面の設定は初めての起動で写す。
    何か引き継いだら True"""
    src = src or character_designer_home()
    if src is None:
        return False
    log: list[str] = []
    if not (home / IMPORTED).exists():
        log += import_character_designer(src, home)
    if QSettings is not None:
        mark = QSettings("AtelIer", "atelier")
        if not mark.value("imported_from_character_designer", False, type=bool):
            log.append(f"画面の設定を {import_character_designer_settings(QSettings)} 件写した")
            mark.setValue("imported_from_character_designer", True)
            mark.sync()
    if not log:
        return False
    home.mkdir(parents=True, exist_ok=True)
    with open(home / "migrate.log", "a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    return True


def main(argv: list[str]) -> int:
    """インストーラーから呼ぶ入口（人は使わない）。引数があればそれを前の版の場所とする"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from atelier.files.paths import GGUF, HOME, HUB, ensure_shared
    import_once(HOME)   # 部品と設定のファイルはインストーラーの間に写す（画面の設定は初めての起動で写す）
    if argv[:1] == ["--import-only"]:
        return 0
    old = Path(argv[0]) if argv else old_install()
    if old is None or not old.is_dir():
        return 0
    ensure_shared()
    return 0 if migrate(old, HUB, GGUF, pictures(), HOME / "migrate.log") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
