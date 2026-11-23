"""確かめの窓・元の頼みとの食い違い・短いツアーの試験。ボタンとメニューを押して、本物と同じ経路で流す"""
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QRect, QTimer  # noqa: E402
from tests.test_uifix import app, draw, shown, spin  # noqa: E402


def answer(w, label, again=False, seen=None):
    """次に出る確かめの窓で、label のボタンを押す。again で「次から聞かない」を入れる・外す（None なら初めのまま）"""
    def press():
        box = getattr(w, "_confirm_box", None)
        if box is None:
            QTimer.singleShot(20, press)
            return
        if seen is not None:
            seen.append(box.text())
        if again is not None:
            box.checkBox().setChecked(again)
        for b in box.buttons():
            if b.text() == label:
                b.click()
                return
        raise AssertionError([b.text() for b in box.buttons()])
    QTimer.singleShot(20, press)


def menu_action(w, top, name):
    for a in w.menuBar().actions():
        if a.text() == top:
            for b in a.menu().actions():
                if b.text().startswith(name):
                    return b
    raise AssertionError((top, name))


def wait(w, s=60):
    import time
    a = app()
    end = time.time() + s
    while time.time() < end:
        a.processEvents()
        if w.thread is None:
            break
        time.sleep(0.01)
    spin(10)
    if w.thread is not None:   # 固まったまま後ろの確かめに進ませない
        raise AssertionError(f"{s} 秒たっても処理が終わらない（固まった）")


class IntentTest(unittest.TestCase):
    def test_conflicts(self):
        from atelier.agent.intent import conflicts
        self.assertEqual(conflicts("赤い髪の少女、帽子、剣", "髪を青に"), [("赤い髪の少女", "髪を青に")])
        self.assertEqual(conflicts("赤い髪の少女、帽子、剣", "帽子を消して"), [("帽子", "帽子を消して")])
        self.assertEqual(conflicts("赤い髪の少女、帽子、剣", "剣を斧に"), [("剣", "剣を斧に")])
        self.assertEqual(conflicts("red hair, hat", "blue hair"), [("red hair", "blue hair")])
        self.assertEqual(conflicts("赤い髪の少女、帽子", "目を大きく"), [])


class FixConfirmTest(unittest.TestCase):
    def _fix(self, w, text):
        w.canvas.set_selection(QRect(10, 10, 40, 40))
        w.mode.setCurrentIndex(2)
        w.entry.setText(text)
        w.button.click()          # 描くボタンを押す
        wait(w)

    def test_conflict_asks_and_each_choice(self):
        with TemporaryDirectory() as d:
            w = shown(d)
            w.settings.set("intent_way", "毎回聞く")   # 聞く形を選んだ人の経路
            draw(w, "赤いマントの騎士、剣")
            self.assertEqual(w.origin_prompt, "赤いマントの騎士、剣")
            n = len(w.canvas.layers)
            texts = []
            answer(w, "やめる", seen=texts)           # やめる: 何も描かない
            self._fix(w, "マントを青に")
            self.assertIn("赤いマントの騎士", texts[0])
            self.assertEqual(len(w.canvas.layers), n)
            answer(w, "元のまま")                      # 食い違った所だけで頼んだので、直す所が残らず描かない
            self._fix(w, "マントを青に")
            self.assertEqual(len(w.canvas.layers), n)
            answer(w, "元のまま")                      # 食い違わない所だけを直す
            self._fix(w, "剣を消して、笑顔に")
            self.assertEqual(len(w.canvas.layers), n + 1)
            self.assertEqual(w.last_text, "笑顔に")
            answer(w, "新しい頼みにする", again=True)  # 新しい頼み: そのまま直し、元の頼みも替える
            self._fix(w, "マントを青に")
            self.assertEqual(len(w.canvas.layers), n + 2)
            self.assertIn("マントを青に", w.origin_prompt)
            self.assertNotIn("赤いマントの騎士", w.origin_prompt)
            self._fix(w, "剣を斧に")                   # 「次から聞かない」: 窓を出さずに新しい頼みで描く
            self.assertEqual(len(w.canvas.layers), n + 3)
            menu_action(w, "設定", "確かめの窓をまた出す").trigger()   # 設定から戻す
            from atelier.ui import confirm
            self.assertEqual(confirm.remembered(w, "intent"), "")
            w.settings.set("intent_way", "今の頼みにする")

    def test_default_never_asks_three_times(self):
        """既定では食い違っても窓を出さず、今の頼みのとおりに直す。3 回続けても 0 回"""
        from atelier.ui import confirm
        with TemporaryDirectory() as d:
            w = shown(d)
            w.settings.set("intent_way", "今の頼みにする")   # 既定（ほかの試験が変えた値を残さない）
            confirm.forget(w)
            draw(w, "赤いマントの騎士、剣")
            n = len(w.canvas.layers)
            opened = []
            real = confirm.QMessageBox.exec
            confirm.QMessageBox.exec = lambda box: opened.append(box.text()) or 0
            try:
                for i, t in enumerate(["マントを青に", "剣を斧に", "マントを緑に"]):
                    self._fix(w, t)
                    self.assertEqual(w.last_text, t)               # 模型に渡す頼みは今書いた指示のまま
                    self.assertEqual(len(w.canvas.layers), n + i + 1)
            finally:
                confirm.QMessageBox.exec = real
            self.assertEqual(opened, [])
            self.assertIn("マントを緑に", w.origin_prompt)

    def test_once_then_remembered(self):
        """聞く窓は「次から聞かない」が初めから入っていて、2 回目からは出ない"""
        from atelier.ui import confirm
        with TemporaryDirectory() as d:
            w = shown(d)
            confirm.forget(w)
            w.ai_panel.count_buttons[1][2].click()
            seen = []
            answer(w, "4 枚描く", again=None, seen=seen)   # 「次から聞かない」は触らずに押す
            w.entry.setText("雪の城の前の騎士")
            w.button.click()
            wait(w)
            self.assertEqual(len(seen), 1)
            self.assertEqual(confirm.remembered(w, "batch"), "go")
            for _ in range(2):
                w.button.click()
                wait(w)
                self.assertIsNone(getattr(w, "_confirm_box", None))
            self.assertEqual(len(w.images), 12)

    def test_no_conflict_no_window(self):
        with TemporaryDirectory() as d:
            w = shown(d)
            draw(w, "赤いマントの騎士")
            n = len(w.canvas.layers)
            self._fix(w, "目を大きく")
            self.assertIsNone(getattr(w, "_confirm_box", None))
            self.assertEqual(len(w.canvas.layers), n + 1)


class BatchConfirmTest(unittest.TestCase):
    def test_batch_asks(self):
        with TemporaryDirectory() as d:
            w = shown(d)
            w.ai_panel.count_buttons[1][2].click()   # 「4 枚」を押す
            self.assertEqual(w.ai_panel.count_spin.value(), 4)
            answer(w, "やめる")
            w.entry.setText("雪の城の前の騎士")
            w.button.click()
            wait(w)
            self.assertEqual(len(w.images), 0)
            answer(w, "4 枚描く")
            w.button.click()
            wait(w)
            self.assertEqual(len(w.images), 4)


class TourTest(unittest.TestCase):
    def test_tours_short_and_no_chain(self):
        from atelier.ui import tours
        with TemporaryDirectory() as d:
            w = shown(d)
            for key, (_name, steps) in tours.catalog(w).items():
                self.assertLessEqual(len(steps), tours.MAX_STEPS, key)
            self.assertLessEqual(len(w.tour_steps()), tours.MAX_STEPS)
            w.layout_store.remove("tour_done")
            w.maybe_tour()
            t = w.tour
            for _ in t.steps:
                spin(3)
                t.next.click()
            self.assertTrue(t.done)
            w.layout_store.remove("tours/layers")
            w.toggle_panel("layers")                      # 閉じた直後に別の機能を触っても、案内は続けて出ない
            self.assertIs(w.tour, t)
            self.assertFalse(tours.seen(w, "layers"))     # 見たことにはしない

    def test_new_tours_menu_and_notice(self):
        from atelier.ui import tours
        from atelier.ui.notice import Notice
        with TemporaryDirectory() as d:
            w = shown(d)
            for k in tours.NEW:
                w.layout_store.remove(f"tours/{k}")
            w.layout_store.remove("tours_noticed")
            w.layout_store.setValue("tour_done", 1)
            help_menu = next(a.menu() for a in w.menuBar().actions() if a.text() == "ヘルプ")
            help_menu.aboutToShow.emit()
            self.assertEqual(w.new_tours_menu.title(), f"新しいツアー（{len(tours.NEW)}）")
            w.maybe_tour()                                 # 起動の知らせは 1 回だけ
            spin(3)
            from PySide6.QtWidgets import QLabel
            said = [lab.text() for n in w.findChildren(Notice) for lab in n.findChildren(QLabel)]
            self.assertTrue(any("新しいツアー" in t for t in said), said)
            before = len(w.findChildren(Notice))
            w.maybe_tour()
            self.assertEqual(len(w.findChildren(Notice)), before)
            first = w.new_tours_menu.actions()[0]
            first.trigger()                                # メニューから見る
            t = w.tour
            for _ in t.steps:
                spin(3)
                t.next.click()
            help_menu.aboutToShow.emit()
            self.assertEqual(w.new_tours_menu.title(), f"新しいツアー（{len(tours.NEW) - 1}）")


if __name__ == "__main__":
    unittest.main()
