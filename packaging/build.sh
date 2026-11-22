#!/bin/sh
# AtelIer の Setup.exe を Linux の上で組む（NSIS の makensis。Windows の機械も CI も要らない）。
#
#   sh packaging/build.sh          dist/AtelIer-Setup.exe を作る
#
# 中身: Python 本体（python.org の埋め込み版 amd64）、pip、画面の部品（PySide6 6.9.3）、numpy、Pillow、
# 模型を取る部品（huggingface_hub）、atelier。
# 入れないもの: 絵を描く部品（torch など）と模型。torch は機械の GPU で版が変わるので、初めて起動したときに合う版を取る。
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYVER="${ATELIER_PYVER:-3.12.10}"
PYTAG="$(echo "$PYVER" | cut -d. -f1-2 | tr -d .)"
VERSION="$(cat "$ROOT/VERSION")"
OUT="$ROOT/dist"
B="$OUT/atelier-build"
SRC="$B/app"
command -v makensis >/dev/null || { echo "makensis が無い（apt install nsis）" >&2; exit 1; }
rm -rf "$B"; mkdir -p "$SRC" "$OUT/download"
cd "$ROOT"
# 中身は HEAD から取る。コミットしていない変更は入らないので、残っていれば止める
if [ -n "$(git status --porcelain --untracked-files=normal -- atelier packaging VERSION tools styles casts config)" ]; then
  echo "コミットしていない変更がある。コミットしてから組む:" >&2; git status --short -- atelier packaging tools styles casts config >&2; exit 1
fi

echo "== atelier（HEAD）"
# 入れる物は atelier/ から import と道の文字列を辿って集める（bundle_list.py）。手で並べた一覧では tools/gen の台本と
# styles・casts の設定が抜け、配った版で検品・おまかせ・仕上げ・キャラクターデザインが import で落ちた。
# 配る中身だけで入口が呼べるかは tests/test_bundle.py が見る
python3 "$ROOT/packaging/bundle_list.py" > "$B/files.txt"
git archive HEAD $(cat "$B/files.txt") | tar -x -C "$SRC"
:

echo "== Python $PYVER（埋め込み版）"
ZIP="$OUT/download/python-$PYVER-embed-amd64.zip"
[ -f "$ZIP" ] || curl -sSfL -o "$ZIP" "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip"
mkdir -p "$SRC/python"
python3 -m zipfile -e "$ZIP" "$SRC/python"
# 埋め込み版は ._pth で読む場所を固定し、-m で入れた場所のパッケージを読まない。外して普通の Python と同じに読ませる
rm -f "$SRC/python/python$PYTAG._pth"

echo "== 部品（Windows 用の wheel）"
W="--platform win_amd64 --python-version $PYVER --implementation cp --only-binary=:all: -q --disable-pip-version-check"
SP="$SRC/python/Lib/site-packages"
# PySide6 は 6.9.3 に固定する（6.12.0 は線を数百本引くと落ちた）
python3 -m pip install $W --target "$SP" pip "PySide6-Essentials==6.9.3" numpy Pillow huggingface_hub

echo "== 同梱物の欠けを見る"
missing=""
for f in VERSION python/python.exe python/pythonw.exe atelier/app/main_window.py atelier/qc/hand_check.py atelier/qc/request_check.py tools/gen/hands.py tools/gen/tagger.py tools/gen/data_home.py atelier/ui/help/install.md atelier/ui/help/manual.md atelier/ui/help_view.py atelier/app/migrate.py atelier/files/paths.py atelier/models/first_setup.py \
         python/Lib/site-packages/PySide6 python/Lib/site-packages/numpy python/Lib/site-packages/PIL \
         python/Lib/site-packages/huggingface_hub python/Lib/site-packages/pip; do
  [ -e "$SRC/$f" ] || missing="$missing $f"
done
[ -z "$missing" ] || { echo "欠けている:$missing" >&2; exit 1; }

echo "== アプリのアイコン（packaging/make_icon.py が作った atelier/ai/icon/app.ico を窓・ショートカット・インストーラーに使う）"
# 入れてある .ico をそのまま使う。Actions の機械は書体が違い、作り直すと形が変わるため。無いときだけ作る
if [ ! -f "$SRC/atelier/ai/icon/app.ico" ]; then
  python3 "$ROOT/packaging/make_icon.py" "$SRC/atelier/ai/icon"
fi
ICONDEF="-DICON=$SRC/atelier/ai/icon/app.ico"

echo "== Setup.exe"
makensis -V2 $ICONDEF -DSRC="$SRC" -DOUT="$OUT/AtelIer-Setup.exe" -DVERSION="$VERSION" "$ROOT/packaging/installer.nsi"
ls -la "$OUT/AtelIer-Setup.exe"
