#!/usr/bin/env python3
"""テストを、ファイルごとに別の処理で流す。

1 つの処理で全部を流すと、閉じた窓の分のメモリが増え続け、数百の窓を開け閉めしたあとに Qt の中で落ちる。
モデルの部品（torch、diffusers）が無い環境では、tests/needs_models.txt のファイルを飛ばす（--all で飛ばさない）。

    python3 scripts/run_tests.py            全部（部品が無ければ、要るファイルを飛ばす）
    python3 scripts/run_tests.py test_brushtools test_canvasfix
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 300   # 1 ファイルの上限（秒）


def needs_models() -> set[str]:
    lines = (ROOT / "tests" / "needs_models.txt").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def have_models() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "diffusers"))


def run(name: str) -> tuple[bool, str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", ATELIER_CHECK="off", ATELIER_ASSUME_FREE_RAM_GB="64")
    try:
        done = subprocess.run([sys.executable, "-m", "unittest", f"tests.{name}"], cwd=ROOT, env=env, capture_output=True,
                              text=True, errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"{TIMEOUT} 秒で終わらなかった"
    lines = [line for line in done.stderr.splitlines() if "propagateSizeHints" not in line]
    last = next((line for line in reversed(lines) if line.startswith(("OK", "FAILED"))), f"終了コード {done.returncode}")
    return done.returncode == 0, last if done.returncode == 0 else "\n".join(lines[-40:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="流すテストのファイルの名前（.py は付けない）")
    parser.add_argument("--all", action="store_true", help="モデルの部品が無くても、全部流す")
    args = parser.parse_args()
    names = args.names or sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
    skip = set() if (args.all or args.names or have_models()) else needs_models()
    failed, skipped, start = [], [], time.time()
    for name in names:
        if name in skip:
            skipped.append(name)
            continue
        ok, text = run(name)
        print(f"{'OK  ' if ok else 'FAIL'} {name}" + ("" if ok else f"\n{text}"), flush=True)
        if not ok:
            failed.append(name)
    ran = len(names) - len(skipped)
    print(f"\n{ran} ファイルを流し、{len(failed)} ファイルが落ちた（{time.time() - start:.0f} 秒）。"
          + (f"モデルの部品が無いので {len(skipped)} ファイルを飛ばした。" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
