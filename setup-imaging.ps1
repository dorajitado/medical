$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$nativeRoot = Join-Path $PSScriptRoot 'runtime\orthanc'
New-Item -ItemType Directory -Path $nativeRoot -Force | Out-Null
$sources = @{
    'Orthanc.exe' = 'https://orthanc.uclouvain.be/downloads/windows-64/orthanc/1.13.0/Orthanc.exe'
    'OrthancDicomWeb.dll' = 'https://orthanc.uclouvain.be/downloads/windows-64/orthanc-dicomweb/OrthancDicomWeb-1.24.dll'
    'OrthancOHIF.dll' = 'https://orthanc.uclouvain.be/downloads/windows-64/orthanc-ohif/OrthancOHIF-1.8.dll'
}
$entries = @()
$locked = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'imaging-runtime-lock.json') | ConvertFrom-Json
foreach ($name in $sources.Keys) {
    $destination = Join-Path $nativeRoot $name
    if (-not (Test-Path -LiteralPath $destination)) {
        Invoke-WebRequest -Uri $sources[$name] -OutFile ($destination + '.download')
        Move-Item -LiteralPath ($destination + '.download') -Destination $destination
    }
    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    $expected = $locked | Where-Object name -eq $name
    if (-not $expected -or $expected.sha256 -ne $hash -or $expected.url -ne $sources[$name]) {
        throw ('Native runtime checksum mismatch: ' + $name)
    }
    $entries += @{ name=$name; url=$sources[$name]; sha256=$hash }
}
$entries | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $nativeRoot 'download-manifest.json')
Write-Host 'Windows native Orthanc/OHIF runtime downloaded. No Docker is used.'
