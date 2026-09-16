param([string]$Python = '', [switch]$Build, [switch]$Foreground)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
if (-not $Python) {
    $localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $condaPython = Join-Path $env:USERPROFILE 'anaconda3\envs\langchain_env\python.exe'
    if (Test-Path -LiteralPath $localPython) { $Python = $localPython }
    elseif (Test-Path -LiteralPath $condaPython) { $Python = $condaPython }
    else { $Python = (Get-Command python).Source }
}
if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.env'))) { throw 'Copy backend/.env.example to backend/.env and configure it first.' }
$env:PYTHONIOENCODING = 'utf-8'
$localTools = Join-Path $projectRoot '.tools'
if (Test-Path -LiteralPath $localTools) { $env:PYTHONPATH = $localTools }
if ($Build -or -not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    $bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
    if (Test-Path -LiteralPath $bundledNode) { $env:PATH = $bundledNode + ';' + $env:PATH }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) { & npm.cmd ci; if ($LASTEXITCODE) { throw 'npm ci failed' } }
        & npm.cmd run build
        if ($LASTEXITCODE) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
if ($Foreground) {
    Push-Location $backendRoot
    try { & $Python main.py } finally { Pop-Location }
} else {
    $logRoot = Join-Path $projectRoot 'logs'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $pidFile = Join-Path $logRoot 'server.pid'
    if (Test-Path -LiteralPath $pidFile) {
        $existingProcess = Get-Process -Id ([int](Get-Content -LiteralPath $pidFile)) -ErrorAction SilentlyContinue
        if ($existingProcess) { Write-Output 'The recorded server is already running. Use Stop.ps1 before restarting.'; exit 0 }
    }
    $serverProcess = Start-Process -FilePath $Python -ArgumentList @('main.py') -WorkingDirectory $backendRoot `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'server.out.log') `
        -RedirectStandardError (Join-Path $logRoot 'server.err.log')
    Set-Content -LiteralPath $pidFile -Value $serverProcess.Id
    Write-Output 'Starting MediAtlas. Default URL: http://127.0.0.1:8010 (see backend/.env for port changes).'
    Write-Output 'Startup progress: logs/server.err.log. Stop: .\Stop.ps1'
}
