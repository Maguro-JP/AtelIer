"""結果の置き方、止める処理、裏の処理の後片付け、進みの表示"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QColorDialog
from atelier.app.window.constants import TOOLS
from atelier.app.window.image_convert import qimage_from_pil
from atelier.app.window.jobs import Job
from atelier.app.window.jobs import PAUSED_HEAD
from atelier.app.window.jobs import Task
from atelier.ui.icons import icon
from pathlib import Path
import sys
import time


class ResultsAndProgressMixin:
    """結果の置き方、止める処理、裏の処理の後片付け、進みの表示（Window が継承する）"""

    def show_preview(self, img):
        """AI が描いている途中の絵を、工程ごとにキャンバスの上に重ねて見せ、タイムラプスにも残す。
        描き終えたあとに遅れて届いた途中の絵は捨てる（仕上がった絵を隠さない）"""
        if self.thread is None:
            return
        q = qimage_from_pil(img)
        self.canvas.show_overlay(q)
        self.progress_popup.set_thumb(q)   # 進みのポップアップにも途中の絵を小さく出す
        self.recorder.add(img)

    def put_result(self, path: str, name: str, replace: bool = False) -> bool:
        """AI の結果を置く。設定「AI の結果の置き場」が「別ファイル」なら新しい作業ファイル（別のウィンドウ）で開き、
        今のキャンバスには触らない。既定の「上のレイヤー」なら一番上の新しいレイヤーに置いて選ぶ。キャンバスに置いたら True"""
        if self.settings.get("result_place") == "別ファイル":
            self.open_in_new_file(path)
            return False
        self.canvas.place_result(path, name, replace=replace)
        return True

    def _put_fix(self, path: str, name: str) -> bool:
        """囲んだ所の直しは、直した所だけのレイヤーにして置く。絵全体の写しを重ねると、
        囲みの外まで同じ絵のレイヤーが積み重なり、邪魔で見分けにくかった"""
        import os
        import tempfile
        from PySide6.QtGui import QImage, QPainter
        if self.settings.get("result_place") == "別ファイル":
            return self.put_result(path, name)
        masks = list(self.canvas.redpen.masks())
        sel = self.canvas.selection_mask()
        if sel is not None:
            masks.append(sel)
        img = QImage(path)
        if not masks or img.isNull():
            return self.put_result(path, name)
        had_alpha = img.hasAlphaChannel()
        img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied if had_alpha else QImage.Format_ARGB32)
        alpha = QImage(img.size(), QImage.Format_Grayscale8)
        alpha.fill(0)
        q = QPainter(alpha)
        q.setCompositionMode(QPainter.CompositionMode_Lighten)
        for m in masks:   # 見えている印ごとの直す所を重ねる（白が直す所。隠した印は空なので出ない）
            q.drawImage(0, 0, m.scaled(img.size()))
        q.end()
        if had_alpha:
            # Studio.fix は直した所だけを不透明にして返すが、継ぎ目をなじませる縁が囲みの外へ数画素はみ出し、
            # 囲みの外が変わった（窓で直して 2,114 画素）。返った透明度を囲みの中だけに絞り、囲みの外は 1 画素も変えない
            cut = QImage(img.size(), QImage.Format_ARGB32)
            cut.fill(0xFFFFFFFF)
            cut.setAlphaChannel(alpha)
            q = QPainter(img)
            q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            q.drawImage(0, 0, cut)
            q.end()
        else:
            img.setAlphaChannel(alpha)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            img.save(tmp)
            return self.put_result(tmp, name)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def open_in_new_file(self, path: str):
        """絵を新しい作業ファイルとして、別のウィンドウで開く。今の作業ファイルはそのまま残る"""
        from PySide6.QtCore import QProcess
        args = ["--open", str(path)] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve()), "--open", str(path)]
        if not QProcess.startDetached(sys.executable, args):
            self.notify("別ファイルで開けませんでした", "error", str(path))

    def place(self, path: str):
        """描けた絵を置く。新しく描いて、まだ何も描いていないキャンバスなら絵を開く。
        キャンバスを元に描いたときと、描いている途中なら、元の絵を残して新しいレイヤーとして重ねる"""
        if self.mode.currentIndex() == 0:
            # 新しく描いた絵は、いつも同じ形で置く（キャンバスを置き換え、前の状態は元に戻すで戻せる）。
            # 前は、キャンバスの状態で置き換えたり上に重ねたりが変わり、大きさの違う絵が重なった
            self.work_save()   # 前の絵の作業を残してから置き換える
            if self.put_result(path, f"AI の絵 {len(self.images)}", replace=True):
                self.work_key = str(path)
            self.origin_prompt = getattr(self, "last_text", "")   # 直しのときに、元の頼みと食い違いを見る
        else:
            self.put_result(path, f"AI の絵 {len(self.images)}")
            self.canvas.fit()   # 結果は全体表示で見せる
        self._placed = path
        self._fix_from = path   # 赤ペンで直すときに、この絵を描いたときの言葉を渡す

    def stop(self):
        """緊急停止。押したら必ず止まる。
        1. 止める旗を立てる（工程の区切りで止まる）
        2. 旗を見ない重い工程（模型の読み込み、言葉の模型の答え待ち、検品、仕上げ）の裏の糸へ Stopped を投げ込む
        3. 裏の糸の終わりを待たずに、画面をすぐ待機に戻す。止めた回の答えは捨てる（キャンバスは元のまま）
        4. 裏の糸が終わったら、メモリを返す（_reap）"""
        from atelier.ai import engine
        t0 = time.time()
        engine.STOP.set()
        for st in (self.studio, getattr(self, "job_studio", None)):
            painter = getattr(st, "painter", None)
            if painter is not None:
                try:
                    painter.stop = True
                except AttributeError:
                    pass
        if getattr(self, "asking", False):   # 言葉の模型に頼みの種類を聞いている途中
            self.asking = False
            self._ask_token = getattr(self, "_ask_token", 0) + 1   # 返ってきた答えは捨てる
            self.button.setEnabled(True)
        worker, obj = self.thread, getattr(self, "_worker", None)
        if worker is None:
            self.statusBar().showMessage("止めました" if getattr(self, "asking", None) is False else "動いている処理はありません", 3000)
            self.activity.idle_check()
            return
        engine.kill_thread(getattr(obj, "tid", None))
        if obj is not None:
            obj.failed.connect(worker.quit)
            obj.done.connect(worker.quit)
        self._zombies = getattr(self, "_zombies", [])
        self._zombies.append((worker, obj, t0))
        worker.finished.connect(self._reap)
        if not worker.isRunning():
            worker.quit()
        self.thread, self._worker = None, None
        self.canvas.show_overlay(None)
        if self.activity.started is not None:
            self.activity.end("止めました")
        self.stop_button.setEnabled(False)
        self.button.setEnabled(True)
        stopped = self._put_stopped_phases() if hasattr(self, "_put_stopped_phases") else None
        if stopped:   # 精度優先で描いていた回は、止めた所までの絵をレイヤーに置き、残った崩れと何工程目で止めたかを出す
            self.progress_popup.tell(stopped[0], stopped[1])
            self.notify(stopped[0], "info", stopped[1])
        else:
            self.progress_popup.tell("止めました", "キャンバスは元のままです")
            self.notify("止めました", "info", "")
        self.hide_progress_if_idle()
        self.last_stop_ui = time.time() - t0
        self.statusBar().showMessage(f"止めました（{self.last_stop_ui:.2f} 秒）", 4000)

    def finish_threads_before_close(self, wait_ms: int = 5000) -> bool:
        """描いている途中に閉じたら、止めて裏の糸の終わりを待つ。動いている QThread を消すと、Qt がアプリごと落とす
        （QThread: Destroyed while thread is still running）。待っても終わらなければ窓だけ隠し、終わってから閉じ直す。閉じてよければ True"""
        if self.thread is not None:
            self.stop()
        left = [w for w, _o, _t in getattr(self, "_zombies", []) if w.isRunning()]
        for w in left:
            w.wait(wait_ms)
        left = [w for w in left if w.isRunning()]
        if not left:
            return True
        self.closing_checked = True   # 保存を聞くのは 1 回だけ
        self.hide()
        for w in left:
            w.finished.connect(self.close, Qt.QueuedConnection)
        return False

    def _stale(self) -> bool:
        """止めた回の裏の処理から遅れて届いた知らせか。止めた回の絵はキャンバスに置かない"""
        src = self.sender()
        return src is not None and isinstance(src, (Job, Task)) and src is not getattr(self, "_worker", None)

    def _reap(self):
        """止めた回の裏の糸が終わった。糸を片付け、描きかけの物を捨ててメモリを返す"""
        import gc
        left = []
        for worker, obj, t0 in getattr(self, "_zombies", []):
            if worker.isRunning():
                left.append((worker, obj, t0))
                continue
            self.last_stop_secs = time.time() - t0
            worker.deleteLater()
            if obj is not None:
                obj.deleteLater()
        self._zombies = left
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None:
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:   # noqa: BLE001  返せなくても止めたことは変わらない
                pass
        self.gc_guard()
        if getattr(self, "_unload_after", False) and not left:
            self._unload_after = False
            self.studio.painter.unload()

    def drawing(self) -> bool:
        return self.thread is not None

    def unload_model(self, repo: str | None = None) -> str:
        """読んだ絵の模型をメモリから降ろす。描いている途中なら止めて、終わってから降ろす"""
        painter = self.studio.painter
        if repo is not None and painter.model != repo:
            return "その模型は読んでいません"
        if self.drawing():
            self._unload_after = True
            self.stop()
            return "止めてから、メモリから降ろします"
        painter.unload()
        return "メモリから降ろしました。次に描くときに読み直します"

    def _redpen_changed(self):
        """赤ペンの印が増えた・消えたとき。印が無くなったら「直す」をやめて新しく描くに戻す。
        印が無いのに「直す」のままだと、次の頼みまで直しとして扱われた。
        道具はここでは替えない。印を付けたあと・直したあとに勝手にペンへ戻ると、続けて囲めなかった"""
        if hasattr(self, "layer_panel"):
            self._refresh_layers()
        c = self.canvas
        box = getattr(self, "note_box", None)
        fewer = len(c.redpen.marks) < getattr(self, "_marks_seen", 0)
        self._marks_seen = len(c.redpen.marks)
        if box is not None and box.isVisible() and (fewer or not 1 <= getattr(self, "note_n", 0) <= len(c.redpen.marks)):
            box.hide()   # 消えた印の指示の欄を残さない（印を消した・直し終えた・絵を替えたあとも枠と欄が残っていた）
        if c.redpen.marks or c.selection is not None:
            return
        if self.mode.currentIndex() == 2:
            self.mode.setCurrentIndex(0)

    def _mode_changed(self, i: int):
        # 直すとき（赤ペン）は描くボタンの文字を替え、押せば囲んだ所を直すと分かるようにする
        if hasattr(self, "button"):
            self.button.setText(" 囲んだ所を直す" if i == 2 else " 描く")
            self.button.setToolTip("赤ペンで囲んだ所だけを、書いた指示どおりに直します（Enter）。囲みの外は変えません" if i == 2
                                   else "AI で描く（Enter）")
        if i == 1 and hasattr(self, "layout_store"):
            self.feature_tour("rough")
        if i == 2 and hasattr(self, "layout_store"):
            self.feature_tour("redpen")
        self.size_pick.setEnabled(i == 0)          # 元に描くときはキャンバスの大きさで描く
        self.strength.setEnabled(i in (1, 2))
        self.strength_label.setEnabled(i in (1, 2))
        if i == 2 and self.strength.value() > 60:
            self.strength.setValue(45)   # 直すときは元の絵を土台に少しだけ変える（微調整）。足りなければもう一度直す
        self.strength.setToolTip("直す強さ。小さいほど元の絵のまま少しだけ直す" if i == 2 else
                                 "ラフに沿う強さ。大きいほどラフの線の形どおりに描く")

    def fail(self, why: str):
        if self._stale():
            return
        if getattr(self, "_fix_hid", None):
            self._end_fix_only()
        self.canvas.show_overlay(None)
        why = (why or "うまくいきませんでした").strip().splitlines()[0]   # 何が起きたかを 1 行で出す（「描けませんでした」の決まり文句は出さない）
        if why.startswith(PAUSED_HEAD) or "一時停止" in why:   # 止めて捨てずに残した。進みの欄に「再開」を出す
            self.offer_paused()
        stop = "止め" in why and "一時停止" not in why
        self.say(why)
        if not stop:
            self._debug_failure("描けませんでした", why, getattr(self.sender(), "trace", "") or getattr(getattr(self, "job", None), "trace", ""))
        if self.activity.started is not None:
            self.activity.end("止めました" if stop else why)
        # 進みの欄の 1 回分の外で落ちたときも、理由を右下に出す（出さないと何も起きなかったように見えた）
        self.progress_popup.tell("止めました" if stop else why, "" if stop else why)
        self.notify("止めました" if stop else why, "info" if stop or "一時停止" in why else "error", "")
        self._end(why)

    def pick_color(self):
        c = QColorDialog.getColor(self.canvas.color, self, "色")
        if c.isValid():
            self.color_panel.set_color(c)

    def ask_text(self, pos):
        """文字の道具で押した所に置く文字を聞く。空なら何もしない"""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "文字", "置く文字（描く色・太さの 4 倍の大きさで置きます）")
        if ok and text:
            self.canvas.place_text(pos, text)

    def _brush_selected(self, name: str):
        if name not in self.canvas.brushes:
            return
        self.canvas.set_brush(name)
        b = self.canvas.brush
        for w, v in ((self.hardness, b.hardness), (self.flow_s, b.flow), (self.spacing, b.spacing)):
            w.blockSignals(True)
            w.setValue(int(v * 100))
            w.blockSignals(False)
        for w, v in ((self.size_pressure, b.size_pressure), (self.opacity_pressure, b.opacity_pressure)):
            w.blockSignals(True)
            w.setChecked(v)
            w.blockSignals(False)
        key = "eraser" if name == "消しゴム" else "pen"
        if key in getattr(self, "tool_actions", {}):
            self.tool_actions[key].setChecked(True)

    def _tool_changed(self, key: str):
        """上の道具の設定の見出しを、選んだ道具の名前にする"""
        label = next(lb for k, lb, _s in TOOLS if k == key)
        self.tool_name.setText(label)
        if hasattr(self, "st_tool"):
            self.st_tool.setText(label)
        if hasattr(self, "fill_shapes_act"):
            self.fill_shapes_act.setVisible(key in ("rect", "ellipse", "polyshape", "regpoly"))
        if hasattr(self, "poly_sides_act"):
            self.poly_sides_act.setVisible(key == "regpoly")
        if hasattr(self, "redpen_shape_bar"):
            self.redpen_shape_bar.setVisible(key == "redpen")
        if hasattr(self, "brush_preview"):
            self.brush_preview.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "progress_popup"):
            self.progress_popup.place()
        if not getattr(self, "_settle_queued", False):   # 大きさが変わったら、収まらなくなった欄の高さを配り直す
            self._settle_queued = True
            from PySide6.QtCore import QTimer

            def again():
                self._settle_queued = False
                from atelier.ui.layouts import settle
                settle(self)
            QTimer.singleShot(0, again)

    def hide_progress_if_idle(self, ms: int = 4000):
        """進みの欄は自分では隠さない。描き終わると消えて、結果も今の状態も分からなかった。閉じるのは利用者だけ"""

    def watch_fetch(self, fetcher, what: str = "模型"):
        """模型を取る進みを、描く進みと同じ右下のポップアップに出す。模型の管理を閉じたあとも、取り終わるまで進みが見える"""
        # 取り始めは新しい 1 回分。前の 1 回分を × で閉じたままだと、取る進みが一度も出なかった
        self.progress_popup._new_run()
        fetcher.progress.connect(lambda msg, pct: self.progress_popup.tell(f"{what}を取っています", msg, pct), Qt.QueuedConnection)
        fetcher.finished.connect(lambda err: self.progress_popup.tell("取れませんでした" if err else "取りました",
                                                                      err or f"{what}を取り終わりました"), Qt.QueuedConnection)

    def show_progress(self, text: str, pct: int):
        """進みをウィンドウの外にも出す。タイトル（タスクバーに出る）、通知の領域のアイコン、終わったときの知らせ"""
        base = "AtelIer"
        if pct == -2:
            self.setWindowTitle(base)
        else:
            self.setWindowTitle(f"{pct}% {text} - {base}" if pct >= 0 else f"{text} - {base}")
        tray = self._tray()
        if tray is not None:
            tray.setToolTip(text if pct < 0 else f"{text}（{pct}%）")
        if pct == -2:
            self.tell_outside("AtelIer", text)

    def _tray(self):
        from PySide6.QtWidgets import QSystemTrayIcon
        if getattr(self, "tray", None) is None:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return None
            self.tray = QSystemTrayIcon(self.windowIcon() if not self.windowIcon().isNull() else icon("ai"), self)
            self.tray.activated.connect(lambda *_: (self.showNormal() if self.isMinimized() else None, self.raise_(),
                                                    self.activateWindow()))
            self.tray.show()
        return self.tray

    def tell_outside(self, title: str, text: str):
        """ほかのウィンドウを見ている間に終わったら、デスクトップの通知とタスクバーの点滅で知らせる（設定の「知らせ」）"""
        if self.settings.get("notify") == "画面の中だけ" or (self.isActiveWindow() and not self.isMinimized()):
            return
        QApplication.alert(self, 0)
        tray = self._tray()
        if tray is not None:
            tray.showMessage(title, text, tray.icon(), 8000)

    def _end(self, msg: str):
        self.statusBar().showMessage(msg, 4000)
        # 加工などで始めた進みの表示も終える。終えないと「確認中」のまま止まって見えた
        act = getattr(self, "activity", None)
        if act is not None and getattr(act, "started", None):
            act.end(msg, None, record=False)
        self.stop_button.setEnabled(False)
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self.button.setEnabled(True)
        self.hide_progress_if_idle()
        if getattr(self, "_unload_after", False):
            self._unload_after = False
            self.studio.painter.unload()
