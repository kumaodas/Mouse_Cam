@echo off
title Gesture Mouse Launcher
echo ===================================================
echo           GESTURE MOUSE - EJECUTOR RAPIDO
echo ===================================================
echo Iniciando Gesture Mouse...
if exist "dist\GestureMouse\GestureMouse.exe" (
    start "" "dist\GestureMouse\GestureMouse.exe"
) else (
    echo [Info] Ejecutando desde entorno Python...
    .venv\Scripts\python.exe run.py
)
