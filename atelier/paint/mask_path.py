"""画素ごとの選んだ・選ばないの表（bool の配列）を、選択範囲や赤ペンの印に使う形にする。"""
from __future__ import annotations


def to_path(mask):
    """bool の配列を QPainterPath にする。穴と飛び地もそのまま持つ"""
    import numpy as np
    from PySide6.QtGui import QBitmap, QImage, QPainterPath, QRegion
    h, w = mask.shape
    a = np.ascontiguousarray(np.where(mask, 0, 255).astype(np.uint8))
    img = QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    region = QRegion(QBitmap.fromImage(img.convertToFormat(QImage.Format_Mono)))
    path = QPainterPath()
    path.addRegion(region)
    return path.simplified()
