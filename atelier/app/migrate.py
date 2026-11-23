"""CharacterDesigner から AtelIer への引き継ぎと、前の版が写しすぎた物の片付け。

引き継ぎは Edge の「ほかのブラウザーから取り込む」と同じ形にする。利用者が窓で引き継ぐ物を選び、選んだ物だけを写す。
0.1.1〜0.1.4 はインストーラーと初めての起動で黙って置き場を丸ごと写し、キャラクターデザインの物や cd の下の古い写しまで
AtelIer の置き場に残した。それを避けるため、黙って写す入口は持たない（窓は atelier/app/migrate_dialog.py）。

引き継ぐ物の組（KINDS）
- settings: 画面の設定（QSettings）と、置き場・言葉・直しの頼みの設定のファイル
- prefs: ★・非表示・役目・自分で足した模型、学んだ基準
- library: ライブラリーと参考の絵の組。一覧（index.json）の道は CharacterDesigner の置き場や保存先（Pictures\\CharacterDesigner）を
  指しているので、絵のファイルも AtelIer の置き場へ写し、道を AtelIer の置き場の道に直して、AtelIer の一覧に足す
  （一覧だけを写すと、CharacterDesigner を外したときに絵が「ファイルが無い」になった）
- records: チャットの会話、描いた記録（draw_log.jsonl）、作業ファイルの途中（work）
- parts: 描く部品（gen、simple、llm の lib など）。写せば取り直さずに済む
- gguf: 言葉の模型（.gguf）。写さずに自作アプリ共通の置き場（C:\\LLM\\gguf）へ移す
CharacterDesigner の前の版がずれて書いた「cd」の下の物は、cd を外した所へ合わせる。AtelIer に既にある物は上書きしない。
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Callable

SOURCE_APP = "CharacterDesigner"
DONE = "integrated-from-CharacterDesigner.txt"    # 引き継いだ記録（AtelIer の置き場の下）
OLD_MARKS = ("imported-from-CharacterDesigner.txt", DONE)   # 0.1.1〜0.1.4 が丸ごと写したときの印
STRAY = "cd"                                      # CharacterDesigner の前の版が設定をずれて書いた所
MODELS = (".gguf",)
SKIP = (".part", ".lock")                         # 取りかけの物は写さない

# 組ごとの、置き場の一段目の名前
KIND_NAMES: dict[str, tuple[str, ...]] = {
    "settings": ("places.json", "words.json", "fixrequests.user.json"),
    "prefs": ("model_prefs.json", "favorites.json", "model_roles.json", "user_models.json", "learn"),
    "library": ("library", "refsets.json"),
    "records": ("chat.json", "draw_log.jsonl", "work"),
    "parts": ("gen", "simple", "llm", "upscale", "lora"),
}
KINDS = ("settings", "prefs", "library", "records", "parts", "gguf")
LABELS = {
    "settings": "設定と画面の並び",
    "prefs": "模型の好み（★・非表示・役目・学んだ基準）",
    "library": "ライブラリーと参考の絵",
    "records": "記録（チャット・描いた記録・作業の途中）",
    "parts": "描く部品（取り直さずに済みます）",
    "gguf": "言葉の模型（共通の置き場へ移します）",
}
# AtelIer が自分の置き場で使う一段目の名前。片付けでは、これに当たる物を消す候補にしない
ATELIER_USES = frozenset(n for names in KIND_NAMES.values() for n in names) | {
    "trash", "autosave", "work", "updates", "backup", "manual", "extensions", "huggingface", "gguf",
    "README.txt", "setup.log", "atelier.log", "migrate.log", "crash.log", "logs"} | set(OLD_MARKS)


def source_home() -> Path | None:
    """CharacterDesigner のデータの置き場。引き継ぐときだけ読む。無ければ None"""
    if os.environ.get("CD_HOME"):
        d = Path(os.environ["CD_HOME"])
    elif os.name == "nt":
        d = Path(os.environ.get("ProgramData") or "C:\\ProgramData") / SOURCE_APP
    else:
        return None
    return d if d.is_dir() else None


def source_places() -> list[Path]:
    """CharacterDesigner の置き場として道を見分ける所。置き場が消えていても（外したあとでも）道は見分ける"""
    out = []
    if os.environ.get("CD_HOME"):
        out.append(Path(os.environ["CD_HOME"]))
    if os.name == "nt":
        out.append(Path(os.environ.get("ProgramData") or "C:\\ProgramData") / SOURCE_APP)
    return list(dict.fromkeys(out))


def _key(path: str) -> str:
    s = str(path).replace("\\", "/").rstrip("/")
    return s.casefold() if os.name == "nt" or ":" in s[:3] else s


def rebase(path: str, places, home: Path) -> Path | None:
    """CharacterDesigner の置き場の下を指す道を、AtelIer の置き場の同じ所の道にする。置き場の外の道は None"""
    k = _key(path)
    for place in places:
        root = _key(str(place))
        if k.startswith(root + "/"):
            parts = [x for x in str(path).replace("\\", "/")[len(root) + 1:].split("/") if x]
            return home / _target(Path(*parts)) if parts else None
    return None


def _target(rel: Path) -> Path:
    """cd の下の物は cd を外した所へ合わせる"""
    parts = rel.parts
    return Path(*parts[1:]) if parts and parts[0] == STRAY else rel


def kind_of(path: Path, src: Path) -> str | None:
    """src の下のファイルが、どの組に入るか。どの組にも入らない物（キャラクターデザインの物など）は None で、写さない"""
    if path.suffix.lower() in MODELS:
        return "gguf"
    rel = _target(path.relative_to(src))
    if not rel.parts:
        return None
    for kind, names in KIND_NAMES.items():
        if rel.parts[0] in names:
            return kind
    return None


def _files(src: Path) -> list[Path]:
    # cd の外の物を先に写す（cd の下は古い写しなので、同じ名前があれば外の物を残す）
    found = [p for p in src.rglob("*") if p.is_file() and not p.is_symlink()]
    return sorted(found, key=lambda p: p.relative_to(src).parts[:1] == (STRAY,))


def survey(src: Path) -> dict[str, tuple[int, int]]:
    """組ごとの (件数, バイト数)。窓に大きさを出すため"""
    out = {k: (0, 0) for k in KINDS}
    for p in _files(src):
        k = kind_of(p, src)
        if k is None or p.suffix.lower() in SKIP:
            continue
        n, size = out[k]
        try:
            size += p.stat().st_size
        except OSError:
            pass
        out[k] = (n + 1, size)
    return out


def _copy(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _place_picture(path: str, places, home: Path, outside: bool) -> tuple[str, int]:
    """一覧の 1 行の絵を AtelIer の置き場に置き、新しい道と写した件数を返す。
    置き場の中の絵は同じ所へ、置き場の外（保存先など）の絵は outside のときだけ library/works へ写す。
    どこにも無い絵は道をそのままにする（ライブラリーが「ファイルが無い」と出し、場所を選び直す・外すを選べる）"""
    target = rebase(path, places, home)
    try:
        if target is not None:
            if target.is_file():
                return str(target), 0
            if Path(path).is_file():
                return str(target), int(_copy(Path(path), target))
            return path, 0
        p = Path(path)
        if not outside or not p.is_file() or _key(str(p)).startswith(_key(str(home)) + "/"):
            return path, 0
        works = home / "library" / "works"
        target = works / p.name
        n = 1
        while target.exists():
            if target.stat().st_size == p.stat().st_size:
                return str(target), 0   # 前に写した物
            target = works / f"{p.stem}-{n}{p.suffix}"
            n += 1
        return str(target), int(_copy(p, target))
    except (OSError, ValueError):
        return path, 0


def _read_list(path: Path) -> list:
    import json
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return v if isinstance(v, list) else []


def _write_list(path: Path, rows: list):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    part.replace(path)


# 一覧のファイルは写さずに、行を合わせる（AtelIer に一覧が既にあると、写さずに飛ばして引き継いだ絵が 1 枚も出なかった）
MERGED = {("library", "index.json"), (STRAY, "library", "index.json"), ("refsets.json",), (STRAY, "refsets.json")}


def _retarget_favorites(home: Path, moved: dict[str, str]):
    """★ は絵の道で覚えている（favorites.json）。写した絵の新しい道に付け替える（古い道は消さない）"""
    fav = home / "favorites.json"
    if not moved or not fav.is_file():
        return
    old = [str(x) for x in _read_list(fav)]
    new = [moved.get(x, x) for x in old]
    if new != old:
        _write_list(fav, list(dict.fromkeys(new + old)))


def merge_library(src: Path, home: Path, places=None) -> tuple[int, int]:
    """CharacterDesigner のライブラリーの一覧と学習セットを AtelIer の一覧に足す。(足した行, 写した絵) を返す"""
    from atelier.files.library import _normalize
    places = list(places or [src])
    rows = _normalize(_read_list(src / "library" / "index.json") + _read_list(src / STRAY / "library" / "index.json"))
    index = home / "library" / "index.json"
    have = _normalize(_read_list(index))
    ids, keys = {r["id"] for r in have}, {_key(r["path"]) for r in have}
    added = copied = 0
    moved: dict[str, str] = {}
    for row in rows:
        old = row["path"]
        row["path"], n = _place_picture(old, places, home, outside=True)
        copied += n
        if row["path"] != old:
            moved[old] = row["path"]
        if _key(row["path"]) in keys:
            continue
        if row["id"] in ids:
            import uuid
            row["id"] = uuid.uuid4().hex[:12]
        ids.add(row["id"])
        keys.add(_key(row["path"]))
        have.append(row)
        added += 1
    if added or copied:
        have.sort(key=lambda r: r.get("added", ""), reverse=True)
        _write_list(index, have)
    sets = [d for d in _read_list(src / "refsets.json") + _read_list(src / STRAY / "refsets.json")
            if isinstance(d, dict) and d.get("name")]
    if sets:
        mine = [d for d in _read_list(home / "refsets.json") if isinstance(d, dict) and d.get("name")]
        names = {d["name"] for d in mine}
        for d in sets:
            if d["name"] in names:
                continue
            images = []
            for img in d.get("images") or []:
                if isinstance(img, str):
                    new, n = _place_picture(img, places, home, outside=False)
                    images.append(new)
                    copied += n
            mine.append({**d, "images": images})
            names.add(d["name"])
        _write_list(home / "refsets.json", mine)
    _retarget_favorites(home, moved)
    return added, copied


def repair_library(lib, home: Path, places=None) -> int:
    """前の版で引き継いだ一覧には、CharacterDesigner の置き場を指す道が残っている。CharacterDesigner を外すと絵が
    「ファイルが無い」になるので、起動のときに AtelIer の置き場へ写し（既に写してあればそれを指し）、道を直す。
    どこにも無い絵は道を変えず、一覧からも消さない。直した行の数を返す"""
    places = list(places if places is not None else source_places())
    if not places:
        return 0
    moved: dict[str, str] = {}
    for item in lib.items:
        new, _ = _place_picture(item["path"], places, home, outside=False)
        if new != item["path"]:
            moved[item["path"]] = new
            item["path"] = new
    fixed = len(moved)
    if fixed:
        _retarget_favorites(home, moved)
        try:
            lib.save()
        except OSError:
            pass
    return fixed


def integrate_files(src: Path, dst: Path, gguf: Path, kinds=KINDS,
                    progress: Callable[[int, int, str], None] | None = None) -> dict[str, int]:
    """src（CharacterDesigner の置き場）から、kinds に選んだ組の物だけを dst（AtelIer の置き場）へ写す。
    言葉の模型は gguf へ移す。返すのは組ごとに写した件数と、"skipped"・"failed" の件数"""
    chosen = [p for p in _files(src) if p.suffix.lower() not in SKIP and kind_of(p, src) in kinds
              and p.relative_to(src).parts not in MERGED]
    counts = {k: 0 for k in kinds} | {"skipped": 0, "failed": 0}
    log = [time.strftime("%Y-%m-%d %H:%M:%S"), f"CharacterDesigner から引き継ぐ: {src} -> {dst}（{', '.join(kinds)}）"]
    for i, path in enumerate(chosen):
        if progress:
            progress(i, len(chosen), path.name)
        kind = kind_of(path, src)
        try:
            if kind == "gguf":
                target = gguf / path.name
                if target.exists():
                    counts["skipped"] += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target))
            else:
                target = dst / _target(path.relative_to(src))
                if target.exists():
                    counts["skipped"] += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            counts[kind] += 1
        except OSError as e:
            counts["failed"] += 1
            log.append(f"引き継げなかった: {path} ({e})")
    if "library" in kinds:
        try:
            added, copied = merge_library(src, dst, [src, *source_places()])
            counts["library"] += added
            log.append(f"ライブラリーの一覧に {added} 行を足し、絵を {copied} 枚写した")
        except OSError as e:
            counts["failed"] += 1
            log.append(f"ライブラリーの一覧を合わせられなかった: {e}")
    if progress:
        progress(len(chosen), len(chosen), "")
    log.append(", ".join(f"{k} {v}" for k, v in counts.items()))
    dst.mkdir(parents=True, exist_ok=True)
    with open(dst / "migrate.log", "a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    (dst / DONE).write_text("\n".join(log) + "\n", encoding="utf-8")
    return counts


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


# ---- 片付け（0.1.1〜0.1.4 が丸ごと写した物） ----

def was_bulk_copied(home: Path) -> bool:
    """前の版が丸ごと写した印があるか"""
    return any((home / m).exists() for m in OLD_MARKS[:1])


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for q in p.rglob("*"):
        try:
            if q.is_file() and not q.is_symlink():
                total += q.stat().st_size
        except OSError:
            pass
    return total


def cleanup_candidates(home: Path, src: Path | None = None) -> list[tuple[Path, int, str]]:
    """AtelIer の置き場のうち、AtelIer が使わない物（キャラクターデザインの物、cd の置き場など）。(道, バイト数, 理由)"""
    out = []
    if not home.is_dir():
        return out
    for p in sorted(home.iterdir()):
        if p.name in ATELIER_USES:
            continue
        if p.name == STRAY:
            why = "CharacterDesigner の前の版の置き場（cd）の写し。中の要る物は外にもあります"
        elif src is not None and not (src / p.name).exists() and not (src / STRAY / p.name).exists():
            continue   # CharacterDesigner から来た物でないなら触らない
        else:
            why = "CharacterDesigner から写した、AtelIer では使わない物"
        try:
            out.append((p, _size(p), why))
        except OSError:
            continue
    return out


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
