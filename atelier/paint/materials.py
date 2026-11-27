"""素材: ブラシの穂先と柄を、パラメータと画像で表す。ユーザーが作って、配って、持ち込める。

素材ファイルは zip（拡張子 .atelier-material）で、中身は manifest.json（種類・名前・パラメータ）と
tip.png（穂先）/ pattern.png（柄）/ grain.png（紙目）。ブラシも柄も同じ形式で扱う。

画像から作る:
- 柄は、端同士を馴染ませて繰り返しても継ぎ目が見えないタイルにする（make_tileable）。
- 穂先は、画像の暗さを濃さにする（tip_from_image）。写真や自分の描いた形からでも作れる。
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

FORMAT_VERSION = 1
MATERIAL_SUFFIX = ".atelier-material"
KINDS = ("brush", "pattern")
_IMAGE_KEYS = ("tip", "pattern", "grain")


def _center_square(image: Image.Image) -> Image.Image:
    w, h = image.size
    s = min(w, h)
    return image.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))


def _fix_seam(a: np.ndarray, axis: int, band_ratio: float) -> np.ndarray:
    """1 方向の継ぎ目を直す。半分ずらして継ぎ目を中心へ移し、中心の帯だけを
    ずらす前の絵と混ぜて馴染ませる。外側の端には触らないので、直交方向の
    繋がりを壊さない"""
    n = a.shape[axis]
    b = np.roll(a, n // 2, axis=axis)
    band = max(2.0, n * band_ratio)
    pos = np.arange(n, dtype=np.float32)
    wgt = np.clip(1.0 - np.abs(pos - n / 2) / band, 0.0, 1.0).astype(np.float32)
    shape = [1, 1, 1]
    shape[axis] = n
    m = wgt.reshape(shape)
    return b * (1.0 - m) + a * m


def make_tileable(image: Image.Image, band_ratio: float = 0.25) -> Image.Image:
    """繰り返しても継ぎ目が見えないタイルにする。縦と横の継ぎ目を別々に直す
    （同時に直すと、端で元の絵が戻って継ぎ目が残る）"""
    a = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = a.shape[:2]
    if h < 4 or w < 4:
        return image.convert("RGB")
    out = _fix_seam(a, axis=1, band_ratio=band_ratio)
    out = _fix_seam(out, axis=0, band_ratio=band_ratio)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def pattern_from_image(image: Image.Image, size: int = 256) -> Image.Image:
    """画像から柄を作る。中心を正方形に切り、繰り返せるタイルにする"""
    tile = _center_square(image.convert("RGB"))
    if size and tile.size != (size, size):
        tile = tile.resize((size, size), Image.LANCZOS)
    return make_tileable(tile)


def tip_from_image(image: Image.Image, size: int = 256) -> Image.Image:
    """画像からブラシの穂先を作る。暗い所ほど濃い（不透明）になる、灰色の絵を返す。
    明るい背景に描かれた形が、そのまま穂先の形になる"""
    g = np.asarray(_center_square(image.convert("L"))).astype(np.float32)
    dark = 255.0 - g
    peak = float(dark.max())
    if peak > 0:
        dark *= 255.0 / peak   # 一番暗い所が最も濃くなるよう引き伸ばす
    tip = Image.fromarray(np.clip(dark, 0, 255).astype("uint8"), "L")
    if size and tip.size != (size, size):
        tip = tip.resize((size, size), Image.LANCZOS)
    return tip


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def save_material(path, *, kind: str, name: str, params: dict | None = None,
                  tip: Image.Image | None = None, pattern: Image.Image | None = None,
                  grain: Image.Image | None = None) -> Path:
    """素材を 1 ファイルに保存する。kind は brush / pattern。画像は PNG で同梱する"""
    if kind not in KINDS:
        raise ValueError(f"知らない素材の種類です: {kind}")
    path = Path(path)
    if path.suffix != MATERIAL_SUFFIX:
        path = path.with_suffix(MATERIAL_SUFFIX)
    manifest = {"format": FORMAT_VERSION, "kind": kind, "name": name, "params": dict(params or {})}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for key, img in (("tip", tip), ("pattern", pattern), ("grain", grain)):
            if img is not None:
                z.writestr(f"{key}.png", _png_bytes(img))
    return path


def load_material(path) -> dict:
    """素材ファイルを読む。{"kind", "name", "params", "tip", "pattern", "grain"} を返し、
    入っていない画像は None"""
    with zipfile.ZipFile(Path(path)) as z:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        out = {"kind": manifest["kind"], "name": manifest["name"], "params": manifest.get("params", {})}
        names = set(z.namelist())
        for key in _IMAGE_KEYS:
            out[key] = Image.open(io.BytesIO(z.read(f"{key}.png"))).copy() if f"{key}.png" in names else None
    return out


def list_materials(folder) -> list[dict]:
    """フォルダにある素材の一覧（manifest だけ読む。画像は読まない）"""
    folder = Path(folder)
    out = []
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob(f"*{MATERIAL_SUFFIX}")):
        try:
            with zipfile.ZipFile(p) as z:
                m = json.loads(z.read("manifest.json").decode("utf-8"))
            out.append({"path": p, "kind": m["kind"], "name": m["name"], "params": m.get("params", {})})
        except Exception:   # noqa: BLE001  壊れた素材は一覧に出さない
            continue
    return out
