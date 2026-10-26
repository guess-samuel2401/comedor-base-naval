@echo off
rem Abre el sistema del comedor sin dejar una consola abierta.
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
) else (
    python main.py
    if errorlevel 1 pause
)
