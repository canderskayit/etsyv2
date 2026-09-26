$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtimeDir = Join-Path $root 'runtime'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows 64 bit gerekir.' }
$download = Join-Path $root 'python-runtime.zip'
Write-Host 'Etsy Ekosistem V2 calisma paketi hazirlaniyor. Ilk kurulum internet gerektirir.'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not (Test-Path -LiteralPath (Join-Path $runtimeDir 'python.exe'))) {
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $download
    if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne '4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3') { throw 'Python paketi dogrulanamadi.' }
    Expand-Archive -LiteralPath $download -DestinationPath $runtimeDir -Force
}
Set-Content -Encoding ASCII -LiteralPath (Join-Path $runtimeDir 'python312._pth') -Value @('python312.zip', '.', '..', 'Lib/site-packages', 'import site')
& (Join-Path $runtimeDir 'python.exe') -B (Join-Path $root 'tools\install_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Bagimliliklar kurulamadi. Internet baglantisini kontrol edip BASLAT dosyasini yeniden acin.' }
Write-Host 'Calisma paketi hazir.'
