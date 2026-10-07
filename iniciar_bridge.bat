@echo off
rem Arranca el bridge QLab -> grandMA2. Si se cae, lo vuelve a levantar.
title QLab -^> grandMA2 bridge
cd /d "%~dp0"
if exist "python\python.exe" (set "PY=python\python.exe") else (set "PY=py -3")
:loop
%PY% ma2_bridge.py %*
if errorlevel 3 if not errorlevel 4 goto duplicado
if errorlevel 2 if not errorlevel 3 goto config
echo.
echo El bridge se detuvo. Reiniciando en 3 segundos... (Ctrl+C para salir)
timeout /t 3 /nobreak >nul
goto loop

:duplicado
echo.
echo Ya hay un bridge corriendo en otra ventana. Esta ventana se cierra.
timeout /t 10
exit /b 3

:config
echo.
echo Revisa config.json: tiene un error. Corrigelo y vuelve a abrir el bridge.
pause
exit /b 2
