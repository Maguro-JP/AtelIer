"""レイヤーのコピー・切り取り・貼り付け・複製・反転と、対称定規（線対称・点対称）。
窓のメニュー・キー・レイヤーの欄の右クリック・絵の上のマウスから押して、画素とレイヤーの数で確かめる（本物と同じ経路）。
直したバグ: ロックしたレイヤーの切り取り・消す・塗る、隠した・ロックしたレイヤーへの結合、図形に効かない対称、絵の大きさを変えても動かない軸"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ATELIER_CHECK", "off")
sys.path.insert(0, str(ROOT / ".cache" / "simple" / "lib"))
sys.path.insert(0, str(ROOT))

from tests.test_brushtools import drag, window  # noqa: E402


def menu_action(w, top: str, text: str):
    """メニューの棒の top の中から、見出しが text の操作を探す（下の段も見る）"""
    from PySide6.QtWidgets import QMenu
    menus = {m.menuAction(): m for m in w.findChildren(QMenu)}

    def walk(menu):
        for a in menu.actions():
            if a in menus:
                found = walk(menus[a])
                if found:
                    return found
            elif a.text() == text:
                return a
    for a in w.menuBar().actions():
        if a.text() == top:
            return walk(menus[a])


def press_keys(w, seq: str):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    w.activateWindow()
    w.canvas.setFocus()
    QApplication.processEvents()
    k = QKeySequence(seq)[0]
    QTest.keyClick(w.canvas, k.key(), k.keyboardModifiers())


def red(c, layer=None):
    from PySide6.QtGui import QColor
    c.layers[c.current if layer is None else layer].image.fill(QColor("red"))


class LayerOpsTest(unittest.TestCase):
    def test_menus_have_layer_ops_with_keys(self):
        w = window()
        for top, text, key in (("編集", "レイヤーをコピー", "Ctrl+Alt+C"), ("編集", "レイヤーを切り取り", "Ctrl+Alt+X"),
                               ("編集", "レイヤーを貼り付け", "Ctrl+Alt+V"), ("編集", "同じ位置に貼り付け", "Ctrl+Shift+V"),
                               ("編集", "結合してコピー", "Ctrl+Shift+C"), ("レイヤー", "レイヤーを複製", ""),
                               ("レイヤー", "選択範囲をコピーして新しいレイヤーへ", "Ctrl+J"),
                               ("レイヤー", "選択範囲を切り取って新しいレイヤーへ", "Ctrl+Shift+J"),
                               ("レイヤー", "下のレイヤーと結合", ""), ("レイヤー", "レイヤーの中を消す", ""),
                               ("レイヤー", "レイヤーを左右反転", ""), ("レイヤー", "レイヤーを上下反転", ""),
                               ("表示", "点対称（中心の周り）", "")):
            a = menu_action(w, top, text)
            self.assertIsNotNone(a, text)
            self.assertEqual(a.shortcut().toString(), key, text)
            self.assertTrue(a.toolTip(), text)   # 説明はツールチップに出す
        # 窓の中で同じキーを 2 つの操作に付けていない
        from atelier.app import key_bindings as keys
        seen = {}
        for name, a in keys.collect(w).items():
            k = a.shortcut().toString()
            if k:
                self.assertNotIn(k, seen, f"{k}: {name} と {seen.get(k)}")
                seen[k] = name

    def test_duplicate_copy_cut_paste_layer_and_undo(self):
        w = window()
        c = w.canvas
        red(c)
        c.layers[c.current].opacity = 0.5
        menu_action(w, "レイヤー", "レイヤーを複製").trigger()
        self.assertEqual(len(c.layers), 3)
        self.assertEqual(c.layers[c.current].name, "レイヤー 1 のコピー")
        self.assertEqual(c.layers[c.current].image.pixelColor(5, 5).name(), "#ff0000")
        self.assertEqual(c.layers[c.current].opacity, 0.5)
        c.undo()
        self.assertEqual(len(c.layers), 2)
        press_keys(w, "Ctrl+Alt+X")                  # 切り取り
        self.assertEqual(len(c.layers), 1)
        from PySide6.QtWidgets import QApplication
        self.assertEqual(QApplication.clipboard().image().pixelColor(5, 5).name(), "#ff0000")
        press_keys(w, "Ctrl+Alt+V")                  # 貼り付け（選んでいるレイヤーのすぐ上、選んだ状態）
        self.assertEqual(len(c.layers), 2)
        self.assertEqual(c.current, 1)
        self.assertEqual(c.layers[1].name, "レイヤー 1")
        self.assertEqual(c.layers[1].opacity, 0.5)
        press_keys(w, "Ctrl+Alt+C")
        press_keys(w, "Ctrl+Alt+V")
        self.assertEqual([x.name for x in c.layers], ["背景", "レイヤー 1", "レイヤー 1 のコピー"])
        c.undo()
        c.undo()
        c.undo()
        self.assertEqual([x.name for x in c.layers], ["背景", "レイヤー 1"])   # 切り取りも元に戻すで戻る

    def test_via_copy_cut_and_paste_in_place(self):
        from PySide6.QtCore import QRect
        w = window()
        c = w.canvas
        red(c)
        c.set_selection(QRect(50, 60, 30, 20))
        press_keys(w, "Ctrl+J")
        self.assertEqual(len(c.layers), 3)
        new = c.layers[c.current].image
        self.assertEqual(new.pixelColor(60, 70).name(), "#ff0000")
        self.assertEqual(new.pixelColor(10, 10).alpha(), 0)            # 選択の外は写さない
        press_keys(w, "Ctrl+Shift+J")                                   # 写したレイヤーから切り取る
        self.assertEqual(len(c.layers), 4)
        self.assertEqual(c.layers[2].image.pixelColor(60, 70).alpha(), 0)
        self.assertEqual(c.layers[3].image.pixelColor(60, 70).name(), "#ff0000")
        # 選択の中をコピーし、選択を外してから同じ位置に貼る
        w.shared["copy"].trigger()
        w.shared["deselect"].trigger()
        press_keys(w, "Ctrl+Shift+V")
        img = c.layers[c.current].image
        self.assertEqual(len(c.layers), 5)
        self.assertEqual(img.pixelColor(60, 70).name(), "#ff0000")
        self.assertEqual(img.pixelColor(5, 5).alpha(), 0)
        # 結合してコピーは見えている絵（白い背景＋赤）
        c.set_selection(QRect(0, 0, 10, 10))
        press_keys(w, "Ctrl+Shift+C")
        from PySide6.QtWidgets import QApplication
        clip = QApplication.clipboard().image()
        self.assertEqual((clip.width(), clip.height()), (10, 10))
        self.assertEqual(clip.pixelColor(5, 5).name(), "#ff0000")
        for _ in range(4):
            c.undo()
        self.assertEqual(len(c.layers), 2)
        self.assertEqual(c.layers[1].image.pixelColor(60, 70).name(), "#ff0000")

    def test_flip_and_clear_layer(self):
        from PySide6.QtGui import QColor
        w = window()
        c = w.canvas
        c.layers[c.current].image.setPixelColor(10, 20, QColor("blue"))
        menu_action(w, "レイヤー", "レイヤーを左右反転").trigger()
        self.assertEqual(c.layers[c.current].image.pixelColor(189, 20).name(), "#0000ff")
        menu_action(w, "レイヤー", "レイヤーを上下反転").trigger()
        self.assertEqual(c.layers[c.current].image.pixelColor(189, 179).name(), "#0000ff")
        menu_action(w, "レイヤー", "レイヤーの中を消す").trigger()
        self.assertEqual(c.layers[c.current].image.pixelColor(189, 179).alpha(), 0)
        c.undo()
        c.undo()
        c.undo()
        self.assertEqual(c.layers[c.current].image.pixelColor(10, 20).name(), "#0000ff")

    def test_layer_panel_right_click_has_ops(self):
        w = window()
        c = w.canvas
        red(c)
        lp = w.layer_panel
        row = lp.row_of(c.current)
        pos = lp.list.visualItemRect(lp.list.item(row)).center()
        m = lp.context_menu(pos)
        texts = [a.text() for a in m.actions()]
        for t in ("レイヤーを複製", "レイヤーを切り取り", "レイヤーをコピー", "レイヤーを貼り付け",
                  "選択範囲をコピーして新しいレイヤーへ", "レイヤーの中を消す", "レイヤーを左右反転", "下のレイヤーと結合"):
            self.assertIn(t, texts)
        next(a for a in m.actions() if a.text() == "レイヤーを複製").trigger()
        self.assertEqual(len(c.layers), 3)

    def test_locked_and_hidden_layers_are_kept(self):
        """直したバグ: ロックしたレイヤーの選択範囲の切り取り・消す・塗るが絵を変えていた。隠した・ロックしたレイヤーへ結合していた"""
        from PySide6.QtCore import QRect
        w = window()
        c = w.canvas
        red(c)
        c.set_locked(c.current, True)
        c.set_selection(QRect(10, 10, 50, 50))
        for k in ("cut", "sel_clear", "sel_fill", "via_cut", "clear_layer", "flip_layer_h"):
            w.shared[k].trigger()
            self.assertEqual(c.layers[c.current].image.pixelColor(20, 20).name(), "#ff0000", k)
        w.shared["layer_cut"].trigger()
        self.assertEqual(len(c.layers), 2)
        c.set_locked(c.current, False)
        c.set_selection(None)
        c.set_locked(0, True)
        self.assertFalse(c.merge_down())                                # 下がロック
        self.assertEqual(len(c.layers), 2)
        c.set_locked(0, False)
        c.set_visible(0, False)
        self.assertFalse(c.merge_down())                                # 下が隠れている
        c.set_visible(0, True)
        c.set_visible(1, False)
        self.assertFalse(c.merge_down())                                # 上が隠れている（黙って捨てていた）
        c.set_visible(1, True)
        self.assertTrue(c.merge_down())
        self.assertEqual(len(c.layers), 1)


class SymmetryTest(unittest.TestCase):
    def setUp(self):
        self.w = window()
        self.c = self.w.canvas
        self.w.size_box.setValue(4)

    def mode(self, key):
        self.w.symmetry.setCurrentIndex(self.w.symmetry.findData(key))

    def black(self, x, y):
        return self.c.flatten().pixelColor(x, y).name() == "#000000"

    def test_vertical_horizontal_point_with_pen(self):
        self.w.tool_actions["pen"].trigger()
        self.mode("ud")
        self.assertTrue(self.c.mirror_item.isVisible())
        drag(self.c, [(40, 30), (50, 30), (60, 30)])
        self.assertTrue(self.black(50, 30) and self.black(50, 169))     # 200 - 30 - 1 付近
        self.mode("point")
        drag(self.c, [(20, 100), (25, 110), (30, 120)])
        self.assertTrue(self.black(25, 110) and self.black(175, 90))
        self.mode("both")
        drag(self.c, [(150, 150), (155, 150), (160, 150)])
        for x, y in ((155, 150), (45, 150), (155, 50), (45, 50)):
            self.assertTrue(self.black(x, y), (x, y))
        # メニューの「対称定規」と欄の選びは同じ設定
        self.assertTrue(self.w.symmetry_actions["both"].isChecked())
        self.w.symmetry_actions[""].trigger()
        self.assertEqual(self.c.symmetry, "")
        self.assertFalse(self.c.mirror_item.isVisible())

    def test_shapes_follow_symmetry(self):
        """直したバグ: 直線・四角・楕円は対称にしても片側にしか描かれなかった"""
        self.mode("lr")
        self.w.tool_actions["line"].trigger()
        drag(self.c, [(20, 100), (40, 120), (60, 140)])
        self.assertTrue(self.black(40, 120) and self.black(160, 120))
        self.mode("point")
        self.w.tool_actions["rect"].trigger()
        drag(self.c, [(20, 20), (30, 30), (40, 40)])
        self.assertTrue(self.black(20, 30) and self.black(180, 170))

    def test_axis_drag_and_resize(self):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        c = self.c
        self.mode("lr")
        self.w.tool_actions["pen"].trigger()
        vp = c.viewport()
        start = c.mapFromScene(QPointF(100, 100))
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, start)
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent
        end = c.mapFromScene(QPointF(120, 80))
        QTest.mouseMove(vp, end)
        ev = QMouseEvent(QEvent.MouseMove, QPointF(end), QPointF(vp.mapToGlobal(end)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication_send(vp, ev)
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, end)
        self.assertAlmostEqual(c.axis_center().x(), 120, delta=1.5)   # 丸をつかんで動かした（描いていない）
        self.assertEqual(c.flatten().pixelColor(110, 90).name(), "#ffffff")
        drag(c, [(100, 40), (105, 40), (110, 40)])
        self.assertTrue(self.black(105, 40) and self.black(135, 40))   # 2×120 - 105
        menu_action(self.w, "表示", "軸を真ん中に戻す").trigger()
        self.assertEqual(c.axis_center().x(), 100)
        c.new_canvas(400, 200)
        self.assertEqual(c.mirror_item.path().boundingRect().center().x(), 200)   # 絵の大きさに合わせる


def QApplication_send(target, ev):
    from PySide6.QtWidgets import QApplication
    QApplication.sendEvent(target, ev)



class LayerPropsTest(unittest.TestCase):
    """合成モード・クリッピング・透明部分の保護。レイヤーの欄のボタンから押し、重ねた絵の画素と、作業ファイル・PSD の往復で確かめる"""

    def _three(self):
        from PySide6.QtGui import QColor, QPainter
        from atelier.panels.layer_panel import LayerPanel
        w = window()
        c = w.canvas
        c.layers[0].image.fill(QColor("white"))
        c.add_layer()
        p = QPainter(c.layers[c.current].image)
        p.fillRect(50, 50, 100, 100, QColor(100, 150, 200))
        p.end()
        c.add_layer()
        p = QPainter(c.layers[c.current].image)
        p.fillRect(0, 0, 200, 100, QColor(128, 128, 128))
        p.end()
        lp = w.findChild(LayerPanel)
        lp.refresh()
        return w, c, lp

    def test_clip_and_multiply_from_panel(self):
        w, c, lp = self._three()
        lp.buttons["clip"].click()
        lp.blend.setCurrentIndex(lp.blend.findData("multiply"))
        lp.blend.activated.emit(lp.blend.currentIndex())
        fl = c.flatten()
        self.assertEqual(fl.pixelColor(10, 10).name(), "#ffffff")      # 土台の外には出ない
        self.assertEqual(fl.pixelColor(100, 60).name(), "#324b64")     # 乗算（100×128/255 = 50）
        self.assertEqual(c.undo_names[-2:], ["クリッピング", "合成モード"])
        c.undo()
        c.undo()
        self.assertEqual((c.layers[-1].blend, c.layers[-1].clip), ("normal", False))   # 元に戻すで戻る

    def test_merge_down_keeps_look(self):
        w, c, lp = self._three()
        c.set_layer_prop(c.current, "clip", True)
        c.set_layer_prop(c.current, "blend", "multiply")
        before = c.flatten()
        c.merge_down()
        after = c.flatten()
        for pt in ((10, 10), (100, 60), (100, 120)):
            self.assertEqual(before.pixelColor(*pt).name(), after.pixelColor(*pt).name())

    def test_alpha_lock_paints_only_on_drawn(self):
        from PySide6.QtGui import QColor
        w, c, lp = self._three()
        c.select(2)
        lp.refresh()
        lp.buttons["alpha_lock"].click()
        w.tool_actions["pen"].trigger()
        w.color_panel.set_color(QColor("red"))
        w.size_box.setValue(20)
        drag(c, [(20, 120), (180, 120)])
        img = c.layers[2].image
        self.assertEqual(img.pixelColor(20, 120).alpha(), 0)
        self.assertEqual(img.pixelColor(100, 120).name(), "#ff0000")
        w.tool_actions["eraser"].trigger()
        drag(c, [(60, 130), (140, 130)])
        self.assertEqual(c.layers[2].image.pixelColor(100, 130).alpha(), 255)   # 保護中の消しゴムは消さない

    def test_project_and_psd_round_trip(self):
        from tempfile import TemporaryDirectory
        from atelier.files import project_file as pf
        w, c, lp = self._three()
        c.set_layer_prop(3, "clip", True)
        c.set_layer_prop(3, "blend", "multiply")
        c.set_layer_prop(2, "alpha_lock", True)
        want = [(l.blend, l.clip, l.alpha_lock) for l in c.layers]
        look = c.flatten().pixelColor(100, 60).name()
        with TemporaryDirectory() as d:
            pf.save(c, f"{d}/t.atelier")
            pf.load(c, f"{d}/t.atelier")
            self.assertEqual([(l.blend, l.clip, l.alpha_lock) for l in c.layers], want)
            pf.export_psd(c, f"{d}/t.psd")
            w.open_path(f"{d}/t.psd")          # 「開く」と同じ道で PSD を開く
            w.wait_io()
            self.assertEqual([(l.blend, l.clip, l.alpha_lock) for l in c.layers], want)
            self.assertEqual([l.name for l in c.layers], ["背景", "レイヤー 1", "レイヤー 2", "レイヤー 3"])
            self.assertEqual(c.flatten().pixelColor(100, 60).name(), look)


class SelectionOpsTest(unittest.TestCase):
    """選択範囲の足し引き（Shift で足す、Alt で引く）。四角の選択を帯から持ち、マウスで押して確かめる"""

    def _drag(self, c, a, b, mod):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        vp = c.viewport()
        pa, pb = c.mapFromScene(*a), c.mapFromScene(*b)
        QTest.mousePress(vp, Qt.LeftButton, mod, pa)
        QApplication.sendEvent(vp, QMouseEvent(QEvent.MouseMove, QPointF(pb), QPointF(vp.mapToGlobal(pb)), Qt.NoButton,
                                               Qt.LeftButton, mod))
        QTest.mouseRelease(vp, Qt.LeftButton, mod, pb)

    def test_shift_adds_and_alt_subtracts(self):
        from PySide6.QtCore import QPointF, Qt
        w = window()
        c = w.canvas
        w.tool_actions["select"].trigger()
        self._drag(c, (10, 10), (60, 60), Qt.NoModifier)
        self._drag(c, (120, 120), (180, 180), Qt.ShiftModifier)
        path = c.selection_path()
        self.assertTrue(path.contains(QPointF(30, 30)) and path.contains(QPointF(150, 150)))
        self.assertFalse(path.contains(QPointF(90, 90)))
        self._drag(c, (20, 20), (40, 40), Qt.AltModifier)
        path = c.selection_path()
        self.assertFalse(path.contains(QPointF(30, 30)))
        self.assertTrue(path.contains(QPointF(15, 15)) and path.contains(QPointF(150, 150)))
        self._drag(c, (100, 10), (150, 50), Qt.NoModifier)   # キー無しは置き換え
        self.assertFalse(c.selection_path().contains(QPointF(150, 150)))


def alpha_at(c, x, y, layer=None):
    from PySide6.QtGui import QColor
    return QColor.fromRgba(c.layers[c.current if layer is None else layer].image.pixel(x, y)).alpha()


class FreeTransformTest(unittest.TestCase):
    """自由変形。メニューから窓を開き、数を入れて確定・取り消しを押し、画素と元に戻すで確かめる"""

    def _square(self):
        from PySide6.QtGui import QColor, QPainter
        w = window()
        c = w.canvas
        c.set_selection(None)
        p = QPainter(c.layers[c.current].image)
        p.fillRect(40, 40, 40, 40, QColor("red"))
        p.end()
        return w, c

    def _ok(self, dlg):
        from PySide6.QtWidgets import QDialogButtonBox
        return next(b for b in dlg.findChildren(QDialogButtonBox)[0].buttons() if b.text() == "確定")

    def test_scale_selection_commit_and_undo(self):
        from PySide6.QtCore import QRect
        w, c = self._square()
        c.set_selection(QRect(40, 40, 40, 40))
        menu_action(w, "選択範囲", "自由変形…").trigger()
        dlg = w.transform_dialog
        dlg.boxes["scale_x"].setValue(200)   # 縦横の比を保つので縦も 200%
        self.assertEqual(alpha_at(c, 25, 25), 255)   # 確定の前から絵の上で見える
        self._ok(dlg).click()
        self.assertEqual(alpha_at(c, 25, 25), 255)
        self.assertEqual(alpha_at(c, 15, 15), 0)
        self.assertEqual(c.selection, QRect(20, 20, 80, 80))
        self.assertEqual(c.undo_names[-1], "自由変形")
        c.undo()
        self.assertEqual(alpha_at(c, 25, 25), 0)
        self.assertEqual(alpha_at(c, 50, 50), 255)

    def test_rotate_flip_shear_and_cancel(self):
        w, c = self._square()
        n = len(c.undo_stack)
        menu_action(w, "レイヤー", "自由変形…").trigger()
        dlg = w.transform_dialog
        dlg.boxes["angle"].setValue(45)
        dlg.flip_h.setChecked(True)
        dlg.boxes["shear_x"].setValue(30)
        self.assertNotEqual(alpha_at(c, 41, 41), 255)   # 回して角がずれた
        dlg.reject()   # 取り消し（Esc と同じ）
        self.assertEqual(alpha_at(c, 41, 41), 255)
        self.assertEqual(len(c.undo_stack), n)   # 取り消しは履歴に残さない

    def test_flip_whole_layer(self):
        w, c = self._square()
        menu_action(w, "レイヤー", "自由変形…").trigger()
        dlg = w.transform_dialog
        dlg.flip_h.setChecked(True)
        self._ok(dlg).click()
        W = c.size_px()[0]
        self.assertEqual(alpha_at(c, W - 41, 50), 255)
        self.assertEqual(alpha_at(c, 50, 50), 0 if W - 80 > 50 else 255)


class LayerFolderTest(unittest.TestCase):
    """レイヤーフォルダー。メニューと欄の右クリックから入れる・出す・畳む・表示・不透明度・合成を押し、
    重ねた絵の画素、元に戻す、作業ファイルと PSD の往復で確かめる"""

    def _setup(self):
        from PySide6.QtGui import QColor
        from atelier.panels.layer_panel import LayerPanel
        w = window()
        c = w.canvas
        c.layers[0].image.fill(QColor("white"))
        c.layers[c.current].image.fill(QColor(0, 0, 255))
        lp = w.findChild(LayerPanel)
        return w, c, lp

    def test_folder_ops_from_menu_and_panel(self):
        from PySide6.QtGui import QColor
        from atelier.panels.layer_panel import ROLE_FOLDER
        w, c, lp = self._setup()
        menu_action(w, "レイヤー", "新しいフォルダー").trigger()
        name = c.layers[c.current].folder
        self.assertTrue(name)
        lp.refresh()
        r = lp.folder_row(name)
        self.assertGreaterEqual(r, 0)
        head = lp.list.item(r)
        # 見出しの右クリックから不透明度 50%
        m = lp.context_menu(lp.list.visualItemRect(head).center())
        op = next(a for a in m.actions() if a.text() == "フォルダーの不透明度").menu()
        next(a for a in op.actions() if a.text() == "50%").trigger()
        self.assertAlmostEqual(c.folders[name].opacity, 0.5)
        px = QColor(c.flatten().pixel(5, 5))
        self.assertTrue(120 <= px.red() <= 135 and px.blue() == 255, px.getRgb())
        # 合成を乗算に（白の上の青は青のまま、不透明度 50% で薄い青）
        lp.refresh()
        m = lp.context_menu(lp.list.visualItemRect(lp.list.item(lp.folder_row(name))).center())
        bl = next(a for a in m.actions() if a.text() == "フォルダーの合成モード").menu()
        next(a for a in bl.actions() if a.text() == "乗算").trigger()
        self.assertEqual(c.folders[name].blend, "multiply")
        # 見出しのチェックで中を全部隠す
        lp.refresh()
        head = lp.list.item(lp.folder_row(name))
        head.setCheckState(Qt_unchecked())
        spin()
        self.assertFalse(c.folders[name].visible)
        self.assertEqual(QColor(c.flatten().pixel(5, 5)).name(), "#ffffff")
        # 畳むと中の行が隠れる
        lp._double(lp.list.item(lp.folder_row(name)))
        lp.refresh()
        self.assertTrue(lp.list.item(lp.row_of(c.current)).isHidden())
        self.assertEqual(head.data(ROLE_FOLDER) if False else name, name)
        # 元に戻すで表示・合成・不透明度が順に戻る
        c.undo()
        self.assertTrue(c.folders[name].visible)
        c.undo()
        self.assertEqual(c.folders[name].blend, "pass")
        # 出す・入れる
        c.add_layer()
        self.assertEqual(c.layers[c.current].folder, "")
        menu_action(w, "レイヤー", "フォルダーに入れる")   # 行き先は開くたびに作る
        w.fill_folder_menu(w.folder_in_menu)
        next(a for a in w.folder_in_menu.actions() if a.text() == name).trigger()
        self.assertEqual(c.layers[c.current].folder, name)
        menu_action(w, "レイヤー", "フォルダーから出す").trigger()
        self.assertEqual(c.layers[c.current].folder, "")

    def test_folder_roundtrip_project_and_psd(self):
        import tempfile
        from atelier.files import project_file as pf
        from atelier.paint.canvas import Canvas
        w, c, lp = self._setup()
        name = c.new_folder("影")
        c.set_folder_prop(name, "blend", "multiply")
        c.set_folder_prop(name, "opacity", 0.5)
        c.set_folder_collapsed(name, True)
        before = c.flatten()
        with tempfile.TemporaryDirectory() as tmp:
            pf.save(c, Path(tmp) / "a.atelier")
            c2 = Canvas()
            pf.load(c2, Path(tmp) / "a.atelier")
            self.assertEqual([l.folder for l in c2.layers], [l.folder for l in c.layers])
            f = c2.folders[name]
            self.assertEqual((f.blend, f.opacity, f.collapsed), ("multiply", 0.5, True))
            self.assertEqual(c2.flatten(), before)
            pf.export_psd(c, Path(tmp) / "a.psd")
            got = pf.read_psd(Path(tmp) / "a.psd")
            self.assertEqual([l.name for l in got["layers"]], [l.name for l in c.layers])
            self.assertEqual([l.folder for l in got["layers"]], [l.folder for l in c.layers])
            g = got["folders"][name]
            self.assertEqual((g.blend, g.collapsed), ("multiply", True))
            self.assertAlmostEqual(g.opacity, 0.5, places=2)


def Qt_unchecked():
    from PySide6.QtCore import Qt
    return Qt.Unchecked


def spin():
    from PySide6.QtWidgets import QApplication
    for _ in range(3):
        QApplication.processEvents()


class SelectionGrowTest(unittest.TestCase):
    """選択範囲の拡張・縮小・境界のぼかし・反転。メニューから押し、塗った画素で確かめる"""

    def test_grow_shrink_feather_invert(self):
        from PySide6.QtCore import QPointF, QRect
        from PySide6.QtGui import QColor
        w = window()
        c = w.canvas
        c.set_selection(QRect(50, 50, 40, 40))
        w.selection_resize("grow", 5)
        self.assertEqual(c.selection, QRect(45, 45, 50, 50))
        w.selection_resize("shrink", 10)
        self.assertEqual(c.selection, QRect(55, 55, 30, 30))
        w.selection_resize("shrink", 40)   # 縮めすぎると選択が無くなる（落ちない）
        self.assertIsNone(c.selection)
        c.set_selection(QRect(50, 50, 40, 40))
        menu_action(w, "選択範囲", "選択範囲を反転").trigger()
        self.assertFalse(c.selection_path().contains(QPointF(70, 70)))
        self.assertTrue(c.selection_path().contains(QPointF(10, 10)))
        c.set_selection(QRect(50, 50, 40, 40))
        w.selection_resize("feather", 8)
        c.color = QColor("red")
        self.assertTrue(c.fill_selection())
        inside, edge, out = alpha_at(c, 70, 70), alpha_at(c, 50, 70), alpha_at(c, 30, 70)
        self.assertGreater(inside, 240)
        self.assertTrue(60 < edge < 200, edge)   # 境目は半分ほど
        self.assertEqual(out, 0)
        c.undo()
        self.assertEqual(alpha_at(c, 70, 70), 0)


if __name__ == "__main__":
    unittest.main()
