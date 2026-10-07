param([string]$Destino = '', [switch]$SinInicioAutomatico)
# Instalador en una linea del bridge QLab -> grandMA2. En PowerShell:
#
#   irm https://raw.githubusercontent.com/MoscoDJ/qlab-grandma2-bridge/main/instalar-web.ps1 | iex
#
# Descarga la ultima version de GitHub a una carpeta temporal y ejecuta instalar.ps1.
# Archivo solo ASCII y sin BOM a proposito: PowerShell 5.1 lo recibe por "irm | iex".

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072  # TLS 1.2

$ma2Repo = 'MoscoDJ/qlab-grandma2-bridge'
$ma2Tmp = Join-Path $env:TEMP ('ma2_bridge_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
try {
    Write-Host "Descargando $ma2Repo desde GitHub..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $ma2Tmp | Out-Null
    $ma2Zip = Join-Path $ma2Tmp 'repo.zip'
    Invoke-WebRequest "https://github.com/$ma2Repo/archive/refs/heads/main.zip" -OutFile $ma2Zip -UseBasicParsing
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($ma2Zip, (Join-Path $ma2Tmp 'src'))
    $ma2Src = Get-ChildItem (Join-Path $ma2Tmp 'src') | Where-Object { $_.PSIsContainer } | Select-Object -First 1

    $ma2Args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $ma2Src.FullName 'instalar.ps1'))
    if ($Destino) { $ma2Args += @('-Destino', $Destino) }
    if ($SinInicioAutomatico) { $ma2Args += '-SinInicioAutomatico' }
    Write-Host 'Iniciando el instalador...' -ForegroundColor Cyan
    & powershell.exe @ma2Args
}
catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
}
finally {
    Remove-Item $ma2Tmp -Recurse -Force -ErrorAction SilentlyContinue
}
