# AI environment dependencies are pinned in backend/ai-requirements-lock.txt.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\runtime\ai-venv\Scripts\python.exe -m pip install monai==1.5.1 pytorch-ignite==0.5.2
if ($LASTEXITCODE -ne 0) { throw 'MONAI dependency installation failed' }
& .\.venv\Scripts\python.exe -m backend.setup_optional monai
if ($LASTEXITCODE -ne 0) { throw 'MONAI asset installation failed' }
