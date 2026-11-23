#!/usr/bin/env python3
"""作業ブランチで直した不具合のうち、main にまだ入っていない物を一覧にして注意に出す。

作業ブランチでだけ直して利用者に「直した」と伝え、main と配った版には入っていなかったことがあった
（起動のたびに出る「前に落ちたときの記録があります」の直しなど）。main は squash でマージするので、
コミットの ID やメッセージでは入ったかどうかが分からない。そこで、コミットが足した行のうち
今のブランチの先にも残っている行が、main の同じファイルにどれだけあるかで見る。

    python3 scripts/unmerged_fixes.py                       origin/claude/* の全部を origin/main と比べる
    python3 scripts/unmerged_fixes.py origin/claude/FIX-x   1 本だけ
    --strict を付けると、見つかったときに 1 で終わる（既定は注意だけで 0）

GitHub Actions では ::warning:: の形で出す（unmerged-fixes.yml）。precheck は scripts/validate.sh から呼ぶ。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

FIX_WORDS = re.compile(r"直す|直し|直した|不具合|バグ|落ち|止ま|崩れ|ずれ|消え|潰れ|隠れ|出たまま|残る")
CODE = (".py", ".yml", ".yaml", ".sh", ".nsi", ".iss", ".ps1", ".json")
MISSING_BELOW = 0.8   # 残っている行のうち main にある割合がこれ未満なら、入っていないと見る（私の推測の境目）


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, errors="replace").stdout


class Files:
    def __init__(self, ref: str):
        self.ref, self.cache = ref, {}

    def lines(self, path: str) -> set[str] | None:
        if path not in self.cache:
            r = subprocess.run(["git", "show", f"{self.ref}:{path}"], capture_output=True, text=True, errors="replace")
            self.cache[path] = {line.strip() for line in r.stdout.splitlines()} if r.returncode == 0 else None
        return self.cache[path]


def coverage(commit: str, main: Files, tip: Files) -> tuple[int, int]:
    """コミットが足した行のうち、ブランチの先に残っている行の数と、そのうち main にある数"""
    total = hit = 0
    cur = None
    for line in git("show", "--format=", "-U0", commit).splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") and line.endswith(CODE) else None
            continue
        if cur is None or not line.startswith("+"):
            continue
        text = line[1:].strip()
        if len(text) <= 12 or text.startswith("#"):
            continue   # 短い行とコメントは、どのファイルにもある・言い回しが変わるので数えない
        at_tip = tip.lines(cur)
        if not at_tip or text not in at_tip:
            continue   # 同じブランチで後から書き換えた行は見ない
        total += 1
        have = main.lines(cur)
        if have and text in have:
            hit += 1
    return total, hit


def check(branch: str, base: str) -> list[tuple[str, str, int, int]]:
    main, tip = Files(base), Files(branch)
    found = []
    for row in git("log", "--no-merges", "--format=%h\t%s", f"{base}..{branch}").splitlines():
        commit, subject = row.split("\t", 1)
        if not FIX_WORDS.search(subject):
            continue
        total, hit = coverage(commit, main, tip)
        if total and hit / total < MISSING_BELOW:
            found.append((commit, subject, hit, total))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("branches", nargs="*")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    branches = a.branches or [b.strip() for b in git("branch", "-r", "--format=%(refname:short)", "--list", "origin/claude/*").splitlines() if b.strip()]
    actions = os.environ.get("GITHUB_ACTIONS") == "true"
    count = 0
    for br in branches:
        rows = check(br, a.base)
        count += len(rows)
        for commit, subject, hit, total in rows:
            msg = f"{br} の {commit}「{subject}」は main に入っていません（足した行 {total} のうち main にあるのは {hit}）"
            print(f"::warning title=main に無い直し::{msg}" if actions else f"注意: {msg}")
    if count:
        print(f"main に無い直しが {count} 件あります。直しだけを main から切ったブランチに当てて出してください")
    return 1 if (count and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
