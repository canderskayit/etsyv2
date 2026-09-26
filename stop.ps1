$ErrorActionPreference = 'Stop'
$dataDir = if ($env:ETSY_V2_DATA_DIR) { $env:ETSY_V2_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'EtsyEkosistemV2' }
$pidFile = Join-Path $dataDir 'server-process.json'
try {
    $saved = $null
    if (Test-Path -LiteralPath $pidFile) {
        try { $saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json } catch {}
    }
    if (-not $saved) {
        $port = if ($env:ETSY_V2_PORT) { [int]$env:ETSY_V2_PORT } else { 8766 }
        try {
            $request = [Net.HttpWebRequest]::Create("http://127.0.0.1:$port/api/health")
            $request.Proxy = $null; $request.Timeout = 1500
            $response = $request.GetResponse()
            $reader = New-Object IO.StreamReader($response.GetResponseStream())
            try { $health = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose(); $response.Dispose() }
            if ($health.app -eq 'etsy-ekosistem-v2' -and $health.root -eq $PSScriptRoot -and $health.pid) {
                $saved = @{ root = $PSScriptRoot; pid = $health.pid; python = (Join-Path $PSScriptRoot 'runtime\python.exe') }
            }
        } catch {}
    }
    if (-not $saved) { Write-Host 'Bu paket tarafindan baslatilmis panel yok.'; exit 0 }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$saved.pid)"
    if ($process -and $process.ExecutablePath -eq $saved.python -and $process.CommandLine -match 'server\.py') {
        if ($saved.root -ne $PSScriptRoot) { throw 'Calisan panel baska bir V2 kopyasina ait. O klasordeki DURDUR dosyasini kullanin.' }
        Write-Host 'Uretim varsa once panelden durdurun. Panel sunucusu kapatiliyor.'
        Stop-Process -Id $saved.pid
        Wait-Process -Id $saved.pid -Timeout 10 -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile }
    Write-Host 'Etsy Ekosistem V2 kapatildi.'
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
