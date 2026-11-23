#!/usr/bin/env bash
# precheck が呼ぶ、このリポジトリだけの検査。
# 作業ブランチで直した不具合が main に無いままになっていないかを、注意として出す（止めない）。
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
git fetch -q origin main 2>/dev/null || true
python3 scripts/unmerged_fixes.py
