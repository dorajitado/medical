# Offline restoration requires stopped app/native imaging and typed confirmation.
param([Parameter(Mandatory=$true)][string]$BackupId)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m backend.restore_workspace --backup-id $BackupId
if ($LASTEXITCODE -ne 0) { throw 'Workspace restore failed; existing workspace recovery was retained.' }
