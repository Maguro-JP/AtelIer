"""拡張の登録口（atelier/extensions.py）。本体がキャラクターデザインを持たずに動くこと、拡張の口が働くこと。

キャラクターデザインは CharacterDesigner の `character_designer` パッケージに移り、entry points で入る
（拡張を付けた窓の試験は CharacterDesigner の tests/test_atelier_extension.py）。ここで見るのは、本体のどのファイルも
キャラクターデザインのパッケージを読んでいないこと（文字で調べる）、同梱の拡張が無いこと、拡張の無い窓に
キャラクターデザインのメニュー・ファイルの項目・ライブラリーのタブ・モードが無いこと、
小さな見本の拡張がメニューとモードを足せること、entry points の拡張が読めること。
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
    def test_core_does_not_import_character_design(self):
        """本体は、キャラクターデザインのパッケージ（前の atelier.chara、今の character_designer）を読まない。
        本体が拡張を読むと、拡張を別のリポジトリに置けなくなるため"""
        self.assertFalse((ROOT / "atelier" / "chara").exists())
        # 読み方の形だけを見る（置き場を書いた説明は読み込みではないので拾わない）
        pattern = re.compile(r"atelier\.chara\b|from\s+atelier\s+import\s+[^\n]*\bchara\b|^\s*(from|import)\s+character_designer\b")
        hits = []
        for path in sorted((ROOT / "atelier").rglob("*.py")):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append((path.relative_to(ROOT).as_posix(), n, line.strip()))
        self.assertEqual(hits, [])

    def test_nothing_is_bundled(self):
        self.assertEqual(extensions.BUNDLED, ())


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
        from tests.test_draw import FakePainter, FakeWords
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
    def test_load_bundled_with_nothing_bundled(self):
        extensions.load_bundled(again=True)   # 同梱の拡張が無くても、読み込みは何もせずに終わる
        self.assertEqual(extensions.registered(), ())
        w = self.window()
        self.assertNotIn(CHARA_MENU, self.menus(w))

    def test_sample_extension_adds_a_mode(self):
        from atelier.app import modes

        class WithMode:
            name = "with-mode"

            def attach(self, window) -> None:
                modes.register("sample", dict(name="見本のモード", sub="見本", tip="見本のモードです", menus=(), hide_panels=()),
                               after="illustrator")
                window.add_mode("sample")

            def unload(self) -> None:
                modes.unregister("sample")

        ext = WithMode()
        extensions.register(ext)
        w = self.window()
        self.assertEqual(list(modes.MODES), ["illustrator", "sample", "logo"])
        self.assertIn("sample", w.mode_actions)
        extensions.unregister(ext)   # 外すと、足したモードも消える
        self.assertEqual(list(modes.MODES), ["illustrator", "logo"])

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


class InstallerPartTest(unittest.TestCase):
    def test_characterdesigner_part_takes_extension_setup_only(self):
        """インストーラーの選べる部品の CharacterDesigner は、Release の拡張だけの Setup（CharacterDesigner-Extension-Setup.exe）を取る。
        Python ごと入った単体の CharacterDesigner-Setup.exe を取ると、AtelIer の横にアプリがもう 1 つ入るため"""
        ps1 = (ROOT / "packaging" / "get-characterdesigner.ps1").read_text(encoding="utf-8")
        self.assertIn("-like '*Extension*Setup*.exe'", ps1)
        self.assertNotIn("-like '*Setup*.exe'", ps1)
        self.assertIn("repos/Maguro-JP/CharacterDesigner/releases/latest", ps1)
        nsi = (ROOT / "packaging" / "installer.nsi").read_text(encoding="utf-8")
        self.assertIn('Section "CharacterDesigner も入れる', nsi)   # 選べる部品として出し、既定で選ぶ（/o を付けない）
        self.assertNotIn('Section /o "CharacterDesigner', nsi)
        self.assertIn("get-characterdesigner.ps1", nsi)


if __name__ == "__main__":
    unittest.main()
