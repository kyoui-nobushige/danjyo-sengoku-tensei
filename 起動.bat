@echo off
set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
if exist "%WT%" (
    "%WT%" cmd /k "cd /d "%~sdp0" && python main.py"
) else (
    cd /d "%~dp0"
    python main.py
    pause
)
