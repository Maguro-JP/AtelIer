# AtelIer の Setup.exe が、選ばれたデザイナーごとに呼ぶ（-Repo owner/name）。最新の Release の拡張だけの Setup（名前に Extension と Setup を含む .exe）を取って静かに入れる。
# Python ごと入った単体の Setup.exe は取らない（AtelIer を使う人は拡張だけを入れる。atelier/extension_catalog.py の EXTENSION_SETUP_PATTERN）。
# 呼ぶ節は packaging/extension_sections.py が atelier/extension_catalog.py の一覧から作る。
# 終わりの番号: 0 は入れた、2 は Release か拡張だけの Setup が無い、1 は取れなかった（どれでも AtelIer の入れ方は止めない。
# 2 と 1 は呼んだ節が理由を窓で出して飛ばす）
param([Parameter(Mandatory = $true)][string]$Repo)
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 は進みの表示があると Invoke-WebRequest が何十倍も遅くなり、数百 MB の Setup.exe が終わらないように見える
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
  $rel = Invoke-RestMethod -UseBasicParsing -Headers @{ 'User-Agent' = 'AtelIer-Setup' } `
    -Uri "https://api.github.com/repos/$Repo/releases/latest"
} catch {
  # Release が 1 つも無いリポジトリは 404 を返す。ネットの失敗と分けて知らせる
  if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404) { exit 2 }
  exit 1
}
$asset = $rel.assets | Where-Object { $_.name -like '*Extension*Setup*.exe' } | Select-Object -First 1
if (-not $asset) { exit 2 }
$out = Join-Path $env:TEMP $asset.name
try {
  Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $out
  $p = Start-Process -FilePath $out -ArgumentList '/S' -Wait -PassThru
  Remove-Item $out -ErrorAction SilentlyContinue
  exit $(if ($p.ExitCode -eq 0) { 0 } else { 1 })
} catch { exit 1 }
