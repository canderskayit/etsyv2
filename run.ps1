$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'runtime\python.exe'
$port = if ($env:ETSY_V2_PORT) { [int]$env:ETSY_V2_PORT } else { 8766 }
$dataDir = if ($env:ETSY_V2_DATA_DIR) { $env:ETSY_V2_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'EtsyEkosistemV2' }
$url = "http://localhost:$port"
New-Item -ItemType Directory -Path (Join-Path $dataDir 'logs') -Force | Out-Null
function Read-Health {
    try { return Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2 } catch { return $null }
}
try {
    if (-not (Test-Path -LiteralPath (Join-Path $root 'runtime\ready.json'))) { & (Join-Path $root 'setup.ps1') }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Paket eksik. ZIP dosyasinin tamamini klasore cikartin; icinden calistirmayin.' }
    $health = Read-Health
    if ($health -and ($health.app -ne 'etsy-ekosistem-v2' -or $health.root -ne $root)) {
        throw '8766 adresinde baska bir uygulama veya farkli bir V2 kopyasi acik. Once o uygulamayi kapatin.'
    }
    if (-not $health) {
        & $python -c 'from PIL import Image; import pypdf, numpy, cv2, imageio_ffmpeg' 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Calisma paketi eksik veya uyumsuz. Windows 10/11 64 bit paketinin tamamini yeniden cikartin.' }
        $process = Start-Process -FilePath $python -ArgumentList @('-B', '-u', 'server.py') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dataDir 'logs\server.out.log') -RedirectStandardError (Join-Path $dataDir 'logs\server.err.log')
        for ($attempt = 0; $attempt -lt 35; $attempt++) {
            Start-Sleep -Milliseconds 600
            $health = Read-Health
            if ($health -and $health.app -eq 'etsy-ekosistem-v2' -and $health.root -eq $root) { break }
            if ($process.HasExited) { throw "Uygulama baslatilamadi. Hata kaydi: $dataDir\logs\server.err.log" }
        }
        if (-not $health -or $health.app -ne 'etsy-ekosistem-v2' -or $health.root -ne $root) { throw "Panel acilmadi. Hata kaydi: $dataDir\logs\server.err.log" }
        @{ pid = $process.Id; python = $python; root = $root } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $dataDir 'server-process.json')
    }
    # This browser window is the app's interactive interface.
    Start-Process $url
} catch {
    Write-Host "Etsy Ekosistem V2: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
