"""作業ブランチでだけ直っていて main に無かった不具合の直しを、デグレしないように見る。

目の色の測り（背景の角を目に数えない）、英語の「加工」の訳、待っている間の緊急停止の数を見る。
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class EyeColorTest(unittest.TestCase):
    def test_background_corners_are_not_eyes(self):
        """丸い顔の外の角（背景）の色を変えても、目の色の測りは変わらない"""
        import numpy as np
        from PIL import Image
        from atelier.ai import face_features as ff
        n = 80
        yy, xx = np.mgrid[:n, :n]
        face = (yy - 40) ** 2 + (xx - 40) ** 2 < 30 ** 2
        labels = np.where(face, ff.FACE, 0)
        eyes = ((yy - 30) ** 2 + (xx - 28) ** 2 < 16) | ((yy - 30) ** 2 + (xx - 52) ** 2 < 16)
        labels[eyes] = 0   # 目は顔の穴（部位分けで顔に入らなかった目）
        got = []
        for bg in ((255, 0, 0), (0, 255, 0)):
            a = np.zeros((n, n, 3), np.uint8)
            a[:] = bg
            a[face] = (240, 200, 180)
            a[eyes] = (20, 40, 200)
            got.append(ff.features(Image.fromarray(a), labels)["eye"])
        self.assertLess(float(np.abs(got[0] - got[1]).max()), 1.0)
        self.assertLess(float(np.abs(got[0] - np.array([20, 40, 200])).max()), 1.0)


class TranslateTest(unittest.TestCase):
    def test_edit_menu_translated(self):
        from atelier.ui import i18n
        self.assertEqual(i18n.t("加工", "English"), "Edit Image")


class ActivityStopTest(unittest.TestCase):
    def test_stop_only_while_running(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from atelier.panels.activity_panel import ActivityPanel
        p = ActivityPanel()
        self.assertTrue(p.stop_tool.isHidden())   # 待っている間は上の帯の緊急停止 1 つだけ
        p.begin("試し", "draw")
        self.assertFalse(p.stop_tool.isHidden())
        p.end("止めました", record=False)
        self.assertTrue(p.stop_tool.isHidden())


if __name__ == "__main__":
    unittest.main()
