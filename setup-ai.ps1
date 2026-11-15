# Install the optional native GPU runtime separately from the lightweight API.
# Downloading packages/weights happens here; CT inference never installs models.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'runtime\ai-venv\Scripts\python.exe')) {
    & .\.venv\Scripts\python.exe -m venv runtime\ai-venv
    if ($LASTEXITCODE -ne 0) { throw 'AI environment creation failed.' }
}
& .\runtime\ai-venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'AI pip installation failed.' }
& .\runtime\ai-venv\Scripts\python.exe -m pip install -r backend\ai-requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'AI dependency installation failed.' }
& .\runtime\ai-venv\Scripts\python.exe -m backend.setup_ai
if ($LASTEXITCODE -ne 0) { throw 'AI weights preparation failed.' }
Write-Host 'AI setup complete. Restart the local app to use analysis.'
