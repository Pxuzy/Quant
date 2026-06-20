@echo off
setlocal
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\quant\.venv\Scripts\python.exe"
set "GUI=%ROOT%\scripts\quant-gui.py"

if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found: %PYTHON%
    echo Run: cd quant ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%GUI%" (
    echo [ERROR] Launcher script not found: %GUI%
    pause
    exit /b 1
)

echo Starting Quant Launcher...
start "" "%PYTHON%" "%GUI%"
endlocal
