# Setup.exe を画面ありで開き、利用者と同じに「次へ」を押して入れる（Actions の Windows で使う。配る物には入れない）。
# /S（黙って入れる）だけでは、ようこそ・コンポーネント・入れる場所・終わり・起動する、の道を一度も通さず、
# 画面で進めたときだけ起きる崩れ（動いているアプリで上書きできない、終わりの起動が動かない）を見逃した。
# NSIS の窓のボタンは Win32 の番号で決まっている（1 が 次へ・インストール・完了・OK、2 がキャンセル）ので、UI Automation で
# 番号 1 のボタンが押せるようになるたびに押す。コンポーネントは既定のまま、入れる場所も既定のまま。
# 窓ごとに見出しと写しを残し、終わったら入った物・ショートカット・起動（pythonw.exe）を見る。
param([Parameter(Mandatory)] [string] $Setup, [Parameter(Mandatory)] [string] $Out, [int] $TimeoutSec = 900)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, System.Drawing
New-Item -ItemType Directory -Force $Out | Out-Null
Add-Type -Namespace W -Name U -MemberDefinition '[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);'
$A = [System.Windows.Automation.AutomationElement]
$T = [System.Windows.Automation.TreeScope]
$log = Join-Path $Out 'pages.txt'

function Shot([string] $name) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save((Join-Path $Out "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}

$proc = Start-Process -FilePath $Setup -PassThru
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$step = 0; $last = ''
while (-not $proc.HasExited) {
  if ((Get-Date) -gt $deadline) { Shot 'timeout'; $proc.Kill(); throw "Setup.exe が $TimeoutSec 秒で終わらない（最後の窓: $last）" }
  $cond = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $proc.Id)
  $wins = $A::RootElement.FindAll($T::Children, $cond)
  foreach ($w in $wins) {
    $texts = ($w.FindAll($T::Descendants, [System.Windows.Automation.Condition]::TrueCondition) |
      Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Text -and $_.Current.Name } |
      Select-Object -First 4 | ForEach-Object { $_.Current.Name }) -join ' / '
    $btnCond = New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty, '1')
    $btn = $w.FindFirst($T::Descendants, $btnCond)
    if (-not $btn -or -not $btn.Current.IsEnabled) { continue }
    $sig = "$($w.Current.Name) | $texts | $($btn.Current.Name)"
    if ($sig -eq $last) { continue }   # 同じ窓で押したばかり。次の窓が出るのを待つ
    $step++
    "$step. $sig" | Tee-Object -Append -FilePath $log
    Shot ("{0:D2}" -f $step)
    # NSIS のボタンは UI Automation の Invoke を持たないことがあるので、Win32 の BM_CLICK を送る
    [W.U]::PostMessage([IntPtr]$btn.Current.NativeWindowHandle, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    $last = $sig
  }
  Start-Sleep -Milliseconds 700
}
"exit=$($proc.ExitCode) steps=$step" | Tee-Object -Append -FilePath $log
if ($proc.ExitCode -ne 0) { throw "Setup.exe の終わりの番号が $($proc.ExitCode)" }
if ($step -lt 4) { throw "押した窓が $step 個しかない（コンポーネント・入れる場所・入れる・終わりを通っていない）" }

$dir = 'C:\Program Files\AtelIer'
$need = @("$dir\python\pythonw.exe", "$dir\atelier\app\main_window.py", "$dir\Uninstall.exe", "$dir\VERSION",
          'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\AtelIer\AtelIer.lnk', 'C:\Users\Public\Desktop\AtelIer.lnk')
$miss = $need | Where-Object { -not (Test-Path $_) }
if ($miss) { throw "入っていない: $($miss -join ', ')" }
$ver = (Get-Content "$dir\VERSION" -Raw).Trim()
$reg = (Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AtelIer').DisplayVersion
"版: $ver 登録: $reg" | Tee-Object -Append -FilePath $log
if ($ver -ne $reg) { throw "入った版 $ver と登録の版 $reg が違う" }
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut('C:\Users\Public\Desktop\AtelIer.lnk')
"ショートカット: $($lnk.TargetPath) $($lnk.Arguments)" | Tee-Object -Append -FilePath $log
if ($lnk.TargetPath -ne "$dir\python\pythonw.exe") { throw "ショートカットの先が違う: $($lnk.TargetPath)" }

# 終わりの「起動する」（既定で付いている）で、アプリが動き出して落ちずにいるか
$app = $null
for ($i = 0; $i -lt 60 -and -not $app; $i++) {
  Start-Sleep 2
  $app = Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$dir\python\*" } | Select-Object -First 1
}
if (-not $app) { Shot 'no-app'; throw "終わりの「起動する」でアプリが動き出さない" }
Start-Sleep 20
if ($app.HasExited) { Shot 'app-exited'; throw "アプリが起動して 20 秒のうちに落ちた（番号 $($app.ExitCode)）" }
Shot 'app'
"起動: pid=$($app.Id) は 20 秒たっても動いている" | Tee-Object -Append -FilePath $log
