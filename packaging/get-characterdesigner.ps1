# AtelIer の Setup.exe が、選ばれたときだけ呼ぶ。CharacterDesigner の最新の Release の Setup.exe を取って静かに入れる。
# 終わりの番号: 0 は入れた、2 は Release に Setup.exe が無い、1 は取れなかった（どれでも AtelIer の入れ方は止めない）
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 は進みの表示があると Invoke-WebRequest が何十倍も遅くなり、数百 MB の Setup.exe が終わらないように見える
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
  $rel = Invoke-RestMethod -UseBasicParsing -Headers @{ 'User-Agent' = 'AtelIer-Setup' } `
    -Uri 'https://api.github.com/repos/Maguro-JP/CharacterDesigner/releases/latest'
} catch { exit 1 }
$asset = $rel.assets | Where-Object { $_.name -like '*Setup*.exe' } | Select-Object -First 1
if (-not $asset) { exit 2 }
$out = Join-Path $env:TEMP $asset.name
try {
  Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $out
  $p = Start-Process -FilePath $out -ArgumentList '/S' -Wait -PassThru
  Remove-Item $out -ErrorAction SilentlyContinue
  exit $(if ($p.ExitCode -eq 0) { 0 } else { 1 })
} catch { exit 1 }
