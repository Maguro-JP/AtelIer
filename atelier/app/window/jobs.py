"""裏で回す処理（描く仕事、時間のかかる処理）と、止める旗の扱い"""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from atelier.ai.engine import Studio
from atelier.paint.canvas import preload
import time


class PhaseAsk(QObject):
    """精度優先の工程の確かめ。描く糸から呼ばれ、画面の糸に窓を出させて、答えが来るまで描く糸を待たせる。
    待つ間も止めるボタンは効く（止める旗を 0.2 秒ごとに見る）"""
    ask = Signal(object)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.ask.connect(self._show, Qt.QueuedConnection)

    def __call__(self, i, name, image, row):
        import threading
        box = {"event": threading.Event(), "answer": "go", "i": i, "name": name, "image": image, "row": row}
        self.ask.emit(box)
        painter = getattr(getattr(self.window, "job_studio", None) or self.window.studio, "painter", None)
        while not box["event"].wait(0.2):
            if getattr(painter, "stop", False) is True:
                break
        return box["answer"]

    def _show(self, box):
        try:
            box["answer"] = self.window.ask_phase(box["i"], box["name"], box["image"], box["row"])
        finally:
            box["event"].set()


class Job(QObject):
    """AI の 1 回分を裏で回す。描く（枚数分）か、直す（regions を渡したとき）"""
    status = Signal(str)
    preview = Signal(object)   # 描いている途中の絵（PIL）
    one = Signal(str, str)     # 1 枚できた（描く言葉、置き場）
    done = Signal()
    failed = Signal(str)

    def __init__(self, studio: Studio, text: str, seeds, base=None, strength: float = 0.6, size=None, style: str = "",
                 regions=None, reference=None, ref_scale: float = 0.6, meta: dict | None = None, check: bool = True):
        super().__init__()
        self.seeds = [seeds] if isinstance(seeds, int) else list(seeds)
        self.studio, self.text, self.style = studio, text, style
        self.base, self.strength, self.size = base, strength, size
        self.regions, self.reference, self.ref_scale, self.meta = regions, reference, ref_scale, meta or {}
        self.check = check
        self.tid = None   # 走っている裏の糸の番号。緊急停止がここへ Stopped を投げ込む
        self._last_preview = 0.0
        fresh_stop(studio)

    PREVIEW_GAP = 0.4   # 途中の絵を画面に渡す間（秒）

    def _preview(self, img):
        """途中の絵は工程ごとに届く。全部を画面の糸に積むと、速い模型では置く処理が溜まって画面とメモリを圧迫したので、間を空けて渡す"""
        now = time.monotonic()
        if now - self._last_preview < self.PREVIEW_GAP:
            return
        self._last_preview = now
        self.preview.emit(img)

    def _say(self, msg: str):
        """工程の知らせ。止める旗が立っていれば、ここで止める（旗を見ない工程の区切りでも止まる）"""
        from atelier.app import debug_log as debuglog
        from atelier.ai.engine import check_stop
        check_stop()
        debuglog.log("工程", msg)
        self.status.emit(msg)

    def run(self):
        guarded(self, self._run)

    def _run(self):
        try:
            if self.regions is not None:
                prompts, path = self.studio.fix(self.base, self.regions, self.seeds[0], on_status=self._say,
                                                style=self.style, strength=self.strength, reference=self.reference,
                                                ref_scale=self.ref_scale, check=self.check,
                                                **({"source": self.meta["source"]} if self.meta.get("source") else {}))
                self._stopped()
                preload(path)
                self.one.emit(" / ".join(prompts), str(path))
            else:
                self._draw_all()
            self.done.emit()
        except Exception as e:  # 描けなかった理由を、次に何をすればよいか分かる日本語で会話に出す
            from atelier.app import debug_log as debuglog
            from atelier.files import pause_keep as pausekeep
            if pausekeep.is_pause(e) and self.regions is None:
                self.paused = self._keep_paused(e)
                self.failed.emit(PAUSED_HEAD + str(e).splitlines()[0])
                return
            self.trace = debuglog.exception("描く・直す", e)
            from atelier.ai.engine import explain
            self.failed.emit(explain(e))   # 何が起きたかを 1 行で返す（「描けませんでした」の決まり文句は付けない）

    def _keep_paused(self, e) -> str:
        """メモリ・時間の打ち切りを、止めて捨てずに一時停止として残す。工程に分けて描いた回は phases.py が途中の工程まで残している。
        1 回で描く回は、まだ描いていない種と頼みを残し、「再開」でその種から描く。返すのは pausekeep の鍵"""
        from atelier.files import pause_keep as pausekeep
        k = getattr(e, "key", None) or getattr(e.__cause__, "key", None)
        left = self.seeds[getattr(self, "drawn", 0):] or self.seeds
        job = {"text": self.text, "seeds": left, "style": self.style, "size": list(self.size) if self.size else None,
               "meta": self.meta, "model": getattr(self.studio.painter, "model", "")}
        if k and pausekeep.info(k):
            return k
        k = pausekeep.key("draw", self.text, left[0], self.style)
        pausekeep.save(k, "draw", f"「{self.text[:30]}」を描く途中で一時停止（種 {left[0]} から）", job)
        return k

    def _draw_one(self, seed):
        extra = dict(reference=self.reference, ref_scale=self.ref_scale) if self.reference is not None else {}
        # 落ちても止めず、軽い設定・小さい大きさ・別の模型・別の種と段を下げて描く（engine.Studio.draw_anyway）
        draw = getattr(self.studio, "draw_anyway", None) or self.studio.draw   # 段を下げる形を持たない描き手（試験の偽物など）はそのまま描く
        prompt, path = draw(self.text, seed, on_status=self._say, base=self.base, strength=self.strength, size=self.size,
                            on_preview=self._preview, style=self.style, meta=self.meta, **extra)
        self._stopped()
        preload(path)   # 置くときに画面の糸で絵を読まないよう、ここ（裏の糸）で先に読む
        self.one.emit(prompt, str(path))

    def _draw_all(self):
        """枚数分を描く。1 枚が描けなくても残りを描き続け、描けなかった枚と理由を覚えて最後に知らせる。
        前は 1 枚の例外が外へ抜けて、まだ描いていない枚まで全部取り消された"""
        from atelier.app import debug_log as debuglog
        from atelier.ai.engine import Stopped, explain
        self.drawn, self.reasons = 0, []
        many = len(self.seeds) > 1
        for i, seed in enumerate(self.seeds, 1):
            debuglog.log("工程", f"{i}/{len(self.seeds)} 枚目を描きます（種 {seed}）", mem=True)
            self.status.emit(f"{i}/{len(self.seeds)} 枚目を描きます")   # 進みの見出しに何枚目かを出す
            try:
                self._draw_one(seed)
                self.drawn += 1
            except Stopped:
                raise
            except Exception as e:   # noqa: BLE001  1 枚だけの失敗で、ほかの枚を取り消さない
                from atelier.files import pause_keep as pausekeep
                if not many or "描きません" in str(e) or pausekeep.is_pause(e):   # メモリ・時間の打ち切りは一時停止にして残りを残す
                    raise   # 1 枚だけの頼みと、描かない頼み（childsafe）は、今までどおり理由を返して終える
                self.trace = debuglog.exception(f"{i} 枚目", e)
                self.reasons.append(f"{i} 枚目: {explain(e)}")
                self.status.emit(f"{i} 枚目は描けませんでした（{explain(e)}）。残りを描きます")
        if many and not self.drawn:
            raise RuntimeError("、".join(self.reasons[:3]))

    def _stopped(self):
        """止められたあとに返ってきた絵（直しの途中で抜けた物など）は置かずに捨てる。キャンバスは元のまま"""
        from atelier.ai.engine import STOP, Stopped
        if STOP.is_set() or getattr(self.studio.painter, "stop", False) is True:
            raise Stopped("止めました")


PAUSED_HEAD = "一時停止しました: "   # fail がこの頭を見て「再開」のボタンを出す


def fresh_stop(studio=None):
    """裏の 1 回分を始める前に、止める旗を戻す（戻すのはここだけ）"""
    from atelier.ai.engine import STOP
    STOP.clear()
    painter = getattr(studio, "painter", None)
    if painter is not None and "stop" in vars(painter):
        painter.stop = False   # 試験の偽の模型など、自分の旗を持つ物


def guarded(obj, body):
    """裏の 1 回分を、1 つずつ・止められる形で走らせる。前の回が止めたあとの後片付け中なら終わるのを待つ。
    緊急停止が投げ込む Stopped は、どこで届いても failed で返す"""
    import threading
    from atelier.ai.engine import WORK, Stopped
    try:
        if not WORK.acquire(blocking=False):
            obj.status.emit("前の処理の後片付けを待っています")
            WORK.acquire()
        try:
            obj.tid = threading.get_ident()
            body()
        finally:
            obj.tid = None
            WORK.release()
    except Stopped:
        obj.failed.emit("止めました")
    except BaseException as e:   # noqa: BLE001  落ちても画面に必ず返す
        from atelier.app import debug_log as debuglog
        obj.trace = debuglog.exception("裏の処理", e)
        obj.failed.emit(f"できませんでした: {e}")


class Task(QObject):
    """時間のかかる処理（拡大など）を裏で回す。fn(on_step) の返りを done で返す"""
    status = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.tid = None
        fresh_stop()

    def _step(self, i, n):
        from atelier.ai.engine import check_stop
        check_stop()
        self.status.emit(f"描いています（{i}/{n}）")

    def run(self):
        guarded(self, self._run)

    def _run(self):
        try:
            self.done.emit(self.fn(self._step))
        except Exception as e:
            from atelier.ai.engine import explain
            self.failed.emit(f"できませんでした: {explain(e)}")


class Bridge(QObject):
    """裏の糸（threading）から画面へ結果を渡す"""
    got = Signal(object)
