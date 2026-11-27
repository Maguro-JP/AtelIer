"""描くための道具: ブラシ・色・柄・図形。

AI（精度優先の工程）が、模型の描き直しだけに頼らず、道具の機能で描くための
決まった描き方をする道具一式。どれも純粋な加工で、同じ入力には同じ結果を返し、
新しい物を勝手に足したり消したりはしない。使う側（工程）が「どこに・何色で」を決め、
道具は「どう描くか」だけを引き受ける。

道具の一覧は TOOLS（名前 → 説明と関数）。工程や将来の計画側は tool_list() で
使える道具を数えられる。
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

BRUSHES = ("pen", "gpen", "pencil", "watercolor")
PATTERNS = ("dots", "stripes", "diagonal", "check", "halftone")


def _overlay(image):
    return Image.new("RGBA", image.size, (0, 0, 0, 0))


def _path_points(points, steps_per_unit=2.0):
    """点の並びを、区間ごとに細かく割った点の並びにする（線が点の間をまっすぐつなぐ）"""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dist = max(abs(x1 - x0), abs(y1 - y0))
        n = max(2, int(dist * steps_per_unit))
        for j in range(1, n + 1):
            out.append((x0 + (x1 - x0) * j / n, y0 + (y1 - y0) * j / n))
    return out


def _brush_profile(kind, t):
    """線の位置 t（0〜1）での太さの倍率。Gペンは入りと抜きで細く、真ん中で太い"""
    if kind == "gpen":
        return float(np.sin(np.pi * min(1.0, max(0.0, t))) ** 0.7) * 0.85 + 0.15
    return 1.0


def stroke(image, points, color=(30, 30, 30), width=3, kind="pen", seed=0):
    """ブラシで線を引く。points は [(x, y), ...]。kind は BRUSHES のどれか。
    pen: 均一な太さ。gpen: 入り抜きと膨らみのある太さ。pencil: 薄くざらついた線。
    watercolor: 透明で縁の濃い線（塗りの輪郭向き）。色は (r, g, b)"""
    if kind not in BRUSHES:
        raise ValueError(f"知らないブラシです: {kind}")
    if len(points) < 2 or width <= 0:
        return image
    ov = _overlay(image)
    dr = ImageDraw.Draw(ov)
    dense = _path_points(points)
    n = len(dense)
    rng = np.random.default_rng(seed)
    for j, (x, y) in enumerate(dense):
        t = j / max(1, n - 1)
        r = max(0.4, width * _brush_profile(kind, t) / 2)
        if kind == "pencil":
            # 鉛筆: 薄い芯で何度か撫でた質感（決まった種でずらす）
            for _ in range(3):
                dx, dy = rng.normal(0, r * 0.35, 2)
                dr.ellipse([x - r + dx, y - r + dy, x + r + dx, y + r + dy],
                           fill=color + (70,))
        elif kind == "watercolor":
            dr.ellipse([x - r, y - r, x + r, y + r], fill=color + (60,))
        else:
            dr.ellipse([x - r, y - r, x + r, y + r], fill=color + (255,))
    if kind == "watercolor":
        # 水彩: 内側をもう一度薄く撫でて、縁だけ濃く残す
        for j, (x, y) in enumerate(dense):
            t = j / max(1, n - 1)
            r = max(0.3, width * _brush_profile(kind, t) / 2 * 0.55)
            dr.ellipse([x - r, y - r, x + r, y + r], fill=color + (40,))
    base = image.convert("RGBA")
    base.alpha_composite(ov)
    return base.convert(image.mode if image.mode in ("RGB", "L") else "RGB")


def draw_line(image, p0, p1, color=(30, 30, 30), width=3, kind="pen"):
    """図形: 直線（ブラシで引く）"""
    return stroke(image, [p0, p1], color=color, width=width, kind=kind)


def draw_curve(image, points, color=(30, 30, 30), width=3, kind="pen"):
    """図形: 曲線。点の並びを Catmull-Rom 補間でなめらかにつないでブラシで引く"""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        return image
    ext = [pts[0]] + pts + [pts[-1]]
    curve = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for j in range(12):
            t = j / 12
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            curve.append((x, y))
    curve.append(pts[-1])
    return stroke(image, curve, color=color, width=width, kind=kind)


def draw_circle(image, center, radius, color=(30, 30, 30), width=3, fill=None, kind="pen"):
    """図形: 円。fill を色にすると中を塗る。輪郭はブラシで引く"""
    cx, cy = center
    if fill is not None:
        ov = _overlay(image)
        ImageDraw.Draw(ov).ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                                   fill=fill + (255,))
        base = image.convert("RGBA")
        base.alpha_composite(ov)
        image = base.convert(image.mode if image.mode in ("RGB", "L") else "RGB")
    if width > 0:
        ring = [(cx + radius * float(np.cos(a)), cy + radius * float(np.sin(a)))
                for a in np.linspace(0, 2 * np.pi, max(24, int(radius * 4)))]
        image = stroke(image, ring + [ring[0]], color=color, width=width, kind=kind)
    return image


def _mask_array(mask):
    return np.asarray(mask.convert("L")) > 0


def fill_region(image, mask, color):
    """色: 囲み（L の絵）の中をベタ塗りする"""
    m = _mask_array(mask)
    a = np.asarray(image.convert("RGB")).astype(float)
    a[m] = np.array(color, dtype=float)
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def gradient_fill(image, mask, color_top, color_bottom, horizontal=False):
    """色: 囲みの中をグラデーションで塗る（縦、または横）"""
    m = _mask_array(mask)
    h, w = m.shape
    if horizontal:
        t = np.tile((np.arange(w, dtype=float) / max(1, w - 1))[None, :], (h, 1))
    else:
        t = np.tile((np.arange(h, dtype=float) / max(1, h - 1))[:, None], (1, w))
    top = np.array(color_top, dtype=float)
    bot = np.array(color_bottom, dtype=float)
    grad = top[None, None, :] * (1 - t[..., None]) + bot[None, None, :] * t[..., None]
    a = np.asarray(image.convert("RGB")).astype(float)
    a[m] = grad[m]
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def tint(image, mask, color, strength=0.35):
    """色: 囲みの中の明るさを保ったまま、色味を指定の色へ寄せる"""
    m = _mask_array(mask)
    a = np.asarray(image.convert("RGB")).astype(float)
    lum = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2])[..., None]
    c = np.array(color, dtype=float)
    c_lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    shaded = c[None, None, :] * (lum / max(1.0, c_lum))
    out = a * (1 - strength) + shaded * strength
    a[m] = out[m]
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def pattern_fill(image, mask, kind="dots", fg=(60, 60, 60), bg=None, scale=12):
    """柄: 囲みの中を柄で塗る。kind は PATTERNS のどれか。
    dots: 水玉。stripes: 横の縞。diagonal: 斜めの縞。check: チェック。
    halftone: 網点（下の絵の明るさで点の大きさが変わる。bg は使わない）。
    bg を None にすると、柄の地は元の絵のまま（fg だけを重ねる）"""
    if kind not in PATTERNS:
        raise ValueError(f"知らない柄です: {kind}")
    m = _mask_array(mask)
    a = np.asarray(image.convert("RGB")).astype(float)
    h, w = m.shape
    yy, xx = np.mgrid[0:h, 0:w]
    s = max(2, int(scale))
    if kind == "dots":
        cx = (xx % s) - s / 2
        cy = (yy % s) - s / 2
        on = (cx * cx + cy * cy) <= (s * 0.28) ** 2
    elif kind == "stripes":
        on = (yy % s) < s / 2
    elif kind == "diagonal":
        on = ((xx + yy) % s) < s / 2
    elif kind == "check":
        on = ((xx // s) + (yy // s)) % 2 == 0
    else:  # halftone: 下の絵が暗い所ほど大きな点
        lum = (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]) / 255.0
        cx = (xx % s) - s / 2
        cy = (yy % s) - s / 2
        r = (1.0 - lum) * s * 0.45
        on = (cx * cx + cy * cy) <= r * r
    if bg is not None:
        a[m] = np.array(bg, dtype=float)
    a[m & on] = np.array(fg, dtype=float)
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


TOOLS = {
    "stroke": ("ブラシで線を引く（pen/gpen/pencil/watercolor）", stroke),
    "draw_line": ("直線を引く", draw_line),
    "draw_curve": ("曲線を引く", draw_curve),
    "draw_circle": ("円を描く", draw_circle),
    "fill_region": ("囲みの中をベタ塗りする", fill_region),
    "gradient_fill": ("囲みの中をグラデーションで塗る", gradient_fill),
    "tint": ("囲みの中の色味を寄せる", tint),
    "pattern_fill": ("囲みの中を柄で塗る（水玉・縞・チェック・網点）", pattern_fill),
}


def tool_list():
    """使える道具の一覧（名前と説明）。AI が道具を選ぶときに見る"""
    return [(name, desc) for name, (desc, _fn) in TOOLS.items()]


def apply(name, image, **kw):
    """名前で道具を使う。知らない名前は ValueError"""
    if name not in TOOLS:
        raise ValueError(f"知らない道具です: {name}")
    return TOOLS[name][1](image, **kw)
