"""置き場所を 1 か所で決める。

模型は数 GB あるので、自作のアプリどうしで共有する。共有の置き場は C:\\LLM（自作アプリ共通の決まり）。

    C:\\LLM\\
      README.txt      この置き場の説明（無ければ作る）
      gguf\\           言葉の模型（llama.cpp で読む .gguf）
      huggingface\\    絵の模型など、Hugging Face の形のままの模型

- 模型はまずここを探し、新しく取る物もここへ置く。同じ物を 2 か所に持たない
- 道は ASCII だけにする（利用者名が全角だと、AppData の道で llama.cpp が模型を開けなかった）
- どのアプリも、ほかのアプリが置いた模型を消さない。消すのは利用者が選んだときだけ
- LLM_HOME を書くと、共有の置き場をほかへ移せる

模型でない物（設定、描いた絵の記録、動かす部品）はアプリごとに C:\\ProgramData\\AtelIer に置く。
アプリ本体は C:\\Program Files\\AtelIer（インストーラーが置く。書き換えない）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = sys.platform == "win32"

README = """この置き場には、自作のアプリが共有して使う AI の模型が入っています。

gguf\\         言葉の模型（llama.cpp で読む .gguf）
huggingface\\  絵の模型など、Hugging Face の形のままの模型

複数のアプリが同じ模型を読みます。消すと、使っているアプリで取り直しになります。
置き場を移したいときは、アプリの「設定」の「保存」で模型の置き場を選んでください。
"""


def _known_pictures() -> Path | None:
    """Windows の既知フォルダーとしてのピクチャの場所。利用者が別のドライブへ
    移動していたり、OneDrive へ向けていたりしても、Windows の設定どおりの
    場所を返す。Windows でない・取れないときは None"""
    if not WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Guid(ctypes.Structure):
            _fields_ = [("data", ctypes.c_ubyte * 16)]
        # FOLDERID_Pictures {33E28130-4E1E-4676-835A-98395C3BC3BB}
        fid = Guid()
        fid.data = (ctypes.c_ubyte * 16).from_buffer_copy(
            bytes.fromhex("30281e33334e4676835a98395c3bc3bb"))
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        if shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) != 0 or not out.value:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:   # noqa: BLE001
        return None


def pictures_dir() -> Path:
    """ピクチャの場所。Windows の既知フォルダー（利用者の設定）を尊重し、
    取れなければホームの下の Pictures にする。C ドライブやホームの下と決めつけない"""
    return _known_pictures() or (Path.home() / "Pictures")


def default_output_dir() -> Path:
    """描いた絵の保存先の既定。ピクチャ（利用者の設定の場所）の下の AtelIer"""
    return pictures_dir() / "AtelIer"


def data_home() -> Path:
    """模型以外（設定・部品・記録）の置き場。ATELIER_HOME > Windows の ProgramData > 開発中の .cache の順に決める"""
    if os.environ.get("ATELIER_HOME"):
        return Path(os.environ["ATELIER_HOME"])
    if WINDOWS:
        return Path(os.environ.get("ProgramData") or "C:\\ProgramData") / "AtelIer"
    return ROOT / ".cache"


def config_file() -> Path:
    """利用者が設定で選んだ置き場を書くファイル。模型の置き場は読み込みの最初に決まるので、QSettings ではなくここに持つ"""
    return data_home() / "places.json"




def _model_dir_in(path: Path) -> str:
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ""
    return str(data.get("model_dir") or "") if isinstance(data, dict) else ""


def chosen_model_dir() -> str:
    """設定で選んだ模型の置き場。AtelIer の設定だけを見る（ほかのアプリの置き場や設定は使わない）"""
    return _model_dir_in(config_file())


def set_model_dir(path: str):
    """模型の置き場を変える。次の起動から効く。空にすると既定の置き場に戻す"""
    data = read_json(config_file(), dict, {})   # 読めないファイルは控えを残す
    data["model_dir"] = path
    write_json(config_file(), data)


def default_model_dir() -> Path:
    if WINDOWS:
        return Path((os.environ.get("SystemDrive") or "C:") + "\\") / "LLM"
    return ROOT / ".cache"


def llm_home() -> Path:
    """共有の模型の置き場。設定で選んだ所 > LLM_HOME > Windows の C:\\LLM > 開発中の .cache の順に決める。
    設定を先にするのは、前の版や別のアプリが残した LLM_HOME に引っ張られて、選んだ所が使われなかったのを避けるため"""
    chosen = chosen_model_dir()
    if chosen:
        return Path(chosen)
    if os.environ.get("LLM_HOME"):
        return Path(os.environ["LLM_HOME"])
    return default_model_dir()


LLM_HOME = llm_home()
HOME = data_home()
# 開発中（Windows でない）は、これまでの置き場（.cache/gen/hf/hub と .cache/llm）をそのまま使う
SHARED = WINDOWS or bool(os.environ.get("LLM_HOME")) or bool(chosen_model_dir())   # 共有の形（huggingface、gguf）で置くか
HUB = LLM_HOME / "huggingface" if SHARED else LLM_HOME / "gen" / "hf" / "hub"
GGUF = LLM_HOME / "gguf" if SHARED else LLM_HOME / "llm"
OWN_LLM = HOME / "llm"   # 言葉の模型を動かす部品（llama-cpp-python）


def legacy_gguf_dirs() -> list[Path]:
    """共有の置き場を決める前に、模型が置かれていた所。読むだけで、ここへは取らない"""
    return [OWN_LLM]   # ほかのアプリの置き場は見ない（共有は C:\\LLM だけ）


def llm_dirs() -> list[Path]:
    """言葉の模型を探す場所。共有の置き場を先に見る"""
    out = []
    for d in [GGUF, LLM_HOME / "manual", *legacy_gguf_dirs()]:   # manual は手で置いた模型の置き場（.gguf もここに置ける）
        if d.is_dir() and d not in out:
            out.append(d)
    return out


def llm_target() -> Path:
    """新しく取る言葉の模型の置き場"""
    return GGUF


def find_gguf(name: str) -> Path | None:
    for d in llm_dirs():
        p = d / name
        if p.is_file():
            return p
    return None


def ensure_shared():
    """共有の置き場と説明を作る。既にある物は書き換えない"""
    for d in (HUB, GGUF):
        d.mkdir(parents=True, exist_ok=True)
    readme = LLM_HOME / "README.txt"
    if (WINDOWS or os.environ.get("LLM_HOME")) and not readme.exists():
        readme.write_text(README, encoding="utf-8")


# 部品（tools/gen）の置き場は cdhome.HOME を data_home() に直接向け、環境変数は変えない


def use_tools_gen():
    """tools/gen の部品を読めるようにし、その置き場（cdhome.HOME）をアプリのデータの置き場に向ける。
    環境変数 ATELIER_HOME は書き換えない（書き換えると data_home() がずれ、利用者の設定が読めなくなる）"""
    gen = ROOT / "tools" / "gen"
    if str(gen) not in sys.path:
        sys.path.insert(0, str(gen))
    import cdhome
    if not os.environ.get("ATELIER_HOME"):
        cdhome.HOME = data_home()
    return cdhome


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
