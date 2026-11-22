"""入れた版が Windows の上で最後まで動くかを通しで確かめる（GitHub Actions の Windows の機械で流す）。

    python -E -s -m atelier.bench.end_to_end <出力の置き場>

手元で段の組み立てだけを見るときは ATELIER_E2E_NO_FETCH=1 を付ける（取る段を飛ばし、torch の要る段は落ちる）。

利用者が踏む順に、本物の経路を通す。
1. ウィンドウを開き、画面の中に収まっているか
2. 初回の取得（Fetcher.run）で、描く部品（CPU 版の torch など）を ProgramData に入れ、絵の模型とラフの部品を取る
3. 取った模型で 1 枚描き、絵が保存されるか
4. ラフから描く部品が取れているか
5. 検品の部品（部位分け・人の枠・タグ・体の点・手・足）が初回の取得で入ったか（atelier/qc/parts.py）
6. 右クリックのメニューと、工程に分けて描く（Studio を直に呼ぶ）
7. 窓から、利用者が押すのと同じメソッドを通す。
   描いた絵がキャンバスの一番上のレイヤーになるか、
   赤ペンの囲みの中だけが直るか（囲みの外の画素の変わった数を数える）、検品の結果が返るか、
   作業ファイルに保存して窓を開き直し、レイヤーの数と絵が同じか、精度優先で描いて工程ごとの絵が出るか

模型は数 GB あるので、形が同じで小さい試験用の SDXL（hf-internal-testing/tiny-stable-diffusion-xl-pipe）を使う。絵の出来は見ない。
結果は report.json に書き、1 つでも落ちたら終了コード 1 で終わる。
"""
from __future__ import annotations

import faulthandler
import json
import os
import sys
import time
import traceback
from pathlib import Path

TINY = "hf-internal-testing/tiny-stable-diffusion-xl-pipe"


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-out")
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    faulthandler.enable()
    report: dict = {"steps": []}

    def save_report():
        tmp = out / "report.json.tmp"
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(out / "report.json")

    def step(name, fn):
        t = time.time()
        print(f"START {name}", flush=True)
        try:
            detail = fn()
            report["steps"].append({"name": name, "ok": True, "seconds": round(time.time() - t, 1), "detail": detail})
            save_report()
            print(f"OK   {name}（{time.time() - t:.0f} 秒）{detail or ''}", flush=True)
            return True
        except Exception:
            error_text = traceback.format_exc()[-3000:]
            report["steps"].append({"name": name, "ok": False, "seconds": round(time.time() - t, 1),
                                    "error": error_text})
            print(f"FAIL {name}\\n{error_text}", flush=True)
            try:
                save_report()
            except Exception:
                print(f"FAIL report.json の保存\\n{traceback.format_exc()[-3000:]}", flush=True)
            return False

    import atelier.app.main_window as app   # 起動と同じ順に読む（出力の付け替え、環境の切り離し、部品の置き場）
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    app.dark(qapp)
    from atelier.ui import window_fit as fit
    fit.install(qapp)
    from atelier.models import catalog as models
    from atelier.models.catalog import FILES, ImageModel
    tiny = ImageModel(TINY, "試験用の小さな SDXL", "", "", 0.1, 2, 5.0, files=FILES["bin"], family="sdxl", score=0)
    models.IMAGES = models.IMAGES + (tiny,)

    def window():
        w = app.Window()
        w.show()
        for _ in range(20):
            qapp.processEvents()
            time.sleep(0.05)
        area = w.screen().availableGeometry()
        w.grab().save(str(out / "window.png"))
        return {"frame": list(w.frameGeometry().getRect()), "screen": list(area.getRect())}

    def fetch():
        from atelier.models.first_setup import Fetcher
        f = Fetcher()
        said, done = [], []
        f.progress.connect(lambda msg, pct: said.append(msg))
        f.finished.connect(lambda err: done.append(err))
        f.run(tiny, None)
        if done and done[0]:
            raise RuntimeError(done[0])
        return {"messages": said[-5:]}

    shot = {}

    def draw():
        from atelier.ai.engine import Painter, Studio, Words
        studio = Studio(Words(Path("")), Painter(TINY, steps=2, size=(256, 256)), out)
        prompt, path = studio.draw("1girl, adult woman, bikini", 1, size=(256, 256))
        shot["path"] = path
        if not Path(path).exists():
            raise RuntimeError(f"絵が保存されていない: {path}")
        return {"file": str(path), "prompt": prompt}

    def rough_parts():
        # 試験用の小さな模型は本物と形が違い、ラフの部品（本物の SDXL 用）と組めないので、取れて読めるかだけを見る
        from atelier.ai.engine import Painter
        if not Painter(TINY).sketch_ready():
            raise RuntimeError("ラフの部品が手元に無い")
        return {}

    ok = step("ウィンドウを開く", window)
    if os.environ.get("ATELIER_E2E_NO_FETCH"):
        # 手元で段の組み立てだけを見るとき。取ると torch と模型（数 GB）が手元に入る
        report["steps"].append({"name": "描く部品と模型を取る", "ok": False, "skipped": True})
        ok = False
    else:
        ok = step("描く部品と模型を取る", fetch) and ok
    ok = step("1 枚描く", draw) and ok
    ok = step("ラフの部品がそろう", rough_parts) and ok

    def qc_parts():
        # 初回の取得（Fetcher.run）が検品の部品も取ったかを、取らずに置き場だけで見る
        from atelier.qc import parts as qcparts
        lack = [p.name for p in qcparts.missing()]
        if lack:
            raise RuntimeError("検品の部品が入っていない: " + "、".join(lack))
        return {"parts": [p.key for p in qcparts.PARTS]}

    ok = step("検品の部品がそろう", qc_parts) and ok

    def right_click():
        # 右クリックのメニューを、下のメニューまで全部開いて閉じる（0.5.30 で右クリックからアプリごと落ちた）
        from PySide6.QtCore import QEventLoop, QPoint
        w = app.Window()
        w.show()
        if shot.get("path"):
            w.place(str(shot["path"]))
        seen = []

        def walk(m, depth=0, visited=None):
            # popup() 自身が aboutToShow を発火する。手動で emit すると、
            # 同じ fill が二重に走る。マウス入力も処理するとカーソル位置の項目から
            # サブメニューが自動で連鎖表示されるため、検査中はユーザー入力を除外する。
            if visited is None:
                visited = set()
            if depth > 12 or len(visited) > 120:
                raise RuntimeError("右クリックのメニューが循環しています")
            # id(m) は Python ラッパーの寿命に依存する。QObject 自体で重複を判定する。
            if m in visited:
                return
            visited.add(m)
            title = m.title()
            started = time.monotonic()
            print(f"MENU OPEN depth={depth} title={title!r} actions={len(m.actions())}", flush=True)
            m.popup(QPoint(20, 20))
            qapp.processEvents(QEventLoop.ExcludeUserInputEvents)
            for a in list(m.actions()):
                seen.append(a.text())
                sub = a.menu()
                if sub is not None:
                    walk(sub, depth + 1, visited)
            m.hide()
            qapp.processEvents(QEventLoop.ExcludeUserInputEvents)
            elapsed = time.monotonic() - started
            print(f"MENU CLOSE depth={depth} title={title!r} seconds={elapsed:.2f}", flush=True)
            if elapsed > 15:
                raise RuntimeError(f"右クリックメニューの表示に時間がかかりすぎています: {title!r} ({elapsed:.1f}s)")
        for _ in range(3):
            m = w.build_canvas_menu(QPoint(20, 20))
            walk(m)
            m.deleteLater()
            qapp.processEvents()
        # 絵を置いたので未保存の変更があり、閉じると「保存しますか」の窓が exec で出たまま戻らない
        # （見る人がいない機械で 30 分止まった）。保存は見ない段なので、変更なしとして閉じる
        w.dirty = False
        w.close()
        qapp.processEvents()
        if w.isVisible():
            raise RuntimeError("右クリックの段の窓が閉じない")
        return {"items": len(seen)}

    def phases_draw():
        # 工程に分けて描く。検品を通るまで工程を足して続けるので、小さな模型（砂嵐の絵）では終わらない。
        # 決めた時間だけ描かせて利用者と同じ「止める」の旗を立て、工程が足されたことと止めた所までの記録を見る
        import json
        import threading
        from atelier.ai.engine import Painter, Studio, Stopped, Words
        painter = Painter(TINY, steps=2, size=(256, 256))
        studio = Studio(Words(Path("")), painter, out)
        studio.way = "phases"
        sec = float(os.environ.get("ATELIER_E2E_PHASE_SECONDS", "180"))
        timer = threading.Timer(sec, lambda: setattr(painter, "stop", True))
        timer.start()
        try:
            studio.draw("1girl, red hair", 2, size=(256, 256))
            stopped = False
        except Stopped:
            stopped = True
        finally:
            timer.cancel()
            painter.stop = False
        keep = studio.last_phase_keep
        got = json.loads((Path(keep) / "progress.json").read_text(encoding="utf-8")) if keep else {}
        detail = {"stopped": stopped, "total": got.get("total"), "need": got.get("need"), "image": got.get("image")}
        if stopped and not (got.get("state") == "stopped" and got.get("image") and Path(got["image"]).exists()):
            raise RuntimeError(f"止めた所までの絵が残っていない: {detail}")
        if stopped and not (got.get("need", 0) > 12):
            raise RuntimeError(f"崩れが残ったのに工程が足されていない: {detail}")
        return detail

    ok = step("工程に分けて 1 枚描く", phases_draw) and ok
    # ---- 窓から、利用者が押すのと同じメソッドを通す。窓の写しは出力の置き場に置く ----
    import numpy as np
    from atelier.ai.engine import Painter, Studio, Words
    from atelier.app.window.image_convert import qimage_to_pil_rgba
    from PySide6.QtWidgets import QMessageBox

    asked = report.setdefault("dialogs", [])

    def no_dialog(_parent, title, text, *a, **k):
        # 見る人のいない機械で、聞く窓が出たまま止まらないようにする。出た窓は report.json に残す
        asked.append(f"{title}: {text}"[:200])
        return QMessageBox.No
    QMessageBox.question = staticmethod(no_dialog)

    def pump(until, sec):
        end = time.time() + sec
        while time.time() < end:
            qapp.processEvents()
            if until():
                return True
            time.sleep(0.05)
        return until()

    def snap(w, name):
        for _ in range(5):
            qapp.processEvents()
        w.grab().save(str(out / name))
        return name

    def pixels(w):
        return np.asarray(qimage_to_pil_rgba(w.canvas.flatten()))

    def layer_names(w):
        return [layer.name for layer in w.canvas.layers]

    said: list = []

    def open_window():
        w = app.Window(Studio(Words(Path("")), Painter(TINY, steps=2, size=(256, 256)), out))
        w.settings.set("phase_confirm", 0)   # 工程ごとに聞く窓を出さない（見る人がいない）
        notify = w.notify

        def keep(title, *a, **k):
            detail = a[1] if len(a) > 1 else k.get("detail", "")
            said.append(f"{title} {detail}".strip())
            return notify(title, *a, **k)
        w.notify = keep
        say = w.say

        def keep_said(text, *a, **k):   # 会話に出した言葉（描けない理由など）も残す
            said.append(str(text))
            return say(text, *a, **k)
        w.say = keep_said
        w.show()
        pump(lambda: False, 1)
        return w

    win: dict = {}

    def press_draw(w, text, way_index):
        w.way_pick.setCurrentIndex(way_index)   # 0: AI モード、1: 精度優先
        w.mode.setCurrentIndex(0)
        w.entry.setText(text)
        w.send()
        if w.thread is None:
            raise RuntimeError("描くを押しても描き始めなかった: " + " / ".join(said[-3:]))
        if not pump(lambda: w.thread is None, 1800):
            raise RuntimeError("30 分たっても描き終わらない")
        pump(lambda: not getattr(w, "bg_pending", 0), 60)

    def draw_in_window():
        w = win.get("w") or open_window()
        win["w"] = w
        press_draw(w, "1girl, red hair", 0)
        names = layer_names(w)
        if not w.images:
            raise RuntimeError("描いた絵が無い: " + " / ".join(said[-3:]))
        if w.canvas.current != len(names) - 1 or not names[-1].startswith("AI の絵"):
            raise RuntimeError(f"描いた絵が一番上のレイヤーでない: 選んだ {w.canvas.current}、並び {names}")
        return {"file": str(w.images[-1]), "layers": names, "shot": snap(w, "draw.png")}

    def redpen_fix():
        w = win.get("w")
        if w is None or not w.images:
            raise RuntimeError("直す絵が無い（描く段が落ちた）")
        width, height = w.canvas.size_px()
        box = (width * 0.3, height * 0.3, width * 0.6, height * 0.5)
        w.add_flaw_mark(box, "blue hair")
        inside = np.zeros((height, width), bool)
        for m in w.canvas.redpen.masks():
            inside |= np.asarray(qimage_to_pil_rgba(m).convert("L")) > 0
        before, count = pixels(w), len(w.canvas.layers)
        snap(w, "redpen-marked.png")
        w.entry.clear()
        w.fix_marked()
        if w.thread is None:
            raise RuntimeError("「囲んだ所を直す」を押しても直し始めなかった: " + " / ".join(said[-3:]))
        if not pump(lambda: w.thread is None, 1800):
            raise RuntimeError("30 分たっても直し終わらない")
        after = pixels(w)
        changed = (before != after).any(axis=2)
        outside, within = int((changed & ~inside).sum()), int((changed & inside).sum())
        top = w.canvas.layers[-1]
        detail = {"inside_pixels": int(inside.sum()), "changed_inside": within, "changed_outside": outside,
                  "layers": layer_names(w), "top_is_fix": bool(top.redpen), "shot": snap(w, "redpen-fixed.png")}
        if len(w.canvas.layers) <= count or not top.redpen:
            raise RuntimeError(f"直しが一番上の赤ペンのレイヤーに置かれていない: {detail}")
        if outside:
            raise RuntimeError(f"囲みの外の画素が {outside} 個変わった: {detail}")
        if not within:
            raise RuntimeError(f"囲みの中が 1 画素も変わっていない: {detail}")
        return detail

    def inspect():
        w = win.get("w")
        if w is None or not w.images:
            raise RuntimeError("検品する絵が無い（描く段が落ちた）")
        start = len(said)
        w.inspect_now()
        if not pump(lambda: not getattr(w, "inspecting", False), 900):
            raise RuntimeError("15 分たっても検品が終わらない")
        got = [s for s in said[start:] if "検品" in s]
        if not got:
            raise RuntimeError("検品の結果が返らない")
        if any("止まりました" in s for s in got):
            raise RuntimeError("検品が止まった: " + " / ".join(got))
        return {"result": got, "marks": len(w.canvas.redpen.marks), "shot": snap(w, "inspect.png")}

    def save_and_reopen():
        from PIL import Image
        w = win.get("w") or open_window()
        win["w"] = w
        if not w.canvas.layers or len(w.canvas.layers) < 2:
            # 描く段が落ちたときも、保存と読み込みだけは見る（模型の要らない絵を開いて置く）
            png = out / "reopen-source.png"
            Image.new("RGB", (320, 240), (200, 120, 60)).save(png)
            w.open_path(str(png))
            pump(lambda: bool(w.canvas.layers), 10)
        png2 = out / "reopen-layer.png"
        Image.new("RGB", (64, 64), (40, 90, 200)).save(png2)
        w.canvas.add_image_layer(str(png2), "足したレイヤー")
        path = out / "e2e.atelier"
        w.project_path = str(path)
        if not w.save_project(wait=True):
            raise RuntimeError("作業ファイルに保存できなかった: " + " / ".join(said[-3:]))
        names, before = layer_names(w), pixels(w)
        w.close()
        pump(lambda: False, 1)
        win.pop("w", None)
        w2 = open_window()
        w2.open_path(str(path))
        pump(lambda: layer_names(w2) == names, 30)
        detail = {"file": str(path), "bytes": path.stat().st_size, "layers_saved": names, "layers_read": layer_names(w2),
                  "shot": snap(w2, "reopen.png")}
        if layer_names(w2) != names:
            raise RuntimeError(f"開き直したレイヤーが違う: {detail}")
        after = pixels(w2)
        if before.shape != after.shape or (before != after).any():
            diff = int((before != after).any(axis=2).sum()) if before.shape == after.shape else -1
            raise RuntimeError(f"開き直した絵が違う（違う画素 {diff}）: {detail}")
        win["w"] = w2
        return detail

    def precise_draw():
        # 精度優先は検品を通るまで工程を足して続ける。小さな模型では終わらないので、決めた時間だけ描かせて「止める」を押し、
        # 「止めました（工程 k で止めました）」が出て「描けました」が出ないこと、止めた所までの絵がレイヤーにあることを見る
        w = win.get("w") or open_window()
        win["w"] = w
        w._two_parts_asked = True
        w.way_pick.setCurrentIndex(1)
        w.mode.setCurrentIndex(0)
        w.entry.setText("1girl, red hair")
        n0 = len(said)
        w.send()
        if w.thread is None:
            raise RuntimeError("描くを押しても描き始めなかった: " + " / ".join(said[-3:]))
        pump(lambda: w.thread is None, float(os.environ.get("ATELIER_E2E_PHASE_SECONDS", "180")))
        ran = said[n0:]
        added = [m for m in ran if "直しを" in str(m) and "要る工程" in str(m)]
        if w.thread is not None:
            w.stop()
        pump(lambda: False, 3)
        ran = said[n0:]
        layers = layer_names(w)
        detail = {"added": added[-3:], "said": [str(m) for m in ran[-6:]], "layers": layers[-4:], "shot": snap(w, "precise.png")}
        if any("描けました" in str(m) for m in ran) and not any("全部の工程が検品を通りました" in str(m) for m in ran):
            raise RuntimeError(f"検品を通っていないのに「描けました」と出た: {detail}")
        if not any("全部の工程が検品を通りました" in str(m) for m in ran):
            if not any(str(m).startswith("止めました（工程") for m in ran):
                raise RuntimeError(f"「止めました（工程 k で止めました）」が出ない: {detail}")
            if not any(n.startswith("止めた所までの絵") for n in layers):
                raise RuntimeError(f"止めた所までの絵がレイヤーに無い: {detail}")
        return detail

    # 利用者が窓で踏む段。Release を決める段（入れる・起動・取る・描く）とは分けて流す
    # （ATELIER_E2E_CORE_ONLY=1 のときは流さない）。ここで固まると、描けると分かった版まで Release に出なかった
    if not os.environ.get("ATELIER_E2E_CORE_ONLY"):
        # 右クリックのメニューは、Windows の機械で開いたまま戻らず 30 分で切れたことがある。Release を止めないよう、こちらで見る
        ok = step("右クリックのメニューを全部開く", right_click) and ok
        ok = step("窓で描き、絵が一番上のレイヤーになる", draw_in_window) and ok
        ok = step("赤ペンで囲んだ中だけを直す", redpen_fix) and ok
        ok = step("描いた絵を検品する", inspect) and ok
        ok = step("作業ファイルに保存して開き直す", save_and_reopen) and ok
        ok = step("精度優先で描き、工程ごとの絵が出る", precise_draw) and ok
    report["said"] = said[-40:]
    if win.get("w") is not None:
        win["w"].close()
        qapp.processEvents()

    from atelier.files.paths import HOME, HUB
    report["data_home"], report["hub"] = str(HOME), str(HUB)
    report["ok"] = ok
    save_report()
    print(f"exit={0 if ok else 1}", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
