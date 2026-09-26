$ErrorActionPreference = 'Stop'
$dataDir = if ($env:ETSY_V2_DATA_DIR) { $env:ETSY_V2_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'EtsyEkosistemV2' }
$pidFile = Join-Path $dataDir 'server-process.json'
try {
    if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'Bu paket tarafindan baslatilmis panel yok.'; exit 0 }
    $saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    if ($saved.root -ne $PSScriptRoot) { throw 'Calisan panel baska bir V2 kopyasina ait. O klasordeki DURDUR dosyasini kullanin.' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)"
    if ($process -and $process.ExecutablePath -eq $saved.python -and $process.CommandLine -match 'server\.py') {
        Write-Host 'Uretim varsa once panelden durdurun. Panel sunucusu kapatiliyor.'
        Stop-Process -Id $saved.pid
    }
    Remove-Item -LiteralPath $pidFile
    Write-Host 'Etsy Ekosistem V2 kapatildi.'
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
