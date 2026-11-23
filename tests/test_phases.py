"""工程に分けて描く（atelier/ai/phases.py）を偽の模型と偽の検品で通す。
工程は人の描き方の 12。崩れは前の工程へ戻らず、今の絵の崩れた所の囲みの中だけを直す（外は 1 画素も変えない）。
手を替えて直しても消えない崩れと囲めない崩れは、工程を足し続けずに利用者に聞いて止まる。ただし描かない工程（目的・サムネイル・アタリ）
では聞かず、前の工程の絵を土台に種を替え強さを上げて描き直す（検品を通っていないアタリの絵をキャンバスに出さない）。
累計は絵が変わった回だけを数える。
偽の検品は必ず「何回目かで通る」形にして、試験が終わらなくならないようにする"""
import os
import re
import sys
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ATELIER_CHECK", "off")
sys.path.insert(0, str(ROOT / ".cache" / "simple" / "lib"))
sys.path.insert(0, str(ROOT))

from atelier.ai import phases  # noqa: E402
from atelier.ai import phase_tools as pt  # noqa: E402
from atelier.ai.engine import Stopped, Studio  # noqa: E402
from tests.test_chatdraw import FakePainter, FakeWords  # noqa: E402

HAND = {"readable": True, "bad": ["手 1: 指が 6 本"], "hands": [{"box": [10, 10, 30, 30], "bad": ["指が 6 本"], "seen": True}],
        "feet": [], "faces": []}
CLEAN_HAND = {"readable": True, "bad": [], "hands": [], "feet": [], "faces": []}


def figure(size=(64, 96)):
    """白い紙に、暗い人物（体と頭）を置いた絵。右側を明るくして光の向きが読めるようにする"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.35, h * 0.25, w * 0.5, h * 0.95], fill=(60, 60, 80))
    d.rectangle([w * 0.5, h * 0.25, w * 0.65, h * 0.95], fill=(150, 150, 170))
    d.ellipse([w * 0.38, h * 0.05, w * 0.62, h * 0.25], fill=(120, 100, 90))
    # 目の検品用に、左右対称の白いハイライトを描く（空の顔を「検品合格」と誤認しない）
    r = max(1, int(min(w, h) * 0.025))
    for x in (w * 0.45, w * 0.55):
        d.ellipse([x - r, h * 0.15 - r, x + r, h * 0.15 + r], fill=(255, 255, 255))
    return im


class Painter(FakePainter):
    abilities = (True, True)
    steps = 20

    def __init__(self):
        super().__init__()
        self.log = []

    def paint(self, prompt, seed, on_step=None, **kw):
        self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
        super().paint(prompt, seed, on_step=on_step, **kw)
        # 頼み・種によらず同じ絵を返すと、同じ工程の繰り返しを見分けられない。種ごとに人物の色を変える
        im = figure(kw.get("size") or (64, 96))
        from PIL import ImageChops
        im = ImageChops.add(im, im.point(lambda _v: seed % 23))
        if kw.get("on_preview"):
            kw["on_preview"](im)
        return im

    def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
        self.log.append(("redraw", seed, kw.get("strength")))
        self.masks = getattr(self, "masks", []) + [mask]
        # 本物の模型と同じく絵全体を返し、囲みの中だけでなく外も変える（外を元に戻すのは phases の役目）。回ごとに違う絵にする
        from PIL import ImageChops
        return ImageChops.add(image.convert("RGB"), image.convert("RGB").point(lambda _v: 5 + seed % 7))


BAD_TIMES = 3   # 崩れを返し続ける検品が、何回目で通るか（必ず通る回を持たせ、試験を終わらせる）


def checks(always_bad: bool):
    """always_bad: どの検品も最初の BAD_TIMES 回は崩れを返し、そのあと通る。False: 1 回目だけ崩れを返す"""
    seen = {"request": 0, "body": 0, "hands": 0, "pose": 0}

    class C:
        @staticmethod
        def request(image, prompt):
            seen["request"] += 1
            # サムネイルとアタリでは依頼物を検査せず、服・髪・持ち物の工程で初めて欠落を検出する。
            # request はサムネイル 2 回・アタリ 1 回の後、服・髪・持ち物で検品する。
            bad = not always_bad and seen["request"] == 4
            return {"readable": True, "missing": ["red scarf"] if bad else [], "extra": [], "people": [], "body": []}

        @staticmethod
        def body(image, prompt, tags=None):
            seen["body"] += 1
            return {"readable": True, "bad": ["余分な腕"] if always_bad and seen["body"] <= BAD_TIMES else [], "avoid": []}

        @staticmethod
        def points(image):
            w, h = image.size
            return {"readable": True, "points": {"left_eye": (w * 0.45, h * 0.15), "right_eye": (w * 0.55, h * 0.15),
                                                 "nose": (w * 0.5, h * 0.18), "left_ear": (w * 0.4, h * 0.15),
                                                 "left_shoulder": (w * 0.4, h * 0.27), "right_shoulder": (w * 0.6, h * 0.27)}}

        @staticmethod
        def pose(image):
            seen["pose"] += 1
            return {"readable": True, "bad": ["骨の長さの比が外れている"] if always_bad and seen["pose"] <= BAD_TIMES else [], "map": image}

        @staticmethod
        def hands(image, prompt):
            seen["hands"] += 1
            # 下描きの描く工程は手を測らないので（測るのは確かめる工程だけ）、崩れを返す回は BAD_TIMES - 1 回にそろえる
            return dict(HAND) if ((always_bad and seen["hands"] <= BAD_TIMES - 1) or seen["hands"] == 1) else dict(CLEAN_HAND)
    return C, seen


N = len(phases.PHASES)


def changed(got):
    """絵が変わった回の数（工程の記録と、その中の直しの回）"""
    return sum(bool(r.get("changed")) + bool(r.get("first_changed")) + sum(bool(m.get("changed")) for m in r.get("mends", []))
               for r in got["history"])

def hand_only_checks(bad_times=BAD_TIMES - 1):
    """体・構図・依頼物は合格させ、手の検品だけを bad_times 回不合格にする。下描きの限定修正を単独で試す。"""
    seen = {"hands": 0}

    class C:
        @staticmethod
        def request(image, prompt):
            return {"readable": True, "missing": [], "extra": [], "people": [], "body": []}

        @staticmethod
        def body(image, prompt, tags=None):
            return {"readable": True, "bad": [], "avoid": []}

        @staticmethod
        def points(image):
            w, h = image.size
            return {"readable": True, "points": {"left_eye": (w * .45, h * .15), "right_eye": (w * .55, h * .15),
                    "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15), "right_ear": (w * .6, h * .15),
                    "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

        @staticmethod
        def pose(image):
            return {"readable": True, "bad": [], "map": image}

        @staticmethod
        def hands(image, prompt):
            seen["hands"] += 1
            return dict(HAND) if seen["hands"] <= bad_times else dict(CLEAN_HAND)
    return C


class PhasesTest(unittest.TestCase):
    def run_phases(self, always_bad, painter=None, confirm=None):
        painter = painter or Painter()
        C, seen = checks(always_bad)
        said = []
        from atelier.ai import phase_tools as pt
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append, checks=C, confirm=confirm)
            files = sorted(p.name for p in (Path(d) / "k").iterdir())
        return got, painter, seen, said, files

    def test_twelve_phases_in_order(self):
        self.assertEqual(phases.NAMES, ["目的", "サムネイル", "アタリ", "体の形", "顔・手・足の下描き", "服・髪・持ち物", "線画の清書",
                                        "下塗り", "光源", "影 2 段", "光・艶・目のハイライト", "仕上げ"])
        for name, decides, looks, numbers in phases.PHASES:
            self.assertTrue(decides and looks and numbers, name)   # 工程ごとに見る物と判定の数字を決めてある

    def test_flaws_add_fix_phases_until_passed(self):
        got, painter, seen, said, files = self.run_phases(always_bad=True)
        self.assertTrue(got["complete"])   # 全部の工程が検品を通ったときだけ完了として返る
        self.assertEqual(got["left"], [])
        self.assertEqual(len(got["phases"]), N)
        self.assertIn("phases.json", files)
        self.assertEqual(got["backs"], 0)   # 前の工程へ戻らない（戻って描き直すと途中で別の絵になった）
        self.assertGreater(got["fixes"], 0)
        plan = got["plan"]
        self.assertEqual(got["need"], len([s for s in plan if s["no"]]))   # 要る工程の数は計画の見せる工程の数
        self.assertEqual([s["no"] for s in plan if s["no"]], list(range(1, got["need"] + 1)))   # 計画の順に 1 つずつ進む
        self.assertTrue(all(s["status"] != "todo" for s in plan))
        kinds = {s["kind"] for s in plan}
        self.assertTrue({"draw", "check", "mend", "recheck"} <= kinds, kinds)   # 描く・確かめる・直す・確かめ直すが別の工程に並ぶ
        for k, s in enumerate(plan):
            if s["kind"] == "recheck":   # 確かめ直すのは、直した項目だけ（直す工程のあとに、同じ工程・同じ項目で並ぶ）
                self.assertTrue(any(x["kind"] == "mend" and x["item"] == s["item"] and x["phase"] == s["phase"] for x in plan[:k]), s)
                last = next(x for x in reversed(plan[:k]) if x["kind"] in ("mend", "check", "recheck", "ask"))
                self.assertEqual((last["kind"], last["item"]), ("mend", s["item"]), s)   # すぐ前は同じ項目の直す工程
        self.assertTrue(all(s["kind"] != "mend" or len(s.get("flaws", [])) >= 1 for s in plan))
        self.assertEqual(got["total"], changed(got))   # 絵が変わった回だけを数える
        mends = [m for r in got["history"] for m in r.get("mends", [])]
        self.assertTrue(mends and all(r["outside"] == 0 for r in mends), mends)   # 囲みの外は 1 画素も変えない
        self.assertEqual(len([f for f in files if f.endswith(".png") and f[:3].isdigit()]), got["total"])
        order = [phases.NAMES.index(r["phase"]) for r in got["history"]]
        self.assertEqual(order, list(range(N)))   # 工程は 1 つずつ順に進み、同じ工程の名前が続けて並ばない
        self.assertTrue(all(r["readable"] and not (r["after"] if r["fixed"] else r["found"]) for r in got["phases"]))
        self.assertEqual(painter.steps, 20)
        self.assertTrue(any(s.startswith("工程 1/") for s in said))
        self.assertTrue(any(f"累計 {got['total']} 工程）" in s for s in said))

    def test_thumbnails_small_and_picked(self):
        got, painter, *_ = self.run_phases(always_bad=False)
        paints = [x for x in painter.log if x[0] == "paint" and not x[3]]   # 下描きの線に沿う描き（base あり）は除く
        # サムネイルは工程の数を減らさずに何枚か描き、選んだ 1 枚をそのままアタリにする（同じ構図を 2 度描かない）
        self.assertEqual(len(paints), phases.THUMBS, painter.log)
        self.assertTrue(all(x[2] == 20 for x in paints))
        self.assertIn("picked", got["phases"][1]["numbers"])

    def test_back_to_draft_fixes_regions_only_and_stronger(self):
        """手の崩れで下描きへ戻ったら、絵全体を描き重ね直さず、崩れた枠の中だけを前より強く直す"""
        class P(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                return image.copy()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            painter = P()
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=hand_only_checks())
        self.assertTrue(got["complete"])
        self.assertEqual(sum(1 for x in painter.log if x[0] == "refine"), 1, painter.log)
        fixes = [m["strength"] for r in got["history"] if r["phase"] == "顔・手・足の下描き" for m in r.get("mends", [])]
        self.assertGreaterEqual(len(fixes), 1, got["history"])
        self.assertEqual(fixes, sorted(fixes))   # 直しを重ねるたびに強くする

    def test_clean_after_first_fix(self):
        got, painter, seen, said, files = self.run_phases(always_bad=False)
        self.assertEqual(got["left"], [])
        self.assertEqual(got["backs"], 0)
        for r in got["phases"]:   # 工程ごとに秒とメモリを残す
            self.assertIn("seconds", r)
            self.assertIn("mem_mb", r)

    def test_no_words_added(self):
        """渡す言葉は頼みの訳だけ。手・足・顔の直しにも five fingers などを足さない"""
        got, painter, *_ = self.run_phases(always_bad=True)
        for r in got["history"]:
            for w in r["words"]:
                rest = w.replace("(red scarf:1.3)", "red scarf")
                self.assertEqual({t.strip() for t in rest.split(",") if t.strip()} - {"1girl", "red scarf"}, set(), w)

    def test_stop_between_phases(self):
        painter = Painter()
        C = hand_only_checks()
        orig = C.hands

        def hands(image, prompt):
            painter.stop = True
            return orig(image, prompt)
        C.hands = staticmethod(hands)
        import json
        with TemporaryDirectory() as d:
            with self.assertRaises(Stopped):
                phases.draw(painter, "1girl", 1, (64, 96), Path(d) / "k", checks=C)
            got = json.loads((Path(d) / "k" / "progress.json").read_text(encoding="utf-8"))
            self.assertEqual(got["state"], "stopped")
            self.assertEqual(got["phase"], "顔・手・足の下描き")   # 手を見る最初の工程で止まった
            self.assertTrue(got["image"] and Path(got["image"]).exists())   # 止めた所までの絵が残る

    def test_draft_blocks_when_landmark_inspection_is_unreadable(self):
        base, _ = checks(always_bad=False)

        class NoLandmarks:
            request = staticmethod(base.request)
            body = staticmethod(base.body)
            pose = staticmethod(base.pose)
            hands = staticmethod(base.hands)

            @staticmethod
            def points(image):
                tries.append(1)
                if len(tries) <= BAD_TIMES:
                    return {"readable": False, "points": {}, "reason": "ランドマーク検出失敗"}
                return base.points(image)

        tries = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=NoLandmarks)
        self.assertTrue(got["complete"])   # 読めない検品は崩れとして直し、読めて通るまで続ける
        unread = [m for r in got["history"] for m in r.get("mends", []) if "検品できませんでした" in m["found"]]
        self.assertTrue(unread)   # 読めなかった絵は崩れとして囲んで直した
        self.assertGreater(got["fixes"], 0)

    def test_without_line_or_fix_still_finishes(self):
        painter = Painter()
        painter.abilities = (False, False)
        got, painter, *_ = self.run_phases(always_bad=True, painter=painter)
        # 囲みの中だけを直せない模型では、全体を描き直して直したことにせず、残った崩れと直し方を出して止まる（終わらない回り方にしない）
        self.assertFalse(got["complete"])
        self.assertIsNotNone(got["asked"])
        self.assertIn("赤ペンで囲んで直す", got["asked"]["choices"])
        self.assertFalse(any(x[0] == "redraw" for x in painter.log))

    def test_fix_masks_are_regions_only(self):
        """直しは囲みの中だけ（絵全体を描き直さない）"""
        import numpy as np
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            painter = Painter()
            from atelier.files import pause_keep as pausekeep
            pausekeep.ROOT = Path(d) / "paused"
            self.addCleanup(setattr, pausekeep, "ROOT", None)
            C = hand_only_checks(bad_times=10 ** 6)
            key = pausekeep.key("phases", "masks")
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C, pause_key=key)
            # 止まって聞いた所（聞く工程）から、窓の「このまま進む」の答えで続ける。済んだ工程は描き直さない
            plan = got["plan"]
            ask_at = next(k for k, s in enumerate(plan) if s["kind"] == "ask")
            self.assertEqual(plan[ask_at]["status"], "todo")
            self.assertTrue(all(s["status"] != "todo" for s in plan[:ask_at]))
            paints = len(painter.log)
            again = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k2", checks=C, pause_key=key, answer=phases.GO_ON)
            self.assertEqual(again["plan"][ask_at]["answer"], phases.GO_ON)
            self.assertFalse(any(x[0] in ("paint", "refine") for x in painter.log[paints:]))   # 構図から描き直さない
            self.assertEqual(again["asked"]["phase"], "仕上げ")   # 次に消えない崩れの所でまた聞く
        # ずっと通らない検品でも固まらず、手を替えた直しのあと、利用者に聞く所で止まる
        self.assertFalse(got["complete"])
        self.assertEqual(got["asked"]["phase"], "顔・手・足の下描き")
        draft = got["history"][-1]
        self.assertEqual({m["mend"] for m in draft["mends"]}, set(range(1, phases.MENDS + 1)))   # 強さの段を MENDS 回替えた
        self.assertTrue(all(m["outside"] == 0 for m in draft["mends"]))
        self.assertEqual([r["phase"] for r in got["history"]], phases.NAMES[:5])
        self.assertTrue(painter.masks)
        for m in painter.masks:
            a = np.asarray(m)
            self.assertLess((a > 0).mean(), 0.99)

    def test_confirm_redo_and_words(self):
        asked, answers = [], {2: ["redo", "go"], 5: [("words", "blue ribbon"), "go"]}

        def confirm(i, name, image, row):
            asked.append(i)
            todo = answers.get(i)
            return todo.pop(0) if todo else "go"
        got, painter, seen, said, files = self.run_phases(always_bad=False, confirm=confirm)
        self.assertEqual(asked.count(2), 2)   # 描き直した工程はもう一度確かめる
        self.assertEqual(asked.count(5), 2)
        self.assertEqual(got["phases"][2]["visit"], 1)
        self.assertTrue(any("blue ribbon" in w for r in got["history"] for w in r["words"]))
        self.assertTrue(any("言葉を足しました" in s for s in said))

    def test_words_added_at_final_phase_return_to_drawing_stage(self):
        asked = {11: [("words", "blue ribbon"), "go"]}

        def confirm(i, name, image, row):
            queue = asked.get(i)
            return queue.pop(0) if queue else "go"

        got, painter, seen, said, files = self.run_phases(always_bad=False, confirm=confirm)
        self.assertTrue(got["complete"])
        wear = [r for r in got["history"] if r["phase"] == "服・髪・持ち物"]
        self.assertTrue(any(any("blue ribbon" in word for word in r["words"]) for r in wear), wear)
        self.assertTrue(any("描き直しを頼まれたので「服・髪・持ち物」から順に進めます" in msg for msg in said))

    def test_studio_way_phases(self):
        from atelier.ai import phase_tools as pt
        C, _ = checks(False)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
             mock.patch.object(phases.Checks, "request", staticmethod(C.request)), \
             mock.patch.object(phases.Checks, "body", staticmethod(C.body)), \
             mock.patch.object(phases.Checks, "points", staticmethod(C.points)), \
             mock.patch.object(phases.Checks, "pose", staticmethod(C.pose)), \
             mock.patch.object(phases.Checks, "hands", staticmethod(C.hands)):
            painter = Painter()
            s = Studio(FakeWords(), painter, Path(d))
            s.way = "phases"
            prompt, path = s.draw("赤いマフラーの子", 7, lambda m: None)
            self.assertEqual(prompt, "1girl, red scarf")   # 背景や構図の言葉を足さない
            self.assertTrue(path.exists())
            self.assertEqual([r["phase"] for r in s.last_phases], phases.NAMES)
            s.way = "one"
            s.draw("赤いマフラーの子", 7, lambda m: None)
            self.assertIsNone(s.last_phases)

    def test_studio_confirm_translates_words(self):
        from atelier.ai import phase_tools as pt
        C, _ = checks(False)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
             mock.patch.object(phases.Checks, "request", staticmethod(C.request)), \
             mock.patch.object(phases.Checks, "body", staticmethod(C.body)), \
             mock.patch.object(phases.Checks, "points", staticmethod(C.points)), \
             mock.patch.object(phases.Checks, "pose", staticmethod(C.pose)), \
             mock.patch.object(phases.Checks, "hands", staticmethod(C.hands)):
            s = Studio(FakeWords(), Painter(), Path(d))
            s.way = "phases"
            calls = []

            def ask(i, name, image, row):
                calls.append(i)
                return ("words", "赤いマフラー") if len(calls) == 1 else "go"
            s.phase_confirm = ask
            s.draw("赤いマフラーの子", 7, lambda m: None)
            words = [w for r in s.last_phases for w in r["words"]]
            self.assertFalse(any("マフラー" in w for w in words), words)   # 日本語のまま模型に渡さない


class ToolsTest(unittest.TestCase):
    """模型を使わない処理（atelier/ai/phase_tools.py）が、人物の外を変えず、数字を返す"""

    def test_lines_and_shade_only_inside_figure(self):
        import numpy as np
        from atelier.ai import phase_tools as pt
        im = figure((128, 192))
        out, hit = pt.weight_lines(im)
        a, b = np.asarray(im), np.asarray(out)
        m = pt._dilate(pt.silhouette(im), 1)
        self.assertTrue((a[~m] == b[~m]).all())
        lit = pt.light(im)
        self.assertEqual(lit["side"], "右")
        out2, hit2 = pt.shade_second(im, lit)
        self.assertGreater(hit2, 0)
        c = np.asarray(out2)
        self.assertTrue((a[~pt.silhouette(im)] == c[~pt.silhouette(im)]).all())
        cols = np.nonzero((a != c).any(axis=2))[1]
        self.assertTrue((cols < 64).all())   # 影の 2 段目は光と反対（左）の側だけ

    def test_numbers(self):
        from atelier.ai import phase_tools as pt
        im = figure((128, 192))
        self.assertTrue(pt.balance(im)["readable"])
        self.assertLess(pt.balance(im)["balance"], pt.BALANCE_MOST)
        self.assertEqual(pt.eye_tilt({"left_eye": (0, 10), "right_eye": (20, 10)}), 0.0)
        self.assertGreater(pt.eye_tilt({"left_eye": (0, 0), "right_eye": (20, 10)}), pt.EYE_TILT)
        self.assertTrue(pt.shrink_view(im)["readable"])
        self.assertTrue(pt.flip_view(im, (40, 0, 90, 50))["readable"])
        self.assertIn("weight_x", pt.thumb_weight(im))


class ToneGuardTest(unittest.TestCase):
    """描き重ねで出た霞み・枠・色褪せを、前の絵の色と明るさに合わせて消す（phase-bench の線画で出た崩れ）"""

    def test_haze_and_frame_removed(self):
        import numpy as np
        from PIL import Image, ImageDraw
        from atelier.ai import phase_tools as pt
        ref = figure((128, 192))
        a = np.asarray(ref, dtype=np.float32) * 0.5 + 110   # 黒が浮いて白く霞む・色が褪せる
        hazy = Image.fromarray(a.astype("uint8"))
        ImageDraw.Draw(hazy).rectangle([0, 0, 127, 191], outline=(40, 40, 40), width=4)   # 額縁のような枠
        self.assertTrue(pt.tone_flaws(pt.tone(hazy), pt.tone(ref)))
        out, rec = pt.guard(hazy, ref)
        self.assertTrue(rec["raw_flaws"])
        self.assertEqual(pt.tone_flaws(pt.tone(out), pt.tone(ref)), [])

    def test_clean_redraw_kept_as_is(self):
        """崩れの無い描き重ねには色合わせを掛けない（掛けると白い背景で色が灰色に寄った）"""
        import numpy as np
        from atelier.ai import phase_tools as pt
        ref = figure((128, 192))
        raw = ref.rotate(1, fillcolor="white")
        out, rec = pt.guard(raw, ref)
        self.assertFalse(rec["matched"])
        self.assertTrue((np.asarray(out) == np.asarray(raw)).all())

    def test_match_keeps_saturation(self):
        """色合わせで彩度を下げない（R・G・B を別々に合わせると、白い背景の絵で彩度 20.4 → 12.9 に落ちた）"""
        from PIL import Image, ImageDraw
        from atelier.ai import phase_tools as pt
        ref = Image.new("RGB", (128, 192), (250, 250, 250))
        ImageDraw.Draw(ref).rectangle([30, 40, 90, 180], fill=(200, 30, 40))
        ImageDraw.Draw(ref).rectangle([40, 60, 80, 100], fill=(20, 20, 60))
        hazy = Image.blend(ref, Image.new("RGB", ref.size, (200, 200, 200)), 0.3)
        self.assertGreaterEqual(pt.tone(pt.match_colors(hazy, ref))["sat"], pt.tone(hazy)["sat"])

    def test_mask_keeps_outside(self):
        import numpy as np
        from PIL import Image
        from atelier.ai import phase_tools as pt
        ref = figure((128, 192))
        other = Image.new("RGB", ref.size, (10, 200, 30))
        mask = Image.new("L", ref.size, 0)
        mask.paste(255, (40, 40, 80, 80))
        out, _ = pt.guard(other, ref, mask)
        a, b, m = np.asarray(out), np.asarray(ref), np.asarray(mask) == 0
        self.assertTrue((a[m] == b[m]).all())


class ConfirmBridgeTest(unittest.TestCase):
    """描く糸から呼んだ確かめが、画面の糸の窓の答えを待って返す"""

    def test_worker_waits_for_answer(self):
        import threading
        import time
        from atelier.app.main_window import PhaseAsk
        from tests.test_editing import app
        qapp = app()

        class W:
            studio = type("S", (), {"painter": Painter()})()

            def ask_phase(self, i, name, image, row):
                return "redo"
        ask = PhaseAsk(W())
        got = []
        t = threading.Thread(target=lambda: got.append(ask(1, "サムネイル", None, {})))
        t.start()
        end = time.time() + 10
        while t.is_alive() and time.time() < end:
            qapp.processEvents()
            time.sleep(0.01)
        self.assertEqual(got, ["redo"])


class PhaseLayersTest(unittest.TestCase):
    def test_phase_images_are_hidden_layers_below(self):
        from PIL import Image
        from atelier.app.main_window import Window
        from tests.test_editing import app
        qapp = app()
        with TemporaryDirectory() as d:
            d = Path(d)
            w = Window(Studio(FakeWords(), Painter(), d))
            try:
                rows = []
                for i, name in enumerate(["構図", "体型と姿勢", "線画", "塗り", "仕上げ"], 1):
                    p = d / f"{i}.png"
                    Image.new("RGB", (64, 64), (i * 40, 0, 0)).save(p)
                    rows.append({"phase": name, "image": str(p), "found": ["崩れ"], "fixed": True, "after": [], "seconds": 1.0})
                final = d / "final.png"
                Image.new("RGB", (64, 64), "white").save(final)
                w.mode.setCurrentIndex(0)
                w.job_kind = "draw"
                w.studio.last_phases = rows
                w.images.append("x")
                w.place(str(final))
                w._put_phases()
                qapp.processEvents()
                c = w.canvas
                names = [l.name for l in c.layers]
                self.assertEqual(names[:5], ["工程 1: 構図", "工程 2: 体型と姿勢", "工程 3: 線画", "工程 4: 塗り", "工程 5: 仕上げ"])
                self.assertFalse(any(l.visible for l in c.layers[:5]))
                self.assertEqual(c.current, len(c.layers) - 1)   # 描いた絵が一番上で選ばれたまま
            finally:
                w.dirty = False
                w.close()



class ManualRedoTest(unittest.TestCase):
    """確認画面の描き直しは、頼まれた回数だけ直しの工程を足し、頼まれなくなったら先へ進んで完了する。"""

    def test_manual_redo_adds_phases(self):
        asked = []

        def confirm(i, *_):
            asked.append(i)
            return phases.REDO if len(asked) <= 3 else "go"
        from atelier.ai import phase_tools as pt
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "1girl", 1, (64, 96), Path(d), checks=checks(False)[0], confirm=confirm)
        self.assertTrue(got["complete"])
        self.assertGreaterEqual(got["backs"], 3)
        self.assertEqual(got["total"], changed(got))   # 頼まれた描き直しも、絵が変わった回だけ数える


class StopFlagTest(unittest.TestCase):
    """止める旗が立ったら「止めました」で返り、完了にしない。止めた所までを残す"""

    def test_stop_returns_stopped(self):
        painter = Painter()
        C = hand_only_checks(bad_times=10 ** 6)   # 止めなければ通らない検品でも、旗で止まる

        def confirm(i, *_):
            if i >= 3:   # 確かめ（confirm）は工程の最後に来る。手の崩れが消えない下描きの前で旗を立てる
                painter.stop = True
            return "go"
        with TemporaryDirectory() as d:
            with self.assertRaises(Stopped) as e:
                phases.draw(painter, "1girl", 1, (64, 96), Path(d), checks=C, confirm=confirm)
            self.assertEqual(str(e.exception), "止めました")
            import json
            kept = json.loads((Path(d) / "phases.json").read_text(encoding="utf-8"))
            self.assertTrue(kept["stopped"])
            self.assertNotIn("complete", kept)


if __name__ == "__main__":
    unittest.main()


class BrokenChecksTest(unittest.TestCase):
    """検品の部品が例外を出しても、描く流れは落ちずに最後の工程まで描き、検品できなかったと残す（0.5.30 で 1 工程目のあとに落ちた）"""

    def test_all_phases_drawn_when_checks_raise(self):
        good, _ = checks(False)
        raised = []

        def boom(name):
            def call(*a, **k):
                if len(raised) < BAD_TIMES:
                    raised.append(name)
                    raise RuntimeError("部品が無い")
                return getattr(good, name)(*a, **k)
            return staticmethod(call)

        class Boom:
            request, body, pose, hands, points = (boom(n) for n in ("request", "body", "pose", "hands", "points"))

        from atelier.ai import phase_tools as pt
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "red hair, 1girl", 1, (64, 64), Path(d), checks=Boom)
        self.assertEqual(len(raised), BAD_TIMES)   # 落ちずに描き続け、検品できなかった絵は直して描き直した
        self.assertTrue(got["complete"])
        self.assertGreater(got["fixes"], 0)
        self.assertIsNotNone(got["image"])


class WindowFlowTest(unittest.TestCase):
    """本物の窓の経路（offscreen の Window、偽の模型）で精度優先を流す。1 工程目のあとに帯が満ちて終わったように見えた"""

    def test_progress_runs_through_all_phases(self):
        import time
        from unittest import mock
        from atelier.app.main_window import Window
        from tests.test_editing import app
        qapp = app()
        d = TemporaryDirectory()
        self.addCleanup(d.cleanup)
        s = Studio(FakeWords(), Painter(), Path(d.name))
        s.way = "phases"
        w = Window(s)
        try:
            seen, chat, events = [], [], []
            act = w.activity
            orig = act.status

            def status(msg, step=None, total=None):
                orig(msg, step, total)
                seen.append((act.state.text(), act.bar.value(), act.bar.maximum(), msg))
            act.status = status
            add = w.chat.add
            w.chat.add = lambda who, text, *a, **k: (chat.append(text), add(who, text, *a, **k))[1]
            ends = []
            end = act.end
            act.end = lambda *a, **k: (ends.append(len(seen)), end(*a, **k))[1]
            C, _ = checks(False)
            from atelier.ai import phase_tools as pt
            with mock.patch.object(w, "check_ai", return_value={"image": True, "reason": ""}), \
                 mock.patch.object(w, "_keep_original", lambda x: x), \
                 mock.patch.object(w, "offer_two_stage_parts", lambda: None), \
                 mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                 mock.patch.object(phases.Checks, "request", staticmethod(C.request)), \
                 mock.patch.object(phases.Checks, "body", staticmethod(C.body)), \
                 mock.patch.object(phases.Checks, "points", staticmethod(C.points)), \
                 mock.patch.object(phases.Checks, "pose", staticmethod(C.pose)), \
                 mock.patch.object(phases.Checks, "hands", staticmethod(C.hands)):
                # Job は _draw_now 内で生成される。_record_job は thread.start より前に呼ばれるため、
                # そこで信号を接続し、速い処理でも完了通知を取りこぼさない。
                record = w._record_job
                def record_and_watch(job):
                    job.one.connect(lambda *_: events.append("one"))
                    job.done.connect(lambda: events.append("done"))
                    record(job)
                with mock.patch.object(w, "_record_job", side_effect=record_and_watch):
                    w._draw_now("赤いマフラーの子")
                t = time.time()
                while w.thread is not None and time.time() - t < 120:
                    qapp.processEvents()
                    time.sleep(0.01)
                qapp.processEvents()
                self.assertIsNone(w.thread, "描く処理が終わらない")
                self.assertEqual([r["phase"] for r in s.last_phases], phases.NAMES)
                self.assertEqual(events, ["one", "done"])   # 1 枚が出来た・終わったの信号は全部の工程のあとに 1 回ずつ
                self.assertEqual(len(ends), 1)
                # 進み具合の欄に計画の「工程 i/N 名前／描く・確かめる…」が順に出て、終わるまで帯は満ちない（目的は出さない）
                heads = [re.match(r"工程 (\d+)/(\d+)　(.+?)／", st) for st, *_ in seen]
                heads = [(int(m.group(1)), int(m.group(2)), m.group(3)) for m in heads if m]
                self.assertEqual([x[2] for x in heads if x[2] == "目的"], [])
                for name in phases.NAMES[1:]:
                    self.assertTrue(any(x[2] == name for x in heads), name)
                nums = [x[0] for x in heads]
                self.assertEqual(sorted(set(nums)), list(range(1, max(nums) + 1)))
                self.assertEqual(nums, sorted(nums))
                N = heads[-1][1]
                for st, v, mx, msg in seen[:ends[0]]:
                    self.assertFalse(mx > 0 and v >= mx, f"終わる前に帯が満ちた: {st} {msg}")
                    self.assertNotIn("完成", st + msg)
                    self.assertNotIn("完了", st + msg)
                last5 = max(k for k, (st, *_r) in enumerate(seen) if st.startswith(f"工程 {N}/{N}"))
                first1 = min(k for k, (st, *_r) in enumerate(seen) if st.startswith("工程 1/"))
                self.assertLess(first1, last5)
                # 模型に渡した言葉は会話に出さず、進み具合の欄の詳細（ツールチップ）にだけ置く
                self.assertFalse([c for c in chat if "渡す言葉" in c or "渡した言葉" in c], chat)
                self.assertIn("模型に渡す言葉: 1girl, red scarf", act.detail.toolTip())
        finally:
            w.dirty = False
            w.close()

    def test_way_pick_switches_mode(self):
        from atelier.app.main_window import Window
        from atelier.app.settings import AI_MODE, PRECISE
        from tests.test_editing import app
        app()
        d = TemporaryDirectory()
        self.addCleanup(d.cleanup)
        w = Window(Studio(FakeWords(), Painter(), Path(d.name)))
        old = w.settings.store.value("draw_way")
        try:
            self.assertEqual([w.way_pick.itemText(i) for i in range(w.way_pick.count())], ["AI モード", "精度優先"])
            self.assertTrue(w.way_pick.toolTip())
            w.way_pick.setCurrentIndex(1)
            self.assertEqual(w.studio.way, "phases")
            self.assertEqual(w.settings.get("draw_way"), PRECISE)
            w.way_pick.setCurrentIndex(0)
            self.assertNotEqual(w.studio.way, "phases")
            self.assertEqual(w.settings.get("draw_way"), AI_MODE)
        finally:
            if old is None:
                w.settings.store.remove("draw_way")
            else:
                w.settings.set("draw_way", old)
            w.dirty = False
            w.close()


class WaySettingTest(unittest.TestCase):
    def test_two_modes_and_old_values(self):
        from PySide6.QtCore import QSettings
        from atelier.app.settings import AI_MODE, FIELDS, PRECISE, Settings, studio_way
        field = next(f for f in FIELDS if f[0] == "draw_way")
        self.assertEqual(field[3], f"choice:{AI_MODE},{PRECISE}")
        self.assertEqual(field[4], AI_MODE)   # 既定は AI モード
        self.assertEqual(studio_way(PRECISE, "おまかせ"), "phases")
        self.assertEqual(studio_way(AI_MODE, "おまかせ"), "auto")
        self.assertEqual(studio_way(AI_MODE, "1つの模型で描く"), "one")
        self.assertEqual(studio_way(AI_MODE, "構図と仕上げを分けて描く"), "two")
        d = TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for old, way in (("工程に分けて描く", "phases"), ("構図と仕上げを分けて描く", "two"), ("おまかせ", "auto"), ("1つの模型で描く", "one")):
            st = Settings(QSettings(str(Path(d.name) / f"{way}.ini"), QSettings.IniFormat))
            st.set("draw_way", old)   # 前の版の 1 つの欄の値は、選んでいた描き方のまま読む
            self.assertEqual(studio_way(st.get("draw_way"), st.get("ai_way")), way, old)


seen = []


class MissingBackRouteTest(unittest.TestCase):
    """欠陥を検出した工程が戻り先を返し忘れても、そのまま次工程へ流さない。"""

    def test_detected_thumbnail_defect_uses_default_route(self):
        class C:
            @staticmethod
            def request(image, prompt):
                seen.append(1)
                return {"readable": True, "missing": [], "extra": [], "people": ["extra person"] if len(seen) <= 2 else [], "body": []}

            @staticmethod
            def body(image, prompt, tags=None):
                return {"readable": True, "bad": [], "avoid": []}

            @staticmethod
            def points(image):
                w, h = image.size
                return {"readable": True, "points": {"left_eye": (w * .45, h * .15), "right_eye": (w * .55, h * .15),
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15), "right_ear": (w * .6, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                return dict(CLEAN_HAND)

        seen.clear()
        from atelier.ai import phase_tools as pt
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "1girl", 9, (64, 96), Path(d), checks=C, say=said.append)
        self.assertTrue(got["complete"])
        self.assertEqual(got["backs"], 0)   # 構図へ勝手に戻らない
        self.assertTrue(any("次の工程から囲んで直します" in msg for msg in said), said)   # サムネイルは描き直し続けずに次へ進む
        self.assertEqual([r["phase"] for r in got["history"]], phases.NAMES)


class CountLimitTest(unittest.TestCase):
    """枚数の欄は数字だけで、8 枚や 9 枚で勝手に止めない"""

    def test_count_spin_has_no_small_cap(self):
        from PySide6.QtWidgets import QApplication
        from atelier.app.main_window import Window
        QApplication.instance() or QApplication([])
        d = TemporaryDirectory()
        self.addCleanup(d.cleanup)
        w = Window(Studio(FakeWords(), FakePainter(), Path(d.name)))
        try:
            spin = w.ai_panel.count_spin
            self.assertEqual(spin.suffix(), "")
            spin.setValue(25)
            self.assertEqual(spin.value(), 25)
        finally:
            w.close()


class PreviewTest(unittest.TestCase):
    """精度優先でも、描いている途中の絵と工程ごとの絵を窓に渡す（描いている所を画面に見せる）"""

    def test_each_phase_image_is_shown(self):
        shown, now, hidden = [], [""], []
        from atelier.ai import phase_tools as pt

        def say(m):
            if m.startswith("工程 "):
                now[0] = m.split("「", 1)[1].split("」", 1)[0] if "「" in m else ""

        def show(im):
            shown.append(im)
            if any(n in now[0] for n in phases.NO_PREVIEW):
                hidden.append(now[0])
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "red hair, 1girl", 1, (64, 64), Path(d), say=say, checks=checks(False)[0], on_preview=show)
        self.assertTrue(shown)
        self.assertEqual(hidden, [])   # 目的・サムネイル・アタリの間は、途中の絵も最後の絵もキャンバスに出さない
        same = [k for k in range(1, len(shown)) if list(shown[k].getdata()) == list(shown[k - 1].getdata())]
        self.assertEqual(same, [])   # 同じ絵を続けて出さない
        # 出すのは、アタリのあとの描いている途中の絵と、絵が変わった工程だけ
        self.assertLessEqual(len(shown), 2 * got["total"])


class NoSketchModelTest(unittest.TestCase):
    """線に沿う部品も範囲の直しも無い世代（FLUX.1 など）でも、線画と塗りの工程を描き重ねで進める（前は構図の絵のまま止まっていた）"""

    def test_refine_used_when_no_sketch(self):
        class Dit(Painter):
            abilities = (False, False)

            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                return image

        from atelier.ai import phase_tools as pt
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            p = Dit()
            C, _seen = checks(False)
            got = phases.draw(p, "1girl, red scarf", 1, (64, 64), Path(d), checks=C)
        self.assertTrue(any(x[0] == "refine" for x in p.log), p.log)
        self.assertFalse(got["complete"])   # 直せない崩れは聞いて止まる（全体の描き重ねを直しとして使わない）
        self.assertIsNotNone(got["asked"])


class AtariRedrawTest(unittest.TestCase):
    """アタリで囲めない崩れ（人数）が出ても聞いて止まらず、前の工程の絵を土台に描き直して、最後の工程まで検品を通す"""

    def test_unenclosable_atari_flaw_redraws_from_previous_until_passed(self):
        import numpy as np

        class P(Painter):
            def __init__(self):
                super().__init__()
                self.refines = []

            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.refines.append({"seed": seed, "strength": strength, "base": image.copy(), "prompt": prompt})
                if len(self.refines) == 1:   # 1 回目は前と同じ絵を返す（工程に数えない）
                    return image.copy()
                from PIL import ImageChops
                return ImageChops.add(image.convert("RGB"), image.convert("RGB").point(lambda _v: 9 + seed % 5))

        painter = P()

        def bad():   # 描き直しが 2 回絵を変えるまで、人数の崩れを返す
            return len(painter.refines[1:]) < 2

        class C(hand_only_checks(bad_times=0)):
            @staticmethod
            def request(image, prompt):
                return {"readable": True, "missing": [], "extra": [], "people": ["multiple girls 0.78"] if bad() else [], "body": []}

        said = []
        silhouette = pt.silhouette

        def whole(im):   # 人数が崩れている間は、人の形が絵の全体（囲めない）
            return np.ones((im.height, im.width), bool) if bad() else silhouette(im)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(pt, "parts", lambda _im: None), mock.patch.object(pt, "silhouette", whole):
            got = phases.draw(painter, "1girl, red hair", 5, (64, 96), Path(d) / "k", say=said.append, checks=C)
            thumb = got["history"][1]
        self.assertTrue(got["complete"], said[-5:])   # 聞いて止まらず、最後の工程まで検品を通った
        self.assertIsNone(got["asked"])
        self.assertFalse(any(s["kind"] == "ask" for s in got["plan"]))
        self.assertEqual(sum(1 for x in painter.log if x[0] == "paint"), phases.THUMBS)   # ゼロから描き直さない（サムネイルの分だけ）
        self.assertTrue(all(r["prompt"] == "1girl, red hair" for r in painter.refines))   # 頼みの言葉は変えない
        atari = got["history"][2]
        redraws = [m for m in atari["mends"] if m.get("whole")]
        self.assertEqual(len(redraws), 3)
        seeds = [m["seed"] for m in redraws]
        self.assertEqual(len(seeds), len(set(seeds)))   # 回ごとに種を替える
        strengths = [m["strength"] for m in redraws]
        self.assertEqual(strengths, sorted(strengths))
        self.assertGreater(strengths[-1], strengths[0])   # 強さを上げる
        self.assertFalse(redraws[0]["changed"])   # 前と同じ絵は工程に数えない
        self.assertIsNone(redraws[0]["image"])
        self.assertEqual(sum(1 for m in redraws if m["changed"]), 2)
        self.assertTrue(thumb["image"])
        self.assertTrue(any("前の工程の絵を土台に" in m for m in said))


class UndoneNotOnCanvasTest(unittest.TestCase):
    """精度優先で検品を通らずに返った絵（聞いて止まった絵）はキャンバスに出さず、隠したレイヤーにだけ置く。通った絵だけを出す"""

    def run_one(self, passed):
        from PIL import Image
        from atelier.app.main_window import Window
        from tests.test_editing import app
        qapp = app()
        d = Path(self.enterContext(TemporaryDirectory()))
        w = Window(Studio(FakeWords(), Painter(), d))
        self.addCleanup(lambda: (setattr(w, "dirty", False), w.close()))
        atari = d / "atari.png"
        Image.new("RGB", (64, 64), (200, 0, 0)).save(atari)
        w.mode.setCurrentIndex(0)
        w.job_kind = "draw"
        w.studio.last_phases = [{"phase": "アタリ", "image": str(atari), "found": ["人数が違う"], "fixed": False, "after": [],
                                 "seconds": 1.0}]
        w.studio.last_passed = passed
        w.batch, w.batch_items, w.images = [], [], []
        before = [l.name for l in w.canvas.layers]
        w.on_one("1girl", str(atari))
        w.show_final()
        qapp.processEvents()
        return w, before

    def test_undone_kept_off_canvas(self):
        w, before = self.run_one(False)
        visible = [l.name for l in w.canvas.layers if l.visible]
        self.assertEqual(visible, [n for n in before])   # 見えるレイヤーは元のまま（アタリの絵を出さない）
        hidden = [l.name for l in w.canvas.layers if not l.visible]
        self.assertIn("工程 1: アタリ", hidden)
        self.assertIn("検品を通っていない絵", hidden)

    def test_passed_is_placed(self):
        w, _before = self.run_one(True)
        self.assertTrue(any(l.visible and l.name.startswith("AI の絵") for l in w.canvas.layers))
