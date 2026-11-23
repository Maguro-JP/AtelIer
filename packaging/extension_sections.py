"""atelier/extension_catalog.py の一覧から、AtelIer の Setup.exe の選べる部品（NSIS の節）を書き出す。

build.sh が組むたびに呼び、出力を installer.nsi が !include する。デザイナーを足すときは一覧を直すだけで済むようにするため。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atelier.extension_catalog import for_installer  # noqa: E402


def sections() -> str:
    out = []
    for i, d in enumerate(for_installer()):
        out.append(f"""
; {d.name}: 既定で入れる（利用者が外せば入れない。/S でも既定どおり）。{d.repo} の最新の Release の拡張だけの Setup を取って静かに入れる
Section "{d.name} も入れる（ネットから取る）" SecExt{i}
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "${{PKGDIR}}\\get-extension.ps1"
  DetailPrint "{d.name} の拡張だけの Setup を取っています"
  nsExec::ExecToLog '"$SYSDIR\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\\get-extension.ps1" -Repo "{d.repo}"'
  Pop $0
  ${{If}} $0 == "2"
    MessageBox MB_OK|MB_ICONINFORMATION "{d.name} の Release に拡張だけの Setup がまだありません。{d.name} を飛ばして先へ進みます。" /SD IDOK
  ${{ElseIf}} $0 != "0"
    MessageBox MB_OK|MB_ICONINFORMATION "{d.name} を取れませんでした（ネットにつながっているかを確かめてください）。{d.name} を飛ばして先へ進みます。" /SD IDOK
  ${{EndIf}}
  SetOutPath "$INSTDIR"
SectionEnd
""")
    return "".join(out)


if __name__ == "__main__":
    sys.stdout.write(sections())
