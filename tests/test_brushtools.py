"""ブラシの見本の線・色の欄（数字・色の出方・自分のパレット・スポイト）・足した道具（スプレー・指先・文字・手ぶれ補正・左右対称）。
道具は窓の道具の帯を押して持ち替え、絵の上をマウスで押して動かして離す（本物と同じ経路）。画素が変わったかで確かめる"""
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ATELIER_CHECK", "off")
sys.path.insert(0, str(ROOT / ".cache" / "simple" / "lib"))
sys.path.insert(0, str(ROOT))

from atelier.ai.engine import Studio  # noqa: E402
from tests.test_chatdraw import FakePainter, FakeWords  # noqa: E402


def window():
    from PySide6.QtWidgets import QApplication
    from atelier.app.main_window import Window
    QApplication.instance() or QApplication([])
    w = Window(Studio(FakeWords(), FakePainter(), Path("/tmp")))
    w.resize(1400, 900)
    w.show()
    w.canvas.new_canvas(200, 200)
    w.canvas.set_zoom(1.0)
    return w


def drag(c, pts):
    """絵の座標の点の列を、ビューの上のマウスの押す・動かす・離すにして流す"""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    vp = c.viewport()
    at = [c.mapFromScene(x, y) for x, y in pts]
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, at[0])
    for p in at[1:]:
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF
        ev = QMouseEvent(QEvent.MouseMove, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication_send(vp, ev)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at[-1] if at else QPoint())


def QApplication_send(target, ev):
    from PySide6.QtWidgets import QApplication
    QApplication.sendEvent(target, ev)


def changed(before, after) -> int:
    return sum(1 for y in range(0, after.height(), 2) for x in range(0, after.width(), 2)
               if before.pixelColor(x, y) != after.pixelColor(x, y))


class BrushPreviewTest(unittest.TestCase):
    def test_preview_follows_size_color_opacity_and_hardness(self):
        w = window()
        pv = w.brush_preview
        if not w.panel_in_front("brushes"):
            w.toggle_panel("brushes")                                    # 欄の帯でブラシの欄を出す
        if w.tour is not None and w.tour.isVisible():
            w.tour.finish()
        self.assertTrue(pv.isVisibleTo(w))
        w.size_box.setValue(4)
        thin = pv.render(240, 56)
        w.size_box.setValue(30)
        thick = pv.render(240, 56)
        count = lambda im: sum(1 for y in range(im.height()) for x in range(im.width()) if im.pixelColor(x, y).alpha() > 40)
        self.assertGreater(count(thick), count(thin) * 2)               # 太さが見本に出る
        w.color_panel.set_color(__import__("PySide6.QtGui", fromlist=["QColor"]).QColor("#ff0000"))
        img = pv.render(240, 56)
        reds = [img.pixelColor(x, 28) for x in range(240) if img.pixelColor(x, 28).alpha() > 200]
        self.assertTrue(reds and all(c.red() > 200 and c.green() < 60 for c in reds[:5]))   # 色が見本に出る
        w.flow.setValue(30)
        faint = max(pv.render(240, 56).pixelColor(x, 28).alpha() for x in range(240))
        self.assertLess(faint, 120)                                      # 濃さが見本に出る
        w.flow.setValue(100)
        w.hardness.setValue(100)
        hard = pv.render(240, 56)
        w.hardness.setValue(0)
        soft = pv.render(240, 56)
        self.assertNotEqual(hard, soft)                                  # 硬さが見本に出る
        self.assertEqual(w.canvas.size, 30)                              # 見本を描いても太さは変えない

    def test_cursor_ring_matches_size(self):
        w = window()
        c = w.canvas
        w.tool_actions["pen"].trigger()
        w.size_box.setValue(40)
        from PySide6.QtCore import QPointF
        c._ring(QPointF(100, 100))
        self.assertAlmostEqual(c.cursor_ring.rect().width(), 40, delta=0.5)
        self.assertTrue(c.cursor_ring.isVisible())
        w.tool_actions["spray"].trigger()
        c._ring(QPointF(100, 100))
        self.assertAlmostEqual(c.cursor_ring.rect().width(), 80, delta=0.5)   # スプレーは太さが半径
        self.assertTrue(c.cursor_ring.isVisible())


class ColorPanelTest(unittest.TestCase):
    def test_numbers_hex_and_eyedropper_button(self):
        from PySide6.QtGui import QColor
        w = window()
        cp = w.color_panel
        cp.h_box.setValue(120)
        cp.s_box.setValue(100)
        cp.v_box.setValue(100)
        self.assertEqual(w.canvas.color.name(), "#00ff00")
        self.assertEqual(cp.hex.text(), "#00ff00")
        cp.set_color(QColor("#3d7bff"))
        self.assertEqual(cp.h_box.value(), QColor("#3d7bff").hsvHue())  # 色を変えると数字もそろう
        cp.eyedropper_wanted.emit()
        self.assertEqual(w.canvas.tool, "eyedropper")
        self.assertTrue(w.tool_actions["eyedropper"].isChecked())

    def test_palette_add_remove_save_load(self):
        from PySide6.QtGui import QColor
        w = window()
        cp = w.color_panel
        cp.set_color(QColor("#112233"))
        cp.add_to_palette()
        cp.add_to_palette("#abcdef")
        cp.add_to_palette("#abcdef")
        self.assertEqual(cp.mine, ["#112233", "#abcdef"])
        self.assertEqual(cp.mine_grid.count(), 2)
        with TemporaryDirectory() as d:
            path = str(Path(d) / "p.json")
            cp.save_palette(path)
            cp.remove_from_palette("#112233")
            self.assertEqual(cp.mine, ["#abcdef"])
            self.assertEqual(cp.load_palette(path), 2)
            self.assertEqual(cp.mine, ["#112233", "#abcdef"])
            Path(path).write_text('{"colors": ["bad", "#00ff00"]}', encoding="utf-8")
            self.assertEqual(cp.load_palette(path), 1)
        cp.mine_grid.itemAt(0).widget().click()
        self.assertEqual(w.canvas.color.name(), "#00ff00")

    def test_rainbow_mode_draws_many_hues(self):
        from PySide6.QtGui import QColor
        w = window()
        c = w.canvas
        w.tool_actions["pen"].trigger()
        w.color_panel.set_color(QColor("#ff0000"))
        w.color_panel.mode.setCurrentText("虹色")
        self.assertEqual(c.color_mode, "虹色")
        w.size_box.setValue(6)
        drag(c, [(10 + i * 9, 100) for i in range(21)])
        img = c.flatten()
        hues = {img.pixelColor(x, 100).hsvHue() // 30 for x in range(10, 190) if img.pixelColor(x, 100).saturation() > 100}
        self.assertGreaterEqual(len(hues), 3)                            # 線の途中で色相が回る
        w.color_panel.mode.setCurrentText("単色")


class NewToolsTest(unittest.TestCase):
    def test_spray_puts_scattered_dots(self):
        from PySide6.QtGui import QColor
        w = window()
        c = w.canvas
        w.tool_actions["spray"].trigger()
        self.assertEqual(c.tool, "spray")
        c.color = QColor("#000000")
        w.size_box.setValue(20)
        before = c.flatten()
        drag(c, [(100, 100), (110, 100), (120, 100)])
        after = c.flatten()
        n = changed(before, after)
        self.assertGreater(n, 10)
        self.assertEqual(before.pixelColor(10, 10), after.pixelColor(10, 10))   # 円の外は変えない
        c.undo()
        self.assertEqual(changed(before, c.flatten()), 0)                # 元に戻せる

    def test_smudge_drags_color(self):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QPainter
        w = window()
        c = w.canvas
        p = QPainter(c.layers[c.current].image)
        p.fillRect(QRect(0, 0, 100, 200), QColor("#0000ff"))
        p.end()
        w.tool_actions["smudge"].trigger()
        w.size_box.setValue(20)
        self.assertEqual(c.flatten().pixelColor(115, 100).name(), "#ffffff")
        drag(c, [(90, 100), (100, 100), (110, 100), (120, 100)])
        px = c.flatten().pixelColor(115, 100)
        self.assertGreater(px.blue() - px.red(), 40)                     # 青が右へ伸びた

    def test_text_tool_asks_and_places_text(self):
        w = window()
        c = w.canvas
        w.tool_actions["text"].trigger()
        before = c.flatten()
        with mock.patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("あA", True)):
            drag(c, [(20, 20)])
        self.assertGreater(changed(before, c.flatten()), 5)
        with mock.patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("", False)):
            mid = c.flatten()
            drag(c, [(120, 120)])
        self.assertEqual(changed(mid, c.flatten()), 0)                   # やめたら何も置かない

    def test_symmetry_mirrors_pen(self):
        w = window()
        c = w.canvas
        w.tool_actions["pen"].trigger()
        w.symmetry.setCurrentIndex(w.symmetry.findData("lr"))
        self.assertTrue(c.mirror_item.isVisible())
        w.size_box.setValue(6)
        drag(c, [(20, 50), (40, 50), (60, 50)])
        img = c.flatten()
        self.assertEqual(img.pixelColor(40, 50).name(), "#000000")
        self.assertEqual(img.pixelColor(160, 50).name(), "#000000")      # 200 - 40
        w.symmetry.setCurrentIndex(w.symmetry.findData(""))
        self.assertFalse(c.mirror_item.isVisible())

    def test_stabilizer_smooths_jitter(self):
        from PySide6.QtCore import QPointF
        w = window()
        c = w.canvas
        w.stabilizer.setValue(25)   # 強さは 0〜100。25 は前の 0〜20 の段の 5 と同じ効き
        self.assertEqual(c.stabilizer, 25)
        c.steady = QPointF(0, 0)
        p = c.steadied(QPointF(60, 0))
        self.assertAlmostEqual(p.x(), 10.0)                              # 1/6 だけ近づく
        w.tool_actions["pen"].trigger()
        jag = [(20 + i * 8, 100 + (12 if i % 2 else -12)) for i in range(18)]
        drag(c, jag)
        img = c.flatten()
        ys = [y for y in range(200) if img.pixelColor(90, y).name() != "#ffffff"]
        self.assertTrue(ys)
        self.assertLess(max(ys) - min(ys), 20)                           # ぎざぎざ（±12）が均される
        w.stabilizer.setValue(0)

    def test_new_tools_have_command_and_tour(self):
        from atelier.agent import commands
        from atelier.ui import tours
        w = window()
        names = {cm.name for cm in commands.COMMANDS}
        cat = tours.catalog(w)
        for key in ("spray", "smudge", "text"):
            self.assertIn(key, w.tool_actions)
            self.assertIn(key, names)
            self.assertIn(key, cat)
            self.assertFalse(w.tool_actions[key].icon().isNull())



class FillAndTaperTest(unittest.TestCase):
    """塗りつぶしの塗り残し・隙間閉じ・参照するレイヤーと、ペンの入り抜き。道具の帯から持ち替え、マウスで押して画素で確かめる"""

    def test_fill_leaves_no_fringe_and_closes_gaps(self):
        import math
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QPainter, QPen
        w = window()
        c = w.canvas
        p = QPainter(c.layers[0].image)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("black"), 3))
        p.drawEllipse(QPointF(100, 100), 60, 60)
        p.end()
        c.add_layer()
        w.tool_actions["fill"].trigger()
        drag(c, [(100, 100)])
        f = c.layers[c.current].image
        gaps = sum(1 for a in range(360)
                   if f.pixelColor(int(100 + 58 * math.cos(math.radians(a))), int(100 + 58 * math.sin(math.radians(a)))).alpha() == 0)
        self.assertEqual(gaps, 0)   # 前は線のふちの薄い画素で 360 点中 124 点が塗り残った
        c.new_canvas(200, 200)
        p = QPainter(c.layers[0].image)
        p.setPen(QPen(QColor("black"), 3))
        p.drawRect(40, 40, 120, 120)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(98, 37, 4, 8, QColor("white"))   # 4 画素の切れ目
        p.end()
        c.add_layer()
        c.fill_gap = 0
        drag(c, [(100, 100)])
        self.assertGreater(c.layers[c.current].image.pixelColor(10, 10).alpha(), 0)   # 隙間閉じ無しは漏れる
        c.undo()
        menu = w.build_canvas_menu(None)                                  # 右クリックの「塗りつぶしの設定」から選ぶ
        fill_menu = next(a.menu() for a in menu.actions() if a.text() == "塗りつぶしの設定")
        gap = next(a.menu() for a in fill_menu.actions() if a.text() == "隙間閉じ")
        next(a for a in gap.actions() if a.text().startswith("中")).trigger()
        self.assertEqual(c.fill_gap, 4)
        drag(c, [(100, 100)])
        img = c.layers[c.current].image
        self.assertEqual(img.pixelColor(10, 10).alpha(), 0)
        self.assertEqual(img.pixelColor(100, 100).alpha(), 255)
        c.fill_gap = 0

    def test_fill_reference_current_layer(self):
        from PySide6.QtGui import QColor, QPainter
        w = window()
        c = w.canvas
        p = QPainter(c.layers[0].image)
        p.fillRect(0, 95, 200, 10, QColor("black"))
        p.end()
        c.add_layer()
        w.tool_actions["fill"].trigger()
        c.fill_ref = "layer"
        drag(c, [(100, 20)])
        self.assertGreater(c.layers[c.current].image.pixelColor(100, 180).alpha(), 0)   # 下の線を見ずに全部塗る
        c.fill_ref = "all"

    def test_pen_taper_in_and_out(self):
        w = window()
        c = w.canvas
        c.new_canvas(300, 120)
        w.tool_actions["pen"].trigger()
        w.size_box.setValue(12)
        drag(c, [(20 + i * 5, 60) for i in range(53)])
        img = c.layers[c.current].image
        thick = lambda x: sum(1 for y in range(120) if img.pixelColor(x, y).alpha() > 128)
        self.assertLessEqual(thick(22), 5)
        self.assertGreaterEqual(thick(150), 11)
        self.assertLessEqual(thick(278), 5)
        c.brush.taper_in = c.brush.taper_out = 0.0          # 無しにすれば端まで同じ太さ
        drag(c, [(20 + i * 5, 100) for i in range(53)])
        img = c.layers[c.current].image
        self.assertGreaterEqual(sum(1 for y in range(120) if img.pixelColor(30, y).alpha() > 128), 11)
        c.brush.taper_in = c.brush.taper_out = 3.0

    def test_tap_still_makes_a_dot(self):
        w = window()
        c = w.canvas
        w.tool_actions["pen"].trigger()
        w.size_box.setValue(10)
        drag(c, [(100, 100)])
        self.assertGreater(c.layers[c.current].image.pixelColor(100, 100).alpha(), 200)   # 入り抜きで点が消えない


def tablet(c, pts, pressure=0.5, tilt=(0.0, 0.0)):
    """ペンタブレットの押す・動かす・離すを、筆圧と傾きを付けて流す"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QPointingDevice, QTabletEvent
    vp = c.viewport()
    dev = QPointingDevice.primaryPointingDevice()
    kinds = [QEvent.TabletPress] + [QEvent.TabletMove] * (len(pts) - 2) + [QEvent.TabletRelease]
    for kind, (x, y) in zip(kinds, pts):
        p = QPointF(c.mapFromScene(x, y))
        ev = QTabletEvent(kind, dev, p, QPointF(vp.mapToGlobal(p.toPoint())), pressure, tilt[0], tilt[1], 0.0, 0.0, 0.0,
                          Qt.NoModifier, Qt.LeftButton, Qt.LeftButton if kind != QEvent.TabletRelease else Qt.NoButton)
        c.tabletEvent(ev)


def thickness(c, x):
    from PySide6.QtGui import QColor
    img = c.layers[c.current].image
    return sum(1 for y in range(img.height()) if QColor.fromRgba(img.pixel(x, y)).alpha() > 128)


class PenCurveTiltTest(unittest.TestCase):
    """筆圧の曲線とペンの傾き。ブラシの欄の「設定」で選び、ペンタブレットの線の太さで確かめる"""

    def _line(self, w, **kw):
        c = w.canvas
        c.layers[c.current].image.fill(0)
        tablet(c, [(20, 100), (60, 100), (100, 100), (140, 100), (180, 100)], **kw)
        return thickness(c, 100)

    def test_curve_and_tilt_from_brush_panel(self):
        w = window()
        w.tool_actions["pen"].trigger()
        w.canvas.size = 20
        w.canvas.brush.size_pressure = True
        w.canvas.brush.taper_in = w.canvas.brush.taper_out = 0.0
        box = w.pressure_curve
        widths = {}
        for key in ("soft", "linear", "hard"):
            box.setCurrentIndex(box.findData(key))
            self.assertEqual(w.canvas.pressure_curve, key)
            widths[key] = self._line(w, pressure=0.4)
        self.assertGreater(widths["soft"], widths["linear"])
        self.assertGreater(widths["linear"], widths["hard"])
        box.setCurrentIndex(box.findData("linear"))
        upright = self._line(w, pressure=0.4)
        w.tilt_size.setChecked(True)
        flat = self._line(w, pressure=0.4, tilt=(60.0, 0.0))
        self.assertGreater(flat, upright * 1.5)
        w.tilt_size.setChecked(False)
        self.assertEqual(self._line(w, pressure=0.4, tilt=(60.0, 0.0)), upright)   # 切ると傾きは効かない

    def test_tilt_kept_when_taper_redraws_on_release(self):
        """入り抜きと傾きを一緒に使うと、離したときの抜きの描き直しで太さが傾きの無い太さに戻っていた"""
        w = window()
        w.tool_actions["pen"].trigger()
        c = w.canvas
        c.size = 20
        c.brush.size_pressure = True
        c.brush.taper_in = c.brush.taper_out = 1.0
        w.pressure_curve.setCurrentIndex(w.pressure_curve.findData("linear"))
        upright = self._line(w, pressure=0.4)
        w.tilt_size.setChecked(True)
        flat = self._line(w, pressure=0.4, tilt=(60.0, 0.0))
        w.tilt_size.setChecked(False)
        c.brush.taper_in = c.brush.taper_out = 3.0
        self.assertGreater(flat, upright * 1.5, (upright, flat))
        c.undo()
        self.assertEqual(thickness(c, 100), 0)   # 元に戻すで線ごと消える

    def test_fill_and_taper_boxes_in_brush_panel(self):
        w = window()
        b = w.fill_boxes["fill_gap"]
        b.setCurrentIndex(b.findData(4))
        b.activated.emit(b.currentIndex())
        self.assertEqual(w.canvas.fill_gap, 4)
        t = w.taper_boxes["taper_in"]
        t.setCurrentIndex(t.findData(3.0))
        t.activated.emit(t.currentIndex())
        self.assertEqual(w.canvas.brush.taper_in, 3.0)
        w.canvas.fill_gap = 8   # 右クリックのメニューで変えたときも、欄の表示を合わせる
        w.sync_tool_boxes()
        self.assertEqual(b.currentData(), 8)


if __name__ == "__main__":
    unittest.main()
