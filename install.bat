@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo Python not found. Install Python 3.11 or 3.12 from https://www.python.org/
    echo Python 3.14 may not support tgcrypto; 3.11/3.12 recommended.
    pause
    exit /b 1
)

echo Installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

if errorlevel 1 (
    echo Install failed.
    pause
    exit /b 1
)

echo.
echo Done. Run the bot with: run.bat
pause
