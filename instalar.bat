@echo off
rem Doble clic aqui para instalar el bridge QLab -> grandMA2 en este PC.
rem Opciones: instalar.bat -Destino D:\ma2_bridge   |   -SinInicioAutomatico   |   -Desinstalar
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
