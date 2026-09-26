param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'runtime\python.exe'
$port = 8766
$mutex = $null
$ownsMutex = $false
$exitCode = 0

function Read-Health {
    $response = $null
    try {
        $request = [Net.HttpWebRequest]::Create("http://127.0.0.1:$port/api/health")
        $request.Proxy = $null
        $request.Timeout = 1500
        $request.ReadWriteTimeout = 1500
        $response = $request.GetResponse()
        $reader = New-Object IO.StreamReader($response.GetResponseStream())
        try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
    } catch { return $null } finally { if ($response) { $response.Dispose() } }
}
function Assert-OurServer($health) {
    if ($health.app -ne 'etsy-ekosistem-v2' -or $health.root -ne $root -or ($health.data_dir -and $health.data_dir -ne $dataDir)) {
        throw "$port portunda baska bir uygulama veya farkli bir V2 kopyasi acik. O kopyayi kendi DURDUR dosyasiyla kapatin."
    }
}
function Test-Runtime {
    if (-not (Test-Path -LiteralPath $python)) { return $false }
    try {
        $check = Start-Process -FilePath $python -ArgumentList @('-B', '-c', '"from PIL import Image; import pypdf, numpy, cv2, imageio_ffmpeg"') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'runtime-check.out.log') -RedirectStandardError (Join-Path $logDir 'runtime-check.err.log')
        # Retain the native handle before exit; PS 5.1 can otherwise lose ExitCode.
        $checkHandle = $check.Handle
        if (-not $check.WaitForExit(30000)) { Stop-Process -Id $check.Id -ErrorAction SilentlyContinue; return $false }
        return ($check.ExitCode -eq 0)
    } catch { return $false }
}
try {
    if ($env:ETSY_V2_PORT) { $port = [int]$env:ETSY_V2_PORT }
    if ($port -lt 1 -or $port -gt 65535) { throw 'ETSY_V2_PORT 1 ile 65535 arasinda olmali.' }
    $dataDir = if ($env:ETSY_V2_DATA_DIR) { [IO.Path]::GetFullPath($env:ETSY_V2_DATA_DIR) } else { Join-Path $env:LOCALAPPDATA 'EtsyEkosistemV2' }
    $logDir = Join-Path $dataDir 'logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $pidFile = Join-Path $dataDir 'server-process.json'
    $url = "http://localhost:$port"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $lockKey = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($dataDir.ToLowerInvariant()))).Replace('-', '') } finally { $sha.Dispose() }
    $mutex = New-Object Threading.Mutex($false, "Local\EtsyEkosistemV2-$lockKey")
    Write-Host 'Etsy Ekosistem V2 kontrol ediliyor...'
    try { $ownsMutex = $mutex.WaitOne(90000) } catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { throw 'Baska bir baslatma islemi devam ediyor. Biraz bekleyip yeniden deneyin.' }
    $health = Read-Health
    if ($health) { Assert-OurServer $health }
    if (-not $health) {
        $running = $null
        if (Test-Path -LiteralPath $pidFile) {
            try { $saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json } catch { $saved = $null }
            if ($saved -and $saved.pid) {
                $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$saved.pid)"
                if ($candidate -and $candidate.ExecutablePath -eq $saved.python -and $candidate.CommandLine -match 'server\.py') {
                    if ($saved.root -ne $root -or ($saved.port -and [int]$saved.port -ne $port)) {
                        throw 'Baska bir V2 kopyasi calisiyor. Once o klasordeki DURDUR dosyasini kullanin.'
                    }
                    $running = Get-Process -Id $saved.pid
                }
            }
        }
        if (-not $running) {
            $tcp = New-Object Net.Sockets.TcpClient
            try { $occupied = $tcp.ConnectAsync('127.0.0.1', $port).Wait(500) -and $tcp.Connected } catch { $occupied = $false } finally { $tcp.Dispose() }
            if ($occupied) { throw "$port portu dolu ama panel yanit vermiyor. Acik V2 kopyasini DURDUR ile kapatip tekrar deneyin." }
            if (-not (Test-Runtime)) {
                Write-Host 'Python bilesenleri hazirlaniyor. Ilk kurulum internet gerektirir...'
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'setup.ps1')
                if ($LASTEXITCODE -ne 0 -or -not (Test-Runtime)) { throw "Calisma paketi hazirlanamadi. Hata kaydi: $logDir\runtime-check.err.log" }
            }
            $running = Start-Process -FilePath $python -ArgumentList @('-B', '-u', 'server.py') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'server.out.log') -RedirectStandardError (Join-Path $logDir 'server.err.log')
            @{ pid = $running.Id; python = $python; root = $root; port = $port } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $pidFile
        }
        $deadline = [DateTime]::UtcNow.AddSeconds(90)
        $nextNotice = [DateTime]::UtcNow
        while ([DateTime]::UtcNow -lt $deadline) {
            $health = Read-Health
            if ($health) { Assert-OurServer $health; break }
            $running.Refresh()
            if ($running.HasExited) { throw "Panel baslatilamadi. Hata kaydi: $logDir\server.err.log" }
            if ([DateTime]::UtcNow -ge $nextNotice) { Write-Host 'Panel hazirlaniyor...'; $nextNotice = [DateTime]::UtcNow.AddSeconds(5) }
            Start-Sleep -Milliseconds 400
        }
        if (-not $health) { throw "Panel 90 saniyede hazir olmadi. DURDUR ile kapatip tekrar deneyin. Hata kaydi: $logDir\server.err.log" }
    }
    if ($health.pid) {
        @{ pid = [int]$health.pid; python = $python; root = $root; port = $port } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $pidFile
    }
    Write-Host "Panel hazir: $url" -ForegroundColor Green
    if (-not $NoBrowser) {
        try { Start-Process $url } catch { Write-Host "Tarayici otomatik acilamadi. Bu adresi tarayiciya yazin: $url" -ForegroundColor Yellow }
    }
} catch {
    $exitCode = 1
    Write-Host "Etsy Ekosistem V2: $($_.Exception.Message)" -ForegroundColor Red
    if ($logDir) { try { Add-Content -Encoding UTF8 -LiteralPath (Join-Path $logDir 'launcher.log') -Value ("$(Get-Date -Format s) $($_.Exception.Message)") } catch {} }
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
exit $exitCode
