"""人物以外の題材の検品（atelier/qc/subject_check.py）を、模型で描いた絵で確かめる（Actions の subject-qc.yml で流す）。

    python -m atelier.bench.subject_bench <置き場>

題材ごとに頼みを 2 つ持ち、BENCH_SUBJECT の題材だけを 1 回ずつ描き、題材の検品と頼んだ物の検品（wd-tagger）を通して、
絵と数字を置き場に残す。合否は付けない。目で見つけた崩れと検品が見つけた崩れを並べるために、絵を 1 枚ずつ見る。
環境変数: BENCH_MODEL、BENCH_SUBJECT（person など、空なら全部）、BENCH_SEED、BENCH_STEPS、BENCH_SIZE
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 題材ごとの頼み 2 つ。頼みの言葉は模型にそのまま渡す（足さない）
PROMPTS = {
    "person": ["1girl, solo, standing, full body, waving, red scarf", "1boy, solo, sitting on a bench, reading a book"],
    "animal": ["a brown horse standing in a field, full body, side view", "a white cat sitting, full body"],
    "vehicle": ["a red bicycle, side view, white background", "a blue car, front view, street"],
    "building": ["tall office building, many windows, street, daytime", "old european town street, houses, windows"],
    "landscape": ["mountain landscape, lake, blue sky, scenery", "ocean, beach, sunset sky, scenery"],
    "interior": ["cozy bedroom interior, bed, window, desk", "kitchen interior, table, chairs, shelves"],
    "object": ["three apples on a wooden table, still life", "two coffee cups, white background"],
    "text": ['logo, text "CAFE", simple background', 'sign, text "OPEN", white background'],
    "pattern": ["seamless floral pattern", "seamless checkered pattern, red and white"],
    "background": ["scenery, no humans, city street at night", "scenery, no humans, forest path"],
}


def run(out: Path):
    from PIL import Image
    from atelier.ai.engine import Painter
    from atelier.qc import request_check, subject_check
    out.mkdir(parents=True, exist_ok=True)
    model = os.environ.get("BENCH_MODEL", "cagliostrolab/animagine-xl-4.0")
    seed = int(os.environ.get("BENCH_SEED", "7"))
    steps = int(os.environ.get("BENCH_STEPS", "14"))
    w, h = (int(x) for x in os.environ.get("BENCH_SIZE", "768x768").split("x"))
    only = [s for s in os.environ.get("BENCH_SUBJECT", "").split(",") if s]
    painter = Painter(model, steps=steps)
    rows = []
    for kind, prompts in PROMPTS.items():
        if only and kind not in only:
            continue
        for i, prompt in enumerate(prompts, 1):
            t = time.perf_counter()
            img = painter.paint(prompt, seed, size=(w, h))
            img = img if isinstance(img, Image.Image) else Image.open(img)
            name = f"{kind}-{i}-s{seed}.png"
            img.save(out / name)
            req = request_check.check(img, prompt, fetch=True)
            res = subject_check.phase_flaws(img, prompt, req)
            row = {"file": name, "kind": subject_check.kind(prompt), "prompt": prompt, "seconds": round(time.perf_counter() - t, 1),
                   "flaws": res["flaws"], "unreadable": res["unreadable"], "numbers": res["numbers"],
                   "missing": req.get("missing", []), "tags_readable": req.get("readable")}
            rows.append(row)
            print("SUBJECT", json.dumps(row, ensure_ascii=False), flush=True)
            (out / "bench.json").write_text(json.dumps({"model": model, "seed": seed, "rows": rows}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return rows


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1 else "subject-out"))
