"""作業ファイル（.atelier）の保存と読み込み、PSD の書き出し、自動保存。

作業ファイルは zip の中に、レイヤーごとの PNG と並び（manifest.json）を入れる。赤ペンの印と指示も残すので、
直しの途中で閉じても続きから頼める。PSD は他の作画ソフトへ渡すための書き出しで、レイヤーの名前・表示・不透明度を保つ。
"""
from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF
from PySide6.QtGui import QImage

VERSION = 1
APP = "AtelIer"
SUFFIX = ".atelier"
# CharacterDesigner の作業ファイル（.cdproj）は中身の形が同じなので開ける。保存は .atelier だけ
LEGACY_APPS = ("Character" + "Designer",)
LEGACY_SUFFIXES = (".cd" + "proj",)
READABLE = (SUFFIX, *LEGACY_SUFFIXES)


def _png(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def _path_points(path) -> list | None:
    """丸・四角などの形の印を点の並びにする。残さないと、開き直したとき形の印が 1 点の印になり、囲みが消えていた"""
    if path is None:
        return None
    return [[[p.x(), p.y()] for p in poly] for poly in path.toSubpathPolygons()]


def _points_path(polys):
    from PySide6.QtGui import QPainterPath, QPolygonF
    if not polys:
        return None
    path = QPainterPath()
    for poly in polys:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
        path.closeSubpath()
    return path


def snapshot(canvas, extra: dict | None = None) -> dict:
    """保存する中身を写し取る（画面の糸で呼ぶ。画素は写しなので、このあと描き続けても保存の中身は変わらない）。
    PNG に縮めて書くのは write で、裏の糸で回せる"""
    w, h = canvas.size_px()
    pen = canvas.redpen
    manifest = {"version": VERSION, "app": APP, "size": [w, h], "current": canvas.current,
                "layers": [], "marks": [[[p.x(), p.y()] for p in pts] for pts in pen.marks], "notes": list(pen.texts),
                "hidden": [bool(pen.hidden[i]) if i < len(pen.hidden) else False for i in range(len(pen.marks))],
                "shapes": [_path_points(pen.shape_of(i + 1)) for i in range(len(pen.marks))],
                **(extra or {})}
    images = []
    for i, layer in enumerate(canvas.layers):
        name = f"layers/{i:03d}.png"
        images.append((name, layer.image.copy()))
        manifest["layers"].append({"name": layer.name, "visible": layer.visible, "opacity": layer.opacity, "file": name,
                                   "blend": layer.blend, "clip": layer.clip, "alpha_lock": layer.alpha_lock,
                                   "locked": layer.locked})
    return {"manifest": manifest, "images": images}


def write(snap: dict, path: str | Path):
    """snapshot の中身を path に書く。途中で落ちても前のファイルを壊さないよう、別名に書いてから替える"""
    path = Path(path)
    part = path.with_name(path.name + ".part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        for name, img in snap["images"]:
            z.writestr(name, _png(img))
        z.writestr("manifest.json", json.dumps(snap["manifest"], ensure_ascii=False, indent=1))
    part.replace(path)


def save(canvas, path: str | Path, extra: dict | None = None):
    """canvas のレイヤー・今のレイヤー・赤ペンの印を path に保存する"""
    write(snapshot(canvas, extra), path)


def read(path: str | Path) -> tuple[dict, list]:
    """作業ファイルを読んで、manifest と（名前, 絵, 表示, 不透明度）の並びを返す。画面に触らないので裏の糸で回せる"""
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("app") not in (APP, *LEGACY_APPS):
            raise ValueError("AtelIer の作業ファイルではありません")
        layers = []
        for info in manifest["layers"]:
            img = QImage.fromData(z.read(info["file"]), "PNG").convertToFormat(QImage.Format_ARGB32_Premultiplied)
            # 合成モード・クリッピング・保護は前の版の作業ファイルに無いので、無ければ通常・無しとして読む
            layers.append((info["name"], img, bool(info.get("visible", True)), float(info.get("opacity", 1.0)),
                           {k: info[k] for k in ("blend", "clip", "alpha_lock", "locked") if k in info}))
    return manifest, layers


def apply(canvas, got: tuple[dict, list]) -> dict:
    """read の結果を canvas に置く（画面の糸で呼ぶ）"""
    from atelier.paint.canvas import Layer
    manifest, parts = got
    from atelier.paint.canvas import BLEND_MODES
    layers = []
    for name, img, visible, opacity, *more in parts:
        props = more[0] if more else {}
        layers.append(Layer(name, img, visible, opacity, locked=bool(props.get("locked", False)),
                            blend=props.get("blend") if props.get("blend") in BLEND_MODES else "normal",
                            clip=bool(props.get("clip", False)), alpha_lock=bool(props.get("alpha_lock", False))))
    canvas._reset(layers, min(int(manifest.get("current", 0)), len(layers) - 1))
    pen = canvas.redpen
    marks = manifest.get("marks", [])
    notes, hidden, shapes = (list(manifest.get(k) or []) for k in ("notes", "hidden", "shapes"))
    # 前の版の作業ファイルには隠す・形が無いので、足りない分は「見せる・手で描いた印」とする（zip で短い方に合わせると印が消えた）
    for i, pts in enumerate(marks):
        pen.marks.append([QPointF(x, y) for x, y in pts])
        pen.texts.append(notes[i] if i < len(notes) else "")
        pen.hidden.append(bool(hidden[i]) if i < len(hidden) else False)
        pen.shapes.append(_points_path(shapes[i]) if i < len(shapes) else None)
    pen.update()
    pen._changed()   # レイヤーの欄に「赤ペン」を出す。update だけでは欄に出ず、隠す・消すができなかった
    return manifest


def load(canvas, path: str | Path) -> dict:
    """path の作業ファイルを canvas に開く。返すのは manifest（作業ファイルに残した設定）"""
    return apply(canvas, read(path))


# ---- PSD ----
def _pascal(name: str) -> bytes:
    """レイヤーの名前（4 バイトの区切りまで埋める）。PSD の名前は 1 バイトの文字だけなので、日本語の名前は別の場所に入れる"""
    raw = name.encode("ascii", "replace")[:255]
    b = bytes([len(raw)]) + raw
    return b + b"\0" * (-len(b) % 4)


def _unicode_name(name: str) -> bytes:
    """日本語のままの名前（luni）。これが無いと、作画ソフトでレイヤーの名前が「?」になる"""
    body = struct.pack(">I", len(name)) + name.encode("utf-16-be")
    body += b"\0" * (-len(body) % 4)
    return b"8BIMluni" + struct.pack(">I", len(body)) + body


def _planes(img: QImage) -> list[bytes]:
    """QImage を R・G・B・透明度の 4 枚の板（1 画素 1 バイト）にする。透明度は掛け合わせない値で渡す"""
    a = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = a.width(), a.height()
    raw = bytes(a.constBits())
    stride = a.bytesPerLine()
    rows = b"".join(raw[y * stride:y * stride + w * 4] for y in range(h))
    return [rows[c::4] for c in (0, 1, 2, 3)]


def export_psd(canvas, path: str | Path):
    """レイヤーを分けたまま PSD に書き出す（圧縮なし）。下のレイヤーから順に並べる"""
    write_psd(psd_snapshot(canvas), path)


def psd_snapshot(canvas) -> dict:
    """PSD に書く中身の写し（画面の糸で呼ぶ）。書くのは write_psd で、裏の糸で回せる"""
    from types import SimpleNamespace
    w, h = canvas.size_px()
    layers = [SimpleNamespace(name=l.name, visible=l.visible, opacity=l.opacity, image=l.image.copy(), blend=l.blend,
                              clip=l.clip, alpha_lock=l.alpha_lock) for l in canvas.layers]
    return {"size": (w, h), "layers": layers, "merged": canvas.flatten().copy()}


def write_psd(snap: dict, path: str | Path):
    w, h = snap["size"]
    records, data = b"", b""
    for layer in snap["layers"]:
        r, g, b, a = _planes(layer.image)
        size = len(r) + 2
        # 絵のある所だけのレイヤーは left・top に置き場を持つ（キャラクターシートの区画。全面の透明を書かないので小さくなる）
        x, y = getattr(layer, "left", 0), getattr(layer, "top", 0)
        records += struct.pack(">iiiiH", y, x, y + layer.image.height(), x + layer.image.width(), 4)
        for cid in (-1, 0, 1, 2):
            records += struct.pack(">hI", cid, size)
        from atelier.paint.canvas import BLEND_MODES
        flags = (0 if layer.visible else 2) | (1 if getattr(layer, "alpha_lock", False) else 0)
        key = BLEND_MODES.get(getattr(layer, "blend", "normal"), BLEND_MODES["normal"])[1].encode("ascii")
        extra = struct.pack(">I", 0) + struct.pack(">I", 0) + _pascal(layer.name) + _unicode_name(layer.name)
        records += b"8BIM" + key + struct.pack(">BBBB", round(layer.opacity * 255), 1 if getattr(layer, "clip", False) else 0,
                                               flags, 0)
        records += struct.pack(">I", len(extra)) + extra
        for plane in (a, r, g, b):
            data += struct.pack(">H", 0) + plane
    info = struct.pack(">h", len(snap["layers"])) + records + data
    info += b"\0" * (len(info) % 2)
    layer_info = struct.pack(">I", len(info)) + info
    section = layer_info + struct.pack(">I", 0)
    r, g, b, _a = _planes(snap["merged"])
    with open(path, "wb") as f:
        f.write(b"8BPS" + struct.pack(">H6xHIIHH", 1, 3, h, w, 8, 3))
        f.write(struct.pack(">I", 0))              # 色の表（RGB では空）
        f.write(struct.pack(">I", 0))              # 画像の資源（無し）
        f.write(struct.pack(">I", len(section)) + section)
        f.write(struct.pack(">H", 0) + r + g + b)  # 重ねた 1 枚（読み込むだけのソフト向け）


def _unpack_bits(src: bytes, n: int) -> bytes:
    """PackBits（PSD の RLE）を n バイトに戻す"""
    out, i = bytearray(), 0
    while len(out) < n and i < len(src):
        c = src[i]
        i += 1
        if c < 128:
            out += src[i:i + c + 1]
            i += c + 1
        elif c > 128:
            out += bytes([src[i]]) * (257 - c)
            i += 1
    return bytes(out[:n]).ljust(n, b"\0")


def _channel(data: bytes, pos: int, w: int, h: int) -> tuple[bytes, int]:
    """1 枚の板（圧縮の種類 2 バイト + 中身）を読む。読んだ板と次の位置を返す"""
    comp = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    if comp == 0:
        return data[pos:pos + w * h], pos + w * h
    if comp == 1:
        counts = struct.unpack_from(f">{h}H", data, pos)
        pos += 2 * h
        rows = []
        for c in counts:
            rows.append(_unpack_bits(data[pos:pos + c], w))
            pos += c
        return b"".join(rows), pos
    raise ValueError("この PSD の圧縮（ZIP）には、まだ対応していません。CLIP STUDIO PAINT・Krita で非圧縮か RLE で保存してください")


def read_psd(path: str | Path) -> dict:
    """PSD を読み、絵の大きさとレイヤー（名前・表示・不透明度・合成モード・クリッピング・透明部分の保護・絵）を返す。
    8 ビットの RGB だけを読む。フォルダーは中のレイヤーを平らに並べて読む（フォルダーはまだ無いので、絵を失わないことを先にした）"""
    from types import SimpleNamespace
    import numpy as np
    from atelier.paint.canvas import PSD_BLEND
    data = Path(path).read_bytes()
    if data[:4] != b"8BPS" or struct.unpack_from(">H", data, 4)[0] != 1:
        raise ValueError("PSD ではないか、PSB（大きな絵の形）です")
    channels, h, w, depth, mode = struct.unpack_from(">HIIHH", data, 12)
    if depth != 8 or mode != 3:
        raise ValueError("8 ビットの RGB の PSD だけを読めます（16 ビット・CMYK・グレーは、作画ソフトで 8 ビットの RGB にしてください）")
    pos = 26
    pos += 4 + struct.unpack_from(">I", data, pos)[0]   # 色の表
    pos += 4 + struct.unpack_from(">I", data, pos)[0]   # 画像の資源
    section_len = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    layers = []
    if section_len:
        info_len = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if info_len:
            count = abs(struct.unpack_from(">h", data, pos)[0])
            pos += 2
            recs = []
            for _ in range(count):
                top, left, bottom, right, nch = struct.unpack_from(">iiiiH", data, pos)
                pos += 18
                chans = []
                for _c in range(nch):
                    cid, ln = struct.unpack_from(">hI", data, pos)
                    chans.append((cid, ln))
                    pos += 6
                key = data[pos + 4:pos + 8].decode("ascii", "replace")
                opacity, clip, flags = data[pos + 8], data[pos + 9], data[pos + 10]
                pos += 12
                extra_len = struct.unpack_from(">I", data, pos)[0]
                pos += 4
                end = pos + extra_len
                q = pos
                q += 4 + struct.unpack_from(">I", data, q)[0]   # マスク
                q += 4 + struct.unpack_from(">I", data, q)[0]   # 合成の範囲
                nlen = data[q]
                name = data[q + 1:q + 1 + nlen].decode("latin-1")
                q += 1 + nlen
                q += -(1 + nlen) % 4
                folder = 0
                while q + 12 <= end:
                    sig, tag, ln = data[q:q + 4], data[q + 4:q + 8], struct.unpack_from(">I", data, q + 8)[0]
                    if sig not in (b"8BIM", b"8B64"):
                        break
                    body = data[q + 12:q + 12 + ln]
                    if tag == b"luni" and len(body) >= 4:
                        n = struct.unpack_from(">I", body)[0]
                        name = body[4:4 + 2 * n].decode("utf-16-be", "replace")
                    elif tag in (b"lsct", b"lsdk") and len(body) >= 4:
                        folder = struct.unpack_from(">I", body)[0]
                    q += 12 + ln
                pos = end
                recs.append(dict(top=top, left=left, bottom=bottom, right=right, chans=chans, key=key, opacity=opacity,
                                 clip=clip, flags=flags, name=name, folder=folder))
            for r in recs:
                lw, lh = r["right"] - r["left"], r["bottom"] - r["top"]
                planes = {}
                for cid, ln in r["chans"]:
                    cw, chh = (lw, lh)
                    if cid == -2:   # レイヤーマスクの板は大きさが違うので読み飛ばす
                        pos += ln
                        continue
                    start = pos
                    if cw > 0 and chh > 0:
                        planes[cid], _p = _channel(data, pos, cw, chh)
                    pos = start + ln
                if r["folder"] in (1, 2, 3):
                    continue   # フォルダーの始まりと終わりの印（絵は無い）
                img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
                img.fill(0)
                if lw > 0 and lh > 0:
                    full = np.full((lh, lw), 255, np.uint8)
                    rgba = np.dstack([np.frombuffer(planes.get(c, full.tobytes()), np.uint8).reshape(lh, lw)
                                      for c in (0, 1, 2, -1)]).copy()
                    part = QImage(rgba.data, lw, lh, lw * 4, QImage.Format_RGBA8888).copy()
                    from PySide6.QtGui import QPainter
                    pt = QPainter(img)
                    pt.setCompositionMode(QPainter.CompositionMode_Source)
                    pt.drawImage(r["left"], r["top"], part)
                    pt.end()
                layers.append(SimpleNamespace(name=r["name"] or "レイヤー", image=img, visible=not (r["flags"] & 2),
                                              opacity=r["opacity"] / 255, blend=PSD_BLEND.get(r["key"], "normal"),
                                              clip=bool(r["clip"]), alpha_lock=bool(r["flags"] & 1)))
    if not layers:   # レイヤーの無い PSD は、重ねた 1 枚を読む
        img = QImage(str(path))
        if img.isNull():
            raise ValueError("PSD の絵を読めません")
        layers.append(SimpleNamespace(name="背景", image=img.convertToFormat(QImage.Format_ARGB32_Premultiplied),
                                      visible=True, opacity=1.0, blend="normal", clip=False, alpha_lock=False))
    return {"size": (w, h), "layers": layers}


def apply_psd(canvas, got: dict):
    """read_psd の結果を canvas に置く（画面の糸で呼ぶ）"""
    from atelier.paint.canvas import Layer
    layers = [Layer(l.name, l.image, l.visible, l.opacity, blend=l.blend, clip=l.clip, alpha_lock=l.alpha_lock)
              for l in got["layers"]]
    canvas._reset(layers, len(layers) - 1)


def autosave_path() -> Path:
    from atelier.files.paths import HOME
    return HOME / "autosave" / ("autosave" + SUFFIX)
