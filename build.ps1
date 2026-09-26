$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Node bagimliliklari kurulamadi.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Panel derlenemedi.' }
