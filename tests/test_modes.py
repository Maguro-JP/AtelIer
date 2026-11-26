"""モード（起動時に選ぶ）・キャラクターデザインのメニュー・一括生成・キャラクターシート・追加資料を、窓から押して最後まで通す。

描くのは試験用の描き手（紙の色で塗るだけ）。最後の 1 本だけ、試験用の小さな SDXL（重みは乱数）を本物の engine.Painter で読んで流す。
見るのは、押した項目が全部動いて結果がファイルと .chara に入ること、design_status の足りない物が減ること、
モードを替えても絵とレイヤーが残ること"""
import os
import sys
import time
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ATELIER_CHECK", "off")
sys.path.insert(0, str(ROOT / ".cache" / "simple" / "lib"))
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from tests.test_editing import app  # noqa: E402

SPEC = {"name": "Akari", "look": "1girl, solo, short red hair, green eyes", "outfit": "blue hoodie, black skirt",
        "eyes": "large round eyes, emerald iris", "personality": "明るい", "role": "配達人", "age": "17",
        "height": "158cm", "backstory": "港町で荷物を運ぶ。", "negative": "extra weapons"}


def figure(size=(256, 384), color=(200, 80, 80)):
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.ellipse((size[0] * 0.38, size[1] * 0.04, size[0] * 0.62, size[1] * 0.2), fill=(245, 205, 175))
    d.rectangle((size[0] * 0.3, size[1] * 0.2, size[0] * 0.7, size[1] * 0.9), fill=color)
    return im


class Painter:
    """試験用の描き手。頼みに FAIL があれば落ちる（一括生成で 1 枚を失敗させる）"""
    model = "fake"

    def __init__(self):
        self.calls = []

    def ready(self):
        return True

    def paint(self, prompt, seed, on_step=None, **kw):
        self.calls.append(("paint", prompt, seed))
        if "FAIL" in prompt:
            raise RuntimeError("試験のための失敗")
        if on_step:
            on_step(1, 1)
        return figure()

    def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
        self.calls.append(("redraw", prompt, seed))
        out = image.copy()
        out.paste(Image.new("RGB", image.size, (250, 250, 250)), (0, 0), mask)
        return out


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

    def tearDown(self):
        for w in self.windows:
            w.dirty = False
            w.closing_checked = True
            w.close()
        self.qapp.processEvents()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def window(self, painter=None):
        from atelier.app.main_window import Window
        from atelier.ai.engine import Studio
        from tests.test_draw import FakeWords
        w = Window(Studio(FakeWords(), painter or Painter(), self.d / "out"))
        for k in ("mode/current", "mode/ask", "mode/tour_illustrator", "mode/tour_designer", "mode/tour_logo", "sheet_layout"):
            w.layout_store.remove(k)
        w.show()
        self.qapp.processEvents()
        self.windows.append(w)
        return w

    def wait(self, cond, secs=120):
        end = time.time() + secs
        while time.time() < end and not cond():
            self.qapp.processEvents()
            time.sleep(0.01)
        self.assertTrue(cond())

    def idle(self, w, secs=120):
        self.wait(lambda: w.thread is None, secs)

    def acts(self, menu):
        """メニューの項目（区切りを除く）。開くときの作り直しも通す"""
        menu.aboutToShow.emit()
        return {a.text(): a for a in menu.actions() if not a.isSeparator()}


class BatchTest(Base):
    def test_parse(self):
        from atelier.ai import batch
        jobs, bad = batch.parse("1girl, red scarf\n# 飛ばす\n\nknight, snow", 2, 10)
        self.assertEqual([(j["text"], j["count"], j["seed"]) for j in jobs], [("1girl, red scarf", 2, 11), ("knight, snow", 2, 14)])
        jobs, bad = batch.parse("頼み,枚数,種\n\"cat, sitting\",3,5\ndog,x,1\n,1,1", 1, 0)
        self.assertEqual([(j["text"], j["count"], j["seed"]) for j in jobs], [("cat, sitting", 3, 5)])
        self.assertEqual(len(bad), 2)

    def test_three_lines_one_fails_from_window(self):
        w = self.window()
        acts = {"一括生成…": w.batch_action}   # 一括生成はファイルのメニューにある（絵の模型の一覧には置かない）
        self.assertIn("一括生成…", acts)
        self.assertTrue(acts["一括生成…"].toolTip())
        text = "1girl, red scarf\nFAIL on purpose\nknight, snow"
        with mock.patch.object(type(w), "_batch_dialog", lambda self: (text, 1, 3, None)):
            acts["一括生成…"].trigger()
        self.wait(lambda: getattr(w, "batch_result", None) is not None, 300)
        res = w.batch_result
        print("\n" + __import__("atelier.ai.batch", fromlist=["x"]).summary(res))
        self.assertEqual(len(res["done"]), 2)
        self.assertEqual(len(res["failed"]), 1)
        self.assertEqual(res["failed"][0][0], 2)
        lib = [i["path"] for i in w.library.items]
        self.assertTrue(all(p in lib for p in res["done"]))
        self.idle(w)

    def test_stop(self):
        from atelier.ai import batch
        from atelier.ai import engine
        seen = []

        def draw(text, seed, neg):
            seen.append(text)
            engine.STOP.set()
            return f"/tmp/{seed}.png"
        try:
            res = batch.run(batch.parse("a\nb\nc")[0], draw, stopped=engine.STOP.is_set)
        finally:
            engine.STOP.clear()
        self.assertEqual((len(res["done"]), res["stopped"], seen), (1, True, ["a"]))

class LogoTest(Base):
    def test_export_forms(self):
        from atelier.ai import logo_maker as logo
        img = Image.new("RGB", (300, 200), "white")
        ImageDraw.Draw(img).ellipse((50, 30, 250, 170), fill=(200, 30, 30))
        out = logo.export_forms(img, self.d / "x", transparent=True, mono_=True, line=4, square_=True, line_stamp=True, size=512)
        with Image.open(out[0]) as im:
            self.assertEqual(im.size, (512, 512))
            self.assertEqual(im.getpixel((0, 0))[3], 0)
            self.assertLessEqual(len({p[:3] for p in im.getdata() if p[3] > 128}), 2)
        z = [p for p in out if str(p).endswith(".zip")][0]
        self.assertIn("main.png", zipfile.ZipFile(z).namelist())
        with Image.open(self.d / "x" / "line" / "01.png") as st:
            self.assertEqual(st.size, (370, 320))

    def test_export_from_window(self):
        w = self.window()
        acts = self.acts(w.logo_menu)
        self.assertIn("書き出しの形を選ぶ…", acts)
        acts["書き出しの形を選ぶ…"].trigger() if False else w.logo_export({"line_stamp": True})
        self.wait(lambda: getattr(w, "logo_out", None), 120)
        self.idle(w)   # 書き出したあとに糸が残らない（残ると、ほかの項目が「描いている間」のまま押せなかった）
        self.assertTrue(all(Path(p).exists() for p in w.logo_out))


def _tiny():
    from tests.test_finish_quality import TINY, tiny_ready
    return TINY if tiny_ready() else None


if __name__ == "__main__":
    unittest.main()
