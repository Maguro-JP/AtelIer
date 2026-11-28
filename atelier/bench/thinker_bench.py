"""考える役（atelier/ai/thinker.py）の確かめ。Actions の thinker-bench で動かす。

頼みごとに 1 回描き、頼んだ物の検品（request_check）で間違い（描かれていない物、背景の違い、人数）を数える。
間違いがあれば、考える役が AI の補完の指示を決め、その囲み（場所の間違いは背景、ほかは人物の所）の中だけを描き直す。
前と後の絵を並べた before-after/<番号>.png と、模型に渡した頼みの言葉・補完の言葉・検品の数を thinker.json に残す。
間違いが無ければ何もしない（補完 0 件）。

  python -m atelier.bench.thinker_bench 出力の置き場
  環境変数: BENCH_MODEL、BENCH_SEED、BENCH_STEPS、BENCH_SIZE、BENCH_PROMPTS（| で区切る。無ければ下の PROMPTS）
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROMPTS = [
    "classroom, sunset, school, indoors, scenery, no humans",
    "1girl, solo, classroom, sunset, school uniform, sitting",
    "train station, platform, scenery, no humans",
    "1boy, solo, train station, platform, day, standing",
    "shrine, torii, stone path, scenery, no humans",
    "beach, town, sea, scenery, no humans",
    "1girl, solo, forest, path, walking",
    "shopping street, rain, scenery, no humans",
    "school, blue sky, scenery, no humans",
    "1girl, solo, waving, full body",
    "1boy, solo, sitting, reading book",
    "dog, 1boy, child, running",
    "1girl, solo, profile, close-up",
]


def flaws_of(req: dict, prompt: str) -> list[str]:
    from atelier.ai import phases
    return phases._people(req) + phases._missing(req) + phases._background_flaws(prompt, req)


def side(a, b):
    from PIL import Image
    im = Image.new("RGB", (a.width + b.width + 8, max(a.height, b.height)), "white")
    im.paste(a, (0, 0))
    im.paste(b, (a.width + 8, 0))
    return im


def mask_for(img, area: str):
    from PIL import Image
    from atelier.ai import phase_tools as pt
    m = pt.silhouette(img)
    if area == "background":
        return Image.fromarray(((~m) * 255).astype("uint8")) if (~m).any() else Image.new("L", img.size, 255)
    return Image.fromarray((m * 255).astype("uint8")) if m.any() else Image.new("L", img.size, 255)


def one(painter, prompt: str, seed: int, size, out: Path, n: int) -> dict:
    from atelier.ai import phases, thinker
    from atelier.qc import request_check as requestcheck
    t = time.perf_counter()
    before = painter.paint(prompt, seed, size=size)
    req = requestcheck.check(before, prompt, fetch=True)
    flaws = flaws_of(req, prompt)
    missing = list(req.get("missing", []))
    item = "背景" if any("背景" in f for f in flaws) or any(m in thinker.places(prompt) for m in missing) else "頼んだ物"
    hint = thinker.complement(prompt, "仕上げ", item, flaws, missing)
    row = {"n": n, "prompt": prompt, "seed": seed, "request_words": prompt, "before": {"flaws": flaws, "missing": missing,
           "readable": req.get("readable")}, "complement": hint}
    after = before
    if hint["words"] or hint["how"] != "none":
        m = mask_for(before, hint["area"] or "background")
        sent = thinker.merge(prompt, hint["words"])
        raw = painter.redraw(sent, seed, before, m, strength=hint.get("strength") or 0.55)
        after = phases._inside(raw, before, m)
        req2 = requestcheck.check(after, prompt, fetch=True)
        row["sent"] = sent
        row["after"] = {"flaws": flaws_of(req2, prompt), "missing": list(req2.get("missing", []))}
        row["outside_diff"] = phases.diff(before, after, m)["outside"]
    row["seconds"] = round(time.perf_counter() - t, 1)
    before.save(out / f"{n:02d}-before.png")
    after.save(out / f"{n:02d}-after.png")
    side(before, after).save(out / "before-after" / f"{n:02d}.png")
    print("THINK " + json.dumps(row, ensure_ascii=False, default=str), flush=True)
    return row


def run(out: Path):
    from atelier.ai.engine import Painter
    out.mkdir(parents=True, exist_ok=True)
    (out / "before-after").mkdir(exist_ok=True)
    model = os.environ.get("BENCH_MODEL", "cagliostrolab/animagine-xl-4.0")
    seed = int(os.environ.get("BENCH_SEED", "7"))
    steps = int(os.environ.get("BENCH_STEPS", "15"))
    w, h = (int(x) for x in os.environ.get("BENCH_SIZE", "768x768").split("x"))
    prompts = [p.strip() for p in os.environ.get("BENCH_PROMPTS", "").split("|") if p.strip()] or PROMPTS
    painter = Painter(model, steps=steps)
    rows = []
    for n, p in enumerate(prompts, 1):
        rows.append(one(painter, p, seed, (w, h), out, n))
        (out / "thinker.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    sum_b = sum(len(r["before"]["missing"]) for r in rows)
    sum_a = sum(len((r.get("after") or r["before"])["missing"]) for r in rows)
    print(f"SUMMARY 描かれていない物: 前 {sum_b} 件 → 後 {sum_a} 件、補完した頼み {sum(1 for r in rows if 'sent' in r)}/{len(rows)}", flush=True)
    return rows


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1 else "thinker-out"))
