"""人物以外の絵の面分けと、題材ごとの工程の段。

部品分け（segformer の顔・腕・脚）は人物の部位しか返さず、風景・建物・物の絵では直しの囲みも下塗りの面も作れなかった。
ここでは模型を使わずに、絵の明るさと色から「空」「地面」「主役」の 3 つの面を取る（どの題材でも動く。精度は人物の部品分けより低い）。
精度優先の工程（phases.PHASES）は人物の描き方で並んでいる。題材ごとに、アタリと仕上げで足す確かめの段を STEPS に持ち、
工程の表そのものは変えない（工程の数を勝手に変えない。足す段は確かめの項目として phase_items に渡す）。
"""
from __future__ import annotations

# 題材ごとに、工程（phases.PHASES の名前）で足す確かめの段。値は phase_items.KEYWORDS の項目名
STEPS = {
    "building": {"アタリ": ["建物の縦線", "遠近の収束"], "線画": ["窓の並び"], "仕上げ": ["建物の縦線", "遠近の収束"]},
    "interior": {"アタリ": ["建物の縦線", "遠近の収束"], "仕上げ": ["建物の縦線", "遠近の収束"]},
    "landscape": {"アタリ": ["画角", "空と地面"], "下塗り": ["空と地面"], "仕上げ": ["空と地面"]},
    "background": {"アタリ": ["画角", "空と地面", "人数"], "仕上げ": ["空と地面", "人数"]},
    "vehicle": {"アタリ": ["車輪の数"], "仕上げ": ["車輪の数", "タイヤの丸み", "左右対称"]},
    "animal": {"アタリ": ["足"], "仕上げ": ["足"]},
    "object": {"アタリ": ["物の数"], "仕上げ": ["物の数", "調べた項目"]},
    "text": {"線画": ["文字"], "仕上げ": ["文字"]},
    "pattern": {"線画": ["模様"], "仕上げ": ["模様"]},
    "unknown": {"アタリ": ["調べた項目"], "仕上げ": ["調べた項目"]},
}


def steps(kind: str, phase: str) -> list[str]:
    """題材と工程から、足す確かめの段。人物と、段の無い工程は空"""
    return list(STEPS.get(kind, {}).get(phase, []))


def regions(image) -> dict:
    """空・地面・主役の面（PIL の L のマスク）。空は上の縁につながる、明るく滑らかな面。地面は地平線より下で主役でない面。
    主役は明るさのシルエットの一番大きい塊（phase_tools）。読めない面は None"""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    from atelier.ai import phase_tools as pt
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    lum = a.mean(axis=2)
    grad = np.hypot(ndimage.sobel(lum, axis=0), ndimage.sobel(lum, axis=1))
    smooth = grad <= max(float(np.percentile(grad, 60)), 1.0)
    lab, _n = ndimage.label(smooth)
    top = set(np.unique(lab[0])) - {0}
    sky = np.isin(lab, list(top)) if top else np.zeros((h, w), bool)
    if sky.mean() < 0.03:
        sky = None
    subject = None
    got = pt._components(image)
    if got is not None and got[2]:
        lab2, sizes, big = got
        if sizes[big - 1] < 0.8 * lab2.size:
            subject = lab2 == big
    hz = pt.horizon(image)
    ground = None
    if hz.get("readable"):
        ground = np.zeros((h, w), bool)
        ground[hz["row"]:] = True
        if subject is not None:
            ground &= ~subject
        if sky is not None:
            ground &= ~sky
        if ground.mean() < 0.03:
            ground = None

    def img(m):
        return None if m is None else Image.fromarray((m * 255).astype("uint8"))
    return {"sky": img(sky), "ground": img(ground), "subject": img(subject)}
