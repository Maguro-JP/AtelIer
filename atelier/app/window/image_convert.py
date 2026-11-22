"""QImage と PIL の絵の変換"""
from __future__ import annotations

from PIL import Image


def gray_to_pil(img):
    """直す所の形（QImage の灰色）を PIL の L にする"""
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format_Grayscale8)
    return Image.frombuffer("L", (img.width(), img.height()), bytes(img.constBits()), "raw", "L", img.bytesPerLine(), 1)


def fit_size(w: int, h: int, area: int = 832 * 1216) -> tuple[int, int]:
    """キャンバスと同じ縦横比で、模型の得意な画素数（約 100 万）に合う大きさ。64 の倍数にする。
    決まった大きさで描くと、ラフと縦横比がずれて、重ねたときに下のラフがはみ出した"""
    k = (area / max(1, w * h)) ** 0.5
    return max(64, round(w * k / 64) * 64), max(64, round(h * k / 64) * 64)


def qimage_from_pil(im):
    from PySide6.QtGui import QImage
    im = im.convert("RGBA")
    return QImage(im.tobytes(), im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()


def qimage_to_pil_rgba(img):
    """レイヤー（QImage）を、透明度を保ったまま PIL にする"""
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA",
                            img.bytesPerLine(), 1).copy()


def qimage_to_pil(img):
    """キャンバスの絵（QImage）を描く模型に渡せる形（PIL）にする"""
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA",
                            img.bytesPerLine(), 1).convert("RGB")
