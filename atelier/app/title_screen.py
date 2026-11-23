"""タイルの画面（起動したときに出るタイトルの画面）。AtelIer が、描く画面と、拡張の置き場に入ったデザイナーを束ねる入口。

並べるのは、押せば必ず中身に入れる物だけにする。
- AtelIer の描く画面（ペイント）
- 拡張の置き場から読めたデザイナー（atelier/extensions.py の load_dropins）
- 一覧（atelier/extension_catalog.py）にあって Release に拡張だけの Setup（名前に Extension と Setup を含む .exe）のある、
  まだ入っていないデザイナーは、小さな「入れる」のタイルにする。押すと、その Setup の取り方を窓の下に出し、Release のページを開く。
  Python ごと入った単体の Setup しか無いデザイナーは出さない（AtelIer を使う人は拡張だけを入れる）。入っていない物を大きなタイルにすると、中身の無い入口になるため。

絵は extension.json の "image"、名前は "title"、一言は "tagline" から読む。無いときは名前の頭文字で絵を作る。
実在の物の写しは使わない。描く画面の絵は、ロゴの字と筆の跡をその場で描く（配る版に docs/images は入らないため）。

デザイナーに入るときは、拡張に open(window) があればそれを呼ぶ。無ければ、拡張が付けたときに増えた物を
モード → 欄 → メニューの最初の操作 の順に開く（extensions.attach_all が window.extension_parts に覚える）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QRectF, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from atelier.ui import logo

# 色は利用者の好み（白・黒・赤・オレンジ）と、ロゴの差し色（atelier/assets/logo.svg）にそろえる
BLACK = "#141416"
CARD = "#1f1f23"
WHITE = "#f4f4f5"
GRAY = "#8e8e95"
RED = "#e5322d"
ORANGE = "#ff5a1f"

KEY_LAST = "title/last"   # 最後に使ったタイル
KEY_SKIP = "title/skip"   # 「次からこの画面を出さない」
PAINT = "paint"


@dataclass
class Tile:
    key: str
    title: str
    tagline: str
    kind: str                    # "paint" | "designer" | "install"
    image: str = ""
    tip: str = ""
    extension: object = field(default=None, repr=False)
    url: str = ""


def tiles() -> list[Tile]:
    """並べるタイル。描く画面、入っているデザイナー、入れられるデザイナーの順"""
    from atelier import extension_catalog as cat
    from atelier import extensions
    out = [Tile(PAINT, logo.NAME, "描く・塗る・AI に直させる", "paint",
                tip="AtelIer の描く画面に入ります。ペン・レイヤー・赤ペン・AI の欄があります")]
    loaded = set()
    for ext in extensions.registered():
        info = extensions.dropin_info(ext.name)
        loaded.add(ext.name)
        if info.get("dropin"):
            loaded.add(info["dropin"])
        title = info.get("title") or ext.name
        out.append(Tile("ext:" + ext.name, title, info.get("tagline") or "デザイナー", "designer",
                        image=info.get("image", ""), extension=ext,
                        tip=f"{title} の画面に入ります（AtelIer の中で開きます）"))
    for d in cat.DESIGNERS:
        if d.installer and d.name not in loaded and d.dropin not in loaded:
            out.append(Tile("install:" + d.key, d.name, "入れる", "install",
                            url=f"https://github.com/{d.repo}/releases/latest",
                            tip=f"{d.name} はまだ入っていません。押すと、拡張だけの Setup の取り方を出し、Release のページを開きます"))
    return out


def install_steps(tile: Tile) -> str:
    """「入れる」を押したときに出す、拡張だけの Setup の取り方"""
    return (f"{tile.title} の Release のページを開きました。添付の中から、名前に Extension と Setup を含む .exe"
            f"（拡張だけの Setup）を取って開いてください。Python ごと入った単体の Setup.exe は取りません。"
            f"入れたあとでアプリを開き直すと、ここに大きなタイルで出ます")


def _initials(name: str) -> str:
    """名前の頭文字（CharacterDesigner なら CD、3DDesigner なら 3D）"""
    caps = [c for c in name if c.isupper() or c.isdigit()]
    return ("".join(caps[:2]) or name[:2]).upper()


def tile_picture(tile: Tile, size: QSize) -> QPixmap:
    """タイルの絵。image があればそれを、無ければその場で描く"""
    pix = QPixmap(size)
    pix.fill(QColor(CARD))
    if tile.image:
        img = QPixmap(tile.image)
        if not img.isNull():
            # 切らずに収める。横長のタイルに正方形の絵を広げて入れると、絵の端（ロゴの字など）が切れたため
            scaled = img.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p = QPainter(pix)
            p.drawPixmap((size.width() - scaled.width()) // 2, (size.height() - scaled.height()) // 2, scaled)
            p.end()
            return pix
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    w, h = size.width(), size.height()
    g = QLinearGradient(0, 0, w, h)
    if tile.kind == "paint":
        g.setColorAt(0, QColor("#24242a"))
        g.setColorAt(1, QColor(BLACK))
        p.fillRect(pix.rect(), g)
        # 筆の跡: 赤からオレンジへ太さの変わる 3 本
        for i, (col, width) in enumerate(((RED, 0.09), (ORANGE, 0.06), (WHITE, 0.025))):
            path = QPainterPath()
            y = h * (0.30 + i * 0.17)
            path.moveTo(w * 0.08, y + h * 0.10)
            path.cubicTo(w * 0.35, y - h * 0.22, w * 0.62, y + h * 0.28, w * 0.92, y - h * 0.04)
            pen = QPen(QColor(col), max(2.0, h * width), Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.drawPath(path)
        _draw_wordmark(p, QRectF(0, h * 0.62, w, h * 0.34), h * 0.16)
    else:
        g.setColorAt(0, QColor(RED) if tile.kind == "designer" else QColor("#2a2a30"))
        g.setColorAt(1, QColor(ORANGE) if tile.kind == "designer" else QColor(CARD))
        p.fillRect(pix.rect(), g)
        p.setPen(QColor(WHITE))
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(h * (0.42 if tile.kind == "designer" else 0.36)))
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignCenter, _initials(tile.title))
    p.end()
    return pix


def _draw_wordmark(p: QPainter, rect: QRectF, px: float) -> None:
    """ロゴの字を、A と I だけ差し色で描く（atelier/ui/logo.py と同じ決まり）"""
    p.setFont(logo.wordmark_font(px))
    fm = p.fontMetrics()
    total = sum(fm.horizontalAdvance(c) for c in logo.NAME)
    x = rect.center().x() - total / 2
    y = rect.center().y() + fm.ascent() / 2 - fm.descent() / 2
    for c in logo.NAME:
        p.setPen(QColor(ORANGE if c in logo.ACCENT_LETTERS else WHITE))
        p.drawText(int(x), int(y), c)
        x += fm.horizontalAdvance(c)


class TileButton(QToolButton):
    """名前・絵・一言のタイル。説明は中に書かず、ツールチップに出す"""

    def __init__(self, tile: Tile, big: bool, parent=None):
        super().__init__(parent)
        self.tile = tile
        pic = QSize(240, 140) if big else QSize(120, 70)
        self.setIcon(tile_picture(tile, pic))
        self.setIconSize(pic)
        self.setText(tile.title + ("\n" + tile.tagline if tile.tagline else ""))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setToolTip(tile.tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(tile.title)
        if tile.kind == "paint":
            # 名前の「AtelIer」も、I が l に見えないよう I に横棒のある書体にする（atelier/ui/logo.py）
            self.setFont(logo.wordmark_font(15 if big else 12))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pad = 14 if big else 8
        self.setFixedSize(pic.width() + pad * 2, pic.height() + (64 if big else 48))
        self.setStyleSheet(
            f"QToolButton {{ background:{CARD}; color:{WHITE}; border:2px solid #2c2c32; border-radius:10px;"
            f" padding:{pad}px; font-size:{14 if big else 12}px; }}"
            f"QToolButton:hover, QToolButton:focus {{ border-color:{ORANGE}; }}"
            f"QToolButton:pressed {{ background:#2a2a30; }}"
            f"QToolButton[last=\"true\"] {{ border-color:{RED}; }}")


class TitleScreen(QDialog):
    """起動したときのタイトルの画面。押したタイルの key を self.picked に入れて閉じる"""

    def __init__(self, parent=None, last: str = "", skip: bool = False):
        super().__init__(parent)
        self.setWindowTitle(logo.NAME)
        self.setObjectName("titleScreen")
        self.setStyleSheet(f"QDialog#titleScreen {{ background:{BLACK}; }} QLabel {{ color:{WHITE}; }}"
                           f"QCheckBox {{ color:{GRAY}; }}")
        self.picked = ""
        self.picked_tile: Tile | None = None
        self.buttons: list[TileButton] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 14)
        head = QLabel(f'<span style="font-size:44px">{logo.wordmark_html(ORANGE, WHITE)}</span>')
        head.setAlignment(Qt.AlignCenter)
        head.setTextFormat(Qt.RichText)
        sub = QLabel("使う物を選んでください")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color:{GRAY}; font-size:14px;")
        root.addWidget(head)
        root.addWidget(sub)
        all_tiles = tiles()
        big = [t for t in all_tiles if t.kind != "install"]
        small = [t for t in all_tiles if t.kind == "install"]
        area = self.area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setStyleSheet(f"QScrollArea, QScrollArea > QWidget > QWidget {{ background:{BLACK}; }}"
                           f"QScrollBar:vertical {{ background:{BLACK}; width:10px; margin:0; }}"
                           f"QScrollBar::handle:vertical {{ background:#3a3a42; border-radius:5px; min-height:30px; }}"
                           "QScrollBar::add-line, QScrollBar::sub-line { height:0; }"
                           "QScrollBar::add-page, QScrollBar::sub-page { background:none; }")
        inner = QWidget()
        col = QVBoxLayout(inner)
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.big_buttons = [self._button(t, True) for t in big]
        col.addLayout(self.grid)
        if small:
            more = QLabel("入れられるデザイナー")
            more.setStyleSheet(f"color:{GRAY}; font-size:12px; margin-top:10px;")
            more.setAlignment(Qt.AlignCenter)
            col.addWidget(more)
            row = QHBoxLayout()
            row.addStretch(1)
            for t in small:
                row.addWidget(self._button(t, False))
            row.addStretch(1)
            col.addLayout(row)
        # 「入れる」を押したときの答え（取り方）を出す所。押すまでは空で、場所も取らない
        self.install_hint = QLabel("")
        self.install_hint.setWordWrap(True)
        self.install_hint.setAlignment(Qt.AlignCenter)
        self.install_hint.setStyleSheet(f"color:{WHITE}; font-size:12px; margin-top:6px;")
        self.install_hint.hide()
        col.addWidget(self.install_hint)
        col.addStretch(1)
        area.setWidget(inner)
        root.addWidget(area, 1)
        foot = QHBoxLayout()
        self.dont_show = QCheckBox("次からこの画面を出さない")
        self.dont_show.setChecked(skip)
        self.dont_show.setToolTip("次の起動から、最後に使った物にそのまま入ります。「ファイル」の「タイルの画面…」でまた出せます")
        close = QPushButton("閉じる")
        close.setToolTip("描く画面に入ります（選んだのと同じです）")
        close.setStyleSheet(f"QPushButton {{ background:{CARD}; color:{WHITE}; border:1px solid #3a3a42; border-radius:6px;"
                            f" padding:6px 18px; }} QPushButton:hover {{ border-color:{ORANGE}; }}")
        close.clicked.connect(lambda: self._pick(big[0]))
        foot.addWidget(self.dont_show)
        foot.addStretch(1)
        foot.addWidget(close)
        root.addLayout(foot)
        for b in self.buttons:
            if b.tile.key == last:
                b.setProperty("last", True)
                b.style().unpolish(b)
                b.style().polish(b)
                b.setFocus()
        self._columns = 0
        self._relayout()
        self.resize(self._fit_size())

    def _button(self, t: Tile, big: bool) -> TileButton:
        b = TileButton(t, big, self)
        b.clicked.connect(lambda _=False, tile=t: self._pick(tile))
        self.buttons.append(b)
        return b

    def _fit_size(self) -> QSize:
        """親の窓（無ければ画面）に収まる大きさ。小さい画面ではスクロールで見せる"""
        host = self.parentWidget()
        avail = host.size() if host is not None and host.isVisible() else (
            self.screen().availableSize() if self.screen() else QSize(1280, 800))
        n = max(1, len(self.big_buttons))
        cols = min(n, 4)
        tw = self.big_buttons[0].width() if self.big_buttons else 270
        th = self.big_buttons[0].height() if self.big_buttons else 210
        rows = (n + cols - 1) // cols
        extra = 150 if len(self.buttons) > len(self.big_buttons) else 0   # 「入れられるデザイナー」の段
        want = QSize(max(cols * (tw + 16), 560) + 80, rows * (th + 16) + 200 + extra)
        return QSize(min(want.width(), max(360, avail.width() - 40)), min(want.height(), max(320, avail.height() - 40)))

    def _relayout(self):
        """横幅に入るだけの列で並べ直す（狭い窓で横にはみ出さない）"""
        if not self.big_buttons:
            return
        tw = self.big_buttons[0].width() + self.grid.spacing()
        cols = max(1, min(4, len(self.big_buttons), (self.width() - 60) // tw))
        if cols == self._columns:
            return
        self._columns = cols
        for b in self.big_buttons:
            self.grid.removeWidget(b)
        for i, b in enumerate(self.big_buttons):
            self.grid.addWidget(b, i // cols, i % cols, Qt.AlignCenter)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _pick(self, tile: Tile):
        if tile.kind == "install":
            # 入れる物は窓を閉じずに、取り方を出して Release のページを開く（押した答えが返り、ほかのタイルもそのまま選べる）
            self.install_hint.setText(install_steps(tile))
            self.install_hint.show()
            # 出した取り方が窓の下で切れないよう、並べ直したあとでそこまで送る
            QTimer.singleShot(0, lambda: self.area.ensureWidgetVisible(self.install_hint))
            QDesktopServices.openUrl(QUrl(tile.url))
            return
        self.picked = tile.key
        self.picked_tile = tile
        self.accept()


def enter(window, tile: Tile | None) -> str:
    """選んだタイルの画面に入る。何を開いたかを返す（"paint" | "open" | "mode" | "dock" | "menu" | "none"）"""
    if tile is None or tile.kind == "paint":
        return "paint"
    ext = tile.extension
    opener: Callable | None = getattr(ext, "open", None)
    if callable(opener):
        opener(window)
        return "open"
    parts = (getattr(window, "extension_parts", {}) or {}).get(getattr(ext, "name", ""), {})
    for key in parts.get("modes", []):
        if hasattr(window, "set_mode"):
            window.set_mode(key)
            return "mode"
    for dock in parts.get("docks", []):
        dock.show()
        dock.raise_()
        return "dock"
    for menu_action in parts.get("menus", []):
        first = next((a for a in menu_action.menu().actions() if not a.isSeparator() and a.isEnabled()
                      and a.menu() is None), None)
        if first is not None:
            first.trigger()
            return "menu"
    if hasattr(window, "notify"):
        window.notify(f"{tile.title} は、開く画面を持っていません", "info", "メニューから使ってください")
    return "none"


def find_tile(key: str) -> Tile | None:
    return next((t for t in tiles() if t.key == key and t.kind != "install"), None)


def open_title(window, ask=None, on_start: bool = False) -> str:
    """タイルの画面を出し、選んだ物に入る。on_start で「次から出さない」なら、窓を出さずに最後に使った物に入る。
    ask は試験の口（窓を受け取り、exec の代わりに呼ぶ）"""
    store = getattr(window, "layout_store", None) or QSettings("AtelIer", "atelier")
    last = str(store.value(KEY_LAST, "") or "")
    skip = str(store.value(KEY_SKIP, "0")) in ("1", "true", "True")
    if on_start and skip:
        tile = find_tile(last) or find_tile(PAINT)
        return enter(window, tile)
    dlg = TitleScreen(window, last, skip)
    window.title_screen = dlg
    done = ask(dlg) if ask else dlg.exec()
    store.setValue(KEY_SKIP, 1 if dlg.dont_show.isChecked() else 0)
    if not done or dlg.picked_tile is None:
        return "paint"   # 閉じたときは描く画面のまま（覚えた物は変えない）
    store.setValue(KEY_LAST, dlg.picked)
    return enter(window, dlg.picked_tile)
