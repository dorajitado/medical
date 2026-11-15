# Install pinned local language files after npm ci; no document is read.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m backend.setup_optional ocr
if ($LASTEXITCODE -ne 0) { throw 'OCR installation failed' }
