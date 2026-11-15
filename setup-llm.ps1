# CPU runtime and GGUF are installed once; inference always uses --offline.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m backend.setup_optional llm
if ($LASTEXITCODE -ne 0) { throw 'Local language-model installation failed' }
