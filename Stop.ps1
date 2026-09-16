$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'logs\server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No recorded server.'; exit 0 }
$serverId = [int](Get-Content -LiteralPath $pidFile)
$serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $serverId" -ErrorAction SilentlyContinue
if ($serverProcess) {
    if ($serverProcess.Name -notmatch '^python(w)?\.exe$' -or $serverProcess.CommandLine -notmatch 'main\.py') {
        throw 'PID no longer belongs to the recorded Python server. Refusing to stop it.'
    }
    Stop-Process -Id $serverId
}
Remove-Item -LiteralPath $pidFile
Write-Output 'MediAtlas stopped.'
