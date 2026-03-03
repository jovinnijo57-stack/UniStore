@echo off
echo ====================================================
echo Starting UniStore Server...
echo ====================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python (3.7+) and try again.
    pause
    exit /b
)

echo.
echo Installing dependencies...
pip install -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo Error installing dependencies. Trying to run anyway...
) else (
    echo Dependencies up to date.
)

echo.
echo Starting Application...
echo Access the site at: http://127.0.0.1:5000
echo.
python app.py

pause
