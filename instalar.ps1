<#
.SYNOPSIS
    Instala el bridge QLab -> grandMA2 en este PC, con su propio Python portátil.

.DESCRIPTION
    No necesita Python instalado ni internet: usa el Python "embeddable" oficial
    que viene en la carpeta python-embed\. Si ese zip no está, lo descarga de
    python.org y verifica su SHA256 antes de usarlo.

    No instala nada en el sistema: todo queda dentro de la carpeta de destino.
    Solo agrega una regla de firewall y los accesos directos.

.EXAMPLE
    .\instalar.ps1
    .\instalar.ps1 -Destino D:\show\ma2_bridge
    .\instalar.ps1 -SinInicioAutomatico
    .\instalar.ps1 -Desinstalar
#>
param(
    [string]$Destino = 'C:\ma2_bridge',
    [switch]$SinInicioAutomatico,
    [switch]$Desinstalar
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest es muy lento con la barra

# Python 3.12 es la última serie que corre en Windows 8.1; 3.12.10 es su último build con binarios.
# Hashes de los zips oficiales, cuya firma GPG (Steve Dower, 7ED10B6531D7C8E1BC296021FC624643487034E5) fue verificada.
$PyVersion = '3.12.10'
$PyHashes = @{
    'amd64' = '4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3'
    'win32' = '084B9EB24CB848605C895D05B738FBC2572EFC8B4C18C415A824065864A2B853'
}

$Origen       = $PSScriptRoot
$Archivos     = 'ma2_bridge.py', 'send_osc.py', 'iniciar_bridge.bat', 'README.md',
                'instalar.ps1', 'instalar.bat', 'desinstalar.bat'
$ReglaFw      = 'QLab -> grandMA2 bridge (OSC entrante)'
$NombreAtajo  = 'Bridge QLab-MA2.lnk'

function Paso([string]$t)  { Write-Host ''; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok([string]$t)    { Write-Host "    $t" -ForegroundColor Green }
function Aviso([string]$t) { Write-Host "    $t" -ForegroundColor Yellow }
function Info([string]$t)  { Write-Host "    $t" }

function Salir([int]$codigo) {
    Write-Host ''
    Read-Host 'Pulsa Enter para cerrar' | Out-Null
    exit $codigo
}

function Ruta-Atajo([string]$carpeta) {
    Join-Path ([Environment]::GetFolderPath($carpeta)) $NombreAtajo
}

function Detener-Bridge {
    # La ventana de iniciar_bridge.bat reinicia el bridge si se cae: se cierra primero.
    $procs = Get-WmiObject Win32_Process | Where-Object {
        ($_.Name -eq 'cmd.exe'    -and $_.CommandLine -like '*iniciar_bridge*') -or
        ($_.Name -eq 'python.exe' -and $_.ExecutablePath -like "$Destino\*")
    }
    foreach ($p in $procs) { [void]$p.Terminate() }
    if ($procs) { Start-Sleep -Milliseconds 500; Ok 'Bridge en ejecución detenido.' }
}

function Quitar-Firewall {
    & netsh advfirewall firewall delete rule name="$ReglaFw" | Out-Null
}

# --------------------------------------------------------------------------
# Permisos de administrador (firewall, accesos directos para todos los usuarios)
# --------------------------------------------------------------------------

$yo = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $yo.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Se necesitan permisos de administrador; Windows te los va a pedir...'
    $argumentos = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Destino', "`"$Destino`"")
    if ($SinInicioAutomatico) { $argumentos += '-SinInicioAutomatico' }
    if ($Desinstalar)         { $argumentos += '-Desinstalar' }
    try {
        Start-Process powershell.exe -Verb RunAs -ArgumentList $argumentos -Wait
    } catch {
        Write-Host 'No se concedieron permisos de administrador. Instalación cancelada.' -ForegroundColor Red
        Salir 1
    }
    exit 0
}

# Ejecutado desde una carpeta ya instalada (p. ej. desinstalar.bat): esa es el destino.
if (-not $PSBoundParameters.ContainsKey('Destino') -and (Test-Path (Join-Path $Origen 'python\python.exe'))) {
    $Destino = $Origen
}
$Destino = [IO.Path]::GetFullPath($Destino).TrimEnd('\')
$py = Join-Path $Destino 'python\python.exe'

# --------------------------------------------------------------------------
# Desinstalar
# --------------------------------------------------------------------------

if ($Desinstalar) {
    Paso "Desinstalando el bridge de $Destino"
    Detener-Bridge
    foreach ($c in 'CommonStartup', 'CommonDesktopDirectory') {
        $a = Ruta-Atajo $c
        if (Test-Path $a) { Remove-Item $a -Force }
    }
    Ok 'Accesos directos eliminados.'
    Quitar-Firewall
    Ok 'Regla de firewall eliminada.'
    if (Test-Path $Destino) {
        $r = Read-Host "¿Borrar también la carpeta $Destino, incluido config.json? (s/N)"
        if ($r -match '^[sS]') {
            Set-Location $env:SystemRoot
            try { Remove-Item $Destino -Recurse -Force; Ok 'Carpeta eliminada.' }
            catch { Aviso "No se pudo borrar todo $Destino ($_). Bórrala a mano." }
        }
        else { Info 'La carpeta se conserva.' }
    }
    Salir 0
}

# --------------------------------------------------------------------------
# Instalar
# --------------------------------------------------------------------------

try {
    Write-Host ''
    Write-Host 'Instalador del bridge QLab -> grandMA2 onPC' -ForegroundColor White

    $os = [Environment]::OSVersion.Version
    if ($os -lt [Version]'6.3') {
        throw "Este PC tiene Windows $os. Se necesita Windows 8.1 o superior."
    }

    Paso "Copiando archivos a $Destino"
    Detener-Bridge
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    $mismaCarpeta = ([IO.Path]::GetFullPath($Origen).TrimEnd('\') -eq $Destino)
    if (-not $mismaCarpeta) {
        foreach ($f in $Archivos) { Copy-Item (Join-Path $Origen $f) $Destino -Force }
        $cfg = Join-Path $Destino 'config.json'
        if (Test-Path $cfg) {
            Aviso 'config.json ya existía: se conserva el actual (con tus triggers).'
        } else {
            Copy-Item (Join-Path $Origen 'config.json') $Destino
        }
    }
    Ok 'Archivos copiados.'

    Paso "Python portátil $PyVersion"
    $versionActual = $null
    if (Test-Path $py) {
        try { $versionActual = (& $py -c 'import sys; print(sys.version.split()[0])') } catch { }
    }
    if ($versionActual -eq $PyVersion) {
        Ok "Ya estaba instalado ($versionActual)."
    } else {
        $arq = if ([Environment]::Is64BitOperatingSystem) { 'amd64' } else { 'win32' }
        $zipNombre = "python-$PyVersion-embed-$arq.zip"
        $zip = Join-Path $Origen "python-embed\$zipNombre"
        if (Test-Path $zip) {
            Info "Usando $zipNombre incluido en el paquete (sin internet)."
        } else {
            $url = "https://www.python.org/ftp/python/$PyVersion/$zipNombre"
            $zip = Join-Path $env:TEMP $zipNombre
            Info "Descargando $url"
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072  # TLS 1.2
            try {
                Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
            } catch {
                throw "No se pudo descargar Python y el paquete no trae python-embed\$zipNombre. " +
                      "Conecta este PC a internet o copia ese zip a la carpeta python-embed. ($_)"
            }
        }
        $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
        if ($hash -ne $PyHashes[$arq]) {
            throw "El zip de Python no coincide con el hash esperado: está dañado o fue alterado.`n    Esperado: $($PyHashes[$arq])`n    Obtenido: $hash"
        }
        Ok 'Integridad verificada (SHA256).'

        $dirPy = Join-Path $Destino 'python'
        if (Test-Path $dirPy) { Remove-Item $dirPy -Recurse -Force }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($zip, $dirPy)

        # El Python embeddable solo busca módulos en las rutas de su ._pth; se agrega
        # la carpeta del bridge para que send_osc.py pueda importar ma2_bridge.
        $pth = Get-ChildItem $dirPy -Filter 'python*._pth' | Select-Object -First 1
        Add-Content -Path $pth.FullName -Value "`r`n.." -Encoding ASCII
        Ok "Python $PyVersion ($arq) instalado en $dirPy"
    }

    Paso 'Autoprueba'
    Push-Location $Destino
    $env:PYTHONIOENCODING = 'utf-8'
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    try {
        & $py ma2_bridge.py --check | ForEach-Object { Info $_ }
        if ($LASTEXITCODE -ne 0) { throw 'La autoprueba falló: revisa config.json.' }
    } finally { Pop-Location }
    Ok 'El bridge arranca correctamente.'

    Paso 'Firewall de Windows'
    $puerto = 8000
    try {
        $conf = Get-Content (Join-Path $Destino 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($conf.osc -and $conf.osc.port) { $puerto = [int]$conf.osc.port }
    } catch { }
    Quitar-Firewall
    # profile=any: las redes de show suelen quedar como "Red pública/no identificada".
    & netsh advfirewall firewall add rule name="$ReglaFw" dir=in action=allow protocol=UDP localport=$puerto profile=any | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la regla de firewall.' }
    Ok "Entrada UDP $puerto permitida (todas las redes)."

    Paso 'Accesos directos'
    $shell = New-Object -ComObject WScript.Shell
    $bat = Join-Path $Destino 'iniciar_bridge.bat'
    $destinos = @(@{ Carpeta = 'CommonDesktopDirectory'; Ventana = 1; Texto = 'Escritorio' })
    if (-not $SinInicioAutomatico) {
        $destinos += @{ Carpeta = 'CommonStartup'; Ventana = 7; Texto = 'Inicio de Windows (minimizado)' }
    } else {
        $a = Ruta-Atajo 'CommonStartup'
        if (Test-Path $a) { Remove-Item $a -Force }
    }
    foreach ($d in $destinos) {
        $lnk = $shell.CreateShortcut((Ruta-Atajo $d.Carpeta))
        $lnk.TargetPath = $bat
        $lnk.WorkingDirectory = $Destino
        $lnk.WindowStyle = $d.Ventana
        $lnk.Description = 'Bridge OSC de QLab a grandMA2 onPC'
        $lnk.Save()
        Ok $d.Texto
    }

    Paso 'Listo'
    $ips = [Net.Dns]::GetHostAddresses($env:COMPUTERNAME) |
        Where-Object { $_.AddressFamily -eq 'InterNetwork' -and -not $_.ToString().StartsWith('169.254.') } |
        ForEach-Object { $_.ToString() }
    Info 'En QLab, crea un Network Patch OSC hacia:'
    foreach ($ip in $ips) { Write-Host "        $ip  puerto $puerto" -ForegroundColor White }
    Info ''
    Info 'Falta en grandMA2: Setup > Console > Global Settings > Telnet = Login Enabled'
    Info "Para arrancar el bridge: icono 'Bridge QLab-MA2' del escritorio."
    if (-not $SinInicioAutomatico) { Info 'Además arrancará solo cada vez que se inicie Windows.' }
    Salir 0
}
catch {
    Write-Host ''
    Write-Host "ERROR: $_" -ForegroundColor Red
    Salir 1
}
