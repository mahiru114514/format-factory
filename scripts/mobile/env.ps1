$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($taskRoot -match '[^\x00-\x7F]') {
    if (-not ('FactoryBuildDrive' -as [type])) {
        Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
using System.Text;
public static class FactoryBuildDrive {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern uint QueryDosDevice(string name, StringBuilder target, uint length);
}
'@
    }
    if (-not (Test-Path F:/)) {
        & subst F: $taskRoot
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create the temporary ASCII build path.' }
    }
    $taskDriveTarget = [Text.StringBuilder]::new(32768)
    [void][FactoryBuildDrive]::QueryDosDevice('F:', $taskDriveTarget, 32768)
    if ($taskDriveTarget.ToString().TrimEnd('\') -ne ('\??\' + $taskRoot.TrimEnd('\'))) {
        throw 'F: is occupied. Use an ASCII project path or free the other mapping first.'
    }
    $taskRoot = 'F:\'
}
$env:FLUTTER_ROOT = Join-Path $taskRoot '.tools\flutter'
$env:ANDROID_HOME = Join-Path $taskRoot '.tools\android-sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_USER_HOME = Join-Path $taskRoot '.tools\android-home'
Remove-Item Env:ANDROID_PREFS_ROOT -ErrorAction SilentlyContinue
$env:ANDROID_AVD_HOME = Join-Path $taskRoot '.tools\android-avd'
$env:PUB_CACHE = Join-Path $taskRoot '.tools\pub-cache'
$env:GRADLE_USER_HOME = Join-Path $taskRoot '.tools\gradle'
$env:APPDATA = Join-Path $taskRoot '.tools\appdata'
$env:LOCALAPPDATA = Join-Path $taskRoot '.tools\localappdata'
$env:TEMP = Join-Path $taskRoot '.tools\mobile-temp'
$env:TMP = $env:TEMP
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'
$env:DART_SUPPRESS_ANALYTICS = 'true'
$env:JAVA_HOME = 'E:\java\jdk-21'
$env:PATH = "$env:FLUTTER_ROOT\bin;$env:ANDROID_HOME\platform-tools;$env:JAVA_HOME\bin;$env:PATH"
$env:GIT_CONFIG_GLOBAL = Join-Path $taskRoot '.tools\gitconfig'
foreach ($taskPath in @($env:APPDATA, $env:LOCALAPPDATA, $env:PUB_CACHE, $env:GRADLE_USER_HOME, $env:ANDROID_USER_HOME, $env:ANDROID_AVD_HOME, $env:TEMP)) {
    New-Item -ItemType Directory -Path $taskPath -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $env:GIT_CONFIG_GLOBAL)) {
    $taskSdkPath = $env:FLUTTER_ROOT.Replace('\', '/')
    [IO.File]::WriteAllText($env:GIT_CONFIG_GLOBAL, "[safe]`n`tdirectory = $taskSdkPath`n", [Text.UTF8Encoding]::new($false))
}
& git config --file $env:GIT_CONFIG_GLOBAL --add safe.directory $env:FLUTTER_ROOT.Replace('\', '/')
# Dart and Gradle do not automatically share the Windows Internet proxy.
# Apply only this process and this project's ignored Gradle cache configuration.
if (-not $env:HTTPS_PROXY) {
    $taskProbeUri = [Uri]'https://pub.dev'
    $taskSystemProxy = [System.Net.WebRequest]::DefaultWebProxy.GetProxy($taskProbeUri)
    if ($taskSystemProxy -and $taskSystemProxy.Host -ne $taskProbeUri.Host) {
        $env:HTTPS_PROXY = $taskSystemProxy.AbsoluteUri
        $env:HTTP_PROXY = $taskSystemProxy.AbsoluteUri
    }
}
$env:NO_PROXY = 'localhost,127.0.0.1,::1'
$taskGradleConfig = @('org.gradle.daemon=true', 'org.gradle.java.installations.auto-download=false')
if ($env:HTTPS_PROXY) {
    $taskProxy = [Uri]$env:HTTPS_PROXY
    foreach ($taskScheme in @('http', 'https')) {
        $taskGradleConfig += @("systemProp.$taskScheme.proxyHost=$($taskProxy.Host)", "systemProp.$taskScheme.proxyPort=$($taskProxy.Port)")
    }
    $taskGradleConfig += 'systemProp.http.nonProxyHosts=localhost|127.*|[::1]'
}
$taskGradleConfig | Set-Content -Encoding ascii (Join-Path $env:GRADLE_USER_HOME 'gradle.properties')
