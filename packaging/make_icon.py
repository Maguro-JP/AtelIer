"""AtelIer のアプリのアイコンを、図形と文字だけから作る台本。

ロゴ（atelier/ui/logo.py）の決まりに合わせ、A と I（AI）を差し色のオレンジにする。
I はペンの形にして、ペン先から赤い線を引かせ、ペイントソフトだと分かるようにした。
地は黒、ペンの口金は白。小さい大きさ（24 画素以下）では細部が潰れるので、
ペンの口金と線の細さを省いた形で別に描き、どの大きさも同じ台本から作り直せるようにしている。

使い方: python3 packaging/make_icon.py [出力のフォルダ]（既定は atelier/ai/icon）
作る物: app.png（1024 画素）、app.ico（16・24・32・48・64・128・256 画素）、sizes/<n>.png（確かめ用）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "atelier" / "ai" / "icon"
SIZES = [16, 24, 32, 48, 64, 128, 256]

BLACK = (23, 24, 27, 255)      # logo.svg の地と同じ
ORANGE = (255, 90, 31, 255)    # ロゴの差し色
RED = (229, 50, 45, 255)       # ロゴの下線の色
WHITE = (255, 255, 255, 255)
FONTS = ["/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Helvetica.ttc"]


def _font(px: int) -> ImageFont.FreeTypeFont:
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, px)
    return ImageFont.load_default(px)


def draw(size: int) -> Image.Image:
    """size 画素のアイコンを描く。4 倍で描いてから縮め、縁を滑らかにする"""
    small = size <= 24
    s = size * 4
    u = s / 256                     # 256 画素を基準にした単位
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int((40 if small else 52) * u), fill=BLACK)

    # 赤い線（ペン先から左へ引いた筆跡）。下に置いて A の足の下を通す
    y = 204 * u
    w = (16 if small else 12) * u
    d.rounded_rectangle([36 * u, y - w / 2, 196 * u, y + w / 2], radius=int(w / 2), fill=RED)

    # A（文字）
    f = _font(int((190 if small else 176) * u))
    box = d.textbbox((0, 0), "A", font=f)
    ax = (18 if small else 28) * u - box[0]
    ay = (196 if small else 190) * u - box[3]
    d.text((ax, ay), "A", font=f, fill=ORANGE)

    # I（ペン）。縦の軸、白い口金、尖ったペン先
    x0, x1 = (178 if small else 182) * u, (226 if small else 222) * u
    top = (30 if small else 34) * u
    cone = (150 if small else 146) * u
    tip = 204 * u
    d.rounded_rectangle([x0, top, x1, cone], radius=int(8 * u), fill=ORANGE)
    if not small:
        d.rectangle([x0, cone - 22 * u, x1, cone], fill=WHITE)
    cx = (x0 + x1) / 2
    d.polygon([(x0, cone), (x1, cone), (cx + 4 * u, tip - 6 * u), (cx, tip), (cx - 4 * u, tip - 6 * u)],
              fill=WHITE if not small else ORANGE)
    if not small:
        d.ellipse([cx - 6 * u, tip - 12 * u, cx + 6 * u, tip], fill=RED)   # ペン先の色（線の色と同じ）
    return im.resize((size, size), Image.LANCZOS)


def main(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    big = draw(1024)
    big.save(out / "app.png", optimize=True)
    images = {n: draw(n) for n in SIZES}
    # .ico は大きさごとに別に描いた絵を入れる（縮めた 1 枚だと 16 画素で線が消える）
    images[256].save(out / "app.ico", format="ICO", sizes=[(n, n) for n in SIZES],
                     append_images=[images[n] for n in SIZES if n != 256])
    return [out / "app.png", out / "app.ico"]


def contact_sheet(path: Path) -> Path:
    """確かめ用に、全部の大きさを等倍と 4 倍で並べた写しを作る"""
    pad = 12
    w = sum(n for n in SIZES) + pad * (len(SIZES) + 1)
    sheet = Image.new("RGBA", (max(w, 1100), 256 + 4 * 64 + pad * 3), (240, 240, 240, 255))
    x = pad
    for n in SIZES:
        sheet.alpha_composite(draw(n), (x, pad))
        x += n + pad
    x = pad
    for n in (16, 24, 32, 48):
        z = draw(n).resize((n * 4, n * 4), Image.NEAREST)
        sheet.alpha_composite(z, (x, 256 + pad * 2))
        x += n * 4 + pad
    sheet.save(path)
    return path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    for p in main(target):
        print(p)
