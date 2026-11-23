# AtelIer の Setup.exe が、選ばれたときだけ呼ぶ。CharacterDesigner の最新の Release の拡張だけの Setup（名前に Extension と Setup を含む .exe）を取って静かに入れる。
# Python ごと入った単体の Setup.exe は取らない（AtelIer を使う人は拡張だけを入れる）。
# 終わりの番号: 0 は入れた、2 は Release か拡張だけの Setup が無い、1 は取れなかった（どれでも AtelIer の入れ方は止めない。2 と 1 は呼んだ節が理由を窓で出して飛ばす）
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 は進みの表示があると Invoke-WebRequest が何十倍も遅くなり、数百 MB の Setup.exe が終わらないように見える
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
  $rel = Invoke-RestMethod -UseBasicParsing -Headers @{ 'User-Agent' = 'AtelIer-Setup' } `
    -Uri 'https://api.github.com/repos/Maguro-JP/CharacterDesigner/releases/latest'
} catch { exit 1 }
$asset = $rel.assets | Where-Object { $_.name -like '*Extension*Setup*.exe' } | Select-Object -First 1
if (-not $asset) { exit 2 }
$out = Join-Path $env:TEMP $asset.name
try {
  Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $out
  $p = Start-Process -FilePath $out -ArgumentList '/S' -Wait -PassThru
  Remove-Item $out -ErrorAction SilentlyContinue
  exit $(if ($p.ExitCode -eq 0) { 0 } else { 1 })
} catch { exit 1 }
