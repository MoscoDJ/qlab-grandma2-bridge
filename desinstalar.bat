@echo off
rem Quita el bridge: accesos directos, regla de firewall y (si lo confirmas) la carpeta.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" -Desinstalar %*
