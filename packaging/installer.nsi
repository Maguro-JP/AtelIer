; AtelIerの Setup.exe。build.sh から makensis で組む（SRC、OUT、VERSION を渡す）
;
; 置き場（atelier/files/paths.py と同じ）
;   C:\Program Files\AtelIer\      プログラム（入れ直すたびに丸ごと置き換える）
;   C:\ProgramData\AtelIer\        部品（torch など。初回の起動で取る）と記録
;   C:\LLM\gguf、C:\LLM\huggingface          模型（自作アプリで共有。消さない）
;   ピクチャ\AtelIer\              描いた絵
;
; 更新: 同じ場所に入れ直す。前のプログラムを消してから置くので、古いファイルが残らない。部品・模型・描いた絵はそのまま
; 消す: アプリが入れたファイル、ショートカット、登録だけを消す（インストール先・ProgramData・C:\LLM を /r で丸ごと消さない）。部品（ProgramData の gen\lib と llm）は聞いてから消す。利用者の設定（QSettings と ProgramData の設定のファイル）、模型、描いた絵は消さない
Target amd64-unicode
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP "AtelIer"
!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

Name "${APP}"
OutFile "${OUT}"
InstallDir "$PROGRAMFILES64\${APP}"
InstallDirRegKey HKLM "Software\${APP}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; アプリのアイコン。build.sh が atelier/ai/icon/app.png（利用者が選んだ絵）から .ico を作ったときだけ ICON を渡す。
; 無い間は今まで通り pythonw.exe のアイコンのまま
!ifdef ICON
  !define MUI_ICON "${ICON}"
  !define MUI_UNICON "${ICON}"
  !define LNK_ICON "$INSTDIR\atelier\ai\icon\app.ico"
!else
  !define LNK_ICON "$INSTDIR\python\pythonw.exe"
!endif

; 終わりの「起動する」は、エクスプローラーにショートカットを開かせて、ふつうの権限で起動する。
; Setup.exe は管理者で動くので、そのまま Exec すると アプリまで管理者で動き、あとでふつうに開いたときと置き場の権限や設定がずれる
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!define MUI_FINISHPAGE_RUN_TEXT "AtelIer を起動する"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Japanese"


; アプリが入れた物だけを消す。並びは build.sh が SRC に置く最上位の名前（bundle_list.py の最上位と python）と同じにする。
; インストール先そのものは /r で消さない（利用者が置いた物を巻き込むため）。空になったときだけ消す
!macro RemoveAppFiles
  ${If} ${FileExists} "$INSTDIR\VERSION"
  ${AndIf} ${FileExists} "$INSTDIR\atelier\__init__.py"
    RMDir /r "$INSTDIR\atelier"
    RMDir /r "$INSTDIR\tools"
    RMDir /r "$INSTDIR\python"
    RMDir /r "$INSTDIR\casts"
    RMDir /r "$INSTDIR\config"
    RMDir /r "$INSTDIR\docs"
    RMDir /r "$INSTDIR\styles"
    Delete "$INSTDIR\VERSION"
    Delete "$INSTDIR\LICENSE"
  ${EndIf}
!macroend

Function LaunchApp
  SetShellVarContext all
  Exec '"$WINDIR\explorer.exe" "$SMPROGRAMS\${APP}\${APP}.lnk"'
FunctionEnd

Section "AtelIer" SecMain
  SectionIn RO
  ; 前の版のアプリ（pythonw.exe）が動いていると python\ の中が消せず、上書きで「書き込めません」の窓が出て入れられない。
  ; 「更新を確かめる」から開いたときや、前の Setup.exe の終わりで起動したままのときに起きる。入れた所の python から動く物だけを閉じる
  ; 動いているかを見て、動いていれば閉じてよいかを聞く（黙って入れる /S のときは閉じる）
  StrCpy $3 "$INSTDIR\python\"
  StrCpy $4 "$$p = @(Get-Process python,pythonw -ErrorAction SilentlyContinue | Where-Object { $$_.Path -and $$_.Path.StartsWith('$3', 'OrdinalIgnoreCase') })"
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "$4; exit $$p.Count"'
  Pop $0
  ${If} $0 != "0"
  ${AndIf} $0 != "error"
  ${AndIf} $0 != "timeout"
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "AtelIer が動いています。閉じてから入れます。$\r$\n保存していない絵があれば、「キャンセル」を押してアプリで保存してから、もう一度 Setup.exe を開いてください。" /SD IDOK IDOK close_app
      Abort "AtelIer が動いていたので、入れるのをやめました"
    close_app:
    nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "$4; $$p | Stop-Process -Force; Start-Sleep -Seconds 2"'
    Pop $0
    DetailPrint "動いていた AtelIer を閉じました"
  ${EndIf}
  ; 更新のとき、前のプログラムを先に消す（消したファイルが残って古いまま読まれないように）。
  ; 消すのはアプリが入れた名前だけで、前の AtelIer が入っている印（VERSION と atelier\__init__.py）がある所に限る。
  ; 利用者が選んだ既存のフォルダー（同じ名前の tools などを持つ所）や、そこに利用者が置いた物を消さないため
  !insertmacro RemoveAppFiles
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; 書き換える置き場。ふつうの利用者も書けるようにする（ProgramData と C:\ 直下は既定で管理者しか書けない）
  CreateDirectory "$COMMONPROGRAMDATA\${APP}"
  nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$COMMONPROGRAMDATA\${APP}" /grant *S-1-5-32-545:(OI)(CI)M /T /Q'
  ; 模型の置き場はシステムのドライブの LLM（アプリの paths.default_model_dir と同じ。C: 以外にも合わせる）
  StrCpy $1 "$WINDIR" 3
  CreateDirectory "$1LLM\gguf"
  CreateDirectory "$1LLM\huggingface"
  CreateDirectory "$1LLM\manual"
  nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$1LLM" /grant *S-1-5-32-545:(OI)(CI)M /Q'

  ; CharacterDesigner からの引き継ぎは、ここでは黙ってしない。初めての起動で利用者が窓で選ぶ（atelier/app/migrate_dialog.py）


  SetShellVarContext all
  SetOutPath "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortcut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\python\pythonw.exe" "-E -s -m atelier" "${LNK_ICON}"
  CreateShortcut "$SMPROGRAMS\${APP}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\python\pythonw.exe" "-E -s -m atelier" "${LNK_ICON}"

  WriteRegStr HKLM "Software\${APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINST}" "DisplayName" "${APP}"
  WriteRegStr HKLM "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST}" "DisplayIcon" "${LNK_ICON}"
  WriteRegStr HKLM "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${UNINST}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST}" "NoRepair" 1
SectionEnd

; 選べる項目。既定は外す。ネットから CharacterDesigner の最新の Release の Setup.exe を取って静かに入れる。
; inetc プラグインは NSIS の標準に無く build.sh の環境に入れる手間が増えるので、Windows に必ずある PowerShell で取る
Section /o "CharacterDesigner も入れる（ネットから取る）" SecCD
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "${__FILEDIR__}\get-characterdesigner.ps1"
  DetailPrint "CharacterDesigner の最新の Setup.exe を取っています"
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\get-characterdesigner.ps1"'
  Pop $0
  ${If} $0 == "2"
    MessageBox MB_OK|MB_ICONINFORMATION "CharacterDesigner の Release に Setup.exe がまだありません。AtelIer だけを入れて先へ進みます。" /SD IDOK
  ${ElseIf} $0 != "0"
    MessageBox MB_OK|MB_ICONINFORMATION "CharacterDesigner を取れませんでした（ネットにつながっているかを確かめてください）。AtelIer だけを入れて先へ進みます。" /SD IDOK
  ${EndIf}
  SetOutPath "$INSTDIR"
SectionEnd

Section "Uninstall"
  ; 入れた物だけを消す。インストール先に利用者が置いた物は残し、空になったときだけフォルダーを消す
  !insertmacro RemoveAppFiles
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  SetShellVarContext all
  ; 取った更新の Setup.exe と自動保存の控えは、部品を残すときも消す（作業ファイルではなく一時の物）
  RMDir /r "$COMMONPROGRAMDATA\${APP}\updates"
  RMDir /r "$COMMONPROGRAMDATA\${APP}\autosave"
  Delete "$SMPROGRAMS\${APP}\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${APP}"
  Delete "$DESKTOP\${APP}.lnk"
  DeleteRegKey HKLM "${UNINST}"
  DeleteRegKey HKLM "Software\${APP}"
  ; 窓の並びと設定（QSettings が HKCU\Software\AtelIer に書く）は消さない。入れ直したときに引き継ぐ
  ; 部品（torch など 数 GB）は取り直せるので、聞いてから消す。消すのは部品の名前だけにする。
  ; ProgramData\AtelIer には利用者の物（設定・ライブラリー・学んだ基準・ごみ箱・控え・拡張の置き場 extensions など）も
  ; 入っているので、フォルダーを /r で消さない。黙って消す（/S）ときは何も消さない
  MessageBox MB_YESNO|MB_ICONQUESTION "絵を描く部品（$COMMONPROGRAMDATA\${APP} の gen\lib と llm）も消しますか？$\r$\n部品は、入れ直したときに取り直せます。設定・ライブラリー・拡張は消さずに残します。描いた絵と模型はここには入っていません。" /SD IDNO IDNO keep_data
    RMDir /r "$COMMONPROGRAMDATA\${APP}\gen\lib"
    RMDir "$COMMONPROGRAMDATA\${APP}\gen"
    RMDir /r "$COMMONPROGRAMDATA\${APP}\llm"
    Delete "$COMMONPROGRAMDATA\${APP}\setup.log"
  keep_data:
  MessageBox MB_OK|MB_ICONINFORMATION "アンインストールしました。$\r$\n$\r$\n次の物は残してあります。$\r$\n描いた絵: ピクチャの ${APP} フォルダー$\r$\n模型: C:\LLM（ほかの自作アプリも使うため。要らなければフォルダーごと消せます）" /SD IDOK
SectionEnd
