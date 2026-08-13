@echo off
cd /d "%~dp0"

echo ============================================
echo   Danjyo Sengoku Tensei - Setup
echo ============================================
echo.

if exist "config.py" (
    echo [1/2] config.py already exists. Skipping copy.
) else (
    echo [1/2] Creating config.py from config.example.py ...
    copy /Y "config.example.py" "config.py" >nul
    if errorlevel 1 (
        echo   ERROR: Failed to copy config.example.py. Please check the file exists.
    ) else (
        echo   Done: config.py created.
    )
)
echo.

echo [2/2] Installing required libraries (pip install -r requirements.txt) ...
pip install -r requirements.txt
echo.

echo ============================================
echo   Setup complete!
echo   Next: open config.py and choose your LLM provider.
echo   See README.md for details (setup guide / LLM selection).
echo ============================================
echo.
pause
