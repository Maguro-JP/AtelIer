"""画風の加工（atelier/ai/restyle.py）が本物の模型で掛かるかを 1 枚で確かめる（Actions の restyle-verify で流す）。

小さな試験の模型は重みが乱数なので、画風はいつも「形が変わりすぎる」で止まり、止めの境目が正しいかを測れなかった。
本物の絵の模型と Union を取り、見本の絵に画風を掛けて、試した強さごとに形の変わり（drift）・元の線の残り（line_kept）・
目の色の差（atelier/ai/face_features.py）を 1 行ずつ出す。止めた画風も、何で止めたかを数字で残す。

  python -m atelier.bench.restyle_verify <絵> <出力の置き場> [画風 ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    from PIL import Image
    from atelier.ai import face_features as facefeat
    from atelier.ai import restyle
    from atelier.ai.engine import IMAGE_MODEL, Painter
    from atelier.ai.finishers import Unavailable
    from atelier.models.catalog import image_model
    src_path, out = Path(argv[0]), Path(argv[1])
    kinds = argv[2:] or [s[0] for s in restyle.STYLES]
    import os
    if os.environ.get("ATELIER_RESTYLE_SIDE"):   # Actions の CPU で 1 枚を時間内に終えるため、描く大きさを縮められるようにする
        restyle.WORK_SIDE = int(os.environ["ATELIER_RESTYLE_SIDE"])
    out.mkdir(parents=True, exist_ok=True)
    m = image_model(IMAGE_MODEL)
    from huggingface_hub import snapshot_download
    from atelier.files.paths import HUB
    snapshot_download(m.repo, cache_dir=str(HUB), **m.files)   # 描く模型は Painter が取らないので先に取る（draw_one と同じ）
    painter = Painter(m.repo, steps=m.steps, guidance=m.guidance)
    src = Image.open(src_path).convert("RGB")
    f0 = facefeat.features(src)
    rows = []
    for kind in kinds:
        t = time.time()
        row = dict(kind=kind)
        try:
            got = restyle.restyle(painter, src, kind)
            got.save(out / f"{kind}.png")
            row.update(applied=True, face=facefeat.compare(f0, facefeat.features(got)))
        except Unavailable as e:
            row.update(applied=False, why=str(e))
        row.update(tries=restyle.LAST.get("tries", []), seconds=round(time.time() - t, 1))
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (out / "restyle-verify.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
