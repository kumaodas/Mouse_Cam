<#
.SYNOPSIS
    Launcher script for Gesture Mouse in PowerShell.
.EXAMPLE
    .\run.ps1
    .\run.ps1 --camera 1 --filter moving_average
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$RunScript = Join-Path $ScriptDir "run.py"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " Iniciando Gesture Mouse..." -ForegroundColor Green
Write-Host " Presiona 'q' o 'ESC' en la ventana para salir." -ForegroundColor Yellow
Write-Host "======================================================" -ForegroundColor Cyan

if (Test-Path $VenvPython) {
    & $VenvPython $RunScript $args
} else {
    python $RunScript $args
}
