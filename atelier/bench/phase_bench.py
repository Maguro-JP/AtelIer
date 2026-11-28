"""1 回で描く形と工程に分けて描く形（atelier/ai/phases.py）を、本物の模型・同じ頼み・同じ種で比べる。Actions の phase-bench で動かす。

どちらの絵も、最後に同じ検品（手・足・顔、体、頼んだ物）に通して崩れの数を数え、かかった秒を残す。
工程に分けた回は、9 の工程ごとの絵（phases/s<種>/01-サムネイル.png 〜 09-仕上げ.png）と、工程ごとの見る物・判定の数字・
秒・常駐のメモリ（MB）・戻った回数を bench.json と phases.json に残す（Actions の artifact で見る）。

  python -m atelier.bench.phase_bench 出力の置き場
  環境変数: BENCH_MODEL、BENCH_PROMPT、BENCH_SEED、BENCH_STEPS、BENCH_SIZE（幅x高さ）、BENCH_WAYS（one,phases）

BENCH_WAYS=draws は速い確かめ（Actions の precise-fast）。精度優先の描く工程だけを、検品と直しの繰り返し無しで 1 回ずつ流し、
工程ごとの絵と数字（線の途切れ、彩度、紙の明るさ）を draws/ と bench.json とログに出す。同じ頼み・同じ種の 1 回描き
（AI モードの初めの 1 枚と同じ呼び方）も並べる。描く工程が絵を壊していないかを、数時間の precise-real を待たずに見る。
BENCH_WAYS=pixels は、それに画素を数える検品とその直し（線、ゴミ、色、影など）を足した確かめ。模型を使う検品は崩れ無しで通す。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path


class Words:
    """頼みは英語のタグで渡すので、訳さずにそのまま描く言葉にする（言葉の模型の差を比べに混ぜない）"""
    untranslated, negative = [], []

    def ready(self):
        return True

    def to_prompt(self, text, tags=True):
        return text


def final_check(path: Path, prompt: str) -> dict:
    from atelier.qc import hand_check as handcheck
    from atelier.qc import request_check as requestcheck
    from atelier.qc import sanity
    hands = handcheck.check(path, asked=prompt)
    req = requestcheck.check(path, prompt, fetch=True)
    body = sanity.check(path, prompt, tags=req.get("read") if req.get("readable") else None)
    bad = list(hands.get("bad", [])) + list(body.get("bad", []))
    if req.get("readable"):
        bad += [f"描かれていない: {m}" for m in req["missing"]] + [f"人数が違う: {p}" for p in req.get("people", [])]
    return {"bad": bad, "count": len(bad), "readable": {"hands": hands.get("readable"), "request": req.get("readable"),
                                                        "body": body.get("readable")}}


class NoChecks:
    """検品をしない（速い確かめ用）。どの検品も「読めない」を返し、描く工程は候補を比べずに 1 回ずつ描く"""

    @staticmethod
    def request(image, prompt):
        return {"readable": False}

    @staticmethod
    def body(image, prompt, tags=None):
        return {"readable": False}

    @staticmethod
    def points(image):
        return {"readable": False}

    @staticmethod
    def pose(image):
        return {"readable": False}

    @staticmethod
    def hands(image, prompt):
        return {"readable": False}


class CleanChecks(NoChecks):
    """重い検品（頼んだ物・体・手足顔）を「崩れ無し」で通す（BENCH_WAYS=pixels 用）。体の点（骨組み）だけは本物で読む
    （目の光・顔の反転・影の顔よけが体の点を使う）。画素を数える検品（線、ゴミ、色、影、縮めて見るなど）と、
    その直しが本物として働く。画素の検品と直しが、描いた絵を壊していないかを、重い検品と直しを待たずに見る"""

    @staticmethod
    def request(image, prompt):
        return {"readable": True, "missing": [], "extra": [], "people": [], "body": []}

    @staticmethod
    def body(image, prompt, tags=None):
        return {"readable": True, "bad": [], "avoid": []}

    @staticmethod
    def points(image):
        from atelier.ai import phases
        return phases.Checks.points(image)

    @staticmethod
    def pose(image):
        from atelier.ai import phases
        return phases.Checks.pose(image)

    @staticmethod
    def hands(image, prompt):
        return {"readable": True, "bad": [], "hands": [], "feet": [], "faces": []}


def picture_numbers(image) -> dict:
    """1 枚の絵の数字。sat は彩度の平均、paper は明るい側 90% の位置の明るさ（紙の明るさ）、gap は外の輪郭のうち線の無い割合、
    max_gap は線の無い所が続く一番長い区間、pieces は暗い画素（明るさ 128 未満）の塊の数、piece_len は塊 1 つの画素の数の平均
    （線が破線に崩れると pieces が増えて piece_len が小さくなる）"""
    import numpy as np
    from scipy import ndimage
    from atelier.ai import phase_tools as pt
    lum = pt.luminance(image)
    t = pt.tone(image)
    ln = pt.lines(image)
    dark = lum < 128
    _lab, n = ndimage.label(dark, structure=np.ones((3, 3), bool))
    return {"sat": t["sat"], "lum": t["lum"], "paper": round(float(np.percentile(lum, 90)), 1), "gap": ln.get("gap"),
            "max_gap": ln.get("max_gap"), "pieces": int(n), "piece_len": round(float(dark.sum()) / max(int(n), 1), 1)}


def run_draws(out: Path, painter, prompt: str, seed: int, size, way: str = "draws") -> dict:
    """速い確かめ。描く工程だけを 1 回ずつ流し（draws）、工程ごとの絵と数字を残す。1 回描きの絵も同じ数字で並べる。
    pixels は、画素を数える検品とその直しも流す（模型を使う検品は崩れ無しで通す）"""
    from PIL import Image
    from atelier.ai import phases
    each = out / way
    keep = each / "work"
    each.mkdir(parents=True, exist_ok=True)
    based = []
    t = time.perf_counter()
    got = phases.draw(painter, prompt, seed, size, keep, say=lambda m: print(f"[{way}] {m}", flush=True),
                      checks=NoChecks if way == "draws" else CleanChecks, only_draw=(way == "draws"), on_base=based.append)
    secs = round(time.perf_counter() - t, 1)
    rows = []
    for r in got["phases"]:
        if not r.get("image"):
            continue
        img = Image.open(r["image"]).convert("RGB")
        shutil.copy(r["image"], each / Path(r["image"]).name)
        made = {k: v for k, v in (r.get("numbers") or {}).items() if isinstance(v, (int, float, str))}   # 描く工程が残した数字（線の埋もれ・太りなど）
        rows.append({"phase": r["phase"], "seconds": r["seconds"], "file": Path(r["image"]).name, **picture_numbers(img), "made": made})
    got["image"].save(each / "final.png")
    rows.append({"phase": "最後の絵", "seconds": secs, "file": "final.png", **picture_numbers(got["image"])})
    t = time.perf_counter()
    one = based[0] if based else painter.paint(prompt, seed, size=size)   # 土台は 1 回描きと同じ呼び方（同じ言葉・種・大きさ）で描いた絵
    one.save(each / "one.png")
    rows.append({"phase": "1 回描き（AI モードの初めの 1 枚）", "seconds": round(time.perf_counter() - t, 1), "file": "one.png",
                 "same_as_base": bool(based), **picture_numbers(one)})
    for r in rows:
        print("DRAWS " + json.dumps(r, ensure_ascii=False), flush=True)
    mends = [{"phase": r["phase"], "item": m.get("item"), "mend": m.get("mend"), "changed": m.get("changed")}
             for r in got["history"] for m in r.get("mends", [])]
    for m in mends:
        print("MEND " + json.dumps(m, ensure_ascii=False, default=str), flush=True)
    return {"way": way, "seconds": secs, "rows": rows, "words": [w for r in got["phases"] for w in r.get("words", [])],
            "mends": mends, "left": list(got.get("left") or [])}


def run_mends(out: Path, painter, prompt: str, seed: int, size) -> dict:
    """直しの段を本物の模型で比べる: 同じ絵・同じ囲み・同じ種で、前（囲みを面で消してから描く）と
    後（囲みの中の線を消しゴムでなぞって消してから描く）を描き、囲みの外の変化と囲みの中の線の鋭さを測る。
    アタリのずれの直し（角度を変える・ずらす・切り貼り）も、1 回描きから抜いたラフに掛けて残す"""
    import numpy as np
    from PIL import Image, ImageDraw
    from atelier.ai import phase_tools as pt
    from atelier.ai import phases
    d = out / "mends"
    d.mkdir(parents=True, exist_ok=True)
    w, h = size
    t = time.perf_counter()
    one = painter.paint(prompt, seed, size=(w, h))
    one.save(d / "one.png")
    m = pt.silhouette(one)
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        return {"way": "mends", "readable": False}
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    # 頭の所（人の形の上 18%、横は人の形の中ほど）を直す囲みにする（検品の模型を使わずに、毎回同じ所を比べる）
    hh = int((y1 - y0) * 0.18)
    cx = int(xs[ys < y0 + hh].mean()) if (ys < y0 + hh).any() else (x0 + x1) // 2
    box = (max(0, cx - hh // 2 - 8), y0, min(w, cx + hh // 2 + 8), y0 + hh)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    rows = {}
    strength = phases.FIXES[0]
    from atelier.ai.engine import erase as area_erase
    for name, (src, clean) in {"before": (area_erase(one, mask), False), "after": (pt.stroke_erase(one, mask)[0], False)}.items():
        src.save(d / f"{name}-src.png")
        raw = painter.redraw(prompt, seed, src, mask, strength=strength, clean=clean)
        out_img = phases._inside(raw, one, mask)
        out_img.save(d / f"{name}.png")
        a, b = np.asarray(one).astype(int), np.asarray(out_img).astype(int)
        inside = np.asarray(mask) > 0
        lum = pt.luminance(out_img)
        gy, gx = np.gradient(lum)
        rows[name] = {"outside_changed": int(((a != b).any(2) & ~inside).sum()),
                      "inside_diff": round(float(np.abs(a - b)[inside].mean()), 2),
                      "inside_sharp": round(float(np.hypot(gx, gy)[inside].mean()), 2),
                      "sat": pt.tone(out_img)["sat"]}
    rough = pt.rough_from(one)
    rough.save(d / "rough.png")
    moves = {}
    for name, tool in (("lean", pt.lean_fix), ("recenter", pt.recenter), ("reattach", pt.reattach)):
        got, amount = tool(rough)
        got.save(d / f"rough-{name}.png")
        moves[name] = {"amount": amount if not hasattr(amount, "item") else amount.item(),
                       "balance": (pt.balance(got) or {}).get("balance"), "weight_x": pt.thumb_weight(got)["weight_x"],
                       "detached": pt.detached(got).get("count")}
    moves["rough"] = {"balance": (pt.balance(rough) or {}).get("balance"), "weight_x": pt.thumb_weight(rough)["weight_x"],
                      "detached": pt.detached(rough).get("count")}
    row = {"way": "mends", "seconds": round(time.perf_counter() - t, 1), "box": list(box), "redraw": rows, "moves": moves}
    print("MENDS " + json.dumps(row, ensure_ascii=False, default=float), flush=True)
    return row


def run_hands(out: Path, painter, prompt: str, seed: int, size) -> dict:
    """手と足の検品が、線の工程の絵（ラフ・線画）で「読めない」を出しているかを、色の絵（1 回描き）と比べて確かめる。
    同じ絵から抜いたラフと線なので、色の絵で読める手・足が線の絵で読めなければ、読めないのは絵の崩れではなく検品の側"""
    from atelier.ai import phase_tools as pt
    from atelier.qc import hand_check as handcheck
    d = out / "hands"
    d.mkdir(parents=True, exist_ok=True)
    w, h = size
    one = painter.paint(prompt, seed, size=(w, h))
    pics = {"one": one, "rough": pt.rough_from(one), "lines": pt.ink_levels(pt.rough_from(one))}
    rows = {}
    for name, im in pics.items():
        im.save(d / f"{name}.png")
        res = handcheck.check(im, asked=prompt)
        rows[name] = {"readable": res.get("readable"), "reason": res.get("reason"), "feet_reason": res.get("feet_reason"),
                      "hands": [{"box": x.get("box"), "bad": x.get("bad"), "missed": x.get("missed", False)} for x in res.get("hands", [])],
                      "feet": [{"box": x.get("box"), "count": x.get("count"), "bad": x.get("bad"), "sharp": x.get("sharp")}
                               for x in res.get("feet", [])],
                      "bad": list(res.get("bad", []))}
        print(f"HANDS {name} " + json.dumps(rows[name], ensure_ascii=False, default=float), flush=True)
    return {"way": "hands", "rows": rows}


def run(out: Path):
    from atelier.ai.engine import Painter, Studio
    from atelier.qc import hand_check as handcheck
    from atelier.qc import request_check as requestcheck
    out.mkdir(parents=True, exist_ok=True)
    model = os.environ.get("BENCH_MODEL", "cagliostrolab/animagine-xl-4.0")
    prompt = os.environ.get("BENCH_PROMPT", "1girl, solo, standing, full body, waving, red scarf, school uniform, looking at viewer")
    seed = int(os.environ.get("BENCH_SEED", "7"))
    steps = int(os.environ.get("BENCH_STEPS", "20"))
    w, h = (int(x) for x in os.environ.get("BENCH_SIZE", "832x1216").split("x"))
    ways = os.environ.get("BENCH_WAYS", "one,phases").split(",")
    from huggingface_hub import snapshot_download
    from atelier.ai import two_stage as twostage
    from atelier.files.paths import HUB
    pose_files = dict(twostage.PARTS)[twostage.POSE]
    fetches = (lambda: snapshot_download(twostage.POSE, cache_dir=str(HUB), allow_patterns=pose_files),
               lambda: requestcheck._tagger(True), lambda: handcheck.ensure_models(True), lambda: handcheck.ensure_feet_model(True))
    if set(ways) <= {"draws", "pixels", "mends"}:   # 速い確かめは重い検品をしない。体の点の部品だけを、画素の検品の組のときに取る
        fetches = fetches[:1] if "pixels" in ways else ()
    elif set(ways) <= {"hands"}:   # 手と足の検品の組は、体の点と手・足の模型だけを取る
        fetches = (fetches[0], fetches[2], fetches[3])
    for fetch in fetches:
        try:
            fetch()   # 検品の部品を先に取る（取らないと検品できず、崩れ 0 と読み違える）
        except Exception as e:   # noqa: BLE001
            print("検品の部品を取れませんでした:", e, flush=True)
    result = {"model": model, "prompt": prompt, "seed": seed, "steps": steps, "size": [w, h], "runs": []}
    painter = Painter(model, steps=steps)
    for way in ways:
        if way == "hands":
            result["runs"].append(run_hands(out, painter, prompt, seed, (w, h)))
            (out / "bench.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
            continue
        if way == "mends":
            result["runs"].append(run_mends(out, painter, prompt, seed, (w, h)))
            (out / "bench.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
            continue
        if way in ("draws", "pixels"):
            result["runs"].append(run_draws(out, painter, prompt, seed, (w, h), way))
            (out / "bench.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            continue
        studio = Studio(Words(), painter, out / way)
        studio.way = way
        t = time.perf_counter()
        said = []
        used, path = studio.draw(prompt, seed, on_status=lambda m: (said.append(m), print(f"[{way}] {m}", flush=True)), size=(w, h))
        secs = round(time.perf_counter() - t, 1)
        shutil.copy(path, out / f"{way}-s{seed}.png")
        from PIL import Image
        from atelier.ai import phase_tools as phasetools
        row = {"way": way, "seconds": secs, "prompt_used": used, "final": final_check(path, prompt),
               "tone": phasetools.tone(Image.open(path).convert("RGB")), "said": said[-40:]}   # 彩度（sat）を 1 回で描いた絵と比べる
        if studio.last_phases:
            row["phases"] = studio.last_phases
            row["per_phase"] = [{"phase": r["phase"], "seconds": r["seconds"], "mem_mb": r.get("mem_mb"), "numbers": r.get("numbers"),
                                 "left": r["after"] if r["fixed"] else r["found"]} for r in studio.last_phases]
            each = out / "phases" / f"s{seed}"
            each.mkdir(parents=True, exist_ok=True)
            for r in studio.last_phases:
                if r.get("image"):
                    shutil.copy(r["image"], each / Path(r["image"]).name)
            src = Path(studio.last_phases[-1]["image"] or "").parent / "phases.json"
            if src.exists():
                shutil.copy(src, each / "phases.json")
        if way == "phases":   # 何工程かかったか、描かない工程を何回描き直したか、全部の工程が検品を通ったか
            import re
            begun = [int(m.group(1)) for m in (re.match(r"工程 (\d+)/\d+「", str(x)) for x in said) if m]
            row["summary"] = {"passed": bool(getattr(studio, "last_passed", False)), "steps": max(begun) if begun else 0,
                              "total": sum(1 for r in (studio.last_phases or []) if r.get("image")),
                              "carried": sum(1 for x in said if "残った崩れとして次の工程へ進みます" in str(x)),
                              "fixes": sum(1 for x in said if "囲みの中だけを直しています" in str(x)),
                              "asked": bool(getattr(studio, "last_asked", None)), "minutes": round(secs / 60, 1)}
            print("SUMMARY " + json.dumps(row["summary"], ensure_ascii=False), flush=True)
        result["runs"].append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "said"}, ensure_ascii=False), flush=True)
        (out / "bench.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    # BENCH_REQUIRE_COMPLETE=1 のときは、精度優先が最後の工程まで検品を通らなければ落とす（precise-real.yml の段）
    if os.environ.get("BENCH_REQUIRE_COMPLETE") == "1":
        rows = [r for r in result["runs"] if r["way"] == "phases"]
        bad = [r.get("summary") for r in rows if not (r.get("summary") or {}).get("passed")]
        if not rows or bad:
            print("精度優先が最後の工程まで検品を通らなかった: " + json.dumps(bad, ensure_ascii=False), flush=True)
            sys.exit(1)


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1 else "phase-out"))
