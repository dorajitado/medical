$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Run setup first. See README.md.'
}
if (-not (Test-Path -LiteralPath 'dist\index.html')) {
    throw 'Run npm run build first.'
}
Write-Host 'Chest Review: http://127.0.0.1:8000 (Ctrl+C to stop)'
& .\.venv\Scripts\python.exe -m backend.run_local
exit $LASTEXITCODE
