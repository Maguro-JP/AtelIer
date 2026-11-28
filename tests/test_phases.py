"""工程に分けて描く（atelier/ai/phases.py）を偽の模型と偽の検品で通す。
工程は人の描き方の 9。崩れは前の工程へ戻らず、今の絵の崩れた所の囲みの中だけを直す（外は 1 画素も変えない）。
囲めない崩れ（人数は余分な人の枠、読めない工程は読めなかった部位の枠で囲む）も、手を替えて直しても消えない崩れも、
利用者に聞いて止まらず、絵の全体も描き直さない。絵を前のまま残し、残った崩れとして次の工程へ進み、最後に知らせる。
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
from tests.test_draw import FakePainter, FakeWords  # noqa: E402

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


def sketch(size=(64, 96)):
    """白い紙に、細い黒い線で描いたラフ画（人物の輪郭と目の線）。線画の工程の絵"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.38, h * 0.05, w * 0.62, h * 0.25], outline=(0, 0, 0), width=1)  # 頭の輪郭
    d.rectangle([w * 0.35, h * 0.25, w * 0.65, h * 0.95], outline=(0, 0, 0), width=1)  # 体の輪郭
    d.line([w * 0.45, h * 0.15, w * 0.55, h * 0.15], fill=(0, 0, 0), width=1)  # 目の線（内側の細い線）
    return im


def tilted_land(size=(128, 96), slope=0.09):
    """上が白い空、下が灰色の地面の風景。地平線が slope だけ傾いている（右下がり）"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for x in range(w):
        y = int(h // 2 + (x - w // 2) * slope)
        d.line([x, y, x, h], fill=(90, 90, 90))
    return im


def _light_gradient(im, amount=10):
    """絵に左から右への明るさの段差を付ける（光の向きが読めるようにする）。
    均一な色の絵だと、光源の検品が「明るさが平たい」と崩れを出す。なだらかな勾配だと色が連続的にばらまき下塗りの色数が増えるので、段差にする（左半分 -5、右半分 +5）。
    段差は水・葉の明るさの広がり（20 未満で崩れ）に 5 しか足さない"""
    import numpy as np
    from PIL import Image
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    w = a.shape[1]
    step = np.full((1, w, 1), -amount / 2, dtype=np.float32)
    step[:, w // 2:, :] = amount / 2
    return Image.fromarray(np.clip(a + step, 0, 255).astype("uint8"))


def water_scene(size=(64, 96), with_light=False):
    """空・地面・水（青い所）の風景。光があるときは水に明るい縦の筋を入れる。右を明るくして光の向きが読めるようにする"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), (200, 220, 240))  # 空
    d = ImageDraw.Draw(im)
    d.rectangle([0, h // 2, w, h], fill=(90, 110, 90))  # 地面
    d.rectangle([0, int(h * 0.62), w, h], fill=(40, 90, 140))  # 水（青）
    if with_light:
        # 水の光の筋。3 か所に太めの筋を入れ、水の 9% ほどを明るくする（95パーセンタイルが光の明るさに届くため）
        for cx in (w * 0.3, w * 0.5, w * 0.7):
            for x in range(int(cx) - 2, int(cx) + 2):
                d.line([x, int(h * 0.62), x, h], fill=(220, 230, 250), width=1)
    return _light_gradient(im)


def leaf_scene(size=(64, 96), with_gloss=False):
    """木の葉（緑の塊）の風景。つやがあるときは葉に明るい点を散らす。右を明るくして光の向きが読めるようにする"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), (220, 225, 235))
    d = ImageDraw.Draw(im)
    d.rectangle([0, h // 2, w, h], fill=(120, 100, 80))
    d.ellipse([w * 0.15, h * 0.1, w * 0.85, h * 0.55], fill=(40, 110, 50))  # 葉の塊
    d.rectangle([w * 0.48, h * 0.5, w * 0.52, h], fill=(90, 60, 40))  # 幹
    if with_gloss:
        import numpy as np
        rng = np.random.default_rng(3)
        for _ in range(40):
            x = int(rng.integers(w * 0.2, w * 0.8))
            y = int(rng.integers(h * 0.15, h * 0.5))
            d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(180, 230, 140))  # 葉のつや
    return _light_gradient(im)


def car_side_scene(size=(64, 96), flat_tire=False):
    """横から見た車。車体と 2 つの黒いタイヤ（円）。flat_tire なら右のタイヤの下を平らにする。右を明るくして光の向きが読めるようにする"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.15, h * 0.35, w * 0.85, h * 0.6], fill=(180, 40, 40))  # 車体
    d.rectangle([w * 0.3, h * 0.2, w * 0.7, h * 0.38], fill=(180, 40, 40))   # キャビン
    for cx in (w * 0.3, w * 0.7):
        r = max(4, int(min(w, h) * 0.11))
        d.ellipse([cx - r, h * 0.55 - r, cx + r, h * 0.55 + r], fill=(20, 20, 20))
    if flat_tire:
        # 右のタイヤの下を平らに切る（白で塗りつぶす）
        d.rectangle([w * 0.7 - 12, h * 0.55 + 6, w * 0.7 + 12, h * 0.55 + 12], fill=(255, 255, 255))
    return _light_gradient(im)


def car_front_scene(size=(64, 96), asym=False):
    """正面から見た車。左右対称。asym なら右側を潰す。右を明るくして光の向きが読めるようにする"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.2, h * 0.3, w * 0.8, h * 0.75], fill=(40, 80, 180))  # 車体
    d.rectangle([w * 0.3, h * 0.15, w * 0.7, h * 0.32], fill=(40, 80, 180))  # キャビン
    d.rectangle([w * 0.28, h * 0.55, w * 0.42, h * 0.62], fill=(240, 240, 200))  # 左のライト
    d.rectangle([w * 0.58, h * 0.55, w * 0.72, h * 0.62], fill=(240, 240, 200))  # 右のライト
    if asym:
        # 右側を潰す（右半分の車体を白で削る）
        d.polygon([(w * 0.65, h * 0.3), (w * 0.8, h * 0.3), (w * 0.8, h * 0.75), (w * 0.65, h * 0.75)], fill=(255, 255, 255))
        d.rectangle([w * 0.58, h * 0.55, w * 0.65, h * 0.62], fill=(255, 255, 255))
    return _light_gradient(im)


def road_scene(size=(64, 96), converge=True):
    """道路の風景。converge なら道の両端が地平線で 1 点に集まる。平行なら両端が平行（斜めの平行線）。
    右を明るくして光の向きが読めるようにする"""
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), (200, 220, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([0, h // 2, w, h], fill=(110, 130, 90))  # 地面
    if converge:
        d.polygon([(w * 0.3, h), (w * 0.7, h), (w * 0.52, h // 2), (w * 0.48, h // 2)], fill=(90, 90, 90))  # 収束する道
    else:
        # 斜めの平行な道。両端が同じ傾きで、地平線に集まらない
        d.polygon([(w * 0.25, h), (w * 0.55, h), (w * 0.75, h // 2), (w * 0.45, h // 2)], fill=(90, 90, 90))
    return _light_gradient(im)


def _scene_checks():
    """体・構図・依頼物は合格させる。風景・車の場面では、手・顔・体を見る模型は使わない"""
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
            return {"readable": True, "points": {}}

        @staticmethod
        def pose(image):
            return {"readable": True, "bad": [], "map": image}

        @staticmethod
        def hands(image, prompt):
            return dict(CLEAN_HAND)
    return C


def mean_diff(a, b):
    """2 枚の絵の平均の差（0-255）。DIFF_MIN と比べる"""
    import numpy as np
    x = np.asarray(a.convert("RGB"), dtype=np.int16)
    y = np.asarray(b.convert("RGB"), dtype=np.int16)
    return float(np.abs(x - y).max(axis=2).mean())


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
        # 描き重ね（base あり）は土台の絵を元に描くので、白紙からの描きとは違う絵になる。本物の模型と同じく、base の有無で絵を変える
        shift = (seed + 11) % 23 if ("base" in kw and kw["base"] is not None) else seed % 23
        im = ImageChops.add(im, im.point(lambda _v: shift))
        if kw.get("on_preview"):
            # 途中の絵は拡散の途中の絵で、最後の絵とは違う。本物の模型と同じく、途中の絵を最後の絵と別の物にする
            pv_im = figure(kw.get("size") or (64, 96))
            pv_im = ImageChops.add(pv_im, pv_im.point(lambda _v: (seed + 5) % 23))
            kw["on_preview"](pv_im)
        return im

    def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
        self.log.append(("redraw", seed, kw.get("strength")))
        self.masks = getattr(self, "masks", []) + [mask]
        # 本物の模型と同じく絵全体を返し、囲みの中だけでなく外も変える（外を元に戻すのは phases の役目）。回ごとに違う絵にする
        from PIL import ImageChops
        return ImageChops.add(image.convert("RGB"), image.convert("RGB").point(lambda _v: 5 + seed % 7))


class ScenePainter(Painter):
    """描くたびに、決めた場面の絵を返す画家。場面は paint のたびに同じ絵（直しの描き直しは Painter の redraw がずらす）"""

    scene = None   # (size) -> Image を返す関数

    def paint(self, prompt, seed, on_step=None, **kw):
        self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
        size = kw.get("size") or (64, 96)
        return self.scene(size)


BAD_TIMES = 3   # 崩れを返し続ける検品が、何回目で通るか（必ず通る回を持たせ、試験を終わらせる）


def checks(always_bad: bool):
    """always_bad: どの検品も最初の BAD_TIMES 回は崩れを返し、そのあと通る。False: 1 回目だけ崩れを返す"""
    seen = {"request": 0, "body": 0, "hands": 0, "pose": 0}

    class C:
        @staticmethod
        def request(image, prompt):
            seen["request"] += 1
            # サムネイルでは依頼物を検査せず、アタリの確かめで初めて欠落を検出する。
            # request はサムネイル 1 回、土台（80 点の一発の絵）の計測 1 回の後、アタリで検品する（アタリの確かめは request を 1 回だけ呼ぶ）。
            bad = not always_bad and seen["request"] == 3
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
            # 下描きの描く工程は手を測らないので（測るのは確かめる工程だけ）、崩れを返す回は BAD_TIMES - 1 回にそろえる。
            # 土台（80 点の一発の絵）の計測が最初の 1 回を消費するので、工程から見える崩れの回数を保つため 1 回分足す
            return dict(HAND) if ((always_bad and seen["hands"] <= BAD_TIMES) or seen["hands"] <= 2) else dict(CLEAN_HAND)
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
            # 土台の計測が最初の 1 回を消費するので、工程から見える不合格の回数を保つため 1 回足す（0 回＝常に合格はそのまま）
            return dict(HAND) if seen["hands"] <= bad_times + (1 if bad_times else 0) else dict(CLEAN_HAND)
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

    def test_nine_phases_in_order(self):
        self.assertEqual(phases.NAMES, ["目的", "サムネイル", "アタリ", "線画",
                                        "下塗り", "光源", "影 2 段", "光・艶・目のハイライト", "ディテール", "仕上げ"])
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
        self.assertTrue(all("累計" not in s for s in said))   # 累計の表記は出さない（利用者の指示）

    def test_thumbnail_direct_and_reused(self):
        got, painter, *_ = self.run_phases(always_bad=False)
        paints = [x for x in painter.log if x[0] == "paint" and not x[3]]   # 下描きの線に沿う描き（base あり）は除く
        # ゼロから描くのは土台の一発の絵の 1 枚だけ（画面には出さない）。サムネイルはその絵から抜いたラフで、そのままアタリにする。
        # 前は「鉛筆のラフ」の言葉で別の 1 枚を描いていた。土台と別の構図になり、線に土台の色を敷けなかった（検証 46089737769）
        self.assertEqual(len(paints), 1, painter.log)
        # 土台の一発の絵は工程の数を減らさない（AI モードの 1 枚と同じ描き方）
        self.assertEqual(sorted(x[2] for x in paints), [20])
        self.assertIn("picked", got["phases"][1]["numbers"])

    def test_back_to_draft_fixes_regions_only_and_stronger(self):
        """手の崩れで下描きへ戻ったら、絵全体を描き重ね直さず、崩れた枠の中だけを前より強く直す"""
        class P(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                return image.copy()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            painter = P()
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=hand_only_checks(bad_times=5))
        self.assertTrue(got["complete"])
        # 下描き（アタリの中。最初は最大 4 枚描いて一番良い物を選ぶ）と線画のペンなぞりは refine で描き重ねる。
        # 下塗りも refine を使うので、強さで分ける（下描き・線画 REFINE、下塗りは土台の色を敷いた絵への描き重ねで BASE_OVER）
        self.assertEqual(sum(1 for x in painter.log if x[0] == "refine" and x[2] == phases.REFINE), 5, painter.log)
        self.assertEqual(sum(1 for x in painter.log if x[0] == "refine" and x[2] == phases.BASE_OVER), 1, painter.log)
        self.assertEqual(sum(1 for x in painter.log if x[0] == "refine" and x[2] == phases.BASE_COLOR), 0, painter.log)   # 白い紙の線画には描き重ねない（色が乗らない）
        fixes = [m["strength"] for r in got["history"] if r["phase"] == "アタリ" for m in r.get("mends", [])]
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
        """渡す言葉は頼みの訳だけ。手・足・顔の直しにも five fingers などを足さない。線の工程の線の描き方の言葉（ROUGH_WORDS・PEN_WORDS）は、色や内容ではなく描き方なので許す"""
        got, painter, *_ = self.run_phases(always_bad=True)
        sketch = {t.strip() for wds in (phases.ROUGH_WORDS, phases.PEN_WORDS) for t in wds.split(",") if t.strip()}
        for r in got["history"]:
            for w in r["words"]:
                rest = w.replace("(red scarf:1.3)", "red scarf")
                self.assertEqual({t.strip() for t in rest.split(",") if t.strip()} - {"1girl", "red scarf"} - sketch, set(), w)

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
            self.assertEqual(got["phase"], "アタリ")   # 手を見る最初の工程で止まった
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
        # 囲みの中だけを直せない模型では、全体を描き直して直したことにせず、聞いて止まらず、残った崩れとして最後まで進む
        self.assertFalse(got["complete"])
        self.assertIsNone(got["asked"])
        self.assertTrue(got["left"])
        self.assertEqual(got["history"][-1]["phase"], "仕上げ")
        self.assertFalse(any(x[0] == "redraw" for x in painter.log))

    def test_fix_masks_are_regions_only(self):
        """直しは囲みの中だけ（外は 1 画素も変えない）。手を替え尽くしても消えない崩れは聞いて止まらず、
        絵を前のまま残して残った崩れとして次の工程へ進み、最後まで描いて残った崩れを返す"""
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            painter = Painter()
            C = hand_only_checks(bad_times=10 ** 6)   # ずっと消えない手の崩れ
            said = []
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append, checks=C)
        self.assertFalse(got["complete"])
        self.assertIsNone(got["asked"])
        self.assertFalse(any(s["kind"] == "ask" for s in got["plan"]))
        self.assertEqual(got["history"][-1]["phase"], "仕上げ")   # 止まらずに最後の工程まで進んだ
        self.assertTrue(any("指が 6 本" in f for f in got["left"]))   # 残った崩れとして返る
        draft = next(r for r in got["history"] if r["phase"] == "アタリ")
        self.assertEqual({m["mend"] for m in draft["mends"]}, set(range(1, phases.MENDS + 1)))   # 強さの段を MENDS 回替えた
        self.assertTrue(all(m["outside"] == 0 for r in got["history"] for m in r["mends"]))
        self.assertTrue(any("残った崩れとして次の工程へ進みます" in m for m in said))


    def test_confirm_redo_and_words(self):
        asked, answers = [], {2: ["redo", "go"], 8: [("words", "blue ribbon"), "go"]}

        def confirm(i, name, image, row):
            asked.append(i)
            todo = answers.get(i)
            return todo.pop(0) if todo else "go"
        got, painter, seen, said, files = self.run_phases(always_bad=False, confirm=confirm)
        self.assertEqual(asked.count(2), 3)   # 描き直した工程はもう一度確かめる。最後の工程で言葉を足してアタリへ戻った分も数える
        self.assertEqual(asked.count(8), 2)
        self.assertEqual(got["phases"][2]["visit"], 2)
        self.assertTrue(any("blue ribbon" in w for r in got["history"] for w in r["words"]))
        self.assertTrue(any("言葉を足しました" in s for s in said))

    def test_words_added_at_final_phase_return_to_drawing_stage(self):
        asked = {8: [("words", "blue ribbon"), "go"]}

        def confirm(i, name, image, row):
            queue = asked.get(i)
            return queue.pop(0) if queue else "go"

        got, painter, seen, said, files = self.run_phases(always_bad=False, confirm=confirm)
        self.assertTrue(got["complete"])
        atari = [r for r in got["history"] if r["phase"] == "アタリ"]
        self.assertTrue(any(any("blue ribbon" in word for word in r["words"]) for r in atari), atari)
        self.assertTrue(any("描き直しを頼まれたので「アタリ」から順に進めます" in msg for msg in said))

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


class NonPersonTest(unittest.TestCase):
    """人物以外（風景・物）の頼みでは、手・顔・体を見る模型を使わず、構図・色・光・背景だけを見る"""

    def test_landscape_skips_character_checks(self):
        seen = {"hands": 0, "body": 0, "pose": 0, "points": 0, "request": 0}

        class C:
            @staticmethod
            def request(image, prompt):
                seen["request"] += 1
                return {"readable": True, "missing": [], "extra": [], "people": [], "body": []}

            @staticmethod
            def body(image, prompt, tags=None):
                seen["body"] += 1
                return {"readable": True, "bad": [], "avoid": []}

            @staticmethod
            def points(image):
                seen["points"] += 1
                w, h = image.size
                return {"readable": True, "points": {}}

            @staticmethod
            def pose(image):
                seen["pose"] += 1
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                return dict(CLEAN_HAND)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "mountain, lake", 1, (64, 64), Path(d), checks=C)
        self.assertTrue(got["complete"], got.get("left"))
        self.assertEqual(seen["hands"], 0, seen)   # 手・顔・体を見る模型は呼ばない
        self.assertEqual(seen["body"], 0, seen)
        self.assertEqual(seen["pose"], 0, seen)
        self.assertEqual(seen["points"], 0, seen)
        self.assertGreater(seen["request"], 0, seen)   # 頼んだ物があるかの確かめは使う


class SubjectKindTest(unittest.TestCase):
    """顔・目・足があるかどうかで分ける（人／顔のある物／物・風景）。動物・人型ロボット・架空の生き物は顔・目・足の検品を回す"""

    def test_word_only(self):
        self.assertEqual(phases.subject_kind("1girl, red scarf"), "person")
        self.assertEqual(phases.subject_kind("dog"), "face")
        self.assertEqual(phases.subject_kind("cat sitting"), "face")
        self.assertEqual(phases.subject_kind("dragon"), "face")
        self.assertEqual(phases.subject_kind("robot"), "face")   # 人型か箱型か分からなければ人型
        self.assertEqual(phases.subject_kind("humanoid robot"), "face")
        self.assertEqual(phases.subject_kind("box robot"), "object")   # 箱型は物
        self.assertEqual(phases.subject_kind("car"), "object")

    def test_tagger_read(self):
        empty = {"readable": True, "people": [], "read": {}}
        self.assertEqual(phases.subject_kind("mountain, lake", empty), "object")
        self.assertEqual(phases.subject_kind("a landscape", empty), "object")
        self.assertEqual(phases.subject_kind("a landscape", {"readable": True, "people": [1], "read": {}}), "person")
        self.assertEqual(phases.subject_kind("a landscape", {"readable": True, "people": [], "read": {"dog": 0.8}}), "face")


def _clean_checks():
    """体・構図・依頼物は合格させ、手の検品だけを 1 回目に崩れ（足）で返す。動物・人型ロボット用"""
    seen = {"hands": 0, "body": 0, "pose": 0, "points": 0, "request": 0}

    class C:
        @staticmethod
        def request(image, prompt):
            seen["request"] += 1
            return {"readable": True, "missing": [], "extra": [], "people": [], "body": []}

        @staticmethod
        def body(image, prompt, tags=None):
            seen["body"] += 1
            return {"readable": True, "bad": [], "avoid": []}

        @staticmethod
        def points(image):
            seen["points"] += 1
            w, h = image.size
            return {"readable": True, "points": {"left_eye": (w * .45, h * .15), "right_eye": (w * .55, h * .15),
                    "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15), "right_ear": (w * .6, h * .15),
                    "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

        @staticmethod
        def pose(image):
            seen["pose"] += 1
            return {"readable": True, "bad": [], "map": image}

        @staticmethod
        def hands(image, prompt):
            seen["hands"] += 1
            if seen["hands"] <= 2:
                # 動物の顔・足はあるが、人の手は無い。足の崩れを返す（土台の計測が 1 回目を消費するので、工程の確かめでも見えるよう 2 回目まで）
                return {"readable": True, "bad": ["足 1: 指が 6 本"], "hands": [],
                        "feet": [{"box": [10, 10, 30, 30], "bad": ["指が 6 本"], "seen": True}],
                        "faces": [{"box": [20, 5, 40, 20]}], "face": {"readable": True}, "legs": []}
            return {"readable": True, "bad": [], "hands": [], "feet": [],
                    "faces": [{"box": [20, 5, 40, 20]}], "face": {"readable": True}, "legs": []}
    return C, seen


class DustyPainter(Painter):
    """描くたびに、主役から離れた所に小さなゴミを描く"""

    def paint(self, prompt, seed, on_step=None, **kw):
        im = super().paint(prompt, seed, on_step=on_step, **kw)
        from PIL import ImageDraw
        d = ImageDraw.Draw(im)
        d.rectangle([5, 5, 7, 7], fill=(30, 30, 30))
        return im


class DetachedPainter(Painter):
    """描くたびに、体の近くに離れた塊（位置ずれ）を描く"""

    def paint(self, prompt, seed, on_step=None, **kw):
        im = super().paint(prompt, seed, on_step=on_step, **kw)
        from PIL import ImageDraw
        d = ImageDraw.Draw(im)
        d.rectangle([45, 40, 55, 50], fill=(60, 60, 80))
        return im


class LandPainter(Painter):
    """最初の 2 回（サムネイルとアタリ）は傾いた地平線の風景を描き、あとは人物の絵を描く。
    風景のままでは「縮めて見る」の検品（人物が紙に載っている前提）が通らないので、アタリの確かめだけを風景で試す"""

    def __init__(self):
        super().__init__()
        self.n = 0

    def paint(self, prompt, seed, on_step=None, **kw):
        self.n += 1
        if self.n <= 2:
            super().paint(prompt, seed, on_step=on_step, **kw)
            return tilted_land((128, 96))
        return super().paint(prompt, seed, on_step=on_step, **kw)


def _counting_lines(weights=None, max_gaps=None):
    """pt.lines の偽物。呼ぶたびに weight / max_gap を順に返す（無ければ最後の値）。gap は 0"""
    weights = weights or [0.6]
    max_gaps = max_gaps or [0.0]
    seen = {"n": 0}

    def fake(_im):
        i = seen["n"]
        seen["n"] += 1
        return {"readable": True, "gap": 0.0,
                "max_gap": max_gaps[min(i, len(max_gaps) - 1)],
                "weight": weights[min(i, len(weights) - 1)]}
    return fake


class NewChecksFlowTest(unittest.TestCase):
    """新しい検品が、崩れを見つけ、直し、直したあとに通ることを、流れで確かめる"""

    def run_draw(self, painter, prompt, checks, lines=None):
        lines = lines or (lambda _im: {"readable": True, "gap": 0.0})
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lines):
            got = phases.draw(painter, prompt, 5, (64, 96), Path(d) / "k", checks=checks)
        return got

    def mends_of(self, got, item):
        return [m for r in got["history"] for m in r.get("mends", []) if m.get("item") == item]

    def test_line_strength_not_checked_at_line_phase(self):
        """線の強弱は線画の確かめでは見ない（線画までは細い線で十分。強弱は清書の描く工程で
        付ける物で、線画で太らせる直しを繰り返すのは適所ではない）"""
        C, _seen = checks(always_bad=False)
        got = self.run_draw(Painter(), "1girl, red scarf", C, lines=_counting_lines(weights=[0.2, 0.6]))
        self.assertTrue(got["complete"], got.get("left"))
        self.assertEqual(self.mends_of(got, "線の強弱"), [])

    def test_line_strength_checked_at_line_finish(self):
        """線画モードの「線の仕上げ」では線の強弱を扱う: 細い線を崩れとし、太らせる直しで直し、確かめ直しで通る"""
        C, _seen = checks(always_bad=False)
        got = self.run_draw(Painter(), "1girl, red scarf, 線画", C, lines=_counting_lines(weights=[0.2, 0.2, 0.6]))
        mends = self.mends_of(got, "線の強弱")
        self.assertTrue(mends, got["history"])
        self.assertEqual(mends[0]["mend"], "太らせる")
        rows = [r["phase"] for r in got["history"] for m in r.get("mends", []) if m.get("item") == "線の強弱"]
        self.assertEqual(set(rows), {"線の仕上げ"})

    def test_line_shift_flagged_then_fixed(self):
        """線のズレ: 線が途中でずれているのを崩れとし、直し、確かめ直しで通る"""
        C, _seen = checks(always_bad=False)
        got = self.run_draw(Painter(), "1girl, red scarf", C, lines=_counting_lines(max_gaps=[0.8, 0.0]))
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "線の途切れ")
        self.assertTrue(mends, got["history"])

    def test_dust_erased_and_recheck_passes(self):
        """ゴミ: 清書（線画の仕上げ）で小さなゴミを塊そのものだけ消す。線画の時点でゴミは無い。
        色の工程に入ってから出たゴミは仕上げで消さない（ゴミ取りは清書だけ、という利用者の規則）"""
        C, _seen = checks(always_bad=False)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(DustyPainter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
            self.assertTrue(got["complete"], got.get("left"))
            row = [r for r in got["history"] if r["phase"] == "線画"][0]
            # 清書で消えたので、線画の絵そのものにゴミは無い（以前は、太らせる加工が
            # ゴミを膨らませて「ゴミの大きさ」を超えさせ、消えずに残ったまま数だけ 0 に
            # なっていた。太らせる上限を入れたら、その誤魔化しが剥がれた）
            from PIL import Image
            self.assertEqual(pt.dust(Image.open(row["image"]))["count"], 0)

    def test_detached_part_carried_not_redrawn(self):
        """位置ずれ: 体から離れた物を崩れとし、直す工程が回る。偽の模型では消せないので、残った崩れとして次へ進む（全体の描き直しはしない）。残った崩れがあるので complete は偽だが、最後の工程まで進む"""
        C, _seen = checks(always_bad=False)
        got = self.run_draw(DetachedPainter(), "1girl, red scarf", C)
        self.assertFalse(got["complete"])
        self.assertEqual(got["history"][-1]["phase"], "仕上げ")
        mends = self.mends_of(got, "位置ずれ")
        self.assertTrue(mends, got["history"])
        self.assertTrue(all(m["outside"] == 0 for m in mends))   # 囲みの外は 1 画素も変えない
        self.assertTrue(any("離れている" in f for f in got["left"]), got["left"])   # 直せないので残った崩れになる

    def test_horizon_tilt_rotated_and_recheck_passes(self):
        """画角: 傾いた地平線を回して直し、確かめ直しで通る"""
        C, _seen = _clean_checks()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(LandPainter(), "mountain, lake", 5, (128, 96), Path(d) / "k", checks=C)
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "画角")
        self.assertTrue(mends, got["history"])
        self.assertEqual(mends[0]["mend"], "回す")

    def test_background_mismatch_carried(self):
        """背景: 頼んだ場所と違う背景を崩れとする。背景の囲みは絵の半分を超えるので、直さずに残った崩れとして次へ進む（全体の描き直しはしない）。残った崩れがあるので complete は偽だが、最後の工程まで進む"""
        seen = {"request": 0}

        class C:
            @staticmethod
            def request(image, prompt):
                seen["request"] += 1
                return {"readable": True, "missing": [], "extra": [], "people": [], "body": [],
                        "read": {"beach": 0.1, "mountain": 0.9}}   # beach を頼んだのに mountain が読めている

            @staticmethod
            def body(image, prompt, tags=None):
                return {"readable": True, "bad": [], "avoid": []}

            @staticmethod
            def points(image):
                w, h = image.size
                return {"readable": True, "points": {}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                return dict(CLEAN_HAND)
        got = self.run_draw(Painter(), "beach", C)
        self.assertFalse(got["complete"])
        self.assertEqual(got["history"][-1]["phase"], "仕上げ")
        self.assertTrue(any("背景が違う" in f for f in got["left"]), got["left"])
        self.assertFalse(any(m["item"] == "背景" and m.get("changed") for r in got["history"] for m in r.get("mends", [])))

    def test_animal_runs_face_feet_checks(self):
        """動物: 顔・目・足の検品を回す。人の手の指・服・等身・骨組みの検品は回さない"""
        C, seen = _clean_checks()
        got = self.run_draw(Painter(), "dog", C)
        self.assertTrue(got["complete"], got.get("left"))
        self.assertGreater(seen["hands"], 0, seen)   # 顔・足を見る模型は使う
        self.assertEqual(seen["body"], 0, seen)   # 人の体の検品は使わない
        self.assertEqual(seen["pose"], 0, seen)   # 人の骨組みの検品は使わない
        self.assertTrue(self.mends_of(got, "足"), got["history"])   # 足の崩れを直す工程が回った

    def test_robot_humanoid_runs_face_checks(self):
        """人型ロボット: 顔・目・足の検品を回す（動物と同じ）"""
        C, seen = _clean_checks()
        got = self.run_draw(Painter(), "robot", C)
        self.assertTrue(got["complete"], got.get("left"))
        self.assertGreater(seen["hands"], 0, seen)
        self.assertEqual(seen["body"], 0, seen)
        self.assertEqual(seen["pose"], 0, seen)

    def test_robot_box_is_object(self):
        """箱型ロボット: 物と同じ扱いで、顔・目・足の検品は回さない"""
        C, seen = _clean_checks()
        got = self.run_draw(Painter(), "box robot", C)
        self.assertTrue(got["complete"], got.get("left"))
        self.assertEqual(seen["hands"], 0, seen)
        self.assertEqual(seen["body"], 0, seen)
        self.assertEqual(seen["pose"], 0, seen)


class LandscapeObjectFlowTest(unittest.TestCase):
    """風景と車・物の新しい検品が、崩れを見つけ、直し、直したあとに通ることを、流れで確かめる"""

    def run_scene(self, painter, prompt, size=(64, 96)):
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, prompt, 5, size, Path(d) / "k", checks=_scene_checks())
        return got

    def mends_of(self, got, item):
        return [m for r in got["history"] for m in r.get("mends", []) if m.get("item") == item]

    def test_water_light_flagged_then_shined(self):
        """水の光: 光の無い水を崩れとし、光の筋を付ける直しで直し、確かめ直しで通る。光の筋は模型で描き直さない"""
        class WP(ScenePainter):
            scene = staticmethod(lambda size: water_scene(size, with_light=False))
        got = self.run_scene(WP(), "mountain, lake")
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "水の光")
        self.assertTrue(mends, got["history"])
        self.assertEqual(mends[0]["mend"], "光を付ける")
        self.assertGreaterEqual(mends[0]["diff"], phases.DIFF_MIN)

    def test_leaf_gloss_flagged_then_shined(self):
        """葉のつや: つやの無い葉を崩れとし、つやの点を付ける直しで直し、確かめ直しで通る"""
        class LP(ScenePainter):
            scene = staticmethod(lambda size: leaf_scene(size, with_gloss=False))
        got = self.run_scene(LP(), "forest")
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "葉のつや")
        self.assertTrue(mends, got["history"])
        self.assertEqual(mends[0]["mend"], "光を付ける")
        self.assertGreaterEqual(mends[0]["diff"], phases.DIFF_MIN)

    def test_tire_roundness_flagged_then_redrawn(self):
        """タイヤの丸み: 丸くないタイヤを崩れとし、タイヤの枠を描き直す。直す言葉に丸いタイヤを入れる"""
        def counting_tire(_im):
            counting_tire.n = getattr(counting_tire, "n", 0) + 1
            if counting_tire.n == 1:
                return {"readable": True,
                        "tires": [{"area": 300, "cv": 0.2, "box": (10, 40, 30, 60)},
                                  {"area": 300, "cv": 0.02, "box": (40, 40, 60, 60)}],
                        "worst": 0.2, "boxes": [(10, 40, 30, 60), (40, 40, 60, 60)]}
            return {"readable": True,
                    "tires": [{"area": 300, "cv": 0.02, "box": (10, 40, 30, 60)},
                              {"area": 300, "cv": 0.02, "box": (40, 40, 60, 60)}],
                    "worst": 0.02, "boxes": [(10, 40, 30, 60), (40, 40, 60, 60)]}
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
             mock.patch.object(pt, "tire_roundness", counting_tire):
            got = phases.draw(Painter(), "car", 5, (64, 96), Path(d) / "k", checks=_scene_checks())
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "タイヤの丸み")
        self.assertTrue(mends, got["history"])
        self.assertTrue(any("round tire" in w for r in got["history"] for m in r.get("mends", [])
                            if m.get("item") == "タイヤの丸み" for w in m.get("words", [])), got["history"])

    def test_symmetry_mirror_flagged_then_mirrored(self):
        """左右対称: 片側が潰れた車を崩れとし、鏡写しで直し、確かめ直しで通る。鏡写しは模型で描き直さない"""
        class FP(ScenePainter):
            scene = staticmethod(lambda size: car_front_scene(size, asym=True))
        got = self.run_scene(FP(), "car, front view")
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "左右対称")
        self.assertTrue(mends, got["history"])
        self.assertEqual(mends[0]["mend"], "鏡写し")
        self.assertGreaterEqual(mends[0]["diff"], phases.DIFF_MIN)

    def test_tire_pair_flagged_then_redrawn(self):
        """左右のタイヤの大きさ: そろっていないタイヤを崩れとし、小さいタイヤの枠を描き直す"""
        def counting_sym(_im):
            counting_sym.n = getattr(counting_sym, "n", 0) + 1
            if counting_sym.n == 1:
                return {"readable": True, "iou": 0.9, "tire_ratio": 1.8, "tire_dy": 2.0, "small_box": (40, 40, 60, 60)}
            return {"readable": True, "iou": 0.9, "tire_ratio": 1.0, "tire_dy": 1.0, "small_box": (40, 40, 60, 60)}
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
             mock.patch.object(pt, "symmetry", counting_sym):
            got = phases.draw(Painter(), "car", 5, (64, 96), Path(d) / "k", checks=_scene_checks())
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "左右対称")
        self.assertTrue(mends, got["history"])

    def test_vanishing_flagged_then_redrawn(self):
        """遠近の収束: 収束しない線を崩れとし、線の所の枠を描き直す。直す言葉に遠近を入れる"""
        def counting_vanish(_im):
            counting_vanish.n = getattr(counting_vanish, "n", 0) + 1
            if counting_vanish.n == 1:
                return {"readable": True, "angle": 5.0, "point": (60, 40), "box": (30, 40, 90, 90)}
            return {"readable": True, "angle": 45.0, "point": (60, 40), "box": (30, 40, 90, 90)}
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
             mock.patch.object(pt, "vanishing", counting_vanish):
            got = phases.draw(Painter(), "car", 5, (64, 96), Path(d) / "k", checks=_scene_checks())
        self.assertTrue(got["complete"], got.get("left"))
        mends = self.mends_of(got, "遠近の収束")
        self.assertTrue(mends, got["history"])
        self.assertTrue(any("vanishing point" in w for r in got["history"] for m in r.get("mends", [])
                            if m.get("item") == "遠近の収束" for w in m.get("words", [])), got["history"])


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

    def test_weight_lines_thickens_sketch_frame(self):
        """線の強弱: 細い線のラフ画を太らせると、線画だけの独立したコマになる（差が DIFF_MIN を超える）。内側の細い線はそのまま"""
        import numpy as np
        from atelier.ai import phase_tools as pt
        sk = sketch((64, 96))
        before = pt.lines(sk)
        self.assertTrue(before["readable"])
        self.assertIn("weight", before)
        out, hit = pt.weight_lines(sk)
        self.assertGreater(hit, 0)
        self.assertGreater(mean_diff(sk, out), phases.DIFF_MIN)   # 線画のコマが DIFF_MIN を超える
        after = pt.lines(out)
        self.assertGreater(after["weight"], before["weight"])   # 外の輪郭が太くなった
        # 内側の目の線（細い線）は太らせない。目の線の辺りの画素は変わらない
        a, b = np.asarray(sk), np.asarray(out)
        eye = a[14:16, 28:36]
        self.assertTrue((eye == b[14:16, 28:36]).all())

    def test_lines_max_gap_finds_broken_line(self):
        """線のズレ: 輪郭の線が途中で薄くなっていると、途切れの長さ（max_gap）が大きくなる。切れていない線は小さい"""
        from atelier.ai import phase_tools as pt
        from PIL import Image, ImageDraw
        sk = sketch((64, 96))
        self.assertLess(pt.lines(sk)["max_gap"], 0.3)
        broken = sketch((64, 96))
        d = ImageDraw.Draw(broken)
        # 体の輪郭の左辺全体を薄い色で描き直す（線が薄く、輪郭に線が無い所が長く続く）
        d.line([int(64 * 0.35), int(96 * 0.25), int(64 * 0.35), int(96 * 0.95)], fill=(200, 200, 200), width=1)
        self.assertGreater(pt.lines(broken)["max_gap"], pt.LINE_MAX_GAP_MOST)
        self.assertGreater(pt.lines(broken)["max_gap"], pt.lines(sk)["max_gap"])

    def test_dust_finds_specks(self):
        """ゴミ: 主役から離れた小さな点をゴミと見る。きれいな絵は 0 個"""
        from PIL import ImageDraw
        from atelier.ai import phase_tools as pt
        im = figure((64, 96))
        self.assertEqual(pt.dust(im)["count"], 0)
        dusty = figure((64, 96))
        d = ImageDraw.Draw(dusty)
        d.rectangle([5, 5, 7, 7], fill=(30, 30, 30))
        d.rectangle([55, 80, 57, 82], fill=(30, 30, 30))
        got = pt.dust(dusty)
        self.assertEqual(got["count"], 2)
        self.assertEqual(len(got["boxes"]), 2)

    def test_detached_finds_near_blob_not_far_blob(self):
        """位置ずれ: 体の近くに離れた塊があれば位置ずれ。遠くの塊（鳥など）は位置ずれにしない"""
        from PIL import ImageDraw
        from atelier.ai import phase_tools as pt
        im = figure((64, 96))
        self.assertEqual(pt.detached(im)["count"], 0)
        det = figure((64, 96))
        d = ImageDraw.Draw(det)
        d.rectangle([45, 40, 55, 50], fill=(60, 60, 80))  # 体の近くに離れた塊
        self.assertEqual(pt.detached(det)["count"], 1)
        far = figure((64, 96))
        d = ImageDraw.Draw(far)
        d.rectangle([5, 5, 12, 12], fill=(60, 60, 80))  # 遠くの塊
        self.assertEqual(pt.detached(far)["count"], 0)

    def test_horizon_tilt_and_flat(self):
        """画角: 傾いた地平線の傾きを測る。水平な地平線は 0 度。地平線の無い絵は読めない"""
        from atelier.ai import phase_tools as pt
        land = tilted_land((128, 96))
        got = pt.horizon(land)
        self.assertTrue(got["readable"])
        self.assertGreater(got["tilt"], pt.HORIZON_TILT_MOST)
        flat = tilted_land((128, 96), slope=0.0)
        self.assertAlmostEqual(pt.horizon(flat)["tilt"], 0.0, places=1)
        self.assertFalse(pt.horizon(figure((64, 96)))["readable"])   # 人物だけの絵に地平線は無い

    def test_bleed_finds_patch(self):
        """色のにじみ: 紙の上に主役から離れた色があればにじみ。きれいな絵は 0 個"""
        from PIL import ImageDraw
        from atelier.ai import phase_tools as pt
        im = figure((64, 96))
        self.assertEqual(pt.bleed(im)["count"], 0)
        bl = figure((64, 96))
        d = ImageDraw.Draw(bl)
        d.rectangle([14, 60, 18, 70], fill=(200, 30, 30))  # 紙の上に赤い色
        got = pt.bleed(bl)
        self.assertEqual(got["count"], 1)
        self.assertGreater(got["share"], 0)

    def test_water_light_spread(self):
        """水の光: 光の筋がある水は明るさの広がりが大きく、光の無い水は広がりが 0 に近い"""
        from atelier.ai import phase_tools as pt
        self.assertGreater(pt.water_light(water_scene((128, 96), with_light=True))["spread"], pt.WATER_LIGHT_LEAST)
        self.assertLess(pt.water_light(water_scene((128, 96), with_light=False))["spread"], pt.WATER_LIGHT_LEAST)
        self.assertFalse(pt.water_light(figure((64, 96)))["readable"])   # 水が無ければ読めない

    def test_shine_water_adds_light(self):
        """水の光の直し: 光の無い水に光の筋を付けると、明るさの広がりがしきい値を超える。絵が変わる"""
        from atelier.ai import phase_tools as pt
        im = water_scene((128, 96), with_light=False)
        out, hit = pt.shine_water(im)
        self.assertGreater(hit, 0)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)
        self.assertGreater(pt.water_light(out)["spread"], pt.WATER_LIGHT_LEAST)

    def test_leaf_gloss_spread(self):
        """葉のつや: つやの点がある葉は明るさの広がりが大きく、つやの無い葉は広がりが 0 に近い"""
        from atelier.ai import phase_tools as pt
        self.assertGreater(pt.leaf_gloss(leaf_scene((128, 96), with_gloss=True))["spread"], pt.LEAF_GLOSS_LEAST)
        self.assertLess(pt.leaf_gloss(leaf_scene((128, 96), with_gloss=False))["spread"], pt.LEAF_GLOSS_LEAST)
        self.assertFalse(pt.leaf_gloss(figure((64, 96)))["readable"])   # 葉が無ければ読めない

    def test_shine_leaf_adds_gloss(self):
        """葉のつやの直し: つやの無い葉につやの点を付けると、明るさの広がりがしきい値を超える。絵が変わる"""
        from atelier.ai import phase_tools as pt
        im = leaf_scene((128, 96), with_gloss=False)
        out, hit = pt.shine_leaf(im)
        self.assertGreater(hit, 0)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)
        self.assertGreater(pt.leaf_gloss(out)["spread"], pt.LEAF_GLOSS_LEAST)

    def test_tire_roundness(self):
        """タイヤの丸み: 丸いタイヤは境界の半径の変動が小さく、平らなタイヤは大きい。楕円（遠近）は丸い方に入る"""
        from atelier.ai import phase_tools as pt
        from PIL import Image, ImageDraw
        good = pt.tire_roundness(car_side_scene((128, 96), flat_tire=False))
        self.assertTrue(good["readable"])
        self.assertLess(good["worst"], pt.TIRE_CV_MOST)
        bad = pt.tire_roundness(car_side_scene((128, 96), flat_tire=True))
        self.assertTrue(bad["readable"])
        self.assertGreater(bad["worst"], pt.TIRE_CV_MOST)
        self.assertEqual(len(bad["boxes"]), 2)   # 2 つのタイヤの枠が返る
        self.assertFalse(pt.tire_roundness(figure((64, 96)))["readable"])   # タイヤが無ければ読めない
        # 楕円のタイヤ（横に 1.4 倍の遠近）は、丸い方に入る
        im = Image.new("RGB", (128, 96), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([20, 33, 108, 58], fill=(180, 40, 40))
        for cx in (38, 90):
            d.ellipse([cx - 15, 53 - 11, cx + 15, 53 + 11], fill=(20, 20, 20))
        self.assertLess(pt.tire_roundness(_light_gradient(im))["worst"], pt.TIRE_CV_MOST)

    def test_symmetry_mirror_iou(self):
        """左右対称: 対称な車は鏡像との重なりが高く、片側が潰れた車は低い"""
        from PIL import Image
        from atelier.ai import phase_tools as pt
        self.assertGreater(pt.symmetry(car_front_scene((128, 96), asym=False))["iou"], pt.SYMMETRY_IOU_LEAST)
        self.assertLess(pt.symmetry(car_front_scene((128, 96), asym=True))["iou"], pt.SYMMETRY_IOU_LEAST)
        self.assertFalse(pt.symmetry(Image.new("RGB", (64, 96), "white"))["readable"])   # 物が無ければ読めない

    def test_mirror_fix_restores_symmetry(self):
        """左右対称の直し: 片側が潰れた車を鏡写しで直すと、鏡像との重なりがしきい値を超える。絵が変わる"""
        from atelier.ai import phase_tools as pt
        im = car_front_scene((128, 96), asym=True)
        out, hit = pt.mirror_fix(im)
        self.assertGreater(hit, 0)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)
        self.assertGreater(pt.symmetry(out)["iou"], pt.SYMMETRY_IOU_LEAST)

    def test_vanishing_angle(self):
        """遠近の収束: 収束する道は斜めの線の角度の差が大きく、平行な道は角度の差が 0 で収束が無い崩れ、人物の絵は斜めの線が無くて読めない"""
        from atelier.ai import phase_tools as pt
        good = pt.vanishing(road_scene((128, 96), converge=True))
        self.assertTrue(good["readable"])
        self.assertGreater(good["angle"], pt.VANISH_ANGLE_LEAST)
        self.assertIsNotNone(good["point"])   # 消失点が返る
        self.assertIsNotNone(good["box"])   # 直しの囲みが返る
        par = pt.vanishing(road_scene((128, 96), converge=False))
        self.assertTrue(par["readable"])   # 平行な斜めの道は線が読め、角度の差が 0 で収束が無い
        self.assertLess(par["angle"], pt.VANISH_ANGLE_LEAST)
        self.assertFalse(pt.vanishing(figure((64, 96)))["readable"])   # 人物の絵に遠近の線は無い


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
            if i >= 3:   # 確かめ（confirm）は工程の最後に来る。線画で旗を立てる
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
                # 余分な人はサムネイルの測り（1 回目の request）だけが見つける。アタリの確かめではもう見つからない
                return {"readable": True, "missing": [], "extra": [], "people": ["extra person"] if len(seen) <= 1 else [], "body": []}

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
        shown, now, phases_shown = [], [""], []
        from atelier.ai import phase_tools as pt

        def say(m):
            if m.startswith("工程 "):
                now[0] = m.split("「", 1)[1].split("」", 1)[0] if "「" in m else ""

        def show(im):
            shown.append(im)
            phases_shown.append(now[0])
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "red hair, 1girl", 1, (64, 64), Path(d), say=say, checks=checks(False)[0], on_preview=show)
        self.assertTrue(shown)
        # ラフ（サムネイル）から筆で見せる。最初の絵はサムネイルのときで、アタリも見せる
        self.assertTrue(phases_shown[0].startswith("サムネイル"), phases_shown)
        self.assertTrue(any(p.startswith("アタリ") for p in phases_shown), phases_shown)
        same = [k for k in range(1, len(shown)) if list(shown[k].getdata()) == list(shown[k - 1].getdata())]
        self.assertEqual(same, [])   # 同じ絵を続けて出さない
        # 出すのは、描いている途中の絵と、絵が変わった工程だけ
        self.assertLessEqual(len(shown), 2 * got["total"])


class PhaseWorkShownTest(unittest.TestCase):
    """サムネイル（ラフ）から先の工程の絵は、描けたら印（PHASE_TAG）を付けて窓に渡す。筆はラフからとる。
    「工程 i/N」は 1 から順に、飛ばずに進む"""

    def test_drawn_phases_tagged_and_numbers_in_order(self):
        tagged, said = [], []

        def show(im):
            if phases.PHASE_TAG in im.info:
                tagged.append(im.info[phases.PHASE_TAG])
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "red hair, 1girl", 1, (64, 64), Path(d), say=said.append, checks=checks(False)[0], on_preview=show)
        first = phases.NAMES.index(phases.SHOW_FROM)
        self.assertTrue(tagged)   # サムネイルから先の絵が窓に届かないと落ちる
        self.assertEqual(tagged[0]["phase"], "サムネイル", tagged)   # 筆はラフからとる
        self.assertTrue(all(phases.NAMES.index(t["phase"]) >= first for t in tagged), tagged)
        # 絵が変わった工程が印を付けて届く。線画は微調整だけの工程で、変化が小さく別画像にならないことがある（weight_lines は黒い線にはほぼ効かない）
        self.assertTrue(any(t["phase"] == "アタリ" for t in tagged), tagged)
        self.assertTrue(any(t["phase"] == "下塗り" for t in tagged), tagged)
        self.assertIn("線画", [r["phase"] for r in got["history"]])   # 線画の工程は回っている
        from atelier.ui.phase_display import relabel
        said = [x for x in said if relabel(x) is not None]   # 進み具合の欄が見せる知らせ（描かない工程「目的」は出さない）
        nos = [int(m.group(1)) for m in (re.match(r"工程 (\d+)/(\d+)「", x) for x in said) if m]
        self.assertTrue(nos)   # 「工程 i/N」が出ないと落ちる
        self.assertEqual(nos[0], 1)
        self.assertTrue(all(b - a in (0, 1) for a, b in zip(nos, nos[1:])), nos)   # 番号が飛ばない
        self.assertTrue(all("累計" not in x for x in said if re.match(r"工程 \d+/\d+「", x)))   # 累計の表記は出さない（利用者の指示）


class WorkLayerTest(unittest.TestCase):
    """窓は印の付いた工程の絵を、一番上の作業用のレイヤー 1 枚に置き直して見せる。元の絵は変えず、元に戻すで消せる"""

    def test_work_layer_on_top_and_undoable(self):
        from PIL import Image
        from atelier.app.main_window import Window
        from tests.test_editing import app
        qapp = app()
        d = Path(self.enterContext(TemporaryDirectory()))
        w = Window(Studio(FakeWords(), Painter(), d))
        self.addCleanup(lambda: (setattr(w, "dirty", False), w.close()))
        w.canvas.new_canvas(64, 64) if hasattr(w.canvas, "new_canvas") else None
        before = [(l.name, l.visible) for l in w.canvas.layers]
        w.thread = object()   # 描いている間だけ受け取る
        for k, (c, name) in enumerate((((10, 10, 10), "アタリ"), ((200, 50, 50), "下塗り")), 1):
            im = Image.new("RGB", (64, 64), c)
            im.info[phases.PHASE_TAG] = {"phase": name, "no": k + 6, "need": 30, "total": k}
            w.show_preview(im)
            qapp.processEvents()
        w.thread = None
        top = w.canvas.layers[-1]
        self.assertTrue(top.visible and top.name.startswith(w.WORK_LAYER), [l.name for l in w.canvas.layers])
        self.assertIn("下塗り", top.name)
        self.assertEqual(sum(1 for l in w.canvas.layers if l.name.startswith(w.WORK_LAYER)), 1)
        self.assertEqual(top.image.pixelColor(5, 5).red(), 200)   # 2 回目の絵に置き直した
        self.assertEqual([(l.name, l.visible) for l in w.canvas.layers[:-1]], before)   # 元のレイヤーはそのまま
        w.canvas.undo()
        self.assertFalse(any(l.name.startswith(w.WORK_LAYER) for l in w.canvas.layers))


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
            C0, _seen = checks(False)

            class C(C0):
                @staticmethod
                def request(image, prompt):
                    # 頼んだ物はずっと描かれていない（検品のたびに崩れを返し続ける）。線画でも確かめ直すので、
                    # 1 回だけ崩れる偽物では「直せない崩れが残る」ことを確かめられない
                    return {"readable": True, "missing": ["red scarf"], "extra": [], "people": [], "body": []}
            got = phases.draw(p, "1girl, red scarf", 1, (64, 64), Path(d), checks=C)
        self.assertTrue(any(x[0] == "refine" for x in p.log), p.log)
        self.assertFalse(got["complete"])   # 直せない崩れは残った崩れになる（全体の描き重ねを直しとして使わない）
        self.assertIsNone(got["asked"])   # 聞いて止まらない
        self.assertTrue(got["left"])


class NoWholeRedrawTest(unittest.TestCase):
    """どの工程でも絵の全体を描き直さない。囲めない崩れは、余分な人の枠・読めなかった部位の枠で囲み、
    それでも囲めなければ絵を前のまま残して、残った崩れとして次の工程へ進む（聞いて止まらない）"""

    def draw(self, C, silhouette=None, painter=None):
        painter = painter or Painter()
        said = []
        patches = [mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), mock.patch.object(pt, "parts", lambda _im: None)]
        if silhouette is not None:
            patches.append(mock.patch.object(pt, "silhouette", silhouette))
        with TemporaryDirectory() as d:
            for pa in patches:
                pa.start()
            try:
                got = phases.draw(painter, "1girl, red hair", 5, (64, 96), Path(d) / "k", say=said.append, checks=C)
            finally:
                for pa in patches:
                    pa.stop()
        return got, painter, said

    def assert_no_whole(self, got, painter):
        import numpy as np
        self.assertFalse(any(s["kind"] == "ask" for s in got["plan"]))
        self.assertIsNone(got["asked"])
        self.assertTrue(all(m["outside"] == 0 for r in got["history"] for m in r["mends"]))   # 囲みの外の差は 0
        self.assertFalse(any(m.get("whole") for r in got["history"] for m in r["mends"]))
        for m in getattr(painter, "masks", []):   # 模型に渡した囲みは、どれも絵の半分以下（全体の描き直しにしない）
            self.assertLessEqual(float((np.asarray(m.convert("L")) > 0).mean()), phases.GROW_MOST)
        self.assertEqual(sum(1 for x in painter.log if x[0] == "paint" and not x[3]), 1)   # ゼロから描いたのは土台の一発の絵だけ（サムネイルは土台から抜く。土台は画面に出さず、作業中の絵を描き直すものではない）

    def test_people_unenclosable_is_carried_not_redrawn(self):
        import numpy as np

        class C(hand_only_checks(bad_times=0)):
            @staticmethod
            def request(image, prompt):
                return {"readable": True, "missing": [], "extra": [], "people": ["multiple girls 0.78"], "body": []}

        whole = lambda im: np.ones((im.height, im.width), bool)   # noqa: E731  背景まで人と読む（塊を分けられない）
        got, painter, said = self.draw(C, silhouette=whole)
        self.assert_no_whole(got, painter)
        self.assertFalse(got["complete"])
        self.assertEqual(got["history"][-1]["phase"], "仕上げ")
        self.assertTrue(any("人数が違う" in f for f in got["left"]))
        self.assertTrue(any("残った崩れとして次の工程へ進みます" in m for m in said))

    def test_extra_person_box_is_the_mask(self):
        import numpy as np
        state = {"n": 0}

        class C(hand_only_checks(bad_times=0)):
            @staticmethod
            def request(image, prompt):
                state["n"] += 1
                return {"readable": True, "missing": [], "extra": [], "people": ["multiple girls 0.78"] if state["n"] <= 4 else [], "body": []}

        def two(im):   # 本人（大きい塊）と、右上の余分な人（小さい塊）。縮めた絵でも同じ形になるよう割合で置く
            h, w = im.height, im.width
            m = np.zeros((h, w), bool)
            m[h * 30 // 96:h * 90 // 96, w * 10 // 64:w * 30 // 64] = True
            m[h * 5 // 96:h * 20 // 96, w * 45 // 64:w * 60 // 64] = True
            return m
        got, painter, said = self.draw(C, silhouette=two)
        self.assert_no_whole(got, painter)
        masks = getattr(painter, "masks", [])
        self.assertTrue(masks)
        a = np.asarray(masks[0].convert("L")) > 0
        self.assertTrue(a[5:20, 45:60].all())   # 余分な人の枠を囲んだ
        self.assertFalse(a[30:90, 10:30].any())   # 本人は囲まない

    def test_unreadable_body_box_is_the_mask(self):
        import numpy as np
        seen = {"body": 0}

        class C(hand_only_checks(bad_times=0)):
            @staticmethod
            def body(image, prompt, tags=None):
                seen["body"] += 1
                return {"readable": seen["body"] > 2, "bad": [], "avoid": []}

        def person(im):
            h, w = im.height, im.width
            m = np.zeros((h, w), bool)
            m[h * 20 // 96:h * 80 // 96, w * 20 // 64:w * 40 // 64] = True
            return m
        got, painter, said = self.draw(C, silhouette=person)
        self.assert_no_whole(got, painter)
        self.assertTrue(got["complete"], said[-4:])
        a = np.asarray(painter.masks[0].convert("L")) > 0
        self.assertTrue(a[20:80, 20:40].all())   # 読めなかった体の枠を囲んだ
        self.assertFalse(a[:, 45:].any())

    def test_every_scenario_keeps_outside(self):
        for always_bad in (False, True):
            C, _seen = checks(always_bad)
            got, painter, _said = self.draw(C)
            with self.subTest(always_bad=always_bad):
                self.assert_no_whole(got, painter)


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


def painted_person(size=(256, 384)):
    """色を塗った人物の絵（本物の絵に近い大きさ）。色の面に細かいざらつき（±10）を付ける"""
    import numpy as np
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), (250, 250, 248))
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.35, h * 0.45, w * 0.65, h * 0.95], fill=(180, 60, 60))   # 赤い服
    d.ellipse([w * 0.40, h * 0.08, w * 0.60, h * 0.32], fill=(235, 205, 180))  # 顔
    d.pieslice([w * 0.38, h * 0.05, w * 0.62, h * 0.35], 180, 360, fill=(60, 40, 30))  # 髪
    for x in (w * 0.45, w * 0.55):
        d.ellipse([x - 3, h * 0.18 - 3, x + 3, h * 0.18 + 3], fill=(30, 30, 30))  # 目
    a = np.asarray(im).astype(float)
    rng = np.random.default_rng(5)
    lum = a.mean(-1)
    mask = lum < 200   # 色の面だけにざらつき（紙はそのまま）
    a = np.where(mask[..., None], np.clip(a + rng.normal(0, 10, a.shape), 0, 255), a)
    return Image.fromarray(a.astype("uint8"))


def dusty_line(size=(256, 384)):
    """白い紙に黒い線で描いた線画に、ほこり（小さな黒い点）を散らした物"""
    import numpy as np
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), (250, 250, 248))
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.38, h * 0.05, w * 0.62, h * 0.25], outline=(0, 0, 0), width=2)
    d.rectangle([w * 0.35, h * 0.25, w * 0.65, h * 0.95], outline=(0, 0, 0), width=2)
    d.line([w * 0.45, h * 0.15, w * 0.55, h * 0.15], fill=(0, 0, 0), width=2)
    a = np.asarray(im).copy()
    rng = np.random.default_rng(7)
    for _ in range(60):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(1, 3))
        a[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1] = (40, 40, 40)
    return Image.fromarray(a)


def uneven_line(size=(256, 384)):
    """白い紙に黒い線で描いた線画に、紙のむら（ゆるやかな明るさの変化と細かいざらつき）を付けた物"""
    import numpy as np
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", (w, h), (250, 250, 248))
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.38, h * 0.05, w * 0.62, h * 0.25], outline=(0, 0, 0), width=2)
    d.rectangle([w * 0.35, h * 0.25, w * 0.65, h * 0.95], outline=(0, 0, 0), width=2)
    d.line([w * 0.45, h * 0.15, w * 0.55, h * 0.15], fill=(0, 0, 0), width=2)
    a = np.asarray(im).astype(float)
    yy, xx = np.mgrid[0:h, 0:w]
    uneven = 8 * np.sin(xx / 40.0) + 6 * np.cos(yy / 55.0)
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 4, (h, w))
    lum = a.mean(-1)
    mask = lum > 200
    for c in range(3):
        a[..., c] = np.where(mask, np.clip(a[..., c] + uneven + noise, 0, 255), a[..., c])
    return Image.fromarray(a.astype("uint8"))


class ProcessingChangesTest(unittest.TestCase):
    """加工を掛けたら絵が変わる。変わらない加工（完全に同じ絵が出る）は、ここで落ちる。
    2026-11-25 に直した物: denoise（ざらつきの数字が 0 になり掛からなかった）、detail（直しが足した細部を消した）、
    retouch_full（denoise が掛からず見えない変わりだけ）、shade_second（影が薄すぎた）、guard（霞んだ描き重ねを捨てて
    元の絵を返した）、clean の線画（ほこりが消えず、均した分が混ぜ戻された）"""

    def test_denoise_changes_noisy_picture(self):
        from atelier.ai import finishers
        im = painted_person()
        out = finishers.run("denoise", im)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_detail_changes_picture(self):
        from atelier.ai import finishers
        im = painted_person()
        out = finishers.run("detail", im)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_retouch_full_changes_noisy_picture(self):
        from atelier.ai import finishers
        im = painted_person()
        out = finishers.run("retouch_full", im)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_clean_changes_noisy_picture(self):
        from atelier.ai import finishers
        im = painted_person()
        out = finishers.run("clean", im)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_face_changes_picture(self):
        from atelier.ai import finishers
        im = painted_person()
        out = finishers.run("face", im)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_retouch_changes_picture(self):
        from atelier.ai import finishers
        im = painted_person()
        out = finishers.run("retouch", im)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_clean_removes_dust_from_sketch(self):
        from atelier.ai import finishers
        sk = dusty_line()
        out = finishers.run("clean", sk)
        self.assertGreater(mean_diff(sk, out), phases.DIFF_MIN)

    def test_clean_evens_uneven_paper_sketch(self):
        from atelier.ai import finishers
        sk = uneven_line()
        out = finishers.run("clean", sk)
        self.assertGreater(mean_diff(sk, out), phases.DIFF_MIN)

    def test_shade_second_changes_picture(self):
        im = painted_person()
        lit = pt.light(im)
        out, hit = pt.shade_second(im, lit)
        self.assertGreater(hit, 0)
        self.assertGreater(mean_diff(im, out), phases.DIFF_MIN)

    def test_guard_keeps_hazy_refine(self):
        """霞んだ描き重ねを捨てて元の絵を返すと、描き重ねが無かったことになる。霞みを直して描き重ねを残す"""
        from PIL import Image, ImageFilter
        ref = painted_person()
        hazy = Image.blend(ref, ref.filter(ImageFilter.GaussianBlur(3)), 0.5)
        out, rec = pt.guard(hazy, ref)
        self.assertFalse(rec["kept_ref"])
        self.assertFalse(rec["left"])
        self.assertGreater(mean_diff(ref, out), phases.DIFF_MIN)


class RecordingPainter(Painter):
    """直しの呼び出しを記録する画家。redraw は言葉・消すかどうか・強さを、refine は言葉・強さを残す"""

    def __init__(self):
        super().__init__()
        self.redraw_calls = []   # (prompt, clean, strength)
        self.refine_calls = []   # (prompt, strength)

    def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
        self.redraw_calls.append((prompt, kw.get("clean", False), kw.get("strength")))
        return super().redraw(prompt, seed, image, mask, on_step=on_step, **kw)

    def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
        self.refine_calls.append((prompt, strength))
        from PIL import ImageChops
        return ImageChops.add(image.convert("RGB"), image.convert("RGB").point(lambda _v: 5 + seed % 7))


def missing_item_checks():
    """頼んだ物だけをいつも欠落させる検品。構図の直し（アタリ全体の描き直し）を単独で試す。
    欠落はずっと残るので、直しは MENDS 回まで重ねてから聞く工程へ進む（完了は見ない）"""
    class C:
        @staticmethod
        def request(image, prompt):
            return {"readable": True, "missing": ["red scarf"], "extra": [], "people": [], "body": []}

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
    return C


class MendFixTest(unittest.TestCase):
    """直しが直せない欠陥の回帰試験。手・足・顔の形の崩れは、崩れた形をなぞらないよう消してから描き直し、
    直す内容の言葉を渡す。構図の崩れ（頼んだ物が無い・物が離れている）は、囲みの中だけでは直せないので
    アタリ全体を描き直す（絵から絵）。"""

    def test_hand_mend_erases_and_names_the_fix(self):
        """手の形の崩れの直しは、囲みの中を消してから描き直し、言葉に指の直しを入れる。
        囲みの中に渡すのは、その囲みの直す内容の言葉だけ。依頼の文（場面の説明）は渡さない"""
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            painter = RecordingPainter()
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=hand_only_checks(bad_times=5))
        self.assertTrue(got["complete"])
        hand_redraws = [(p, c, s) for (p, c, s) in painter.redraw_calls if "five fingers" in p]
        self.assertTrue(hand_redraws, painter.redraw_calls)
        self.assertTrue(all(c for (_p, c, _s) in hand_redraws), painter.redraw_calls)
        # 囲みの中の直しは、依頼の文を渡さない。直す内容の言葉だけを渡す
        self.assertTrue(all("red scarf" not in p for (p, _c, _s) in hand_redraws), painter.redraw_calls)

    def test_composition_mend_redraws_whole_atari(self):
        """アタリで頼んだ物が無い崩れの直しは、囲みの描き直しではなくアタリ全体の描き直し（絵から絵）になる"""
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            painter = RecordingPainter()
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=missing_item_checks())
        mends = [m for r in got["history"] if r["phase"] == "アタリ" for m in r.get("mends", [])
                 if m.get("item") == "頼んだ物"]
        self.assertTrue(mends, got["history"])
        self.assertTrue(any(m.get("full") for m in mends), mends)
        self.assertTrue(any("red scarf" in p for (p, _s) in painter.refine_calls), painter.refine_calls)
        # 描かれていない物は、言葉の頭に置いて強く出す。後ろに足すだけでは埋もれて、模型は同じ物を描かない
        self.assertTrue(any(p.startswith("red scarf") for (p, _s) in painter.refine_calls), painter.refine_calls)


class BrushUpBaseTest(unittest.TestCase):
    """土台から磨き上げる進め方（ユーザーの方針、2026-11-26）。
    最初に一発で描いた絵（人間で言う 80 点）を内側の土台として持ち、工程はそれを 100 点へ磨き上げる。
    土台の絵は画面にも工程の絵にも出さない（見せるのは白い紙から描き上がる工程の絵だけ）。
    最後の絵の崩れの重さが土台より小さくなければ完成にしない"""

    def _img(self, red=False, mark=False):
        """人物の絵。red は頼んだ物（赤い塊）、mark は手の崩れの印（黒い塊）。どちらも手の囲み（[10, 10, 30, 30] の円）の中に置く"""
        from PIL import ImageDraw
        im = figure()
        d = ImageDraw.Draw(im)
        if mark:
            d.rectangle([13, 13, 20, 20], fill=(0, 0, 0))
        if red:
            d.rectangle([22, 16, 30, 24], fill=(200, 30, 30))
        return im

    def _content_checks(self):
        """絵の中身で返す検品。赤い塊が無ければ頼んだ物が無い、手の印があれば手の崩れ。呼び出し回数には依存しない"""
        import numpy as np

        def has_red(im):
            a = np.asarray(im.convert("RGB"), dtype=np.int16)
            return int(((a[..., 0] > 150) & (a[..., 1] < 100) & (a[..., 2] < 100)).sum()) > 30

        def has_mark(im):
            a = np.asarray(im.convert("RGB"), dtype=np.int16)
            return int((a[12:28, 12:28] < 40).all(axis=2).sum()) > 20

        class C:
            @staticmethod
            def request(image, prompt):
                return {"readable": True, "missing": [] if has_red(image) else ["red scarf"], "extra": [], "people": [], "body": []}

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
                return dict(HAND) if has_mark(image) else dict(CLEAN_HAND)
        return C

    def _painter(self, base_img, phase_img, mend_img):
        """土台の絵・工程の絵・直しの絵をそれぞれ決めて返す画家。描き重ね（base あり）は工程の絵を返す"""
        class P(Painter):
            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                if kw.get("base") is not None:
                    return phase_img.copy()
                return (base_img if "monochrome" not in prompt else phase_img).copy()

            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.log.append(("redraw", seed, kw.get("strength")))
                self.masks = getattr(self, "masks", []) + [mask]
                return mend_img.copy()
        return P()

    def _run(self, painter, checks):
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append, checks=checks)
        return got, said

    def test_better_mends_complete_below_base(self):
        """直しが崩れを減らすケース: 土台（手の崩れ＋頼んだ物が無い、重さ 2）から磨き上げ、最後の絵の重さ 0 で完成になる"""
        from PIL import Image, ImageDraw
        fixed = Image.new("RGB", (64, 96), "white")
        ImageDraw.Draw(fixed).rectangle([22, 16, 30, 24], fill=(200, 30, 30))   # 囲みの中は白と頼んだ物だけ（手の印は無い）
        painter = self._painter(self._img(mark=True), self._img(red=True, mark=True), fixed)
        got, said = self._run(painter, self._content_checks())
        self.assertEqual(got.get("base", {}).get("severity"), 2, got.get("base"))
        self.assertEqual(got.get("final_severity"), 0, got.get("base"))
        self.assertTrue(got["complete"], got["left"])
        self.assertEqual(got["left"], [])

    def test_worse_mends_do_not_complete(self):
        """直しが別の崩れを増やすケース: 手の印は消えるが、頼んだ物まで消える。工程ごとの検品は通っても、
        最後の絵の重さが土台より小さくなっていないので、完成にしない"""
        from PIL import Image, ImageDraw
        worse = Image.new("RGB", (64, 96), "white")
        d = ImageDraw.Draw(worse)
        d.rectangle([11, 15, 13, 17], fill=(0, 0, 0))   # 囲みの中にゴミ 2 つ（手の印でも頼んだ物でもない別の崩れ）
        d.rectangle([11, 24, 13, 26], fill=(0, 0, 0))
        painter = self._painter(self._img(red=True, mark=True), self._img(red=True, mark=True), worse)
        got, said = self._run(painter, self._content_checks())
        self.assertEqual(got.get("base", {}).get("severity"), 1, got.get("base"))
        self.assertGreaterEqual(got.get("final_severity") or 0, 1, got.get("base"))
        self.assertFalse(got["complete"])
        self.assertTrue(any("良くなっていない" in f for f in got["left"]), got["left"])

    def test_base_image_is_never_shown(self):
        """土台の絵は内側だけ。preview にも、工程の絵のファイルにも、最後の絵にもならない"""
        from PIL import Image
        base_img = Image.new("RGB", (64, 96), (255, 0, 255))

        class P(Painter):
            painted_base = False

            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                if kw.get("base") is not None:
                    return figure(kw.get("size") or (64, 96))
                if "monochrome" not in prompt:
                    self.painted_base = kw.get("on_preview") is None
                    return base_img.copy()
                return figure(kw.get("size") or (64, 96))
        painter = P()
        shown = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0), on_preview=shown.append)
            files = sorted((Path(d) / "k").glob("*.png"))
            base_px = list(base_img.getdata())
            self.assertTrue(painter.painted_base)   # 土台は描かれた（そのとき preview は渡されていない）
            self.assertFalse(any(list(im.getdata()) == base_px for im in shown), "土台が preview に出た")
            self.assertFalse(any(list(Image.open(p).getdata()) == base_px for p in files), "土台が工程の絵として保存された")
        self.assertNotEqual(list(got["image"].getdata()), base_px)

    def test_color_starts_from_clean_lines(self):
        """線の段階にゴミが残ったまま色の工程に入らない。ゴミ消しは清書（線画の仕上げ）で済ませる"""
        def dusty(size=(64, 96)):
            im = sketch(size)
            from PIL import ImageDraw
            d = ImageDraw.Draw(im)
            for x, y in ((5, 5), (58, 10), (5, 90)):
                d.rectangle([x, y, x + 1, y + 1], fill=(0, 0, 0))
            return im

        class P(Painter):
            abilities = (True, False)   # 囲みの中だけを直せない。線画のゴミは直しの工程では消せない

            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                if kw.get("base") is not None:
                    return kw["base"].copy()
                return figure(kw.get("size") or (64, 96)) if "monochrome" not in prompt else dusty(kw.get("size") or (64, 96))
        said = []
        # 線の強弱付け（weight_lines）は別の試験で確かめる。ここでは「線画にゴミが残ったまま下塗りに来る」条件を作るため素通しにする
        # （偽の線画では、強弱付けが小さな断片を線に寄せてしまい、ゴミが残らない）
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(pt, "weight_lines", lambda im: (im, 0)):
            got = phases.draw(P(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append,
                              checks=hand_only_checks(bad_times=0))
            files = sorted((Path(d) / "k").glob("*.png"))
            from PIL import Image
            line_files = [p for p in files if "線画" in p.name and not p.name.startswith("layer")]
            self.assertTrue(line_files, [p.name for p in files])
            self.assertEqual(pt.dust(Image.open(line_files[-1]))["count"], 0)   # 清書で消えたので、線画の時点でゴミは無い
        self.assertEqual(pt.dust(got["image"])["count"], 0)   # 色の工程以降、ゴミは無い


class DegradationGuardTest(unittest.TestCase):
    """工程が進むほど絵が壊れた事故（検証 45696035067）の回帰試験。良い線画（サムネイル）が出たのに、
    アタリの直しで対比 35.9 → 12.8 に落ち、離れた物が 2 個 → 124 個に増え、仕上げのゴミ取りで
    平らな紙の塊が顔を覆った。原因は 3 つ: 構図の直し（全体の描き直し）に色と明るさの守りが無かったこと、
    確かめ直しの戻しが文の数だけを見て文に埋まった数（〜個）を見なかったこと、
    ゴミ取りの囲みが枠の円で広がり、塊そのものより何倍も広く消したこと"""

    def run_draw(self, painter, prompt, checks, said):
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, prompt, 5, (64, 96), Path(d) / "k", say=said.append, checks=checks)
        return got

    def test_composition_mend_keeps_tone(self):
        """アタリの構図の直し（全体の描き直し）が霞んだ絵を返しても、色と明るさの守りが掛かり、霞んだ絵を採らない。
        下描きの描き重ねには守りがあったが、構図の直しには無く、直しのたびに色が薄くなり汚れが広がった"""
        class WashPainter(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                from PIL import Image
                return Image.blend(image.convert("RGB"), Image.new("RGB", image.size, (235, 235, 235)), 0.8)

        said = []
        got = self.run_draw(WashPainter(), "1girl, red scarf", missing_item_checks(), said)
        mends = [m for r in got["history"] if r["phase"] == "アタリ" for m in r.get("mends", []) if m.get("item") == "頼んだ物"]
        self.assertTrue(mends, got["history"])
        self.assertTrue(any("構図の直し" in m for m in said), said)   # 守り（keep_tone）が構図の直しにも掛かった
        self.assertTrue(all(not m["changed"] for m in mends), mends)   # 霞んだ絵は採られなかった

    def test_detached_growth_is_reverted(self):
        """位置ずれの直しで離れた物が増えたら、文に埋まった数を見て直す前の絵に戻す。
        前は文の数（いつも 1 本）だけを見ていたので、2 個 → 124 個に増えても戻らなかった"""
        class BlobPainter(Painter):
            def __init__(self):
                super().__init__()
                self.n = 0

            def paint(self, prompt, seed, on_step=None, **kw):
                im = super().paint(prompt, seed, on_step=on_step, **kw)
                from PIL import ImageDraw
                ImageDraw.Draw(im).rectangle([16, 26, 20, 30], fill=(60, 60, 80))   # 体から離れた塊 1 つ
                return im

            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.n += 1
                im = image.convert("RGB").copy()
                from PIL import ImageDraw
                y = 26 + (self.n % 5) * 13
                ImageDraw.Draw(im).rectangle([16, y, 20, y + 4], fill=(60, 60, 80))   # 描き重ねるたびに塊が 1 つ増える
                return im

        said = []
        got = self.run_draw(BlobPainter(), "1girl, red scarf", hand_only_checks(bad_times=0), said)
        self.assertTrue(any("位置ずれ" in m and "戻します" in m for m in said), said)
        self.assertLessEqual(pt.detached(got["image"])["count"], 4, pt.detached(got["image"]))   # 塊が積み上がっていない

    def test_dust_mask_is_the_specks_themselves(self):
        """ゴミの囲みは塊そのものだけ。枠の円で広げると、細い線の欠片が集まった所（顔など）まで
        紙の色で消えて、平らな塊になる（実測: 影 2 段の絵で円の囲みは頭の 19% を覆った）"""
        import numpy as np
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (256, 384), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([100, 120, 160, 360], fill=(60, 60, 80))   # 主役
        d.ellipse([105, 20, 155, 90], fill=(250, 250, 250))    # 紙とほぼ同じ色の顔（線の欠片だけが塊になる）
        for j in range(8):   # 髪の線の欠片（細く短い線。塊の画素は少ないが、枠は塊より大きい）
            x = 112 + j * 5
            d.line([x, 30, x + 6, 40], fill=(30, 30, 30), width=1)
        got_dust = pt.dust(im)
        self.assertGreaterEqual(got_dust["count"], 6, got_dust)   # 検品は今までどおり欠片を見つける
        mask = pt.dust_mask(im)
        self.assertIsNotNone(mask)
        m = np.asarray(mask.convert("L")) > 0
        circles = np.asarray(phases._mask(im.size, [(b, "dust") for b in got_dust["boxes"]]).convert("L")) > 0
        self.assertLessEqual(int(m.sum()), int(circles.sum()) // 3)   # 円で広げていない
        self.assertFalse(bool((m & ~pt.silhouette(im)).any()))   # 囲みはゴミの画素だけ（紙の所は囲まない）
        arr = np.asarray(im.convert("RGB")).copy()
        arr[m] = pt.paper_color(im)
        self.assertEqual(pt.dust(Image.fromarray(arr.astype("uint8")))["count"], 0)   # この囲みで消せば検品が通る


class LayerBasePainter(Painter):
    """線画は白地に黒い帯、下塗りの描き重ねは薄い色の一色を返す画家。
    本物の模型で下塗りが線を薄くしたのと同じ壊れ方をさせる"""

    def paint(self, prompt, seed, on_step=None, **kw):
        self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
        from PIL import Image, ImageDraw
        size = kw.get("size") or (64, 96)
        im = Image.new("RGB", size, "white")
        d = ImageDraw.Draw(im)
        d.rectangle([size[0] // 2 - 2, 0, size[0] // 2 + 2, size[1]], fill=(0, 0, 0))   # 線画の線
        return im

    def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
        self.log.append(("refine", seed, strength))
        if strength in (phases.BASE_COLOR, phases.BASE_OVER):
            import numpy as np
            from PIL import Image
            w, h = image.size
            grad = np.tile(np.linspace(195, 230, w, dtype=np.uint8), (h, 1))   # 薄い色（右が明るい）。線は入っていない
            return Image.fromarray(np.stack([grad, grad, grad], axis=2))
        return image.copy()


class GreyPaperPainter(LayerBasePainter):
    """線画を灰色の紙（明るさ 165）に描き、下塗りの描き重ねは土台の紙が灰色なら
    灰色のまま返す画家。実機の検証 46030668432 で、灰色の紙の線画から描き重ねた
    下塗りに色がほとんど乗らなかったのと同じ壊れ方をさせる"""

    def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
        if "monochrome" in prompt:   # 線の工程（ラフ・ペン）の描き重ねが、紙を灰色にする
            import numpy as np
            from PIL import Image
            self.log.append(("refine", seed, strength))
            a = np.asarray(image.convert("RGB")).astype(np.float32) * (165.0 / 255.0)
            return Image.fromarray(a.astype("uint8"))
        if strength in (phases.BASE_COLOR, phases.BASE_OVER):
            import numpy as np
            from PIL import Image
            self.log.append(("refine", seed, strength))
            a = np.asarray(image.convert("RGB")).astype(np.float32)
            paper = float(np.percentile(a.mean(axis=2), 90))
            self.base_paper = paper
            if paper < 200:
                return image.convert("RGB").copy()   # 灰色の土台からは色が乗らない
            w, h = image.size
            out = np.zeros((h, w, 3), np.uint8)
            out[:] = (230, 150, 150)   # 薄い赤の下塗り。線は入っていない
            return Image.fromarray(out)
        return super().refine(prompt, seed, image, strength=strength, on_step=on_step, on_preview=on_preview)


class LayerTest(unittest.TestCase):
    """レイヤー管理: 線画をレイヤーに残し、清書して、色は別レイヤーに塗る"""

    def run_layered(self):
        painter = LayerBasePainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
            rows = {r["phase"]: r for r in got["phases"]}
            img = None
            if rows["下塗り"].get("image"):
                from PIL import Image
                img = Image.open(rows["下塗り"]["image"]).convert("RGB")
        return got, rows, img

    def test_base_color_does_not_bury_the_lines(self):
        """下塗りの色が線を埋めない。線画レイヤーを色の上に乗せるので、
        線の所は線画の黒が残り、線の無い所は塗った色が出る"""
        got, rows, img = self.run_layered()
        self.assertTrue(got["complete"])
        self.assertIsNotNone(img)
        self.assertLess(img.getpixel((32, 48))[0], 60, "線が色に埋もれている")   # 線の所
        self.assertGreater(img.getpixel((8, 48))[0], 180, "色が付いていない")   # 線の無い所

    def test_layers_are_recorded(self):
        """下塗りの記録に、残したレイヤー（ラフ・線画・清書・下塗り）が出る"""
        got, rows, img = self.run_layered()
        self.assertEqual(rows["下塗り"]["numbers"].get("layers"), ["ラフ", "線画", "清書", "下塗り"])

    def test_grey_paper_line_art_still_gets_color(self):
        """線画の紙が灰色でも、下塗りに色が乗り、線は残る（検証 46030668432 の不具合）"""
        painter = GreyPaperPainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
            rows = {r["phase"]: r for r in got["phases"]}
            self.assertGreaterEqual(painter.base_paper, 235, "描き重ねの土台の紙が灰色のまま")
            self.assertTrue(rows["下塗り"].get("image"), "下塗りの絵が線画から変わっていない")
            from PIL import Image
            img = Image.open(rows["下塗り"]["image"]).convert("RGB")
        r, g, b = img.getpixel((8, 48))
        self.assertGreater(r - g, 40, "線の無い所に色が乗っていない")
        self.assertLess(img.getpixel((32, 48))[0], 60, "線が色に埋もれている")
        self.assertEqual(rows["下塗り"]["words"], ["1girl, red scarf"], "模型に渡す言葉が変わった")

    def test_whiten_paper_keeps_white_and_color(self):
        """紙を白に戻すのは灰色の紙の線画だけ。白い紙の線画と色の絵は触らない"""
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (64, 96), "white")
        ImageDraw.Draw(im).rectangle([30, 0, 34, 96], fill=(0, 0, 0))
        self.assertIs(pt.whiten_paper(im), im)
        scene = car_side_scene((64, 96))
        self.assertIs(pt.whiten_paper(scene), scene)
        grey = Image.new("RGB", (64, 96), (165, 165, 165))
        ImageDraw.Draw(grey).rectangle([30, 0, 34, 96], fill=(20, 20, 20))
        self.assertFalse(pt.line_like(grey))
        self.assertTrue(pt.line_like(pt.whiten_paper(grey)))

    def test_line_like_gate(self):
        """上に乗せてよいのは本物の線画だけ。色の付いた絵は線レイヤーにしない"""
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (64, 96), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([30, 0, 34, 96], fill=(0, 0, 0))
        self.assertTrue(pt.line_like(im))
        self.assertFalse(pt.line_like(car_side_scene((64, 96))))


class ThickColorPainter(Painter):
    """線画は細い線（5px の帯）。下塗りの描き重ねは、色と一緒に太い線（15px、2px ずれ）も
    描き直す画家。実モデルの描き重ね（img2img）は線も描き直すので、色の絵に線が入って
    いない前提（LayerBasePainter）は現実には崩れる"""

    def paint(self, prompt, seed, on_step=None, **kw):
        self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
        from PIL import Image, ImageDraw
        size = kw.get("size") or (64, 96)
        im = Image.new("RGB", size, "white")
        d = ImageDraw.Draw(im)
        d.rectangle([size[0] // 2 - 2, 0, size[0] // 2 + 2, size[1]], fill=(0, 0, 0))   # 5px の線
        return im

    def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
        self.log.append(("refine", seed, strength))
        if strength in (phases.BASE_COLOR, phases.BASE_OVER):
            import numpy as np
            from PIL import Image, ImageDraw
            w, h = image.size
            grad = np.tile(np.linspace(195, 230, w, dtype=np.uint8), (h, 1))   # 薄い色（右が明るい）
            im = Image.fromarray(np.stack([grad, grad, grad], axis=2))
            ImageDraw.Draw(im).rectangle([w // 2 - 5, 0, w // 2 + 9, h], fill=(30, 30, 30))   # 15px の太い線（2px ずれ）
            return im
        return image.copy()


class BaseLineRestoreTest(unittest.TestCase):
    """下塗りの描き重ねが線を描き直しても、結果の線は清書レイヤーの太さのまま。
    線レイヤーを乗算で乗せる合成は、色の絵自身の暗さを消せない。色の線が残ると
    線レイヤーの線と合わさった太さになり、下塗りの描く工程で線が太くなって
    壊れる（利用者の目撃、2026-11-27）"""

    def _dark_runs(self, img, y=48):
        import numpy as np
        row = np.asarray(img.convert("L"))[y]
        runs, start = [], None
        for x, v in enumerate(row < 100):
            if v and start is None:
                start = x
            if not v and start is not None:
                runs.append((start, x - start))
                start = None
        return runs

    def test_base_result_keeps_line_layer_width(self):
        painter = ThickColorPainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
            rows = {r["phase"]: r for r in got["phases"]}
            from PIL import Image
            img = Image.open(rows["下塗り"]["image"]).convert("RGB")
            line_img = Image.open(Path(d) / "k" / "layer-05-清書.png").convert("L")
            runs = self._dark_runs(img)
        self.assertEqual(runs, [(30, 5)], f"下塗りの結果の線が清書の太さ（5px）でない: {runs}")
        self.assertLess(img.getpixel((32, 48))[0], 60)      # 線の所は線画の黒が残る
        self.assertGreater(img.getpixel((8, 48))[0], 180)   # 線の無い所は塗った色が出る
        # 線の完全性: 結果の暗い所は、清書レイヤーの線と画素単位で一致する
        # （線が埋もれる・ずれる・欠ける・余分に太る、のどれも無い）
        import numpy as np
        out_dark = np.asarray(img.convert("L")) < 100
        line_dark = np.asarray(line_img) < 100
        self.assertTrue((out_dark == line_dark).all(),
                        "下塗りの結果の線が清書レイヤーの線と一致していない（埋もれ・ずれ・欠け・太り）")


def blotchy_image(size):
    """平らな色の面に、8x8 の濃い斑点（でき物のような塊）を 6 個置いた絵"""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.rectangle([16, 12, 48, 84], fill=(205, 175, 155))
    for (x, y) in ((20, 20), (36, 20), (20, 40), (36, 44), (20, 62), (36, 66)):
        d.rectangle([x, y, x + 7, y + 7], fill=(120, 60, 50))
    return im


def band_image(size, n_bands):
    """主役の矩形を n_bands 色の縦帯で塗った絵（色が散っている下塗りの再現）"""
    import colorsys
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = (16, 14, 48, 82)
    step = (x1 - x0) / n_bands
    for i in range(n_bands):
        r, g, b = colorsys.hsv_to_rgb((i / n_bands) % 1.0, 0.45, 0.78 if i % 2 else 0.95)
        d.rectangle([x0 + i * step, y0, x0 + (i + 1) * step, y1],
                    fill=(int(r * 255), int(g * 255), int(b * 255)))
    return im


class ColoringPainter(Painter):
    """線画（白地に黒い帯）を返し、下塗りの描き重ね（strength == BASE_COLOR）だけ差し替える画家"""

    def paint(self, prompt, seed, on_step=None, **kw):
        self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
        from PIL import Image, ImageDraw
        size = kw.get("size") or (64, 96)
        im = Image.new("RGB", size, "white")
        d = ImageDraw.Draw(im)
        d.rectangle([size[0] // 2 - 2, 0, size[0] // 2 + 2, size[1]], fill=(0, 0, 0))   # 線画の線
        return im

    def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
        self.log.append(("refine", seed, strength))
        if strength in (phases.BASE_COLOR, phases.BASE_OVER):
            return self.base_color(image.size)
        return image.copy()

    def base_color(self, size):
        raise NotImplementedError

    def run(self):
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(self, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
            rows = {r["phase"]: r for r in got["phases"]}
        return got, rows


class ColoringDefectsTest(unittest.TestCase):
    """塗りの欠陥（利用者の再発報告、2026-11-27）: 斑点・塗り残し・色の差で諦めて未完成。
    検品には必ず、実際に効く直しがあること"""

    def test_blotches_are_flagged_and_removed(self):
        """下塗りの斑点は、粒の物差しでは測れなかった。平らにした絵と比べる検品で見つけ、
        周りの色で埋める直しで消える。目の光（紙に近い白）は斑点として消さない"""
        class P(ColoringPainter):
            def base_color(self, size):
                im = blotchy_image(size)
                from PIL import ImageDraw
                d = ImageDraw.Draw(im)
                r = 2
                for x in (size[0] * 0.45, size[0] * 0.55):   # 目の光（figure と同じ位置）
                    d.ellipse([x - r, size[1] * 0.15 - r, x + r, size[1] * 0.15 + r], fill=(255, 255, 255))
                return im
        got, rows = P().run()
        self.assertTrue(any("斑点" in f for f in rows["下塗り"].get("found", [])), rows["下塗り"].get("found"))
        self.assertEqual(pt.blotch_mask(got["image"])[1], 0)   # 斑点は消えている
        self.assertGreater(got["image"].getpixel((29, 14))[0], 240)   # 目の光は残っている

    def test_color_scatter_is_fixed_by_posterize_without_redraw(self):
        """色が散っている崩れは、近い色を寄せる純粋な直しで直る。模型の描き直しだけが
        手だった頃は、描き直すたびに色数が変わって責任の判定で戻され、未完成で終わっていた"""
        class P(ColoringPainter):
            def __init__(self):
                super().__init__()
                self.redraw_calls = 0

            def base_color(self, size):
                # 主役を 4x4 の格子で 16 色に塗る（色が散っている）。細い帯だと
                # 下塗りの線の始末（strip_own_lines）が暗い帯を線と見分ける話と混ざるので、面で塗る
                import colorsys
                from PIL import Image, ImageDraw
                im = Image.new("RGB", size, "white")
                d = ImageDraw.Draw(im)
                x0, y0, x1, y1 = (16, 14, 48, 82)
                for gy in range(4):
                    for gx in range(4):
                        r, g, b = colorsys.hsv_to_rgb((gy * 4 + gx) / 16.0, 0.45, 0.78 if (gx + gy) % 2 else 0.95)
                        d.rectangle([x0 + gx * (x1 - x0) / 4, y0 + gy * (y1 - y0) / 4,
                                     x0 + (gx + 1) * (x1 - x0) / 4, y0 + (gy + 1) * (y1 - y0) / 4],
                                    fill=(int(r * 255), int(g * 255), int(b * 255)))
                r = 2
                for x in (size[0] * 0.45, size[0] * 0.55):   # 目の光（ほかの工程の直しを呼ばないため）
                    d.ellipse([x - r, size[1] * 0.15 - r, x + r, size[1] * 0.15 + r], fill=(255, 255, 255))
                return im

            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.redraw_calls += 1
                return band_image(image.size, 20)   # 描き直すと色が増える画家
        painter = P()
        got, rows = painter.run()
        self.assertFalse(any("色が散っている" in f for f in got["left"]), got["left"])
        mends = [m for r in got["history"] for m in r.get("mends", []) if m.get("item") == "色の差"]
        # 色の差の直しは全部「色を寄せる」（純粋な操作）で、描き直しは 1 回も使われていない
        self.assertTrue(mends and all(m.get("mend") == "色を寄せる" for m in mends), mends)
        self.assertTrue(any(m.get("changed") for m in mends), mends)

    def test_uncolored_part_is_flagged_and_filled(self):
        """主役の輪郭の内側が紙のまま（塗り残し）は、今まで測る検品が無く、黙って通っていた。
        検品で見つけ、直しで埋まること"""
        class P(ColoringPainter):
            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                from PIL import Image, ImageDraw
                size = kw.get("size") or (64, 96)
                im = Image.new("RGB", size, "white")
                d = ImageDraw.Draw(im)
                d.rectangle([16, 12, 48, 84], outline=(0, 0, 0))   # 主役の輪郭（閉じている）
                d.rectangle([size[0] // 2 - 2, 0, size[0] // 2 + 2, size[1]], fill=(0, 0, 0))
                return im

            def base_color(self, size):
                from PIL import Image, ImageDraw
                im = Image.new("RGB", size, "white")
                d = ImageDraw.Draw(im)
                d.rectangle([16, 12, 48, 48], fill=(205, 175, 155))   # 上半分だけ。下半分は紙のまま
                r = 2
                for x in (size[0] * 0.45, size[0] * 0.55):
                    d.ellipse([x - r, size[1] * 0.15 - r, x + r, size[1] * 0.15 + r], fill=(255, 255, 255))
                return im

            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                from PIL import ImageDraw
                out = image.copy()
                ImageDraw.Draw(out).rectangle([18, 50, 46, 64], fill=(205, 175, 155))   # 下半分の途中までしか塗らない画家
                return out
        got, rows = P().run()
        self.assertTrue(any("塗り残し" in f for f in rows["下塗り"].get("found", [])), rows["下塗り"].get("found"))
        mends = [m for r in got["history"] for m in r.get("mends", []) if m.get("item") == "塗り残し"]
        self.assertTrue(any(m.get("mend") == "塗り残しを埋める" and m.get("changed") for m in mends), mends)   # 残りは埋める手で直った
        self.assertLessEqual(pt.coverage_mask(got["image"])[1], phases.COVERAGE_MOST)
        self.assertLess(got["image"].getpixel((24, 76))[0], 250)   # 下半分の一番下まで色が付いている

    def test_speck_scattering_redraw_is_rejected_and_cover_fills(self):
        """塗り残しの描き直しが斑点を散らかしたら採用しない。見張りで戻された直しは
        同じ手を繰り返さず、次の手（周りの色で埋める）に進んで、塗り残しは直る"""
        class P(ColoringPainter):
            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                from PIL import Image, ImageDraw
                size = kw.get("size") or (64, 96)
                im = Image.new("RGB", size, "white")
                d = ImageDraw.Draw(im)
                d.rectangle([16, 12, 48, 84], outline=(0, 0, 0))
                d.rectangle([size[0] // 2 - 2, 0, size[0] // 2 + 2, size[1]], fill=(0, 0, 0))
                return im

            def base_color(self, size):
                from PIL import Image, ImageDraw
                im = Image.new("RGB", size, "white")
                ImageDraw.Draw(im).rectangle([16, 12, 48, 48], fill=(205, 175, 155))
                return im

            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                from PIL import ImageDraw
                out = image.copy()
                d = ImageDraw.Draw(out)
                d.rectangle([18, 50, 46, 82], fill=(205, 175, 155))   # 塗り残しは塗る
                for x in (20, 26, 38, 44):   # しかし黒い斑点を散らかす
                    for y in range(54, 79, 6):
                        d.rectangle([x, y, x + 1, y + 1], fill=(0, 0, 0))
                return out
        got, rows = P().run()
        mends = [m for r in got["history"] for m in r.get("mends", []) if m.get("item") == "塗り残し"]
        self.assertTrue(mends, got["history"])
        self.assertFalse(mends[0].get("changed"), mends)   # 斑点を散らかした描き直しは採用されていない
        self.assertTrue(any(m.get("mend") == "塗り残しを埋める" and m.get("changed") for m in mends), mends)
        self.assertLessEqual(pt.coverage_mask(got["image"])[1], phases.COVERAGE_MOST)
        for x, y in ((20, 54), (26, 60), (38, 66), (44, 72)):   # 散らかった斑点の位置に黒は無い
            self.assertGreater(got["image"].getpixel((x, y))[0], 150, (x, y))


class DetailAccumulationTest(unittest.TestCase):
    """ディテールの斑点は、1 回ごとの見張り（8 個）だけでは積み重なる。工程に入ったときの
    絵と比べる見張りで、工程全体の合計でも止める（利用者の目撃、2026-11-27: ディテールで斑）"""

    def test_detail_passes_do_not_accumulate_specks(self):
        class P(Painter):
            def __init__(self):
                super().__init__()
                self.detail_calls = 0
                self.before_detail = None

            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                if "detailed texture" in prompt:
                    self.detail_calls += 1
                    if self.before_detail is None:
                        self.before_detail = image.copy()
                    from PIL import ImageDraw
                    out = image.copy()
                    d = ImageDraw.Draw(out)
                    x0 = 6 + (self.detail_calls - 1) * 8   # 呼ぶたびに別の場所へ、境目未満の斑点を足す
                    for dx in range(5):
                        d.rectangle([x0 + dx, 88, x0 + dx + 1, 89], fill=(0, 0, 0))
                    return out
                return image.copy()
        painter = P()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(pt, "shadows", lambda *_a, **_k: {"readable": True, "shade_minus_lit": 5}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
        self.assertGreaterEqual(painter.detail_calls, 2)   # ディテールの描き重ねが複数回走った
        self.assertIsNotNone(painter.before_detail)
        specks = pt.new_specks(painter.before_detail, got["image"])
        self.assertLessEqual(specks, phases.SPECKS_MOST,
                             f"ディテール工程で斑点が {specks} 個まで積み重なった")


class EraseThenDrawOrderTest(unittest.TestCase):
    """形を変える直しは、消してから描く（利用者の指摘、2026-11-27: アタリの修正が
    書いてから消す順番になっている）。前は手・足・顔だけが消してから描いていて、
    アタリの骨組み・線の途切れなどは古い線の上に描いていた（薄く残って二重になる）"""

    def test_form_mends_erase_before_drawing(self):
        class Rec(Painter):
            def __init__(self):
                super().__init__()
                self.cleans = []

            def redraw(self, words, seed, image, mask, strength=0.45, clean=False, **kw):
                self.cleans.append(clean)
                return super().redraw(words, seed, image, mask, strength=strength, clean=clean, **kw)

        painter = Rec()
        C, _seen = checks(True)
        with TemporaryDirectory() as d:
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
        items = [m.get("item") for r in got["history"] for m in r.get("mends", [])]
        self.assertIn("骨組みの比", items)   # アタリの形の直しが走った
        self.assertEqual(len(painter.cleans), len(items))   # この流れの直しは全部描き直し
        self.assertTrue(all(painter.cleans),
                        f"消してから描いていない直しがある（clean の並び: {painter.cleans}、直し: {items}）")


class LineIntegrityExitTest(unittest.TestCase):
    """後の工程が清書の線を埋めたら、その工程の出口で清書のレイヤーから戻す
    （利用者の指摘、2026-11-27: 先の工程に行ったら壊れてても修正に戻らない）"""

    def test_lines_buried_by_a_later_mend_are_restored_at_phase_exit(self):
        class Bury(Painter):
            def redraw(self, words, seed, image, mask, strength=0.45, clean=False, **kw):
                out = super().redraw(words, seed, image, mask, strength=strength, clean=clean, **kw)
                from PIL import ImageDraw
                ImageDraw.Draw(out).rectangle([0, 40, out.width, 47], fill=(235, 235, 235))   # 帯の線を薄くして埋める
                return out

        painter = Bury()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(pt, "shadows", lambda *_a, **_k: {"readable": True, "shade_minus_lit": 5}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
            line_row = next(r for r in got["phases"] if r["phase"] == "線画")
            from PIL import Image
            line_img = Image.open(line_row["image"]).convert("RGB")
            mend_files = [m["image"] for r in got["history"] if r["phase"] == "影 2 段"
                          for m in r.get("mends", []) if m.get("image")]
            mend_imgs = [Image.open(p).convert("RGB") for p in mend_files]
        shadow_mends = [m for r in got["history"] if r["phase"] == "影 2 段" for m in r.get("mends", [])]
        self.assertTrue(shadow_mends)   # 影の直し（線を埋める描き直し）が走った
        import numpy as np
        dark_l = pt.luminance(line_img) < 80
        band = np.zeros_like(dark_l)
        band[40:48, :] = True
        ref = dark_l & band
        self.assertGreater(int(ref.sum()), 0)   # 帯の中に清書の線がある

        def missing_of(im):
            present = pt._dilate(pt.luminance(im) < 80, 1)
            return float((ref & ~present).sum()) / float(ref.sum())

        self.assertTrue(mend_imgs)
        buried = max(missing_of(im) for im in mend_imgs)
        self.assertGreater(buried, phases.LINE_LOSS_MOST,
                           "直しの絵で線が埋もれていない（このテストの前提が崩れている）")
        missing = missing_of(got["image"])
        self.assertLessEqual(missing, phases.LINE_LOSS_MOST,
                             f"影の出口で帯の線の {missing:.0%} が埋もれたまま")


class CompareSeverityTest(unittest.TestCase):
    """土台と比べる重さ: ゴミの個数で完成が決まらないこと"""

    def test_dust_count_does_not_dominate(self):
        """ゴミの文は個数を数えず 1 件。線の欠片まで数える検品なので、個数で比べると
        絵の良し悪しではなくゴミの数だけで「良くなっていない」が決まってしまう"""
        self.assertEqual(phases._compare_severity(["ゴミがある（758 個）"]), 1.0)
        self.assertEqual(phases._compare_severity(["ゴミがある（758 個）", "描かれていない: waving"]),
                         phases._compare_severity(["描かれていない: waving"]) + 1.0)

    def test_other_counts_still_count(self):
        """離れた物の数のような、増えると悪くなる数は今までどおり数える"""
        self.assertGreater(phases._compare_severity(["体から離れている物がある（124 個）"]),
                           phases._compare_severity(["体から離れている物がある（2 個）"]))
        self.assertEqual(phases._compare_severity(["描かれていない: waving"]),
                         phases._severity(["描かれていない: waving"]))


class EraseFillTest(unittest.TestCase):
    """消すは塗りつぶしではない: 周りの色合いを流し込む"""

    def test_fill_matches_local_tone_not_corner_color(self):
        """横の階調（左 100 → 右 200）の真ん中のゴミを消すと、消した所は
        その場所の色合い（約 150）になる。四隅の色（紙の色）で平らに塗らない"""
        import numpy as np
        from PIL import Image
        w, h = 64, 64
        grad = np.tile(np.linspace(100, 200, w, dtype=np.uint8), (h, 1))
        im = Image.fromarray(np.stack([grad, grad, grad], axis=2))
        arr = np.asarray(im).copy()
        arr[30:34, 30:34] = 0   # ゴミ
        im = Image.fromarray(arr)
        mask = Image.new("L", (w, h), 0)
        ma = np.asarray(mask).copy()
        ma[30:34, 30:34] = 255
        mask = Image.fromarray(ma)
        out = pt.erase_fill(im, mask)
        center = out.getpixel((32, 32))[0]
        self.assertLess(abs(center - 150), 20, f"消した所がその場所の色合いになっていない: {center}")
        self.assertEqual(out.getpixel((5, 5)), im.getpixel((5, 5)))   # 囲みの外は変えない

    def test_fill_does_not_blend_colors(self):
        """左が赤・右が青の境目を消しても、紫（混ざった色）はできない。一番近い外の色を
        そのまま写すから。平均で広げると色が混ざって滲む（利用者の指摘: 滲ませてる・下手な消しゴム）"""
        import numpy as np
        from PIL import Image
        w, h = 64, 64
        arr = np.zeros((h, w, 3), np.uint8)
        arr[:, :32] = (200, 30, 30)
        arr[:, 32:] = (30, 30, 200)
        im = Image.fromarray(arr)
        ma = np.zeros((h, w), np.uint8)
        ma[28:36, 28:36] = 255   # 境目にかかる囲み
        out = np.asarray(pt.erase_fill(im, Image.fromarray(ma)))
        hole = out[28:36, 28:36].reshape(-1, 3)
        blended = ((hole[:, 0] > 80) & (hole[:, 2] > 80)).sum()
        self.assertEqual(int(blended), 0, "消した所に、混ざった色（紫）ができている")
        self.assertTrue((hole[:, 0] == 200).any() and (hole[:, 2] == 200).any())   # 両側の色が写っている

    def test_layer_files_are_saved(self):
        """レイヤーはファイルにも残る（線画レイヤーには線だけ、下塗りレイヤーには色だけ）。
        あとから見て、線画が残っていることを確かめられるようにする"""
        painter = LayerBasePainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              checks=hand_only_checks(bad_times=0))
            from PIL import Image
            line = Image.open(Path(d) / "k" / "layer-05-線画.png").convert("RGB")
            color = Image.open(Path(d) / "k" / "layer-05-下塗り.png").convert("RGB")
        self.assertLess(line.getpixel((32, 48))[0], 60)      # 線画レイヤーの線は黒いまま
        self.assertGreater(color.getpixel((32, 48))[0], 180)   # 下塗りレイヤーに線は無い（色だけ）


class LineStagesTest(unittest.TestCase):
    """線の段階: ラフ（鉛筆でさっと）→線画（ペンで描く）→清書（強弱とゴミ消し）"""

    def test_rough_words_pen_words_and_pen_pass(self):
        class P(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                return image.copy()
        painter = P()
        C = hand_only_checks(bad_times=0)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
        rows = {r["phase"]: r for r in got["phases"]}
        # サムネイルは頼みの言葉そのままで土台を描き、ラフはその絵から抜く（頼んでいない言葉を足さない）
        self.assertEqual(rows["サムネイル"]["words"], ["1girl, red scarf"])
        rough_words = " ".join(rows["アタリ"]["words"])
        self.assertIn("pencil", rough_words)           # ラフ（アタリ）は鉛筆でさっと描く
        self.assertNotIn("clean lines", rough_words)   # ラフは、きれいに清書された線画ではない
        line_words = " ".join(rows["線画"]["words"])
        self.assertIn("inked", line_words)             # 線画はペンで描く
        # ペンなぞりは描き重ね（refine）でする。下描きの描き重ねと合わせて 2 回
        self.assertEqual(sum(1 for x in painter.log if x[0] == "refine" and x[2] == phases.REFINE), 2, painter.log)

    def test_pen_pass_must_not_fade_the_lines(self):
        """ペンなぞりの描き重ねが線を薄くしたら、土台の線の暗さを乗せて戻す。
        色と明るさの見張り（暗い所の下位 5%）は細い線の薄れを見逃す
        （検証 45696035067 で、線画の濃い線が 3.2% → 0.5% に落ちても異常なしだった）"""
        import numpy as np
        from PIL import Image

        class FadingPainter(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                if "inked" not in prompt:
                    return image.copy()
                a = np.asarray(image.convert("RGB")).astype(int)
                lum = a.mean(axis=2)
                a[lum < 150] = (190, 190, 190)   # 線だけを薄い灰色にする（模型の描き重ねで線が霞む崩れ）
                return Image.fromarray(a.astype("uint8"))

        painter = FadingPainter()
        C = hand_only_checks(bad_times=0)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
            rows = {r["phase"]: r for r in got["phases"]}
            # アタリの描き重ねは絵を変えない偽物なので、線の土台はサムネイルの絵で比べる。
            # ラフは鉛筆の薄さ（明るさ 100 前後）なので、線の画素は明るさ 150 未満で数える
            rough_lines = float((pt.luminance(Image.open(rows["サムネイル"]["image"])) < 150).mean())
            ink_lines = pt.ink_share(Image.open(rows["線画"]["image"]))
        self.assertGreater(rough_lines, 0.02)
        self.assertGreaterEqual(ink_lines, rough_lines * 0.6)   # 霞んだ線も、ペンの濃さ（明るさ 80 未満）に戻っている


class PhaseBrushTest(unittest.TestCase):
    """工程ごとの道具: 指定が無ければラフ=鉛筆、線画=ペン、清書=Gペン。
    頼みに画材の指定（鉛筆の画像など）があれば、その画材が清書の既定（Gペン）にも勝つ
    （利用者の指示、2026-11-27 22:13: 見ただけでどの工程か分かるようにする）"""

    class BrushPainter(Painter):
        """模型に渡した言葉を全部記録する画家。描き重ねは絵を変えない写しを返す"""
        def __init__(self):
            super().__init__()
            self.prompts = []

        def paint(self, prompt, seed, on_step=None, **kw):
            self.prompts.append(prompt)
            return super().paint(prompt, seed, on_step=on_step, **kw)

        def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
            self.prompts.append(prompt)
            self.log.append(("refine", seed, strength))
            return image.copy()

    def run_draw(self, prompt, painter=None):
        painter = painter or self.BrushPainter()
        C = hand_only_checks(bad_times=0)
        calls = {"weight": 0}
        orig = pt.weight_lines

        def spy(im, r=None):
            calls["weight"] += 1
            return orig(im, r=r)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(pt, "weight_lines", spy):
            got = phases.draw(painter, prompt, 5, (64, 96), Path(d) / "k", checks=C)
        return got, painter, calls

    def test_request_medium_parsing(self):
        self.assertEqual(phases.request_medium("鉛筆の画像"), "pencil")
        self.assertEqual(phases.request_medium("1girl, pencil sketch"), "pencil")
        self.assertEqual(phases.request_medium("Gペンで描いた線画"), "gpen")   # 「ペン」より先に見る
        self.assertEqual(phases.request_medium("水彩の風景"), "watercolor")
        self.assertEqual(phases.request_medium("ペン画"), "pen")
        self.assertIsNone(phases.request_medium("1girl, red scarf"))
        self.assertIsNone(phases.request_medium("open the door"))   # 'pen' の部分一致で拾わない

    def test_default_brushes_per_phase(self):
        got, painter, calls = self.run_draw("1girl, red scarf")
        rows = {r["phase"]: r for r in got["phases"]}
        self.assertEqual(rows["サムネイル"]["numbers"].get("brush"), "pencil")   # ラフは鉛筆
        self.assertEqual(rows["アタリ"]["numbers"].get("brush"), "pencil")       # アタリもラフの続き（鉛筆）
        self.assertEqual(rows["線画"]["numbers"].get("brush"), "pen")            # 線画はペンでなぞる
        self.assertEqual(rows["線画"]["numbers"].get("clean_brush"), "gpen")     # 清書は Gペン
        self.assertGreaterEqual(calls["weight"], 1)   # 清書（Gペン）は線の強弱を付ける

    def test_line_finish_uses_gpen_words(self):
        """線の仕上げは清書の続き。模型への言葉も Gペンで、記録の画材も gpen"""
        painter = self.BrushPainter()
        C, _seen = checks(False)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf, 線画", 5, (64, 96), Path(d) / "k", checks=C, confirm=None)
        rows = {r["phase"]: r for r in got["phases"]}
        words = " ".join(rows["線の仕上げ"]["words"])
        self.assertIn("G-pen", words)
        self.assertEqual(rows["線の仕上げ"]["numbers"].get("brush"), "gpen")

    def test_pencil_request_overrides_gpen_at_clean(self):
        """鉛筆の指定がある頼みでは、清書も鉛筆のまま。Gペンの強弱付けは掛けない"""
        got, painter, calls = self.run_draw("1girl, red scarf, 鉛筆の絵")
        rows = {r["phase"]: r for r in got["phases"]}
        self.assertEqual(rows["サムネイル"]["numbers"].get("brush"), "pencil")
        self.assertEqual(rows["線画"]["numbers"].get("brush"), "pencil")
        self.assertEqual(rows["線画"]["numbers"].get("clean_brush"), "pencil")   # 清書が Gペンに化けない
        self.assertEqual(calls["weight"], 0)   # 鉛筆の線に、Gペンの線の強弱付けをしない
        self.assertFalse(any("G-pen" in p for p in painter.prompts), painter.prompts)


class CarriedFlawGuardTest(unittest.TestCase):
    """持ち越した崩れは、その項目を実際に測った工程の確かめでだけ外す。
    項目名だけが工程の並びにあって検品が測っていない場合は、消えたことにしない"""

    def test_uncovered_phase_does_not_clear_carried_flaw(self):
        from atelier.ai import phase_plan
        patched = [list(x) for x in phase_plan.PHASE_ITEMS]
        patched[4] = patched[4] + ["位置ずれ"]   # 下塗りの並びに位置ずれを足す（が、下塗りの検品は離れた物を測らない）
        painter = DetachedPainter()   # 離れた物がずっと残る絵（アタリで直しても消えない）
        C, _seen = checks(False)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(phase_plan, "PHASE_ITEMS", patched):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
        self.assertFalse(got["complete"])
        self.assertTrue(any("離れている" in f for f in got["left"]), got["left"])


class BaseThumbTest(unittest.TestCase):
    """土台の絵は通常の見せ方では出さない。デバッグモードで薄く重ねて見るためだけに、
    専用の渡し口（on_base）で窓へ渡す。preview（見せる絵の通り道）には流さないし、
    工程の絵にも混ぜない。前は印を付けて preview に流していて、受け側が見落とすと
    土台がそのまま画面に出た（0.1.28）"""

    def test_base_is_handed_to_the_window_with_its_tag_only(self):
        shown, bases = [], []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            phases.draw(Painter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                        checks=hand_only_checks(bad_times=0), on_preview=shown.append, on_base=bases.append)
        self.assertEqual(len(bases), 1, [im.size for im in bases])   # 窓へは専用の渡し口で 1 回だけ
        self.assertEqual(bases[0].size, (64, 96))
        self.assertNotIn(phases.PHASE_TAG, bases[0].info)   # 工程の絵として扱わせない
        # 土台そのものが preview に出ていないことは、土台だけ別の色で描く
        # BrushUpBaseTest.test_base_image_is_never_shown が画素で確かめている
        self.assertFalse(any(phases.BASE_TAG in getattr(im, "info", {}) for im in shown), "土台が印付きで preview に出た")


class FlatMendTest(unittest.TestCase):
    """直しの描き直しが囲みの中を平らに塗りつぶしたら、採用しない。
    形を無くせば検品の崩れは消えるが、それは直したのではない（利用者の指摘）"""

    def test_flat_redraw_is_not_adopted(self):
        from PIL import Image

        class FlatPainter(Painter):
            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.log.append(("redraw", seed, kw.get("strength")))
                return Image.new("RGB", image.size, (200, 200, 200))   # 平らな塗りつぶしを返す

        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(FlatPainter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              say=said.append, checks=hand_only_checks(bad_times=10 ** 6))
        self.assertTrue(any("塗りつぶしたので、採用しません" in s for s in said), said[-8:])
        self.assertFalse(got["complete"])
        self.assertTrue(any("手" in l for l in got["left"]), got["left"])   # 塗りつぶして「直った」ことにはならない


class WeightLinesScopeTest(unittest.TestCase):
    """線の強弱の検品を通る線（正常な線画）は、太らせる加工を掛けない。
    太らせるのは「線の強弱が無い」と検品で出たときだけの直し。清書（clean_lines）は
    検品を見ずに毎回掛けていたので、検品を通る線まで狙いの太さ（2r+3）に
    膨らまされ、正常な線画が太くなって壊れた（利用者の指摘、2026-11-27）"""

    def _passing_lines(self):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (64, 96), "white")
        dr = ImageDraw.Draw(im)
        dr.ellipse([24, 5, 40, 24], outline="black", width=2)      # 頭の輪郭
        dr.rectangle([22, 24, 42, 91], outline="black", width=2)   # 体の輪郭
        return im

    def test_passing_lines_are_left_alone(self):
        import numpy as np
        im = self._passing_lines()
        self.assertGreaterEqual(pt.lines(im)["weight"], pt.LINE_WEIGHT_LEAST)   # 検品を通る線
        out, hit = pt.weight_lines(im)
        self.assertEqual(hit, 0)
        self.assertTrue((np.asarray(im) == np.asarray(out)).all())   # 1 画素も変えない

    def test_weak_lines_still_get_strength(self):
        sk = sketch((128, 192))
        self.assertLess(pt.lines(sk)["weight"], pt.LINE_WEIGHT_LEAST)   # 検品で「線の強弱が無い」側
        out, hit = pt.weight_lines(sk)
        self.assertGreater(hit, 0)
        self.assertGreater(pt.lines(out)["weight"], pt.lines(sk)["weight"])


    def test_speckled_rough_is_not_turned_into_dashes(self):
        """紙の目やハッチングの粒が散った鉛筆のラフに線の強弱を掛けても、粒を暗くして
        太らせない。粒を太らせると線が破線に崩れ、次の工程がその破線をなぞって固まる
        （検証 46030668432 のアタリでは、細かい暗い塊が 798 から 2476 に増えていた）"""
        import numpy as np
        from PIL import Image
        from scipy import ndimage
        sk = np.asarray(sketch((256, 384))).copy()
        rng = np.random.default_rng(0)
        lum = sk.mean(axis=2)
        # 人物の内外に、鉛筆の粒のような 1 画素の灰色の点を散らす（それだけでは線の暗さに届かない）
        spots = (rng.random(lum.shape) < 0.08) & (lum > 200)
        sk[spots] = 150
        im = Image.fromarray(sk)

        def small_dark(img):
            d = np.asarray(img.convert("L")) < 100
            lab, n = ndimage.label(d, np.ones((3, 3), bool))
            return n

        out, _ = pt.weight_lines(im)
        self.assertLessEqual(small_dark(out), small_dark(im))

class WeightLinesWidthEstimateTest(unittest.TestCase):
    """線の強弱（太らせる）を何度重ねても、線が際限なく太くならない。
    太さの見積もりが浅いと、処理のたびに太り続けて極太になる（利用者の指摘）"""

    def test_repeated_weight_lines_converge(self):
        import numpy as np
        im = sketch((64, 96))   # 線の強弱が無い側の線（weight < LINE_WEIGHT_LEAST）。太らせる対象はこちら

        def ink(img):
            return int((np.asarray(img.convert("L")) < 100).sum())

        base = ink(im)
        out1, _ = pt.weight_lines(im)
        out2, _ = pt.weight_lines(out1)
        out3, _ = pt.weight_lines(out2)
        self.assertGreater(ink(out1), base)                 # 強弱は付く
        self.assertLessEqual(ink(out3), ink(out1) * 1.3)    # 重ねても太り続けない


class MendResponsibilityTest(unittest.TestCase):
    """直しが別の所を壊したら、それは新しい仕事ではなく、その直しの失敗。
    直す前の絵に戻し、壊した項目の崩れは残りに出さない（利用者の指摘:
    塗りつぶして見えなくすることで修正箇所を減らそうとするな。そもそも壊すな）"""

    def test_mend_that_breaks_another_item_is_reverted(self):
        from PIL import Image, ImageDraw

        class FragmentPainter(Painter):
            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.log.append(("redraw", seed, kw.get("strength")))
                self.masks = getattr(self, "masks", []) + [mask]
                fixed = Image.new("RGB", image.size, "white")
                ImageDraw.Draw(fixed).rectangle([22, 16, 30, 24], fill=(200, 30, 30))
                return fixed   # 手の囲みの中に、体から離れた欠片ができる絵を返す

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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                return dict(HAND) if seen["hands"] >= 2 else dict(CLEAN_HAND)   # アタリの確かめ以降ずっと手が崩れている（直しは別の所を壊すので直らない）

        said = []
        with TemporaryDirectory() as d:
            got = phases.draw(FragmentPainter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append, checks=C)
        self.assertTrue(any("が壊れたので、直す前の絵に戻します" in s for s in said), said[-8:])   # 責任の判定で戻した
        self.assertFalse(any("位置ずれ" in l for l in got["left"]), got["left"])   # 壊した分は、新しい修正箇所として残らない
        self.assertTrue(any("手" in l for l in got["left"]), got["left"])          # 直せなかった手は、正直に残る


class AtariBestOfTest(unittest.TestCase):
    """最初のアタリは 2 枚描いて、崩れの少ない方を採る。悪いアタリを直しで
    何度もいじるより、最初から良いアタリを描く（利用者の指摘）"""

    def test_better_atari_candidate_is_picked(self):
        from PIL import ImageDraw

        class TwoDrafts(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.refine_seeds = getattr(self, "refine_seeds", []) + [seed]
                out = image.copy()
                if seed == 5:   # 1 枚目のアタリだけ、手の所に濃い印（崩れ）を付ける
                    ImageDraw.Draw(out).rectangle([13, 13, 20, 20], fill=(0, 0, 0))
                return out

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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                # 呼び出し順: 1=土台の計測, 2=アタリ候補 1 の計測（崩れている）, 3=候補 2 の計測（崩れていない）
                return dict(HAND) if seen["hands"] == 2 else dict(CLEAN_HAND)

        painter = TwoDrafts()
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append, checks=C)
        self.assertIn(5, painter.refine_seeds)      # 1 枚目
        self.assertIn(505, painter.refine_seeds)    # 2 枚目（種 +500）
        self.assertTrue(any("アタリを 2 枚描いて" in s for s in said), said[-6:])   # 崩れの少ない方が選ばれた


class AtariScreenCostTest(unittest.TestCase):
    """アタリの候補選びに、一番重い体の検品（部位分け・人数の模型）まで回さない。
    候補の順位付けはアタリの物差し（頼んだ物・手足顔・ゴミ）で足りる。採った 1 枚は
    直後の工程の確かめ（m_atari）が全部測る。候補ごとに検品一式を回すと、候補 4 枚で
    検品一式 4 回分が乗り、アタリが全体の大半を食う（利用者の指摘、2026-11-27）。
    あわせて、体の検品には頼んだ物の検品が読んだタグを使い回す（同じ絵のタグを
    2 度読まない）"""

    def _run(self, body_bad):
        from PIL import ImageDraw

        class TwoDrafts(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.refine_seeds = getattr(self, "refine_seeds", []) + [seed]
                out = image.copy()
                if seed == 5:   # 1 枚目のアタリだけ印を付ける（AtariBestOfTest と同じ絵）
                    ImageDraw.Draw(out).rectangle([13, 13, 20, 20], fill=(0, 0, 0))
                return out

        seen = {"hands": 0, "body_tags": []}

        class C:
            @staticmethod
            def request(image, prompt):
                return {"readable": True, "missing": [], "extra": [], "people": [], "body": [],
                        "read": {"1girl": 0.9}}

            @staticmethod
            def body(image, prompt, tags=None):
                seen["body_tags"].append(tags)
                return {"readable": True, "bad": list(body_bad), "avoid": []}

            @staticmethod
            def points(image):
                w, h = image.size
                return {"readable": True, "points": {"left_eye": (w * .45, h * .15), "right_eye": (w * .55, h * .15),
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                # 呼び出し順: 1=土台の計測, 2=アタリ候補 1 の計測（崩れている）, 3=候補 2 の計測（崩れていない）
                return dict(HAND) if seen["hands"] == 2 else dict(CLEAN_HAND)

        painter = TwoDrafts()
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", say=said.append, checks=C)
        return painter, said, seen

    def test_candidates_are_screened_without_body(self):
        # 体の検品は全候補に重い崩れ（重さ 10）を返す。候補選びが体の検品まで
        # 使っていたら、良い候補（手の崩れ無し）でも重さ 10 になり、そこで止まらず
        # 4 枚まで描き、知らせの重さも 10 になる。ふるいに掛ければ候補 2 の重さは 0 で、
        # 2 枚で止まる
        painter, said, _seen = self._run(["体の崩れ（9）"])
        self.assertIn(5, painter.refine_seeds)
        self.assertIn(505, painter.refine_seeds)
        self.assertTrue(any("アタリを 2 枚描いて" in s and "崩れの重さ 0" in s for s in said), said[-6:])

    def test_body_reuses_request_tags(self):
        # 体の検品は、頼んだ物の検品が読んだタグ（read）を受け取って使い回す。
        # 受け取らずに読み直すと、同じ絵でタガーの推論が 2 回走る
        _painter, _said, seen = self._run([])
        self.assertTrue(any(t == {"1girl": 0.9} for t in seen["body_tags"]), seen["body_tags"])


class FinishGuardsTest(unittest.TestCase):
    """仕上げ系の見張り: 足すはずの描き重ねがゴミを散らかしたら採用しない。
    下塗りの色が粒だらけなら、面の色に寄せて平らにする"""

    def test_new_specks_counts_only_new_small_dark_blobs(self):
        from PIL import Image, ImageDraw
        before = Image.new("RGB", (64, 64), "white")
        after = before.copy()
        d = ImageDraw.Draw(after)
        for x in range(4, 60, 8):
            d.rectangle((x, 30, x + 2, 32), fill="black")   # 新しい点が 7 個
        self.assertEqual(pt.new_specks(before, after), 7)
        self.assertEqual(pt.new_specks(before, before), 0)

    def test_new_bumps_counts_blotches_on_smooth_areas(self):
        from PIL import Image, ImageDraw
        before = Image.new("RGB", (64, 64), (210, 180, 160))   # 滑らかな肌色
        after = before.copy()
        d = ImageDraw.Draw(after)
        for x in range(6, 60, 10):
            d.ellipse((x, 30, x + 4, 34), fill=(150, 60, 50))   # でき物のような塊が 6 個
        self.assertEqual(pt.new_bumps(before, after), 6)
        self.assertEqual(pt.new_bumps(before, before), 0)

    def test_flatten_base_removes_grain_keeps_faces(self):
        import numpy as np
        from PIL import Image
        rng = np.random.default_rng(3)
        arr = np.zeros((64, 64, 3), np.uint8)
        arr[:, :32] = (200, 80, 80)
        arr[:, 32:] = (80, 80, 200)
        noisy = arr.copy()
        noisy[rng.random((64, 64)) < 0.2] = (30, 30, 30)   # 粒（ブツブツ）
        im = Image.fromarray(noisy)
        self.assertGreater(pt.grain(im), 0.02)
        flat = pt.flatten_base(im)
        self.assertLess(pt.grain(flat), pt.grain(im) * 0.3)
        self.assertEqual(flat.getpixel((8, 8)), (200, 80, 80))   # 面の色は残る
        self.assertEqual(flat.getpixel((56, 8)), (80, 80, 200))

    def test_detail_refine_that_scatters_specks_is_not_adopted(self):
        """ディテールの描き重ねがゴミの線を散らかしたら、その結果は採用せず元の絵で進む"""
        from PIL import Image, ImageDraw

        class SpecklePainter(Painter):
            speckled = 0

            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                if "detailed texture" not in prompt:
                    return image.copy()
                self.speckled += 1
                out = image.copy()
                d = ImageDraw.Draw(out)
                for x in range(4, 60, 5):
                    for y in range(4, 92, 7):
                        d.rectangle((x, y, x + 2, y + 2), fill="black")
                return out

        painter = SpecklePainter()
        C, _seen = checks(always_bad=False)
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C, say=said.append)
            keep = Path(d) / "k"

            def phase_img(name):
                hits = sorted(keep.glob(f"*-{name}.png"))
                return Image.open(hits[-1]).convert("RGB") if hits else None

            before = phase_img("影 2 段")   # ディテールの直前の、描く工程の絵
            after = phase_img("ディテール")
        self.assertGreater(painter.speckled, 0)   # ディテールの描き重ね自体は呼ばれた
        self.assertTrue(any("元の絵のまま" in s or "前の絵を使います" in s for s in said), said)   # 散らかした結果は採用されず、元の絵で進んだ
        if after is not None and before is not None:
            self.assertEqual(pt.new_specks(before, after), 0)   # ゴミは増えていない


class DustPrecisionTest(unittest.TestCase):
    """ゴミは、主役から離れた所に孤立した小さな塊だけ。主役の中や線の近くにある小さな塊
    （目・ボタン・線の欠片などのディテール）はゴミにしない（利用者の指摘: 必要な線もゴミとして消される）"""

    def _img(self):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (200, 200), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([60, 40, 140, 160], outline=(0, 0, 0), width=3)   # 主役の輪郭（大きい成分）
        d.ellipse([97, 82, 103, 88], fill=(0, 0, 0))                 # 目（輪郭の中の小さな塊）
        d.rectangle([10, 10, 12, 12], fill=(0, 0, 0))                # 紙の隅のゴミ（孤立）
        return im

    def test_detail_inside_subject_is_not_dust(self):
        got = pt.dust(self._img())
        self.assertTrue(got["readable"])
        self.assertEqual(got["count"], 1, got)   # 隅のゴミだけ。目は数えない
        import numpy as np
        a = np.asarray(pt.dust_mask(self._img()))
        self.assertEqual(int(a[85, 100] > 0), 0)   # 目の所は消す範囲に入っていない
        self.assertTrue(a[11, 11] > 0)             # 隅のゴミは入っている


class DustOnlyAtCleanStageTest(unittest.TestCase):
    """ちゃんとしたゴミ取りは清書（線画）だけ。色の工程に入ってから出たゴミは、
    仕上げで消さない（都度入るゴミ消しが細い線やディテールを壊す、という利用者の規則）"""

    def test_dust_appearing_after_lines_is_not_erased_at_finish(self):
        def speckled(base):
            from PIL import ImageDraw
            im = base.copy()
            ImageDraw.Draw(im).rectangle([3, 3, 5, 5], fill=(30, 30, 30))
            return im

        class P(Painter):
            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                if kw.get("base") is not None:
                    # 線の工程（モノクロの言葉）は土台のまま。色の工程で初めてゴミが入る
                    return kw["base"].copy() if "monochrome" in prompt else speckled(kw["base"])
                return sketch(kw.get("size") or (64, 96)) if "monochrome" in prompt else figure(kw.get("size") or (64, 96))
        C = hand_only_checks(bad_times=0)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(P(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
        self.assertEqual(pt.dust(got["image"])["count"], 1)   # 仕上げで消されていない
        late = [m for r in got["history"] if r["phase"] in ("下塗り", "光源", "影 2 段", "光・艶・目のハイライト", "仕上げ")
                for m in r.get("mends", []) if m.get("item") == "ゴミ"]
        self.assertEqual(late, [])


class UnreadableCheckTest(unittest.TestCase):
    """検品の部品が無い・検品自体が例外で落ちる場合、その検品は絵を直しても直らない。
    絵を壊す直しを繰り返さず、未検品として理由つきで残す（ただし完成にはしない）"""

    def _run(self, checks_cls):
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            return phases.draw(Painter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=checks_cls)

    def test_missing_check_component_is_not_mended(self):
        base, _ = checks(always_bad=False)

        class NoHands:
            request = staticmethod(base.request)
            body = staticmethod(base.body)
            pose = staticmethod(base.pose)
            points = staticmethod(base.points)
            # hands が無い = 手の検品の部品が無い

        got = self._run(NoHands)
        self.assertFalse(got["complete"])   # 読めていない検品を、通ったことにしない
        unread = [m for r in got["history"] for m in r.get("mends", []) if "検品できませんでした" in m["found"]]
        self.assertEqual(unread, [])   # 部品の無い検品のために絵を描き直さない
        self.assertTrue(any("検品 hands がありません" in x for x in got["left"]))

    def test_throwing_check_is_mended_once_then_left(self):
        base, _ = checks(always_bad=False)

        class BoomHands:
            request = staticmethod(base.request)
            body = staticmethod(base.body)
            pose = staticmethod(base.pose)
            points = staticmethod(base.points)

            @staticmethod
            def hands(image, prompt):
                raise RuntimeError("boom")

        got = self._run(BoomHands)
        self.assertFalse(got["complete"])
        unread = [m for r in got["history"] for m in r.get("mends", []) if "検品できませんでした" in m["found"]]
        self.assertEqual(len(unread), 1)   # 直しは 1 度だけ試し、直しても読めなければ諦めて残す
        self.assertTrue(any("RuntimeError" in x for x in got["left"]))


class PhantomRegionTest(unittest.TestCase):
    """検品が、主役の絵に全く重ならない場所を「崩れた手」と読んだら、その枠は直さない。
    背景の何も無い所を囲んで描き直すと、直しがそこに手を描いてしまう（手足の量産）"""

    def test_bad_region_outside_the_subject_is_not_mended(self):
        base = hand_only_checks(bad_times=0)

        class PhantomHands:
            request = staticmethod(base.request)
            body = staticmethod(base.body)
            pose = staticmethod(base.pose)
            points = staticmethod(base.points)

            @staticmethod
            def hands(image, prompt):
                # 絵の隅の白い紙の上 (0,0)-(8,8) を「崩れた手」と言い続ける検品
                return {"readable": True, "bad": ["手 1: 指が 6 本"],
                        "hands": [{"box": [0, 0, 8, 8], "bad": ["指が 6 本"], "seen": True}],
                        "feet": [], "faces": []}

        painter = Painter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=PhantomHands)
        self.assertFalse(got["complete"])   # 直していない崩れを、直ったことにしない
        self.assertTrue(any("指が 6 本" in f for f in got["left"]))
        for m in getattr(painter, "masks", []):
            self.assertEqual(m.getpixel((4, 4)), 0)   # 隅の白い所を囲んだ直しは一度も無い


class WeightLinesConvergeTest(unittest.TestCase):
    """太らせる加工は、繰り返しても太り続けない。直しのたびに半径を大きくして
    太らせ直していた行程が、正常な線画を 10 倍ぐらいの太さにしていた（利用者の指摘）。
    Gペンのような強弱付け自体は仕事として残す"""

    def test_repeated_weight_lines_converges(self):
        import numpy as np
        img = sketch((128, 192))

        def dark(im):
            return int((np.asarray(im.convert("L")) < 80).sum())

        once, _ = pt.weight_lines(img)
        again = once
        for _ in range(3):
            again, _ = pt.weight_lines(again)
        self.assertGreater(dark(once), dark(img))              # 1 回目は太る（強弱付けの仕事）
        self.assertLessEqual(dark(again), dark(once) * 1.15)   # 繰り返しても太り続けない


class HeadsFramingTest(unittest.TestCase):
    """等身は全身が写っているときだけ測る。足首の点が無い構図（上半身だけなど）では、
    人物の高さそのものが写っていないので比に意味が無く、直しでも直らない。
    検証 45839398250 では upper body shot の絵に等身 15.8 が出続け、直しを繰り返した"""

    def _checks(self, ankles):
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
                pts = {"left_eye": (w * .45, h * .15), "right_eye": (w * .55, h * .15),
                       "nose": (w * .5, h * .17), "left_ear": (w * .4, h * .15),
                       "left_shoulder": (w * .4, h * .19), "right_shoulder": (w * .6, h * .19),
                       "left_hip": (w * .42, h * .5), "right_hip": (w * .58, h * .5),
                       "left_knee": (w * .43, h * .75), "right_knee": (w * .57, h * .75)}
                if ankles:
                    pts["left_ankle"] = (w * .43, h * .97)
                    pts["right_ankle"] = (w * .57, h * .97)
                return {"readable": True, "points": pts}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                return dict(CLEAN_HAND)
        return C

    def _found_text(self, ankles):
        painter = Painter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              say=lambda _s: None, checks=self._checks(ankles))
        texts = [f for r in got["history"] for f in (r.get("found") or [])]
        texts += [f for r in got["history"] for f in (r.get("after") or [])]
        texts += [str(x) for x in got["left"]]
        return "\n".join(str(t) for t in texts)

    def test_heads_not_measured_without_ankles(self):
        self.assertNotIn("等身", self._found_text(ankles=False))

    def test_heads_measured_with_ankles(self):
        self.assertIn("等身が外れている", self._found_text(ankles=True))


class NoProgressMendTest(unittest.TestCase):
    """直しても崩れの重さが下がらない項目は、1 つの工程で手を替え尽くしたら、
    後の工程で同じ直しを繰り返さない。検証 45839398250 では、手の形・位置と等身が
    強さを変えても同じ値のまま、線画だけで直し 37 回・総工程 123 まで膨らんだ"""

    def test_unmoving_flaw_is_not_remended_in_later_phases(self):
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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                return dict(HAND)   # 何度直しても同じ崩れを返し続ける

        painter = Painter()
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                              say=said.append, checks=C)
        self.assertEqual(len(got["phases"]), N)                    # 工程は最後まで進む
        self.assertLessEqual(len(painter.masks), phases.MENDS)     # 直しは最初の工程の分だけ。後の工程で繰り返さない
        self.assertTrue(any("手" in k for k in got["left"]))        # 崩れは残った崩れとして正直に残る
        self.assertTrue(any("変わりませんでした" in s for s in said))


class PhaseScopeTest(unittest.TestCase):
    """工程ごとに、直しの対象にする項目はその工程の仕事だけ。線画は状態の把握のために
    アタリの検品一式でも測るが、構図の項目（位置ずれ・背景・画角・等身・骨組みなど）も
    パーツ（手・足・顔・頼んだ物）も、線画で直しの対象にしない。線画はただのスタート
    ラインで、ここで完成にしようとしない（利用者の指摘）。構図はアタリで、パーツは
    アタリと仕上げで直す。線画で構図を描き直すと清書した線が壊れるし、直しが膨らんで
    終わらない（検証 #27・#28）"""

    def run_draw(self, painter, prompt, checks):
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            return phases.draw(painter, prompt, 5, (64, 96), Path(d) / "k", say=lambda _s: None, checks=checks)

    @staticmethod
    def mend_phases(got, item):
        return [r["phase"] for r in got["history"] for m in r.get("mends", []) if m.get("item") == item]

    def test_parts_are_mended_at_finish_not_at_line_phase(self):
        """パーツ（手）は線画では直さない。線画はスタートラインで、ここで完成にしようと
        しない（利用者の指摘）。手の直しは仕上げでやる"""
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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                return dict(HAND) if seen["hands"] >= 3 else dict(CLEAN_HAND)   # 線画の確かめから手が崩れる

        got = self.run_draw(Painter(), "1girl, red scarf", C)
        self.assertNotIn("線画", self.mend_phases(got, "手"))   # 線画では直さない
        self.assertIn("仕上げ", self.mend_phases(got, "手"))     # 仕上げで直す

    def test_detached_is_mended_at_atari_not_at_line_phase(self):
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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                return dict(HAND) if seen["hands"] >= 3 else dict(CLEAN_HAND)   # 線画の確かめから手が崩れる

        got = self.run_draw(DetachedPainter(), "1girl, red scarf", C)
        self.assertEqual(len(got["phases"]), N)
        self.assertTrue(self.mend_phases(got, "位置ずれ"))                     # アタリでは直す
        self.assertNotIn("線画", self.mend_phases(got, "位置ずれ"))             # 線画では構図を直さない
        self.assertNotIn("線画", self.mend_phases(got, "手"))                   # パーツも線画では直さない
        self.assertIn("仕上げ", self.mend_phases(got, "手"))                     # パーツの直しは仕上げでやる


class LineStageRedrawScaleTest(unittest.TestCase):
    """線の段階（ラフ・アタリ・線画）の直しは、絵を広げずに描く。広げる（1.5 倍）のは
    細部の画素数を稼ぐためだが、線だけの絵にその理由は無く、画素数 2.25 倍の時間が
    そのまま 1 回の直しの重さになっていた（検証 #27・#28 で、線画の一箇所の直しに
    何十分もかかった）。色の段階（仕上げなど）の直しは、今までどおり広げる"""

    def run_with(self, bad_from):
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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                return dict(HAND) if seen["hands"] >= bad_from else dict(CLEAN_HAND)

        class ScalePainter(Painter):
            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.scales = getattr(self, "scales", []) + [kw.get("max_scale")]
                return super().redraw(prompt, seed, image, mask, on_step=on_step, **kw)

        painter = ScalePainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                        say=lambda _s: None, checks=C)
        return painter.scales

    def run_with_gap(self):
        """線画で線の途切れが見つかる場合。直しは線画の囲み描き直し（shape）になる"""
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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                return dict(CLEAN_HAND)

        class ScalePainter(Painter):
            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.scales = getattr(self, "scales", []) + [kw.get("max_scale")]
                return super().redraw(prompt, seed, image, mask, on_step=on_step, **kw)

        painter = ScalePainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", _counting_lines(max_gaps=[0.8, 0.0])):
            phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                        say=lambda _s: None, checks=C)
        return painter.scales

    def test_line_stage_mends_do_not_upscale(self):
        # hands の呼び出し順: 1=土台の計測, 2=アタリの確かめ, 3=線画の確かめ, 4=仕上げの確かめ
        self.assertEqual(self.run_with(2), [1.0, 1.0, 1.0])   # アタリで初めて崩れた直しは広げない
        self.assertEqual(self.run_with_gap(), [1.0])           # 線画の線の直しも広げない（パーツは線画で直さない）

    def test_finish_stage_mends_keep_the_upscale(self):
        self.assertEqual(self.run_with(4), [None, None, None])   # 仕上げの直しは今までどおり広げる


class StageStepsTest(unittest.TestCase):
    """描く速さは工程で分ける。序盤（サムネイル・アタリ）はラフで十分なので軽くし、
    線画は少し軽く、清書以降（仕上げなど）はそのまま。時間をかけるべきは線画以降、
    特に清書以降で、序盤のアタリを線画や清書と同じレベルまで仕上げようとしない
    （利用者の指示、2026-11-27）。直しの間も途中の絵を出す（出さないと筆が止まって見える）"""

    def run_with(self, bad_from, on_step=None):
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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                seen["hands"] += 1
                return dict(HAND) if seen["hands"] >= bad_from else dict(CLEAN_HAND)

        class StepPainter(Painter):
            steps = 20

            def redraw(self, prompt, seed, image, mask, on_step=None, **kw):
                self.seen_steps = getattr(self, "seen_steps", []) + [self.steps]
                self.seen_preview = getattr(self, "seen_preview", []) + [on_step is not None]
                return super().redraw(prompt, seed, image, mask, on_step=on_step, **kw)

        painter = StepPainter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                        say=lambda _s: None, checks=C, on_step=on_step)
        return painter

    def test_atari_mends_are_light_and_previewed(self):
        painter = self.run_with(2, on_step=lambda *_a: None)
        self.assertTrue(painter.seen_steps)
        self.assertTrue(all(s == 10 for s in painter.seen_steps), painter.seen_steps)   # アタリの直しは半分の速さ
        self.assertTrue(all(painter.seen_preview))   # 直しの間も途中の絵が出る（筆が止まらない）

    def test_finish_mends_use_full_steps(self):
        painter = self.run_with(4)
        self.assertTrue(painter.seen_steps)
        self.assertTrue(all(s == 20 for s in painter.seen_steps), painter.seen_steps)   # 仕上げの直しはそのままの速さで時間をかける


class SmallMendCycleTest(unittest.TestCase):
    """直しは枠ごとに 1 つずつ。全部の枠を一度に消して描くと変化が大きくて崩れる。
    1 枠ずつ小さく消して描いてを繰り返すと、変化が小さいので崩れずに整っていく（利用者の指摘）"""

    def test_two_bad_hands_are_mended_one_region_at_a_time(self):
        import numpy as np
        two = {"readable": True, "bad": ["手 1: 指が 6 本"],
               "hands": [{"box": [10, 10, 30, 30], "seen": True, "bad": True},
                         {"box": [40, 60, 55, 80], "seen": True, "bad": True}],
               "feet": [], "faces": []}

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
                        "nose": (w * .5, h * .18), "left_ear": (w * .4, h * .15),
                        "left_shoulder": (w * .4, h * .27), "right_shoulder": (w * .6, h * .27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                return dict(two)

        painter = Painter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            phases.draw(painter, "1girl, red scarf", 5, (64, 96), Path(d) / "k",
                        say=lambda _s: None, checks=C)
        masks = [np.asarray(m.convert("L")) > 0 for m in painter.masks]
        # 枠ごとに直すので、直しの回数は枠の数だけ増える（まとめて直す作りなら半分以下）。
        # どの囲みも、2 つの枠（y 8〜44 と y 46〜94）をまたがない = 1 枠ずつ
        self.assertGreaterEqual(len(masks), 4)
        for m in masks:
            ys, _xs = np.nonzero(m)
            self.assertTrue(ys.max() < 45 or ys.min() > 45, "2 つの枠をまとめて直している")


class RoughLayerTest(unittest.TestCase):
    """ラフはレイヤーとして残し、線画の工程の絵は「薄くしたラフの上に線」を合成して見せる。
    検品と次の工程は線のレイヤーそのもので進める（利用者の進め方: ラフをレイヤーにして
    透過させ、その上に線画を描いて構図・検品・修正をする）"""

    def test_underlay_keeps_line_pixels_and_fades_rough(self):
        from PIL import Image
        line = Image.new("RGB", (8, 8), (255, 255, 255))
        rough = Image.new("RGB", (8, 8), (0, 0, 0))
        for y in range(8):
            line.putpixel((3, y), (30, 30, 30))       # 線の所（真ん中の 1 列）
        out = pt.underlay(line, rough)
        self.assertEqual(out.getpixel((3, 4)), (30, 30, 30))     # 線はそのまま残る
        ghost = out.getpixel((6, 4))[0]                          # 線の無い所はラフが薄く見える
        self.assertGreater(ghost, 120)
        self.assertLess(ghost, 220)

    def test_line_phase_shows_lines_over_faded_rough(self):
        from PIL import Image
        seen = {}

        def spy(line, rough, strength=0.35):
            seen["line"], seen["rough"] = line, rough
            return Image.new("RGB", line.size, (200, 30, 30))    # 合成の代わりに目印の絵を返す

        painter = Painter()
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
                mock.patch.object(pt, "underlay", spy):
            keep = Path(d) / "k"
            got = phases.draw(painter, "1girl, red scarf", 5, (64, 96), keep,
                              say=lambda _s: None, checks=hand_only_checks())
            self.assertIn("rough", seen)                                    # ラフを下に敷いて合成した
            self.assertTrue((keep / "layer-03-ラフ.png").exists())           # ラフがレイヤーのファイルとして残る
            phase3 = [r for r in got["history"] if r["phase"] == "線画" and r.get("image")]
            self.assertTrue(phase3)
            shown = Image.open(phase3[-1]["image"]).convert("RGB")          # 工程の絵は合成の方
            self.assertGreater(shown.getpixel((2, 2))[0], 150)
            self.assertLess(shown.getpixel((2, 2))[1], 80)


class DustPatternTest(unittest.TestCase):
    """ゴミの判定: 同じくらいの大きさの小さい塊がたくさんあれば模様（星・雪・質感）で、ゴミではない"""

    def _field(self, specks):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        dr = ImageDraw.Draw(img)
        dr.rectangle([20, 20, 80, 160], fill=(40, 40, 40))   # 主役（土台になる大きな塊）
        for (x, y) in specks:
            dr.rectangle([x, y, x + 2, y + 2], fill=(30, 30, 30))
        return img

    def test_many_similar_specks_are_a_pattern_not_dust(self):
        specks = [(120 + (i % 4) * 20, 20 + (i // 4) * 30) for i in range(12)]
        d = pt.dust(self._field(specks))
        self.assertTrue(d["readable"])
        self.assertEqual(d["count"], 0, d)   # 星空のような模様をゴミとして消してはいけない

    def test_few_specks_are_still_dust(self):
        d = pt.dust(self._field([(120, 20), (160, 90), (130, 170)]))
        self.assertTrue(d["readable"])
        self.assertEqual(d["count"], 3, d)


class DetailToolsTest(unittest.TestCase):
    """ディテールの物差しと加工、差し戻しの見張り、直しの後始末"""

    def test_detail_density_reads_texture(self):
        from PIL import Image, ImageDraw
        flat = Image.new("RGB", (120, 120), (255, 255, 255))
        dr = ImageDraw.Draw(flat)
        dr.rectangle([30, 30, 90, 90], fill=(120, 120, 120))
        busy = flat.copy()
        dr2 = ImageDraw.Draw(busy)
        for x in range(32, 90, 4):
            for y in range(32, 90, 4):
                if (x + y) % 8 == 0:
                    dr2.rectangle([x, y, x + 1, y + 1], fill=(30, 30, 30))
        d_flat = pt.detail_density(flat)
        d_busy = pt.detail_density(busy)
        self.assertTrue(d_flat["readable"] and d_busy["readable"])
        self.assertGreater(d_busy["density"], d_flat["density"])

    def test_enhance_detail_sharpens_only_inside_subject(self):
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np
        img = Image.new("RGB", (120, 120), (255, 255, 255))
        dr = ImageDraw.Draw(img)
        dr.rectangle([30, 30, 90, 90], fill=(100, 100, 100))
        dr.rectangle([45, 45, 75, 75], fill=(180, 180, 180))
        soft = img.filter(ImageFilter.GaussianBlur(2))
        before = pt.detail_density(soft)["sharp"]
        out = pt.enhance_detail(soft)
        after = pt.detail_density(out)["sharp"]
        self.assertGreater(after, before)
        # 主役の外（紙）は変えない
        self.assertEqual(np.asarray(out)[5, 5].tolist(), [255, 255, 255])

    def test_edge_leftovers_finds_orphaned_fragment(self):
        from PIL import Image, ImageDraw
        import numpy as np
        before = Image.new("RGB", (200, 200), (255, 255, 255))
        dr = ImageDraw.Draw(before)
        dr.rectangle([20, 20, 60, 160], fill=(40, 40, 40))        # 主役
        dr.rectangle([90, 97, 130, 102], fill=(30, 30, 30))       # 囲みを横切る物
        mask = Image.new("L", (200, 200), 0)
        ImageDraw.Draw(mask).rectangle([100, 40, 120, 160], fill=255)
        after = before.copy()
        dr2 = ImageDraw.Draw(after)
        dr2.rectangle([100, 97, 120, 102], fill=(255, 255, 255))  # 囲みの中は消して描き直した
        dr2.ellipse([104, 60, 116, 72], fill=(90, 90, 90))        # 囲みの中の新しい絵
        left = pt.edge_leftovers(before, after, mask)
        self.assertIsNotNone(left)
        a = np.asarray(left)
        self.assertEqual(int(a[99, 125]), 255)   # 縁の外に残った欠片（121〜130）を拾う
        self.assertEqual(int(a[99, 95]), 255)    # 反対側の欠片（90〜99）も、囲みの中とつながっていない残り
        self.assertEqual(int(a[100, 30]), 0)     # 主役そのものは欠片ではない


class DetailPhaseTest(PhasesTest):
    """ディテール工程: 仕上げの直前にあること、消す直しが無いこと、影を潰す結果を採用しないこと"""

    def test_detail_phase_position_and_items(self):
        from atelier.ai import phase_items as items
        self.assertEqual(phases.NAMES[8], "ディテール")
        self.assertEqual(phases.NAMES[9], "仕上げ")
        self.assertEqual(items.PHASE_ITEMS[8], ["ディテール", "影の締まり"])
        for i in range(4, len(items.PHASE_ITEMS)):
            self.assertNotIn("ゴミ", items.PHASE_ITEMS[i])   # 清書より後の工程は、ゴミを消す項目を持たない

    def test_draw_completes_with_detail_phase(self):
        got, painter, seen, said, files = self.run_phases(always_bad=False)
        names = [r["phase"] for r in got["history"]]
        self.assertIn("ディテール", names)
        self.assertLess(names.index("ディテール"), len(names) - 1)
        self.assertEqual(names[-1], "仕上げ")

    def test_detail_pass_that_crushes_shadows_is_not_adopted(self):
        class WashPainter(Painter):
            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                if "detailed texture" in prompt:
                    from PIL import ImageFilter
                    return image.filter(ImageFilter.GaussianBlur(4))   # 質感も影の締まりも潰す結果
                return image.copy()
        got, painter, seen, said, files = self.run_phases(always_bad=False, painter=WashPainter())
        self.assertTrue(any("潰れるので、元の絵のまま" in s for s in said), said[-6:])

    def test_restore_missing_lines_bridges_cuts_but_not_moved_lines(self):
        from PIL import Image, ImageDraw
        import numpy as np
        src = Image.new("RGB", (120, 120), (255, 255, 255))
        ImageDraw.Draw(src).line([20, 60, 100, 60], fill=(30, 30, 30), width=2)
        cut = src.copy()
        ImageDraw.Draw(cut).rectangle([55, 58, 65, 62], fill=(255, 255, 255))   # 線の真ん中が消えた
        out, n = pt.restore_missing_lines(src, cut)
        self.assertGreater(n, 0)
        self.assertLess(int(np.asarray(out)[60, 60][0]), 80)   # 途切れがつながった
        moved = Image.new("RGB", (120, 120), (255, 255, 255))
        ImageDraw.Draw(moved).line([20, 70, 100, 70], fill=(30, 30, 30), width=2)   # 描き直しで線が下に移った
        out2, n2 = pt.restore_missing_lines(src, moved)
        self.assertEqual(n2, 0)   # 移った線は二重に描かない
        self.assertEqual(int(np.asarray(out2)[60, 60][0]), 255)


class DetachedErasureMaskTest(unittest.TestCase):
    """位置ずれの欠片消し: 小さい離れた欠片だけを消し、大きい離れた物（部位かもしれない）は消さない"""

    def test_only_small_detached_fragments_are_masked(self):
        from PIL import Image, ImageDraw
        import numpy as np
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        dr = ImageDraw.Draw(img)
        dr.rectangle([60, 40, 120, 160], fill=(40, 40, 40))     # 主役
        dr.rectangle([130, 60, 140, 70], fill=(30, 30, 30))     # 小さい欠片（11x11。主役の近く）
        dr.rectangle([130, 100, 159, 129], fill=(30, 30, 30))   # 大きい離れた物（30x30。消さない）
        mask = pt.detached_erasure_mask(img)
        self.assertIsNotNone(mask)
        a = np.asarray(mask)
        self.assertEqual(int(a[65, 135]), 255)    # 欠片は消す対象
        self.assertEqual(int(a[114, 144]), 0)     # 大きい物は対象外
        self.assertEqual(int(a[100, 90]), 0)      # 主役は対象外


class TonePatternWiringTest(unittest.TestCase):
    """道具の配線: 頼みに網点があれば、ディテール工程で影の側に網点の柄が道具で入る"""

    def run_with_prompt(self, prompt):
        painter = Painter()
        C, _seen = checks(False)
        said = []
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, prompt, 5, (64, 96), Path(d) / "k", say=said.append, checks=C, confirm=None)
        return got, said

    def test_tone_request_gets_halftone_at_detail(self):
        _got, said = self.run_with_prompt("1girl, red scarf, 網点")
        self.assertTrue(any("網点" in s and "道具" in s for s in said))

    def test_no_tone_without_the_word(self):
        _got, said = self.run_with_prompt("1girl, red scarf")
        self.assertFalse(any("網点" in s for s in said))


class CompositionMendScopeTest(unittest.TestCase):
    """構成の直しの範囲: アタリで手を尽くした頼んだ物を、線画以降で振り直さない。
    振り直すと清書した線まで壊れ、崩れの顔ぶれが変わり続けて直しが終わらない
    （検証 #27 の監査: その直しは正しくない）。残った崩れとして正直に残す。
    アタリで直していない（初めて見つかった）欠けは、この限りではない"""

    def test_item_mended_at_atari_is_not_rerolled_at_line_phase(self):
        calls = {"request": 0, "hands": 0}

        class C:
            @staticmethod
            def request(image, prompt):
                calls["request"] += 1
                # アタリの確かめ（3 回目）から、ずっと欠けている（直しの描き直しでも直らない）
                missing = ["red scarf"] if calls["request"] >= 3 else []
                return {"readable": True, "missing": missing, "extra": [], "people": [], "body": []}

            @staticmethod
            def body(image, prompt, tags=None):
                return {"readable": True, "bad": [], "avoid": []}

            @staticmethod
            def points(image):
                w, h = image.size
                return {"readable": True, "points": {"left_eye": (w * 0.45, h * 0.15), "right_eye": (w * 0.55, h * 0.15),
                                                     "nose": (w * 0.5, h * 0.18), "left_ear": (w * 0.4, h * 0.15),
                                                     "left_shoulder": (w * 0.4, h * 0.27), "right_shoulder": (w * 0.6, h * 0.27)}}

            @staticmethod
            def pose(image):
                return {"readable": True, "bad": [], "map": image}

            @staticmethod
            def hands(image, prompt):
                calls["hands"] += 1
                return dict(HAND) if calls["hands"] <= 2 else dict(CLEAN_HAND)

        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(Painter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C, confirm=None)
        atari_mends = [m for r in got["history"] if r["phase"] == "アタリ"
                       for m in r.get("mends", []) if m.get("item") == "頼んだ物"]
        line_mends = [m for r in got["history"] if r["phase"] == "線画"
                      for m in r.get("mends", []) if m.get("item") == "頼んだ物"]
        self.assertTrue(atari_mends)          # アタリでは直しをかけた
        self.assertEqual(line_mends, [])      # 線画では振り直さない
        self.assertTrue(any("描かれていない" in f for f in got["left"]), got["left"])   # 残った崩れとして正直に残る
        self.assertEqual(got["history"][-1]["phase"], "仕上げ")   # 最後まで進む

class LineArtModeTest(unittest.TestCase):
    """線画の頼み: 線画で終わると指定されたときだけ、色の工程を置かず線の仕上げで完成にする。
    指定が無ければ線画はスタートラインで、色の工程まで進む（利用者の規則）"""

    def run_with_prompt(self, prompt):
        painter = Painter()
        C, _seen = checks(False)
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(painter, prompt, 5, (64, 96), Path(d) / "k", checks=C, confirm=None)
        return got

    def test_line_art_request_ends_at_line_finish(self):
        got = self.run_with_prompt("1girl, red scarf, 線画")
        names = [r["phase"] for r in got["history"]]
        self.assertEqual(names, ["目的", "サムネイル", "アタリ", "線画", "線の仕上げ"])
        self.assertTrue(got["complete"], got["left"])

    def test_no_line_art_word_goes_to_color(self):
        got = self.run_with_prompt("1girl, red scarf")
        names = [r["phase"] for r in got["history"]]
        self.assertIn("下塗り", names)
        self.assertEqual(names[-1], "仕上げ")


class AtariLineArtMeasureTest(unittest.TestCase):
    """最初のアタリが、描いた本人（線のラフ画）のままで検品に通ること。
    アタリが描くのは輪郭だけの線画なのに、位置ずれ・ゴミの物差しが「塗りつぶした
    人物の塊」を前提に成分を数えていたため、頭の輪郭や目の線といった絵そのものが
    「体から離れた物」「ゴミ」に化け、最初のアタリに必ず直しが入っていた
    （利用者の指摘、2026-11-27: 最初のアタリがズレてるせいで描き直しが確定で入る）"""

    def test_sketch_outlines_are_not_detached_or_dust(self):
        """線のラフ画: 輪郭の線と内側の線（目など）は、離れた物でもゴミでもない"""
        for size in ((64, 96), (256, 384)):
            im = sketch(size)
            self.assertEqual(pt.detached(im)["count"], 0, (size, pt.detached(im)))
            self.assertEqual(pt.dust(im)["count"], 0, (size, pt.dust(im)))

    def test_detached_blob_beside_sketch_still_found(self):
        """線画でも、本当に体から離れた塊は位置ずれとして見つける（直しすぎない）"""
        from PIL import ImageDraw
        im = sketch((64, 96))
        d = ImageDraw.Draw(im)
        d.rectangle([45, 40, 55, 50], fill=(30, 30, 30))  # 体の輪郭の外に、離れた塊
        self.assertEqual(pt.detached(im)["count"], 1, pt.detached(im))

    def test_first_atari_of_clean_sketch_needs_no_mend(self):
        """検品（模型）が全部通る線のラフ画を描く画家では、最初のアタリに
        崩れが出ず、直しも入らない。直しは本当に崩れた絵のためだけに残る"""
        class SketchPainter(Painter):
            def paint(self, prompt, seed, on_step=None, **kw):
                self.log.append(("paint", seed, self.steps, "base" in kw and kw["base"] is not None, kw.get("size")))
                return sketch(kw.get("size") or (64, 96))

            def refine(self, prompt, seed, image, strength=0.5, on_step=None, on_preview=None):
                self.log.append(("refine", seed, strength))
                return image.copy()

        C = hand_only_checks(0)   # 頼んだ物・体・手の検品は全部通す
        with TemporaryDirectory() as d, mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}):
            got = phases.draw(SketchPainter(), "1girl, red scarf", 5, (64, 96), Path(d) / "k", checks=C)
        atari = [r for r in got["history"] if r["phase"] == "アタリ"]
        self.assertTrue(atari)
        for r in atari:
            self.assertEqual(r["found"], [], r)
            self.assertEqual(r.get("mends", []), [], r)
        self.assertEqual([x for x in got["left"] if x.startswith("アタリ")], [], got["left"])

