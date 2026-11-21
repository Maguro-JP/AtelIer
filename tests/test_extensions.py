"""拡張の登録口（atelier/extensions.py）。本体がキャラクターデザインを読まずに動くこと、拡張を付けると前と同じ物が出ること。

見るのは、本体のどのファイルもキャラクターデザインのパッケージを読んでいないこと（文字で調べる）、拡張を外した窓に
キャラクターデザインのメニュー・ファイルの項目・ライブラリーのタブ・モードが無いこと、付けた窓には有ること、
小さな見本の拡張がメニューを 1 本足せること。
"""
from __future__ import annotations

import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ATELIER_CHECK", "off")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atelier import extensions  # noqa: E402
from tests.test_editing import app  # noqa: E402

CHARA_MENU = "キャラクターデザイン"


class SourceTest(unittest.TestCase):
    def test_core_does_not_import_the_chara_package(self):
        """本体（atelier/chara/ の外）は、キャラクターデザインのパッケージを読まない。
        許すのは atelier/extensions.py の BUNDLED の 1 行だけ（同梱の拡張を文字で持つ。パッケージを移したら消す行）"""
        # 読み方の形だけを見る（`atelier/chara/...` と置き場を書いた説明は読み込みではないので拾わない）
        pattern = re.compile(r"atelier\.chara\b|from\s+atelier\s+import\s+[^\n]*\bchara\b|from\s+\.+\s*chara\b|from\s+\.+\s+import\s+[^\n]*\bchara\b")
        hits = []
        for path in sorted((ROOT / "atelier").rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith("atelier/chara/"):
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append((rel, n, line.strip()))
        self.assertEqual([(rel, line) for rel, _n, line in hits],
                         [("atelier/extensions.py", 'BUNDLED = ("atelier.chara.extension",)')], hits)


class Base(unittest.TestCase):
    def setUp(self):
        self.qapp = app()
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        from atelier.files import paths
        self.patches = [mock.patch.object(paths, "data_home", lambda: self.d / "data"),
                        mock.patch.object(paths, "LLM_HOME", self.d / "LLM"),
                        mock.patch.object(paths, "HOME", self.d / "home")]
        for p in self.patches:
            p.start()
        self.windows = []
        self.clear()

    def tearDown(self):
        for w in self.windows:
            w.dirty = False
            w.closing_checked = True
            w.close()
        self.qapp.processEvents()
        self.clear()
        os.environ.pop(extensions.NO_BUNDLED_ENV, None)
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def clear(self):
        for e in extensions.registered():
            extensions.unregister(e)

    def window(self):
        from atelier.ai.engine import Studio
        from atelier.app.main_window import Window
        from tests.test_chatdraw import FakePainter, FakeWords
        w = Window(Studio(FakeWords(), FakePainter(), self.d / "out"))
        for k in ("mode/current", "mode/ask"):
            w.layout_store.remove(k)
        w.show()
        self.qapp.processEvents()
        self.windows.append(w)
        return w

    @staticmethod
    def menus(w):
        return [a.text() for a in w.menuBar().actions() if a.menu() is not None]

    @staticmethod
    def file_items(w):
        return [a.text() for a in w.file_menu.actions() if not a.isSeparator()]

    @staticmethod
    def library_tabs(w):
        tabs = w.library_panel.tabs
        return [tabs.tabText(i) for i in range(tabs.count())]


class WithoutExtensionTest(Base):
    def test_window_opens_without_character_design(self):
        from atelier.app import modes
        os.environ[extensions.NO_BUNDLED_ENV] = "1"
        w = self.window()
        self.assertEqual(extensions.registered(), ())
        self.assertTrue(w.isVisible())
        self.assertNotIn(CHARA_MENU, self.menus(w))
        self.assertFalse(hasattr(w, "chara_menu"))
        self.assertEqual([t for t in self.file_items(w) if "キャラクター" in t], [])
        self.assertEqual(self.library_tabs(w), ["作品", "資料", "好み"])
        self.assertEqual(list(modes.MODES), ["illustrator", "logo"])
        self.assertEqual(list(w.mode_actions), ["illustrator", "logo"])
        self.assertEqual([b for b in modes.ModeDialog(w).buttons], ["illustrator", "logo"])
        self.assertEqual(w.studio_hooks, [])
        # 表情差分を持つ拡張が無いので、スタンプの項目も出さない。直に呼んでも、知らせを出して終わる
        self.assertNotIn("表情差分をまとめてスタンプにする…", [a.text() for a in w.logo_menu.actions()])
        said = []
        with mock.patch.object(w, "notify", lambda *a, **k: said.append(a)):
            w.stamp_from_expressions("line")
        self.assertEqual([a[0] for a in said], ["スタンプにできませんでした"])
        # モードを替えても、描く仕組みを作り直しても動く
        for key in modes.MODES:
            w.set_mode(key, tour=False)
            self.assertEqual(w.app_mode, key)
        w.set_mode("designer", tour=False)   # 前の回に覚えた、今は無いモードは初めのモードで開く
        self.assertEqual(w.app_mode, modes.DEFAULT)
        self.assertIsNone(w._studio_from_settings().character)
        w.library_panel.refresh()
        print(f"\n拡張なしのメニュー {len(self.menus(w))} 本: {'、'.join(self.menus(w))}")


class WithExtensionTest(Base):
    def test_bundled_extension_adds_character_design_as_before(self):
        from atelier.app import modes
        extensions.load_bundled(again=True)
        self.assertEqual([e.name for e in extensions.registered()], ["chara"])
        w = self.window()
        menus = self.menus(w)
        self.assertEqual(menus[menus.index(CHARA_MENU) + 1], "ロゴ・スタンプ")   # 前と同じ位置（ロゴ・スタンプの前）
        self.assertEqual(menus[menus.index(CHARA_MENU) - 1], "AI")
        self.assertIn("キャラデザを作る…", [a.text() for a in w.chara_menu.actions()])
        items = self.file_items(w)
        at = items.index("キャラクターを新しく作る…")
        self.assertEqual(items[at - 1:at + 5], ["名前を付けて保存…", "キャラクターを新しく作る…", "キャラクターを開く…", "キャラクターを保存",
                                                "キャラクターを書き出す…", "書き出す"])   # 前と同じ位置（保存と書き出しの間）
        self.assertEqual(self.library_tabs(w), ["作品", "資料", "キャラクター", "好み"])
        self.assertEqual(list(modes.MODES), ["illustrator", "designer", "logo"])
        self.assertEqual(sorted(w.mode_actions), sorted(modes.MODES))
        shown = [a.text() for a in w.mode_menu.actions()][:3]
        self.assertEqual(shown, [modes.MODES[k]["name"] for k in modes.MODES])   # 「表示」の「モード」の並びも前と同じ
        w.set_mode("designer", tour=False)
        visible = [a.text() for a in w.menuBar().actions() if a.isVisible()]
        self.assertIn(CHARA_MENU, visible)
        self.assertNotIn("ロゴ・スタンプ", visible)
        self.assertEqual(len(modes.tour(w, "designer")), 3)
        w.set_mode("logo", tour=False)
        self.assertNotIn(CHARA_MENU, [a.text() for a in w.menuBar().actions() if a.isVisible()])
        self.assertIn("表情差分をまとめてスタンプにする…", [a.text() for a in w.logo_menu.actions()])
        # 開いた人物は、描く仕組みを作り直しても渡る
        path = w.charafile_new({"name": "Akari", "look": "1girl, red hair"})
        self.assertTrue(Path(path).is_file())
        self.assertIn("red hair", w._studio_from_settings().character["words"])
        lib = w.library_panel
        self.assertEqual([lib.characters.item(i).data(0x0101) for i in range(lib.characters.count())], [path])
        # 拡張を外すと、次の窓から付かず、足したモードも消える
        extensions.unregister(extensions.registered()[0])
        self.assertEqual(list(modes.MODES), ["illustrator", "logo"])
        w2 = self.window()
        self.assertNotIn(CHARA_MENU, self.menus(w2))

    def test_sample_extension_adds_one_menu(self):
        from PySide6.QtWidgets import QMenu
        os.environ[extensions.NO_BUNDLED_ENV] = "1"
        seen = []

        class Sample:
            name = "sample"

            def attach(self, window) -> None:
                window.sample_menu = QMenu("見本", window)
                window.sample_menu.addAction("見本の項目", lambda: seen.append(window))
                window.menuBar().addMenu(window.sample_menu)

        before = self.menus(self.window())
        sample = Sample()
        extensions.register(sample)
        extensions.register(sample)   # 2 回登録しても 1 つ
        self.assertEqual(extensions.registered(), (sample,))
        w = self.window()
        self.assertEqual(self.menus(w), before + ["見本"])
        w.sample_menu.actions()[0].trigger()
        self.assertEqual(seen, [w])

    def test_broken_extension_does_not_stop_the_window(self):
        os.environ[extensions.NO_BUNDLED_ENV] = "1"

        class Broken:
            name = "broken"

            def attach(self, window) -> None:
                raise RuntimeError("付けられない")

        extensions.register(Broken())
        err = io.StringIO()
        with redirect_stderr(err):
            w = self.window()
        self.assertTrue(w.isVisible())
        self.assertIn("broken", err.getvalue())        # 失敗は捨てずに stderr へ出す
        self.assertIn("付けられない", err.getvalue())

    def test_entry_points_load_and_skip_a_broken_one(self):
        class Good:
            name = "good"

            def attach(self, window) -> None:
                pass

        class Point:
            def __init__(self, name, value):
                self.name, self.value, self._value = name, name, value

            def load(self):
                if isinstance(self._value, Exception):
                    raise self._value
                return self._value

        points = [Point("bad", ImportError("読めない")), Point("cls", Good), Point("not-extension", object())]
        err = io.StringIO()
        with mock.patch("importlib.metadata.entry_points", lambda group: points if group == extensions.GROUP else []), \
                redirect_stderr(err):
            names = extensions.load_entry_points()
        self.assertEqual(names, ["good"])
        self.assertEqual([e.name for e in extensions.registered()], ["good"])
        self.assertIn("bad", err.getvalue())
        self.assertIn("not-extension", err.getvalue())


if __name__ == "__main__":
    unittest.main()
