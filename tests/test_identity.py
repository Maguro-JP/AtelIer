"""ロゴと構成の決まり。ロゴは AtelIer の A と I だけを差し色にする。流用元の名前や、まだ持ってきていない部品への参照を残さない。"""
import re
import unittest
from pathlib import Path

from atelier.ui import logo
from tests.helpers import close, window

ROOT = Path(__file__).resolve().parents[1]
ACCENT, TEXT = "#ff0000", "#222222"


class LogoTest(unittest.TestCase):
    def test_wordmark_colors_only_a_and_i(self):
        html = logo.wordmark_html(ACCENT, TEXT)
        letters = re.findall(r'<span style="color:(#[0-9a-f]{6})">(.)</span>', html)
        self.assertEqual("".join(ch for _c, ch in letters), "AtelIer")
        self.assertEqual([ch for c, ch in letters if c == ACCENT], ["A", "I"])
        self.assertEqual([ch for c, ch in letters if c == TEXT], list("teler"))

    def test_svg_files_color_only_a_and_i(self):
        svg = logo.LOGO_SVG.read_text(encoding="utf-8")
        accents = re.findall(r'<tspan\s+fill="#[0-9a-f]{6}">(\w+)</tspan>', svg)
        self.assertEqual(accents, ["A", "I"])
        self.assertEqual(re.sub(r"<[^>]+>", "", svg[svg.index("<text"):svg.index("</text>")]).strip(), "AtelIer")
        from PySide6.QtSvg import QSvgRenderer
        from tests.helpers import application
        application()
        for path in (logo.LOGO_SVG, logo.ICON_SVG):
            self.assertTrue(QSvgRenderer(str(path)).isValid(), path)   # 絵として読める

    def test_window_shows_logo_and_follows_theme(self):
        from atelier.ui import themes
        w = window()
        self.assertEqual(w.windowTitle(), "AtelIer")
        w.set_theme("ペーパー")
        self.assertIn(themes.THEMES["ペーパー"]["a1"], w.logo_label.text())
        w.set_theme(themes.DEFAULT)
        self.assertIn(themes.THEMES[themes.DEFAULT]["a1"], w.logo_label.text())
        close(w)


class ToolBarTest(unittest.TestCase):
    def test_every_tool_is_reachable_in_the_window(self):
        """道具の帯が窓の高さからはみ出し、下の道具（文字・スポイト・手のひら・拡大）が押せなかった"""
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from atelier.app.tools import TOOLS
        w = window()
        w.reset_layout()
        w.resize(1280, 720)
        QApplication.processEvents()
        for key in (k for k, _label, _s in TOOLS if k):
            button = w.tool_buttons[key]
            self.assertTrue(button.isVisible(), key)
            bottom = button.mapTo(w, QPoint(0, button.height())).y()
            self.assertLessEqual(bottom, w.height() - w.statusBar().height(), key)
            self.assertFalse(button.icon().isNull(), key)
        w.tool_buttons["zoom"].click()
        self.assertEqual(w.canvas.tool, "zoom")
        close(w)


class StructureTest(unittest.TestCase):
    def test_no_reference_to_the_source_app(self):
        for path in (ROOT / "atelier").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("chatdraw", text, path)
            self.assertIsNone(re.search(r"\bCD_[A-Z]+", text), path)

    def test_layers_do_not_import_upward(self):
        """下の層は上の層を読まない。paint は欄や窓を知らず、欄は窓を知らない"""
        forbidden = {"paint": ("atelier.panels", "atelier.app"), "files": ("atelier.panels", "atelier.app"),
                     "ui": ("atelier.panels", "atelier.app", "atelier.paint"), "panels": ("atelier.app",)}
        for package, banned in forbidden.items():
            for path in (ROOT / "atelier" / package).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for name in banned:
                    self.assertNotIn(name, text, f"{path} が {name} を読んでいる")

    def test_every_package_has_init(self):
        for d in (ROOT / "atelier").iterdir():
            if d.is_dir() and d.name not in ("assets", "__pycache__"):
                self.assertTrue((d / "__init__.py").exists(), d)


if __name__ == "__main__":
    unittest.main()
