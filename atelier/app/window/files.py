"""作業ファイルの開閉と保存、書き出し、自動保存、更新、続きからの再開"""
from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QDockWidget
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QMessageBox
from atelier.app.window.image_convert import qimage_to_pil
from atelier.app.window.jobs import Bridge
from atelier.app.window.jobs import Job
from atelier.app.window.process_check import crashed_before
from pathlib import Path
import os
import time


class FilesMixin:
    """作業ファイルの開閉と保存、書き出し、自動保存、更新、続きからの再開（Window が継承する）"""

    def outpaint_canvas(self, left: int, top: int, right: int, bottom: int, background: bool = False):
        """絵の外へ広げる。広げた絵でキャンバスを置き換える（元に戻すで戻せる）。使えないときは理由を出して止めない"""
        from atelier.ai import finishers
        base = qimage_to_pil(self.canvas.flatten()).convert("RGB")
        known = (getattr(self, "edit_meta", None) or {}).get("prompt", "")
        last, words = self.last_text, self.studio.words

        def to_prompt():   # 言葉の模型に聞くので、裏の糸で呼ぶ（画面の糸で読むと数秒〜数十秒固まる）
            # 括弧が無いと「(known or 訳) if last else ""」と読まれ、開いて直す絵（頼みが無く、言葉だけ残る）で言葉を捨てた
            return known or (words.to_prompt(last) if last else "")
        painter, seed = getattr(self.studio, "painter", None), self.ai_panel.seed.value()
        if background:   # 描くのは模型なので裏の糸で回す（画面の糸で回すと描き終えるまで固まる）
            if self.busy("絵の外へ広げる"):
                return None
            if painter is None:
                self.notify("広げられませんでした", "info", "絵の模型がまだ読めていません。AI の欄で模型を選んでください")
                return None
            self.activity.begin("絵の外へ広げる", "広げる")
            path = self._finished_path("outpaint")
            meta = dict(getattr(self, "edit_meta", None) or {}, text=last, mode="広げる", grow=[left, top, right, bottom])

            def work(_step):
                prompt = to_prompt()
                out = finishers.outpaint(base, left, top, right, bottom, painter=painter, prompt=prompt, seed=seed)
                return self._save_out(out, path, dict(meta, prompt=prompt)), prompt
            self._run_task(work, lambda got: (self._place_outpaint(got[0], got[1], left, top, right, bottom, path),
                                              self._end("絵の外へ広げました")))
            return None
        prompt = to_prompt()
        try:
            out = finishers.outpaint(base, left, top, right, bottom, painter=painter, prompt=prompt, seed=seed)
        except finishers.Unavailable as e:
            self.notify("広げられませんでした", "info", str(e))
            return None
        except Exception as e:  # 道具の中の失敗も、止めずに理由を出す
            from atelier.ai.engine import explain
            self.notify("広げられませんでした", "error", explain(e))
            return None
        return self._place_outpaint(out, prompt, left, top, right, bottom)

    def _place_outpaint(self, out, prompt, left, top, right, bottom, path: Path | None = None):
        if path is None:
            path = self._finished_path("outpaint")
            self._save_out(out, path, dict(getattr(self, "edit_meta", None) or {}, text=self.last_text, prompt=prompt,
                                           mode="広げる", grow=[left, top, right, bottom]))
        self.put_result(str(path), "広げた絵", replace=True)
        self.notify("絵の外へ広げました", "ok", "元の絵の画素はそのままです。広げた所を見て、使うか元に戻すかを決めてください")
        return path

    def merge_and_overwrite(self):
        """見えているレイヤーを結合し、開いた元の画像に上書きで保存する。上書きの前に元の画像の控えを取る"""
        import shutil
        import time
        from atelier.files.paths import HOME
        src = getattr(self, "source_path", None)
        if not src or not Path(src).is_file():
            self.notify("上書きする元の画像がありません", "info", "画像を開いてから使います。作業ファイルは「保存」で保存します")
            return
        from atelier.ui import confirm
        if confirm.ask(self, "overwrite", "元の画像に上書き", f"見えているレイヤーを結合して、\n{src}\nに上書きします。\n"
                       "元の画像の控えをアプリのデータの backup に残します。", [("yes", "上書きする")]) != "yes":
            return
        backup = HOME / "backup" / f"{Path(src).stem}-{time.strftime('%Y%m%d-%H%M%S')}{Path(src).suffix}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, backup)
        self.canvas.merge_visible(Path(src).stem)
        if not self.canvas.flatten().save(src):
            self.notify("上書きできませんでした", "error", f"控えは {backup} にあります")
            return
        self.dirty = False
        self.statusBar().showMessage(f"上書きしました。元の画像の控え: {backup}", 8000)

    def open_path(self, path: str, restore: bool = False):
        from atelier.files import project_file as project
        if not Path(path).is_file():   # 消した・動かした絵。黙って白いキャンバスにしない
            self.notify("開けませんでした", "error", f"ファイルが見つかりません（{path}）")
            return
        self.work_save()
        self.inspect_prompt = ""   # 開いた絵は描いた言葉が分からない。前の絵の言葉で頼んだ物を検品しない
        self.work_key = None   # 作業ファイル・手元の絵は、そのファイルに保存する（絵ごとの作業の置き場は使わない）
        is_project = path.lower().endswith(project.READABLE)   # 前の形（CharacterDesigner の作業ファイル）も開ける
        self._fix_from = None if is_project else path   # 記録の無い絵は、直すときに絵からタグを読む
        if is_project:
            # 読んで PNG を戻すのは裏の糸。置くのは画面の糸（レイヤーが多いと 0.1 秒を超えた）
            def done(got):
                if isinstance(got, BaseException):
                    self.notify("開けませんでした", "error", str(got))
                    return
                project.apply(self.canvas, got)
                # 自動保存から戻したときは、自動保存の場所に上書き保存しない
                own = path.lower().endswith(project.SUFFIX)   # 前の形のファイルには上書きしない（保存のときに置き場を聞く）
                self.project_path, self.dirty = (None, True) if restore else (path if own else None, False)
            self.run_io(lambda: project.read(path), done, "読み込み")
            return
        else:
            self.canvas.show_image(path)
            self.project_path = None
            self.source_path = str(path)
        self.dirty = False

    def new_blank(self, w: int = 1200, h: int = 1600):
        """白い新しいキャンバスにする。前は積み重ねごと消していたので、描いた絵が元に戻すで戻らなかった
        （説明には「戻せます」と書いてあった）。前の絵を 1 手として積み、作業ファイルの道も外す
        （外さないと、続けて保存したとき前の作業ファイルを白い絵で上書きした）"""
        from PySide6.QtGui import QColor
        from atelier.paint.canvas import Layer, blank
        c = self.canvas
        if not c.layers:
            c.new_canvas(w, h)
        else:
            c.snapshot_all()
            c._clear_marks()   # replace_with_image と同じく、前の絵の赤ペンの枠を残さない
            c.layers = [Layer("背景", blank(w, h, QColor("white"))), Layer("レイヤー 1", blank(w, h))]
            c.current = 1
            c.sym_center = None
            c.set_selection(None)
            c.rebuild()
            c.fit()
        self.project_path, self.source_path = None, None
        self.statusBar().showMessage("新しいキャンバスにしました（元に戻すで前の絵に戻せます）", 4000)

    def save_project(self, ask: bool = False, wait: bool = False) -> bool:
        """作業ファイル（レイヤー・赤ペンの印ごと）に保存する。初めてか ask なら置き場を聞く。
        書くのは裏の糸（PNG に縮めるのに 1 枚 0.1〜0.3 秒かかり、その間描けなかった）。wait なら書き終えるまで待つ
        （閉じる前・拡大の前など、保存できたかで次を決めるとき）。書き始めたか書けたら True"""
        from atelier.files import project_file as project
        path = getattr(self, "project_path", None)
        if ask or not path:
            if self.tour_first("project", lambda: self.save_project(ask)):
                return False
            path, _ = QFileDialog.getSaveFileName(self, "作業ファイルを保存", "drawing" + project.SUFFIX,
                                                  f"作業ファイル (*{project.SUFFIX})")
            if not path:
                return False
            if not path.endswith(project.SUFFIX):
                path += project.SUFFIX
        snap = project.snapshot(self.canvas)
        if wait:
            try:
                project.write(snap, path)
            except OSError as e:
                self.notify("保存できませんでした", "error", f"{e}\n保存先に書き込めるか、ディスクに空きがあるかを確かめてください")
                return False
            self.project_path, self.dirty = path, False
            self.statusBar().showMessage("保存しました", 3000)   # 「保存しています…」を残すと、終わったのか分からなかった
            self.notify("保存しました", "ok", Path(path).name)
            return True
        self.project_path, self.dirty = path, False
        self.statusBar().showMessage("保存しています…")

        def done(err):
            if isinstance(err, BaseException):
                self.dirty = True
                self.notify("保存できませんでした", "error", f"{err}\n保存先に書き込めるか、ディスクに空きがあるかを確かめてください")
                return
            self.statusBar().showMessage("保存しました", 3000)   # 「保存しています…」を残すと、終わったのか分からなかった
            self.notify("保存しました", "ok", Path(path).name)
        self.run_io(lambda: project.write(snap, path), done, "保存")
        return True

    def run_io(self, work, done, name: str = "保存・読み込み"):
        """保存・読み込みなどの書き物を裏の糸で回す。同じ置き場に重ねて書かないよう、1 本の列に並べて順に書く"""
        if getattr(self, "_io_closed", False):
            # 閉じたあとに呼ばれた書き物（閉じる途中の作業の保持など）は、糸を作り直さずにその場で書く（糸が窓ごとに残らないように）
            try:
                work()
            except Exception:   # noqa: BLE001  閉じたあとは知らせる先が無い
                pass
            return
        import queue
        import threading
        if getattr(self, "_io_queue", None) is None:
            self._io_queue = queue.Queue()

            import weakref
            ref = weakref.ref(self)

            # 裏の糸は窓を弱くだけ持つ。強く持つと、閉じた窓が消えずに残り（窓を開くたびに 1 本ずつ増えた）、
            # 消えた窓へ答えを返そうとしてアプリごと落ちた。閉じたら None を入れて糸を終える
            def loop(q):
                while True:
                    item = q.get()
                    if item is None:
                        q.task_done()
                        return
                    fn, key = item
                    try:
                        v = fn()
                    except BaseException as e:   # noqa: BLE001  裏で落ちても画面の糸に必ず返す
                        v = e
                    fn = item = None   # 次を待つ間、終わった仕事を持ち続けない
                    w = ref()
                    if w is not None and not getattr(w, "_io_closed", False):
                        try:
                            w._bg_emit(key, v)
                        except RuntimeError:   # 窓の C++ の側がもう消えている
                            pass
                    w = None
                    q.task_done()
            threading.Thread(target=loop, args=(self._io_queue,), name="io", daemon=True).start()
        self._io_queue.put((work, self._bg_register(done, name)))

    def _bg_done(self, got):
        """裏の糸の答えを画面の糸で受ける。done が落ちても数は戻す（数が残ると、試験と閉じる前の待ちが終わらない）"""
        key, v = got
        done = self._waiting.pop(key, None)
        self.bg_pending -= 1
        self.activity.bg_end(key)
        if done is not None:
            done(v)

    def wait_io(self, sec: float = 30.0):
        """裏で書いている物を書き終えるまで待つ（閉じる前に、途中のファイルを残さない）"""
        q = getattr(self, "_io_queue", None)
        end = time.time() + sec
        while q is not None and q.unfinished_tasks and time.time() < end:
            time.sleep(0.01)

    def export_psd(self):
        from atelier.files import project_file as project
        dst, _ = QFileDialog.getSaveFileName(self, "PSD で書き出す", "drawing.psd", "PSD (*.psd)")
        if not dst:
            return
        snap, n = project.psd_snapshot(self.canvas), len(self.canvas.layers)
        self.statusBar().showMessage("PSD を書き出しています…")
        self.run_io(lambda: project.write_psd(snap, dst),
                    lambda err: self.notify("書き出せませんでした", "error", f"{err}\n書き出す先に書き込めるかを確かめてください") if isinstance(err, BaseException)
                    else self.notify("書き出しました", "ok", f"{Path(dst).name}（レイヤー {n} 枚）"))

    def autosave(self):
        """変わっていれば、決まった置き場に作業ファイルを書く。落ちたときに次の起動で戻せるように"""
        from atelier.files import project_file as project
        if not getattr(self, "dirty", False) or not self.canvas.layers:
            return
        if getattr(self, "_autosaving", False):
            return   # 前の自動保存がまだ書き終わっていない
        path = project.autosave_path()
        snap = project.snapshot(self.canvas)   # 写すのは画面の糸、書くのは裏の糸（前は 2 分ごとに 1 秒近く固まった）
        self._autosaving = True

        def work():
            path.parent.mkdir(parents=True, exist_ok=True)
            project.write(snap, path)

        def done(err):
            self._autosaving = False
            if not isinstance(err, BaseException):   # 自動保存が書けなくても、描く邪魔はしない
                self.autosaved = True
        self.run_io(work, done)

    def check_update(self, manual: bool = False):
        """新しい版があるかを裏で確かめる。自分で頼んだとき以外は 1 日に 1 回だけ"""
        import datetime
        import threading
        from atelier.app import updater
        today = datetime.date.today().isoformat()
        if not manual and self.layout_store.value("update_checked", "") == today:
            return
        self.layout_store.setValue("update_checked", today)
        self.update_bridge = Bridge()
        self.update_bridge.got.connect(lambda info: self._update_found(info, manual))

        def run():
            try:
                info = updater.check(quiet=False)
            except Exception as e:   # noqa: BLE001  確かめられなかったことを画面の糸に返す
                info = {"error": str(e) or type(e).__name__}
            self.update_bridge.got.emit(info)
        threading.Thread(target=run, daemon=True).start()

    def _update_found(self, info, manual: bool):
        from atelier.app import updater
        if info and info.get("error"):
            if manual:   # 自分で押したときだけ知らせる（起動時の確かめは黙る）
                self.notify("更新を確かめられませんでした", "error", "ネットに届きませんでした: " + info["error"][:120])
            return
        if not info:
            if manual:
                self.notify("今の版が最新です", "ok", f"版 {updater.current()}")
            return
        self.update_info = info
        self.notify(f"新しい版 {info['version']} があります", "info", "押すと取って、入れるかを聞きます",
                    on_click=self.get_update)

    def get_update(self):
        """新しい Setup.exe を取り、入れるかを聞く。入れるときはアプリを閉じてから Setup.exe を開く"""
        from atelier.app import updater
        info = getattr(self, "update_info", None)
        if not info or not info.get("setup"):
            self.notify("取れる Setup.exe がありません", "info", info.get("page", "") if info else "")
            return
        if self.thread:
            return
        self.activity.begin(f"版 {info['version']} を取る", "更新")
        self._run_task(lambda on_step: str(updater.download(info["setup"], lambda got, total: on_step(got >> 20, total >> 20))),
                       self._update_ready)

    def _update_ready(self, path: str):
        import os
        import subprocess
        import sys as _sys
        self.activity.end("取りました", None, record=False)
        self._end("取りました")
        box = QMessageBox(QMessageBox.Question, "更新を入れる",
                          "新しい版を取りました。アプリを閉じて入れますか。描いている絵は先に保存します。", parent=self)
        go = box.addButton("閉じて入れる", QMessageBox.AcceptRole)
        box.addButton("あとで", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            self.notify("あとで入れられます", "info", path)
            return
        if getattr(self, "dirty", False) and not self.save_project(wait=True):
            return
        if _sys.platform == "win32":
            os.startfile(path)   # noqa: S606  利用者が「閉じて入れる」を選んだときだけ開く
        else:
            subprocess.Popen([path])
        self.dirty = False
        self.close()

    def offer_paused(self) -> bool:
        """一時停止して残した件（atelier/files/pause_keep.py）があれば、進みの欄に「再開」を出す。起動したときの「続きから」もここ"""
        from atelier.files import pause_keep as pausekeep
        got = pausekeep.listing()
        if not got:
            self.activity.offer_resume(None)
            return False
        more = f"（ほかに {len(got) - 1} 件）" if len(got) > 1 else ""
        self.activity.offer_resume(f"続きから: {got[0]['label']}{more}　{got[0]['at']}", lambda: self.resume_paused(got[0]["key"]))
        dock = self.findChild(QDockWidget, "progress")
        if dock is not None and dock.isHidden():
            dock.show()   # 利用者が閉じていた欄でも、残した件があることに気づけるように出す
        self.notify("続きから始められます", "info", got[0]["label"] + "。進み具合の欄の「再開」で続けます")
        return True

    def resume_paused(self, k: str) -> bool:
        """残した件を続きから始める。工程に分けて描く回は、同じ頼み・種・模型で呼び直すと phases.py が残した工程から続ける"""
        from atelier.files import pause_keep as pausekeep
        rec = pausekeep.info(k)
        if rec is None or self.busy("再開"):
            return False
        job, kind = rec.get("job") or {}, rec.get("kind")
        if kind == "batch":
            pausekeep.clear(k)
            return self.batch_draw(jobs=job["jobs"], start=int(job.get("start", 0)))
        if kind == "fetch":
            from atelier.files.fetch_file import fetch_resumable
            self.activity.begin(rec["label"], "取得")
            self._run_task(lambda _s: fetch_resumable(job["url"], Path(job["dest"]), int(job.get("total") or 0),
                                                      note=self.task.status.emit),
                           lambda _p: (self.notify("取り終えました", "ok", Path(job["dest"]).name), self._end("取り終えました")))
            return True
        if kind == "draw":
            pausekeep.clear(k)   # 1 回で描く回は、まだ描いていない種から描き直す（途中の工程は持たない）
        self.say(f"続きから始めます: {rec['label']}")
        self.activity.begin(job.get("text", ""), "再開")
        self.button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.batch, self.batch_items = [], []
        self.job_kind = "draw"
        self.job_studio = self.studio
        self.thread = QThread()
        self.job = Job(self.studio, job.get("text", ""), job.get("seeds") or [0], style=job.get("style", ""),
                       meta=job.get("meta") or {}, size=tuple(job["size"]) if job.get("size") else self.size_pick.currentData())
        self._worker = self.job
        self.job.moveToThread(self.thread)
        self.thread.started.connect(self.job.run)
        self.job.status.connect(self.on_status)
        self.job.preview.connect(self.show_preview)
        self._record_job(self.job)
        self.job.one.connect(self.on_one)
        self.job.done.connect(self.finish)
        self.job.failed.connect(self.fail)
        self.gc_guard()
        self.thread.start()
        return True

    def offer_restore(self):
        """前に閉じずに終わっていて、自動保存が残っていれば、戻すかを聞く（自動保存は消さない）"""
        from atelier.files import project_file as project
        crashed = crashed_before(self.layout_store)
        self.layout_store.setValue("running", os.getpid())
        path = project.autosave_path()
        if not crashed or not path.exists():
            return False
        box = QMessageBox(QMessageBox.Question, "前の絵を戻す",
                          "前回は正しく閉じられませんでした。自動保存した絵を開きますか。", parent=self)
        yes = box.addButton("開く", QMessageBox.AcceptRole)
        box.addButton("開かない", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.open_path(str(path), restore=True)
            return True
        return False

    def save_as(self) -> bool:
        """保存できたら True"""
        if not self.canvas.layers:
            return False
        if self.tour_first("save", self.save_as):
            return False
        dst, _ = QFileDialog.getSaveFileName(self, "名前を付けて保存", "drawing.png", "PNG (*.png)")
        if not dst:
            return False
        ok = self.canvas.flatten().save(dst)
        self.notify("保存しました" if ok else "保存できませんでした", "ok" if ok else "error", Path(dst).name)
        return bool(ok)
