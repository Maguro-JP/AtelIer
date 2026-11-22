"""頼み 1 件を、指定の模型で 1 枚描く（GitHub Actions の draw-one.yml で流す）。

    python -m atelier.bench.draw_one <置き場>   （頼みは config/draw-request.json）

手元に置けない大きな模型（FLUX、Z-Image など）を、描く仕組み（Painter）と同じ経路で試すために使う。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


REQUEST = Path(__file__).resolve().parents[2] / "config" / "draw-request.json"


def read_request(composition: str | None = None) -> dict:
    """頼みを読む。config/draw-request.json が無いとき（頼みを消したブランチで、構図を使い回して仕上げだけ描き直すとき）は、
    構図の隣に構図の段が残した頼み（request-compose.json）を使う。前は無い頼みを開こうとして、描き直しの段が落ちた。
    道はリポジトリから引く（今いるフォルダーからでは、別の所から動かすと見つからなかった）"""
    places = [REQUEST]
    if composition:
        places.append(Path(composition).with_name("request-compose.json"))
    for p in places:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit("頼みがありません: " + "、".join(str(p) for p in places))


def main():
    import os
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    req = read_request(os.environ.get("DRAW_COMPOSITION"))
    if req.get("mode") == "twostage":
        # 段は環境変数 DRAW_STAGE（compose、finish、all）で選ぶ。Actions では段ごとに別のジョブにして、
        # 1 つのジョブが打ち切られても、前の段の絵は draw-results に残る
        from atelier.ai.two_stage import draw
        stage = os.environ.get("DRAW_STAGE", "all")
        # 頼みの composition に、立体の人形（関節の可動域を検査した姿勢）を撮った絵を書けば、構図の模型をとばして
        # その骨格で縛って仕上げる。言葉だけの構図は、手の置き場所と腕の数を守らなかった（docs/knowledge/learning/illustration-composition.md）
        comp = os.environ.get("DRAW_COMPOSITION") or req.get("composition") or None
        t = time.time()
        seed = int(os.environ.get("DRAW_SEED") or req.get("seed", 7))   # 検品を通るまで、種を変えて描き直す（draw-one.yml）
        draw(req["prompt"], req["tags"], seed, req["compose"], req["render"], size=tuple(req.get("size", (832, 1216))),
             say=lambda m: print(m, flush=True), keep=out, composition=comp, variants=req.get("variants"), stage=stage,
             negative=req.get("negative", ""))
        from atelier.qc import hand_check as handcheck
        checks = {}
        for f in sorted(out.glob("1-composition.png")) + sorted(out.glob("3-*.png")):
            res = handcheck.check(f)
            checks[f.name] = res
            print(f"{f.name}: {handcheck.summary(res)}", flush=True)
        if checks:
            (out / f"check-{stage}.json").write_text(json.dumps(checks, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (out / f"request-{stage}.json").write_text(json.dumps(dict(req, seconds=round(time.time() - t)), ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
        print("exit=0")
        return
    if req.get("mode") == "logo":
        logo_candidates(req, out)
        print("exit=0")
        return
    from huggingface_hub import snapshot_download
    from atelier.models.catalog import image_model
    from atelier.files.paths import HUB
    m = image_model(req["repo"])
    t = time.time()
    snapshot_download(m.repo, cache_dir=str(HUB), **m.files)
    print(f"取った: {time.time() - t:.0f} 秒", flush=True)
    from atelier.ai.engine import Painter
    p = Painter(m.repo, steps=req.get("steps", m.steps), size=tuple(req.get("size", (832, 1216))), guidance=req.get("guidance", m.guidance))
    t = time.time()
    im = p.paint(req["prompt"], req.get("seed", 7), on_step=lambda i, n: print(f"描いています {i}/{n}", flush=True))
    name = f"{m.repo.replace('/', '_')}-s{req.get('seed', 7)}.png"
    im.save(out / name)
    (out / "request.json").write_text(json.dumps(dict(req, seconds=round(time.time() - t), size_out=list(im.size)), ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(f"描いた: {name} {im.size} {time.time() - t:.0f} 秒")
    print("exit=0")


def logo_candidates(req: dict, out: Path, painter=None):
    """ロゴの候補を種ごとに 1 枚ずつ描く（アプリのアイコンの候補など）。アプリの「ロゴ・マークを作る」と同じ atelier/ai/logo_maker.py の経路。
    頼みの形: {"mode": "logo", "repo": 模型, "name", "mood", "colors", "seeds": [..], "size": [w, h]}"""
    from atelier.ai import logo_maker as logo
    if painter is None:
        from huggingface_hub import snapshot_download
        from atelier.ai.engine import Painter
        from atelier.models.catalog import image_model
        from atelier.files.paths import HUB
        m = image_model(req["repo"])
        snapshot_download(m.repo, cache_dir=str(HUB), **m.files)
        painter = Painter(m.repo, steps=req.get("steps", m.steps), size=tuple(req.get("size", (1024, 1024))),
                          guidance=req.get("guidance", m.guidance))
    done = []
    for seed in req.get("seeds", [7]):
        t = time.time()
        mark = logo.draw_logo(painter, req.get("name", ""), req.get("mood", ""), req.get("colors", ""), seed,
                              size=tuple(req.get("size", (1024, 1024))), say=lambda m: print(m, flush=True))
        name = f"icon-s{seed}.png"
        logo.square(mark, 1024, 48).save(out / name)
        done.append(dict(file=name, seed=seed, seconds=round(time.time() - t)))
        print(f"描いた: {name} {time.time() - t:.0f} 秒", flush=True)
    prompt, avoid = logo.logo_prompt(req.get("name", ""), req.get("mood", ""), req.get("colors", ""))
    (out / "request.json").write_text(json.dumps(dict(req, prompt=prompt, avoid=avoid, done=done), ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    return done


if __name__ == "__main__":
    main()
