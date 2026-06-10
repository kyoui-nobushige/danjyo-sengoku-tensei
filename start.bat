@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONWARNINGS=ignore
python main.py
pause
