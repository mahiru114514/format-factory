$ErrorActionPreference = 'Stop'
$taskName = 'format-factory-mobile-service'
$taskContainer = & docker ps -a --filter "name=^/$taskName`$" --format '{{.ID}}'
if (-not $taskContainer) { Write-Output '转换服务没有运行。'; exit 0 }
$taskManaged = & docker inspect --format '{{index .Config.Labels "dev.formatfactory.managed"}}' $taskContainer
if ($taskManaged -ne 'true') { throw '同名容器不属于本工具，未作修改。' }
& docker stop --timeout 10 $taskContainer
if ($LASTEXITCODE -ne 0) { throw '服务未能正常停止，请查看 Docker 提示。' }
Write-Output '转换服务已停止，临时服务文件随容器清理。手机中已保存的结果保留。'
