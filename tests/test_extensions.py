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
    def test_nothing_is_bundled(self):
        self.assertEqual(extensions.BUNDLED, ())


class CatalogTest(unittest.TestCase):
    """一緒に開発するデザイナーの一覧（atelier/extension_catalog.py）。名前を 1 か所で持ち、ほかはそこから取る"""

    def test_six_designers(self):
        from atelier import extension_catalog as cat
        self.assertEqual([d.name for d in cat.DESIGNERS],
                         ["CharacterDesigner", "FashionDesigner", "LogoDesigner", "EmblemDesigner", "3DDesigner", "VirtualDesigner"])
        for d in cat.DESIGNERS:
            self.assertEqual(d.repo, f"Maguro-JP/{d.name}")
            self.assertTrue(d.dropin.isidentifier(), d.dropin)   # 置き場の名前はパッケージの名前にもできる形
        self.assertEqual(len({d.key for d in cat.DESIGNERS}), 6)
        self.assertEqual(len({d.dropin for d in cat.DESIGNERS}), 6)

    def test_installer_sections_come_from_the_catalog(self):
        """Release のあるデザイナーだけを選べる部品にし、取れないときは理由を出して飛ばす"""
        from atelier import extension_catalog as cat
        sys.path.insert(0, str(ROOT / "packaging"))
        try:
            import extension_sections
        finally:
            sys.path.remove(str(ROOT / "packaging"))
        nsh = extension_sections.sections()
        for d in cat.DESIGNERS:
            shown = f'Section /o "{d.name} も入れる' in nsh
            self.assertEqual(shown, d.installer, d.name)
            if d.installer:
                self.assertIn(f'-Repo "{d.repo}"', nsh)
        self.assertEqual(nsh.count("MessageBox"), 2 * len(cat.for_installer()))
        nsi = (ROOT / "packaging" / "installer.nsi").read_text(encoding="utf-8")
        self.assertIn('!include "${EXTNSH}"', nsi)
        self.assertNotIn("CharacterDesigner も入れる", nsi)   # 節を手で書かない
        ps1 = (ROOT / "packaging" / "get-extension.ps1").read_text(encoding="utf-8")
        self.assertNotIn("CharacterDesigner", ps1)
        self.assertIn("exit 2", ps1)

    def test_migration_source_comes_from_the_catalog(self):
        from atelier import extension_catalog as cat
        from atelier.app import migrate
        self.assertEqual(migrate.SOURCE_APP, cat.by_key("character").name)


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

    def test_every_designer_loads_through_the_dropin_folder(self):
        """6 つのデザイナーが、どれも同じ道（置き場の <dropin>\\extension.json）で読まれる。置き場に無い物は読まない"""
        import json
        from atelier import extension_catalog as cat
        root = self.d / "extensions"
        present = [d for d in cat.DESIGNERS if d.key != "virtual"]   # 1 つは入れずにおき、無い物に何も出ないことを見る
        for d in present:
            pkg = root / d.dropin / f"sample_{d.dropin}"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text(
                f"class E:\n    name = {d.name!r}\n    def attach(self, window):\n        pass\nEXTENSION = E()\n", encoding="utf-8")
            (root / d.dropin / extensions.MANIFEST).write_text(
                json.dumps({"module": f"sample_{d.dropin}", "attr": "EXTENSION"}), encoding="utf-8")
        (root / cat.by_key("virtual").dropin).mkdir()   # extension.json の無いフォルダーは拡張ではない
        added = []
        try:
            names = extensions.load_dropins(root)
            added = [str((root / d.dropin).resolve()) for d in present]
        finally:
            for where in added:
                if where in sys.path:
                    sys.path.remove(where)
            for d in present:
                sys.modules.pop(f"sample_{d.dropin}", None)
        self.assertEqual(sorted(names), sorted(d.name for d in present))
        self.assertNotIn("VirtualDesigner", [e.name for e in extensions.registered()])

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
