"""人物以外の題材の検品（atelier/qc/subject_check.py）と、その場で調べて検品する形（atelier/qc/research_check.py）の試験。
絵は合成の図形で作り、崩れた絵と崩れていない絵の両方で、崩れだけを見つけるかを見る。"""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from atelier.qc import research_check as rc
from atelier.qc import subject_check as sc


def building(lean=0.0, irregular=False, size=256):
    """縦の線の倒れは、模型の絵と同じく建物ごと傾ける（窓の縁も一緒に倒れる）"""
    im = Image.new("RGB", (size, size), (200, 220, 240))
    d = ImageDraw.Draw(im)
    for x in (40, 216):
        d.line([(x, 20), (x, size - 10)], fill=(20, 20, 20), width=4)
    xs = [56, 80, 100, 150, 160, 196] if irregular else [56, 86, 116, 146, 176]
    for x in xs:
        for y in (60, 120, 180):
            d.rectangle([x, y, x + 14, y + 24], fill=(30, 30, 60))
    return im.rotate(lean, resample=Image.BICUBIC, fillcolor=(200, 220, 240)) if lean else im


def landscape(gap=False, upside=False, size=200):
    im = Image.new("RGB", (size, size), (90, 140, 60))
    d = ImageDraw.Draw(im)
    sky = (110, 160, 235)
    if upside:
        d.rectangle([0, size // 2, size, size], fill=sky)
    else:
        d.rectangle([0, 0, size, size // 2], fill=sky)
    if gap:
        d.rectangle([0, size // 2 - 10, size, size // 2 + 10], fill=(255, 255, 255))
    return im


def pattern(broken=False, size=256):
    im = Image.new("RGB", (size, size), (240, 240, 240))
    d = ImageDraw.Draw(im)
    widths = [12, 28, 4, 20, 9, 26, 14, 6]   # 崩れた模様: 幅が繰り返さない
    for i, x in enumerate(range(0, size, 32)):
        w = widths[i % len(widths)] if broken else 12
        d.rectangle([x, 0, x + w, size], fill=(40, 40, 120))
    return im


class KindTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(sc.kind("1girl, solo"), "person")
        self.assertEqual(sc.kind("old castle on a hill, windows"), "building")
        self.assertEqual(sc.kind("mountain lake at dawn"), "landscape")
        self.assertEqual(sc.kind("red bicycle, side view"), "vehicle")
        self.assertEqual(sc.kind('logo, text "ATELIER"'), "text")
        self.assertEqual(sc.kind("seamless floral pattern"), "pattern")
        self.assertEqual(sc.kind("scenery, no humans, empty field"), "background")
        self.assertEqual(sc.kind("three apples on a table"), "object")
        self.assertEqual(sc.kind("cozy bedroom"), "interior")
        self.assertEqual(sc.kind("a brown dog running"), "animal")
        self.assertEqual(sc.kind("hasselblad 500c/m"), "unknown")

    def test_coverage_has_every_subject(self):
        self.assertEqual(set(sc.COVERAGE), set(sc.SUBJECTS))
        for seen, unseen in sc.COVERAGE.values():
            self.assertTrue(seen and unseen)

    def test_asked_count_and_text(self):
        self.assertEqual(sc.asked_count("three apples"), 3)
        self.assertEqual(sc.asked_count("3 cups, table"), 3)
        self.assertIsNone(sc.asked_count("1girl, apple"))
        self.assertEqual(sc.asked_count("林檎が三つ"), 3)
        self.assertEqual(sc.asked_text('logo, text "CAFE"'), "CAFE")
        self.assertEqual(sc.asked_text("看板に「本日休業」"), "本日休業")


class MeasureTest(unittest.TestCase):
    def test_vertical_lean(self):
        ok = sc.vertical_lean(building(0))
        bad = sc.vertical_lean(building(9))
        self.assertTrue(ok["readable"] and bad["readable"])
        self.assertLessEqual(ok["lean"], sc.VERTICAL_LEAN_MOST)
        self.assertGreater(bad["lean"], sc.VERTICAL_LEAN_MOST)

    def test_window_grid(self):
        ok = sc.window_grid(building(irregular=False))
        bad = sc.window_grid(building(irregular=True))
        self.assertTrue(ok["readable"] and bad["readable"])
        self.assertLess(ok["cv"], sc.WINDOW_CV_MOST)
        self.assertGreater(bad["cv"], ok["cv"])

    def test_sky_ground(self):
        self.assertLessEqual(sc.sky_ground(landscape())["gap"], sc.GAP_ROWS_SHARE)
        self.assertGreater(sc.sky_ground(landscape(gap=True))["gap"], sc.GAP_ROWS_SHARE)
        self.assertFalse(sc.sky_ground(landscape())["upside_down"])
        self.assertTrue(sc.sky_ground(landscape(upside=True))["upside_down"])

    def test_pattern(self):
        ok = sc.pattern_repeat(pattern())
        bad = sc.pattern_repeat(pattern(broken=True))
        self.assertTrue(ok["readable"])
        self.assertLessEqual(ok["diff"], sc.PATTERN_DIFF_MOST)
        self.assertTrue(not bad["readable"] or bad["diff"] > ok["diff"])

    def test_check_routes(self):
        r = sc.check(building(9), "tall building, windows, street")
        self.assertTrue(any("縦の線" in f for f in r["flaws"]), r)
        r = sc.check(landscape(gap=True), "mountain landscape")
        self.assertTrue(any("空と地面" in f for f in r["flaws"]), r)
        r = sc.check(landscape(), "mountain landscape")
        self.assertEqual(r["flaws"], [])
        r = sc.check(Image.new("RGB", (64, 64), "white"), 'logo, text "CAFE"', ocr=lambda im: {"readable": True, "text": "Cafe."})
        self.assertEqual(r["flaws"], [])
        r = sc.check(Image.new("RGB", (64, 64), "white"), 'logo, text "CAFE"', ocr=lambda im: {"readable": True, "text": "CAFF"})
        self.assertTrue(any("文字" in f for f in r["flaws"]))   # 1 字の綴りの違いも崩れ
        r = sc.check(Image.new("RGB", (64, 64), "white"), 'logo, text "CAFE"', ocr=lambda im: {"readable": True, "text": "xq"})
        self.assertTrue(any("文字" in f for f in r["flaws"]))
        r = sc.check(Image.new("RGB", (64, 64), "white"), 'logo, text "CAFE"', ocr=lambda im: {"readable": False, "reason": "無い"})
        self.assertFalse(r["readable"])   # 読めないのを崩れが無いとしない
        r = sc.check(landscape(), "scenery, no humans, field", tags={"1girl": 0.9})
        self.assertTrue(any("人数" in f for f in r["flaws"]))
        r = sc.check(landscape(), "a horse in a field", tags={"extra legs": 0.6})
        self.assertTrue(any("足の数" in f for f in r["flaws"]))

    def test_object_count(self):
        im = Image.new("RGB", (200, 120), "white")
        d = ImageDraw.Draw(im)
        for x in (20, 90):
            d.ellipse([x, 40, x + 40, 80], fill=(200, 30, 30))
        r = sc.check(im, "three apples, white background")
        self.assertIn("blobs", r["numbers"])
        self.assertTrue(any("物の数" in f for f in r["flaws"]), r)

    def test_person_is_left_to_person_checks(self):
        self.assertEqual(sc.phase_flaws(building(9), "1girl, solo, city")["flaws"], [])


class ResearchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "subject_checks.json"

    def test_research_then_remember(self):
        calls = []

        def research(subject, ask_web=None, fetch=None):
            calls.append(subject)
            return {"subject": subject, "source": "words_model", "note": "",
                    "checklist": [{"name": "wheel", "kind": "count", "expect": 2},
                                  {"name": "lens", "kind": "shape", "expect": "round"},
                                  {"name": "bad", "kind": "color", "expect": "red"}]}
        got = rc.checklist_for("penny-farthing", research=research, path=self.path)
        self.assertEqual(got["source"], "words_model")
        self.assertEqual([i["name"] for i in got["checklist"]], ["wheel", "lens"])   # 形に合わない項目は覚えない
        again = rc.checklist_for("Penny-Farthing ", research=research, path=self.path)
        self.assertEqual(again["source"], "remembered")
        self.assertEqual(calls, ["penny-farthing"])   # 2 回目は調べない
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(stored["penny-farthing"]), {"checklist", "source"})   # 絵も言葉も覚えない

    def test_web_needs_permission(self):
        asked = []

        def research(subject, ask_web=None, fetch=None):
            if ask_web and ask_web(subject):
                return {"source": "web", "checklist": [{"name": "窓", "kind": "count", "expect": 3}]}
            return {"source": "none", "checklist": [], "note": "知らない"}
        no = rc.checklist_for("x", research=research, ask_web=lambda s: asked.append(s) or False, path=self.path)
        self.assertEqual(no["checklist"], [])
        self.assertEqual(asked, ["x"])
        yes = rc.checklist_for("x", research=research, ask_web=lambda s: True, fetch=lambda s: "", path=self.path)
        self.assertEqual(yes["source"], "web")

    def test_evaluate_and_unknown_flow(self):
        im = Image.new("RGB", (200, 120), "white")
        d = ImageDraw.Draw(im)
        for x in (20, 90, 150):
            d.rectangle([x, 40, x + 25, 80], fill=(20, 20, 20))
        res = rc.evaluate(im, [{"name": "body", "kind": "count", "expect": 2},
                               {"name": "parts", "kind": "order", "expect": ["a", "b"]}])
        self.assertTrue(any("body" in f for f in res["flaws"]))
        self.assertTrue(any("parts" in u for u in res["unreadable"]))   # 測れない項目は残す
        out = rc.check(im, "hasselblad 500c/m", research=lambda s, **k: {"checklist": [], "note": "知らない"}, path=self.path)
        self.assertTrue(out["used"] and out["unreadable"])
        self.assertFalse(rc.check(im, "mountain lake")["used"])

    def test_no_thinker_is_unreadable(self):
        out = rc.checklist_for("zzz", research=None, path=self.path) if rc._thinker_research() is None else {"checklist": []}
        self.assertEqual(out["checklist"], [])


class PartsTest(unittest.TestCase):
    def test_regions_and_steps(self):
        from atelier.ai import subject_parts as sp
        r = sp.regions(landscape())
        self.assertIsNotNone(r["sky"])
        self.assertIn("空と地面", sp.steps("landscape", "仕上げ"))
        self.assertEqual(sp.steps("person", "仕上げ"), [])
        from atelier.ai import phase_items as pi
        names = {n for n, _w in pi.KEYWORDS}
        for kind in sp.STEPS.values():
            for items in kind.values():
                self.assertTrue(set(items) <= names, items)


if __name__ == "__main__":
    unittest.main()
