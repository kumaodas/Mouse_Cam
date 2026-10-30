@echo off
title Gesture Mouse - AI Vision Control
echo ======================================================
echo  Iniciando Gesture Mouse...
echo  Presiona 'q' o 'ESC' en la ventana para salir.
echo ======================================================

if exist "%~dp0\.venv\Scripts\python.exe" (
    "%~dp0\.venv\Scripts\python.exe" "%~dp0\run.py" %*
) else (
    python "%~dp0\run.py" %*
)

pause
