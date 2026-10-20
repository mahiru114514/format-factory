param(
    [string]$ListenAddress = '127.0.0.1',
    [ValidateRange(1024,65535)][int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$taskProject = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$taskAddress = $null
if (-not [Net.IPAddress]::TryParse($ListenAddress, [ref]$taskAddress)) { throw '请输入明确的本机或局域网 IPv4 地址。' }
$taskOctets = $taskAddress.GetAddressBytes()
$taskPrivate = $taskOctets.Length -eq 4 -and (
    $taskOctets[0] -eq 127 -or $taskOctets[0] -eq 10 -or
    ($taskOctets[0] -eq 172 -and $taskOctets[1] -ge 16 -and $taskOctets[1] -le 31) -or
    ($taskOctets[0] -eq 192 -and $taskOctets[1] -eq 168))
if (-not $taskPrivate) { throw '测试服务仅允许本机或私有局域网地址。' }
& docker info --format '{{.OSType}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw '请先启动电脑上已安装的 Docker Desktop，再运行本脚本。' }
$taskName = 'format-factory-mobile-service'
$taskExisting = & docker ps -a --filter "name=^/$taskName`$" --format '{{.ID}}'
if ($taskExisting) {
    $taskManaged = & docker inspect --format '{{index .Config.Labels "dev.formatfactory.managed"}}' $taskExisting
    if ($taskManaged -ne 'true') { throw '同名容器不属于本工具，未作修改。' }
    $taskState = & docker inspect --format '{{.State.Status}}' $taskExisting
    if ($taskState -eq 'running') {
        & docker port $taskExisting 8765/tcp
        Write-Output '转换服务已在运行。需要修改地址时先运行停止脚本。'
        exit 0
    }
    throw '已有未运行的测试服务实例，请先运行停止脚本清理。'
}
Push-Location $taskProject
try {
    & docker build --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.13-slim -f mobile_server/Dockerfile -t format-factory-service:mobile-test .
    if ($LASTEXITCODE -ne 0) { throw '转换服务准备失败，请检查网络和 Docker 提示。' }
    & docker run --rm -d --name $taskName --label dev.formatfactory.managed=true --memory 2g --cpus 2 --cap-drop ALL --security-opt no-new-privileges -p "${ListenAddress}:${Port}:8765" format-factory-service:mobile-test python -m uvicorn mobile_server.app:app --host 0.0.0.0 --port 8765 --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw '转换服务未能启动，请检查端口是否占用。' }
    $taskUrl = "http://${ListenAddress}:$Port"
    $taskReady = $false
    Add-Type -AssemblyName System.Net.Http
    $taskHandler = [Net.Http.HttpClientHandler]::new()
    $taskHandler.UseProxy = $false
    $taskHttp = [Net.Http.HttpClient]::new($taskHandler)
    $taskHttp.Timeout = [TimeSpan]::FromSeconds(1)
    for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
        try {
            $taskBody = $taskHttp.GetStringAsync("$taskUrl/v1/capabilities").GetAwaiter().GetResult()
            $taskCapabilities = $taskBody | ConvertFrom-Json
            $taskReady = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    $taskHttp.Dispose()
    if (-not $taskReady) { throw '服务尚未就绪，请查看 Docker 容器日志。' }
    Write-Output "转换服务已就绪：$taskUrl"
    if ($taskOctets[0] -eq 127) {
        Write-Output '此地址仅电脑本机可用。手机联调请用 -ListenAddress 参数指定电脑实际局域网地址。'
    } else {
        Write-Output '在同一可信局域网中，将以上地址填入手机 App 设置，检查服务后使用。'
    }
    Write-Output "单文件上限 $($taskCapabilities.max_upload_bytes) 字节；任务保留 $($taskCapabilities.retention_seconds) 秒。"
} finally { Pop-Location }
