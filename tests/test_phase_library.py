"""精度優先で 1 回描くごとに、ライブラリーに増えるのは利用者が見る最後の絵 1 枚だけかを、本物の窓の経路（offscreen、偽の模型）で数える。
0.1.16 までは、崩れが残って聞いて止まるたびに途中の絵がライブラリーと履歴に足され、描き続けると溜まった。
溜まった分は、起動のときに 1 回だけ聞いてごみ箱へ移せる（戻せる）ことも確かめる"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, PngImagePlugin  # noqa: E402

from atelier.ai import phases  # noqa: E402
from atelier.ai import phase_tools as pt  # noqa: E402
from atelier.ai.engine import Studio  # noqa: E402
from tests.test_chatdraw import FakeWords  # noqa: E402
from tests.test_phases import Painter, checks  # noqa: E402


def counts(lib_dir: Path) -> int:
    try:
        return len(json.loads((lib_dir / "index.json").read_text(encoding="utf-8")))
    except OSError:
        return 0


class PhaseLibraryTest(unittest.TestCase):
    def setUp(self):
        from tests.test_editing import app
        self.qapp = app()
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.home = mock.patch("atelier.files.paths.HOME", self.d / "home")
        self.home.start()

    def tearDown(self):
        self.home.stop()
        self.tmp.cleanup()

    def window(self):
        from atelier.app.main_window import Window
        from atelier.files.library import Library
        s = Studio(FakeWords(), Painter(), self.d / "out")
        s.way = "phases"
        w = Window(s)
        w.library = Library(self.d / "lib")
        w.library_panel.refresh()
        return w, s

    def draw(self, w, change=None):
        C, _ = checks(False)
        real = phases.draw

        def draw(*a, **k):
            got = real(*a, **k)
            return change(got) if change else got
        with mock.patch.object(w, "check_ai", return_value={"image": True, "reason": ""}), \
             mock.patch.object(w, "_keep_original", lambda x: x), \
             mock.patch.object(w, "offer_two_stage_parts", lambda: None), \
             mock.patch.object(pt, "lines", lambda _im: {"readable": True, "gap": 0.0}), \
             mock.patch.object(phases, "draw", draw), \
             mock.patch.object(phases.Checks, "request", staticmethod(C.request)), \
             mock.patch.object(phases.Checks, "body", staticmethod(C.body)), \
             mock.patch.object(phases.Checks, "points", staticmethod(C.points)), \
             mock.patch.object(phases.Checks, "pose", staticmethod(C.pose)), \
             mock.patch.object(phases.Checks, "hands", staticmethod(C.hands)):
            w._draw_now("赤いマフラーの子")
            t = time.time()
            while w.thread is not None and time.time() - t < 120:
                self.qapp.processEvents()
                time.sleep(0.01)
            self.qapp.processEvents()
        self.assertIsNone(w.thread, "描く処理が終わらない")

    def close(self, w):
        w.dirty = False
        w.close()

    def test_one_draw_adds_one(self):
        w, s = self.window()
        try:
            before = counts(self.d / "lib")
            self.draw(w)
            after = counts(self.d / "lib")
            print("通った回: 描く前", before, "描いた後", after)
            self.assertEqual(after - before, 1)
            item = w.library.items[0]
            self.assertNotIn(".stages", Path(item["path"]).parts)   # 工程の絵ではなく、最後の絵
            self.assertEqual(sum(1 for i in range(w.history.count())), 1)
        finally:
            self.close(w)

    def test_left_flaws_end_adds_one(self):
        w, s = self.window()
        try:
            before = counts(self.d / "lib")
            self.draw(w, lambda g: dict(g, complete=False, left=["手の指が多い"], unresolved=["手の指が多い"]))
            after = counts(self.d / "lib")
            print("崩れが残って終わった回: 描く前", before, "描いた後", after)
            self.assertEqual(after - before, 1)
        finally:
            self.close(w)

    def test_asked_adds_none(self):
        w, s = self.window()
        try:
            before = counts(self.d / "lib")
            asked = {"phase": "アタリ", "index": 2, "left": ["人数が違う"], "why": "試験", "choices": ["このまま進む"]}
            self.draw(w, lambda g: dict(g, complete=False, asked=asked, left=["人数が違う"]))
            after = counts(self.d / "lib")
            print("聞いて止まった回: 描く前", before, "描いた後", after)
            self.assertEqual(after, before)   # 途中の絵。再開した回が最後の絵を 1 枚入れる
            self.assertEqual(w.history.count(), 0)
            self.assertTrue(any(l.name == "検品を通っていない絵" for l in w.canvas.layers))   # 隠したレイヤーには置く
            self.assertTrue(list((s.out / ".stages").rglob("*.png")))
        finally:
            self.close(w)

    def test_stop_adds_one(self):
        w, s = self.window()
        try:
            keep = s.out / ".stages" / "x-phases"
            keep.mkdir(parents=True)
            img = keep / "003-03-線画.png"
            Image.new("RGB", (32, 32), "white").save(img)
            (keep / "progress.json").write_text(json.dumps({"state": "stopped", "total": 3, "need": 9, "left": [],
                                                            "images": [str(img)], "names": ["線画"], "image": str(img)}), encoding="utf-8")
            s.last_phase_keep = keep
            w.job_kind, w.job_studio = "draw", s
            before = counts(self.d / "lib")
            w._put_stopped_phases()
            after = counts(self.d / "lib")
            print("止めた回: 描く前", before, "止めた後", after)
            self.assertEqual(after - before, 1)
            self.assertNotIn(".stages", Path(w.library.items[0]["path"]).parts)
        finally:
            self.close(w)

    def test_old_interim_asked_once_and_restorable(self):
        from atelier.ai.finishers import KEY
        from atelier.files.library import Library
        from atelier.ui import confirm
        out = self.d / "out"
        day = out / "2026-11-23"
        day.mkdir(parents=True)
        st = out / ".stages" / "20261123-1-phases"
        st.mkdir(parents=True)
        (st / "phases.json").write_text(json.dumps({"asked": {"phase": "アタリ"}}), encoding="utf-8")
        st2 = out / ".stages" / "20261123-2-phases"
        st2.mkdir(parents=True)
        (st2 / "phases.json").write_text(json.dumps({"asked": None}), encoding="utf-8")

        def png(p, meta):
            info = PngImagePlugin.PngInfo()
            if meta is not None:
                info.add_itxt(KEY, json.dumps(meta, ensure_ascii=False))
            Image.new("RGB", (16, 16)).save(p, pnginfo=info)
            return p
        a = png(day / "a.png", {"way": "phases", "stages": str(st), "passed": False})        # 聞いて止まった回（旧版）
        b = png(st / "002-03-アタリ.png", None)                                            # 工程の絵
        c = png(day / "c.png", {"way": "phases", "interim": True})                         # 印の付いた途中の絵
        e = png(day / "e.png", {"way": "phases", "stages": str(st2), "passed": False})       # 最後の絵（崩れが残って終わった）
        f = png(day / "f.png", None)                                                       # 見分けられない絵
        lib = Library(self.d / "lib")
        lib.items = [dict(id=str(i), kind="work", path=str(p), rating=0, tags=[], note="", text="", added="", seen=True)
                     for i, p in enumerate((a, b, c, e, f))]
        lib.save()
        w, s = self.window()
        asked = []
        try:
            t = time.time()
            while getattr(w, "_interim_busy", False) and time.time() - t < 10:   # 起動のときの 1 回（古い一覧を読んだ物）を終わらせる
                self.qapp.processEvents()
                time.sleep(0.01)
            w.settings.store.remove(w.INTERIM_KEY)
            with mock.patch.object(confirm, "ask", lambda *x, **k: (asked.append(x[3]), "yes")[1]):
                w.sweep_phase_interim()
                t = time.time()
                while not asked and time.time() - t < 10:
                    self.qapp.processEvents()
                    time.sleep(0.01)
                self.qapp.processEvents()
                print("聞いた文:", asked)
                self.assertEqual(asked, ["描いている途中の絵が 3 枚、ライブラリーに入っています。ゴミ箱へ移しますか"])
                self.assertEqual(sorted(i["path"] for i in w.library.items), sorted([str(e), str(f)]))
                self.assertFalse(a.exists() or b.exists() or c.exists())
                self.assertTrue(e.exists() and f.exists())
                w.sweep_phase_interim()   # 2 度目は聞かない
                self.qapp.processEvents()
                self.assertEqual(len(asked), 1)
            entries = [x for x in w.trash.entries() if x.get("label") == "精度優先の途中の絵"]
            self.assertEqual(len(entries), 1)
            self.assertTrue(w.restore_trash(entries[0]["key"]))
            self.assertTrue(a.exists() and b.exists() and c.exists())
            self.assertEqual(len(w.library.items), 5)
        finally:
            w.settings.store.remove(w.INTERIM_KEY)
            self.close(w)


if __name__ == "__main__":
    unittest.main()
