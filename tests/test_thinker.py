"""考える役（atelier/ai/thinker.py）の試験。AI の補完の指示は頼みと照らして食い違う語を捨て、
形に合わない答えは捨てて決まった手順に回り、利用者の頼みの言葉には何も足さないことを確かめる"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(ROOT))

from atelier.ai import thinker  # noqa: E402

SCENES = [
    "classroom, sunset, school, scenery, no humans",
    "1girl, solo, classroom, sunset, school uniform",
    "train station, platform, scenery, no humans",
    "shrine, torii, stone path, 1boy, solo",
    "beach, town, sea, scenery, no humans",
    "forest, path, 1girl, solo, walking",
    "shopping street, rain, scenery, no humans",
]
PEOPLE = ["1girl, solo, waving, full body", "1boy, solo, sitting, reading book",
          "dog, 1boy, child, running", "1girl, solo, profile, close-up"]


class Reply:
    def __init__(self, text):
        self.text = text

    def ask(self, system, text, max_tokens=64, one_line=True):
        return self.text


class ThinkerTest(unittest.TestCase):
    def test_new_person_and_place_dropped(self):
        keep, drop = thinker.check_words("2girls, castle, sky, soft clouds", "1girl, solo, sky")
        self.assertEqual(keep, ["sky"])
        self.assertEqual(len(drop), 3)   # 2girls（人物）、castle（場所）、soft clouds（頼みに無い好み）

    def test_scene_words_allowed(self):
        keep, _ = thinker.check_words("school building, windows", "1girl, school, sunset")
        self.assertEqual(keep, ["school building", "windows"])

    def test_negative_dropped(self):
        keep, drop = thinker.check_words("hat, sky", "1girl, sky", negative=["hat"])
        self.assertEqual(keep, ["sky"])

    def test_rules_background_uses_place(self):
        for p in SCENES:
            r = thinker.complement(p, "下塗り", "背景", flaws=["背景が違う"], model=None)
            self.assertEqual(r["area"], "background")
            self.assertTrue(r["words"], p)
            keep, drop = thinker.check_words(r["words"], p)
            self.assertFalse(drop, p)

    def test_rules_people_parts(self):
        for p in PEOPLE:
            r = thinker.rules(p, "線画", "手", regions=[([0, 0, 4, 4], "hand")])
            self.assertIn("five fingers", r["words"])
            self.assertEqual(r["source"], "rules")

    def test_thinker_answer_checked(self):
        m = Reply('{"area": "background", "how": "erase_redraw", "words": "sky, soft clouds, 1boy", "strength": 0.5}')
        r = thinker.complement("1girl, solo, sky", "下塗り", "背景", flaws=["背景が違う"], model=m)
        self.assertEqual(r["source"], "thinker")
        self.assertNotIn("1boy", r["words"])
        self.assertNotIn("soft clouds", r["words"])   # 頼みに無い好みは捨てる
        self.assertTrue(any("1boy" in d for d in r["dropped"]))

    def test_bad_shape_falls_back(self):
        for text in ("no json", '{"area": "moon", "how": "erase_redraw", "words": ""}',
                     '{"area": "background", "how": "erase_redraw", "words": "sky", "strength": 3}'):
            r = thinker.complement("1girl, sky", "下塗り", "背景", flaws=["背景が違う"], model=Reply(text))
            self.assertEqual(r["source"], "rules", text)

    def test_no_flaw_no_complement(self):
        """間違いの無い所には、思考の模型が何を答えても補完は 0 件"""
        m = Reply('{"area": "whole", "how": "erase_redraw", "words": "sky", "strength": 0.5}')
        for p in SCENES + PEOPLE:
            r = thinker.complement(p, "仕上げ", "背景", model=m)
            self.assertEqual((r["words"], r["source"]), ("", "none"))

    def test_keep_asked_time_and_weather(self):
        """青空・昼の頼みに、夕焼けや夜の語を足さない"""
        m = Reply('{"area": "background", "how": "erase_redraw", "words": "sunset, orange sky, night, school building", "strength": 0.5}')
        for p in ("school, blue sky, scenery", "train station, platform, day, scenery"):
            r = thinker.complement(p, "下塗り", "背景", flaws=["背景が違う"], model=m)
            for bad in ("sunset", "orange sky", "night"):
                self.assertNotIn(bad, thinker._tags(r["words"]), p)

    def test_words_follow_request_not_converge(self):
        """頼みが違えば補完も違い、同じ頼みなら何回呼んでも同じ（前の答えを覚えて寄せない）"""
        got = {p: thinker.complement(p, "下塗り", "背景", flaws=["背景が違う"], model=None)["words"] for p in SCENES}
        self.assertEqual(len(set(got.values())), len(SCENES) - 1)   # 教室の 2 つは場所が同じなので、背景の補完も同じ
        for p in SCENES:
            self.assertEqual(thinker.complement(p, "下塗り", "背景", flaws=["背景が違う"], model=None)["words"], got[p])

    def test_no_model(self):
        r = thinker.complement("forest, path", "下塗り", "背景", flaws=["背景が違う"], model=None)
        self.assertEqual(r["source"], "rules")
        self.assertIn("trees", r["words"])

    def test_merge_keeps_user_words_first(self):
        user = "1girl, solo, sky"
        out = thinker.merge(user, "sky, soft clouds")
        self.assertTrue(out.startswith(user))
        self.assertEqual(out, "1girl, solo, sky, soft clouds")
        self.assertEqual(thinker.merge(user, ""), user)


class PhasesRecordTest(unittest.TestCase):
    def test_request_words_unchanged_and_complement_separate(self):
        """精度優先で直しが入っても、頼みの言葉（request_words）は渡した頼みのままで、補完は別の欄に残る"""
        import json
        from tempfile import TemporaryDirectory
        from tests import test_phases as tp
        prompt = "1girl, solo, classroom, sunset"
        with TemporaryDirectory() as d:
            try:
                tp.phases.draw(tp.FakePainter(), prompt, 1, (64, 96), Path(d), checks=tp.hand_only_checks(),
                               thinker_model=None)
            except Exception as e:   # 偽の部品の形が変わったときは、この試験を飛ばさず落とす
                raise AssertionError(e)
            rec = json.loads((Path(d) / "phases.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["request_words"], prompt)
        for m in rec["complements"]:
            self.assertIn(m["source"], ("rules", "thinker"))
        for r in rec["history"]:
            for m in r.get("mends") or []:
                for w in m.get("words") or []:
                    self.assertNotIn("five fingers, correct hand, soft clouds", str(w))


if __name__ == "__main__":
    unittest.main()
