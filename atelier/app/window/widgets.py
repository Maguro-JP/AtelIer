"""ウィンドウで使う小さな部品（右クリックのメニュー、ナビゲーター、参考の絵、欄の見出し、赤ペンの指示の欄）"""
from __future__ import annotations

from PySide6.QtWidgets import QDockWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QWidget
from pathlib import Path


def exec_once(menu, pos):
    """右クリックのたびに作るメニューを開き、閉じたら捨てる。窓を親にして作るので、捨てないと右クリックのたびに
    メニュー（キャンバスでは子のメニューを合わせて 20 余り）が窓に溜まり続けた（50 回で 1,000 を超えた）。
    押した項目の処理は exec の中で済んでいるので、閉じたあとに捨ててよい"""
    try:
        return menu.exec(pos)
    finally:
        menu.deleteLater()


class Navigator(QLabel):
    """キャンバス全体の縮小図。今見えている所を四角で示し、押した所を真ん中に出す。四角は引いて動かせる。
    描くたびに作り直すと重いので、絵は変わってから少し待って作る（四角はすぐ描き直す）"""

    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(120)
        self.setToolTip("赤い四角が今見えている所です。押すか四角を引くと、表示する場所が動きます")
        self._grab = None   # 四角を引いているとき、押した所と四角の中心のずれ
        from PySide6.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.redraw)
        canvas.changed.connect(self.timer.start)
        canvas.history_changed.connect(self.timer.start)
        canvas.horizontalScrollBar().valueChanged.connect(self.update)
        canvas.verticalScrollBar().valueChanged.connect(self.update)
        canvas.zoomed.connect(self.update)

    def redraw(self):
        if not self.isVisible() or not self.canvas.layers:
            return
        img = self.canvas.flatten().scaled(max(1, self.width() - 8), max(1, self.height() - 8), Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(img))

    def showEvent(self, e):
        super().showEvent(e)
        self.redraw()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.timer.start()

    def _frame(self):
        """縮小図の置き場（左上と倍率）。絵がまだ無ければ None"""
        pm = self.pixmap()
        w, h = self.canvas.size_px()
        if pm is None or pm.isNull() or not w or not h:
            return None
        return (self.width() - pm.width()) / 2, (self.height() - pm.height()) / 2, pm.width() / w, pm.height() / h

    def view_rect(self):
        """今キャンバスに見えている所を、縮小図の上の四角で返す"""
        from PySide6.QtCore import QRectF
        f = self._frame()
        if f is None:
            return None
        x0, y0, sx, sy = f
        r = self.canvas.mapToScene(self.canvas.viewport().rect()).boundingRect() & self.canvas.scene().sceneRect()
        return QRectF(x0 + r.x() * sx, y0 + r.y() * sy, r.width() * sx, r.height() * sy)

    def paintEvent(self, e):
        super().paintEvent(e)
        r = self.view_rect()
        if r is None or r.isEmpty():
            return
        from PySide6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        p.setPen(QPen(QColor(230, 40, 40), 2))
        p.drawRect(r.adjusted(1, 1, -1, -1))
        p.end()

    def _center_at(self, pos):
        f = self._frame()
        if f is None:
            return
        x0, y0, sx, sy = f
        w, h = self.canvas.size_px()
        self.canvas.centerOn(min(max((pos.x() - x0) / sx, 0), w), min(max((pos.y() - y0) / sy, 0), h))
        self.update()

    def mousePressEvent(self, e):
        r = self.view_rect()
        pos = e.position()
        if r is not None and r.contains(pos):
            self._grab = pos - r.center()   # 四角の中を押したら、押した所がずれないように引く
        else:
            self._grab = pos - pos
            self._center_at(pos)

    def mouseMoveEvent(self, e):
        if self._grab is not None and e.buttons() & Qt.LeftButton:
            self._center_at(e.position() - self._grab)

    def mouseReleaseEvent(self, e):
        self._grab = None


class Reference(QLabel):
    """参考画像。押すか画像を落とすと読み込み、欄の大きさに合わせて縮めて見せる"""

    def __init__(self):
        super().__init__("押すか画像をここへ落とすと\n参考画像を置けます")
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("cardMeta")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.image: QPixmap | None = None

    def load(self, path: str):
        pm = QPixmap(path)
        if not pm.isNull():
            self.image = pm
            self.path = path
            self.setToolTip(Path(path).name)
            self._fit()

    def _fit(self):
        if self.image is not None:
            self.setPixmap(self.image.scaled(self.width() - 8, self.height() - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(self, "参考画像", "", "画像 (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.load(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.load(urls[0].toLocalFile())


class PanelTitle(QWidget):
    """欄の見出し。畳む（最小化）・別ウィンドウにする・隠す の 3 つのボタンを持つ。見出しをダブルクリックしても畳める"""

    def __init__(self, dock: "QDockWidget"):
        super().__init__(dock)
        self.dock = dock
        self.collapsed = False
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 2, 2, 2)
        row.setSpacing(2)
        self.label = QLabel(dock.windowTitle())
        row.addWidget(self.label)
        row.addStretch()
        place = QPushButton("⋯")
        place.setToolTip("置き場所（左・右・下・上・別ウィンドウ）")
        place.setFixedSize(22, 20)
        place.setFlat(True)
        place.clicked.connect(lambda: self.place_menu().exec(place.mapToGlobal(place.rect().bottomLeft())))
        row.addWidget(place)
        for text, tip, fn in (("▁", "畳む（見出しだけにする）", self.toggle), ("⧉", "別ウィンドウにする・戻す", self.float_),
                              ("✕", "隠す（「ウィンドウ」メニューで戻せます）", dock.hide)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedSize(22, 20)
            b.setFlat(True)
            b.clicked.connect(fn)
            row.addWidget(b)
            if text == "▁":
                self.collapse_button = b

    def place_menu(self):
        """欄の置き場所を選ぶメニュー。どの欄も左右・下・上と別ウィンドウに置ける"""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        mw = self.dock.parent()
        for label, area in (("左に置く", Qt.LeftDockWidgetArea), ("右に置く", Qt.RightDockWidgetArea),
                            ("下に置く", Qt.BottomDockWidgetArea), ("上に置く", Qt.TopDockWidgetArea)):
            menu.addAction(label, lambda area=area: mw.move_panel(self.dock, area))
        menu.addSeparator()
        menu.addAction("別ウィンドウにする", lambda: self.dock.setFloating(True))
        main = getattr(mw, "main", mw)
        if hasattr(main, "put_panel_in"):
            menu.addAction("新しいまとめた窓に入れる", lambda: main.put_panel_in(self.dock))
            for g in getattr(main, "groups", []):
                if g is not mw:
                    menu.addAction(f"{g.windowTitle()}に入れる", lambda g=g: main.put_panel_in(self.dock, g))
            if mw is not main:
                menu.addAction("元の窓に戻す", lambda: main.return_panel(self.dock))
        return menu

    def toggle(self):
        """畳む・広げる。中身を薄くしてから畳み、広げたら中身を濃くしていく（どこが畳まれたかを目で追える）。
        高さそのものは動かさない。中身の最小の高さより低くできず、動きの途中で止まった"""
        from atelier.ui.motion import fade_in, fade_out
        if not self.collapsed and self.dock.isFloating():
            return   # 別ウィンドウは畳まない（見出しだけの細い窓になり、どこにあるか分からなくなった）。窓の最小化を使う
        self.collapsed = not self.collapsed
        body = self.dock.widget()
        head = self.height() + 4
        if self.collapsed:
            def done():
                if not self.collapsed:
                    return   # 畳む途中で広げた
                self.dock.setMinimumHeight(0)   # 欄の最小の高さが中身の分（例: 256）に上がっていて、畳めなかった
                self.dock.setMaximumHeight(head)
            if body is not None:
                fade_out(body, then=done)
            else:
                done()
        else:
            self.dock.setMaximumHeight(16777215)
            self.dock.setMinimumHeight(80)
            if body is not None:
                fade_in(body)
        self.collapse_button.setText("▔" if self.collapsed else "▁")

    def expand(self):
        """畳んでいれば広げる。置き場所を変えた・別ウィンドウにした・タブにした欄が、見出しだけの細い帯のまま
        残ると、同じ所の欄（タブの相手）まで高さを奪われ、欄が消えたように見えた"""
        if self.collapsed:
            self.toggle()

    def float_(self):
        self.dock.setFloating(not self.dock.isFloating())

    def mouseDoubleClickEvent(self, e):
        self.toggle()


class NoteEdit(QLineEdit):
    """赤ペンの指示を書く欄。キャンバスの上に置くので、打ったキーを欄の外へ逃がさない。
    1 文字のショートカット（B、E、T など）、Space の手のひら、Delete、Ctrl+Z、Tab に文字を取られ、書けなかった"""

    def event(self, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.ShortcutOverride:
            if not (e.key() == Qt.Key_Escape and e.modifiers() & Qt.ShiftModifier):   # 非常停止（Shift+Esc）だけは効かせる
                e.accept()   # 受けると、帯やメニューのショートカットより先に、この欄にキーが来る
                return True
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            return True   # Tab で欄を離れない
        return super().event(e)

    def keyPressEvent(self, e):
        super().keyPressEvent(e)
        e.accept()   # 欄が使わなかったキーも、親のキャンバス（Space で手のひら、Delete で消す）へ渡さない



_BIG_ICON_STYLE = []


def _big_icon_style():
    """メニューの小さな絵を 48 画素で描くスタイル（アプリで 1 つ）"""
    if not _BIG_ICON_STYLE:
        from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

        class Big(QProxyStyle):
            def pixelMetric(self, metric, option=None, widget=None):
                return 48 if metric == QStyle.PM_SmallIconSize else super().pixelMetric(metric, option, widget)
        name = QApplication.style().name()
        style = Big(name) if name else Big()
        style.setParent(QApplication.instance())   # アプリが持つ（メニューと一緒に消えない）
        _BIG_ICON_STYLE.append(style)
    return _BIG_ICON_STYLE[0]
