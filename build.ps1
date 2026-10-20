$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTemp = Join-Path $PSScriptRoot '.work\tmp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
& '.\.venv\Scripts\python.exe' -X utf8 -m PyInstaller --noconfirm FormatFactory.spec
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
Copy-Item -LiteralPath 'README.md' -Destination 'dist\FormatFactory\使用说明.md' -Force
Copy-Item -LiteralPath 'THIRD_PARTY.md' -Destination 'dist\FormatFactory\THIRD_PARTY.md' -Force
Write-Host 'Ready: dist\FormatFactory\FormatFactory.exe'
