param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$taskProject = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$taskBuildProject = $taskRoot
Push-Location (Join-Path $taskBuildProject 'mobile')
try {
    flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
    if (-not $SkipTests) {
        flutter analyze --no-pub
        if ($LASTEXITCODE -ne 0) { throw 'Static analysis failed.' }
        flutter test --no-pub
        if ($LASTEXITCODE -ne 0) { throw 'Mobile tests failed.' }
    }
    # Flutter regenerates the release plugin registrant only when pub is enabled;
    # otherwise an earlier device test leaves its dev-only plugin in Java source.
    flutter build apk --release
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
    $taskDelivery = Join-Path $taskProject 'deliverables/mobile'
    New-Item -ItemType Directory -Path $taskDelivery -Force | Out-Null
    $taskApk = Join-Path $taskDelivery '格式转换工厂-安卓测试版.apk'
    Copy-Item -LiteralPath 'build/app/outputs/flutter-apk/app-release.apk' -Destination $taskApk -Force
    & (Join-Path $env:ANDROID_HOME 'build-tools/36.0.0/apksigner.bat') verify --verbose --print-certs $taskApk
    if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed.' }
    # aapt's native Windows path handling requires the ASCII build path.
    & (Join-Path $env:ANDROID_HOME 'build-tools/36.0.0/aapt.exe') dump badging 'build/app/outputs/flutter-apk/app-release.apk' | Set-Content (Join-Path $taskDelivery 'android-package-info.txt') -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'APK metadata inspection failed.' }
    $taskHash = (Get-FileHash -LiteralPath $taskApk -Algorithm SHA256).Hash.ToLower()
    "$taskHash  格式转换工厂-安卓测试版.apk" | Set-Content (Join-Path $taskDelivery 'SHA256SUMS.txt') -Encoding utf8
    Write-Output "Verified Android test package: $taskApk"
} finally { Pop-Location }
