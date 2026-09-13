@echo off
REM Double-click this to launch the Auto-Master app on Windows.
REM The first run sets up a private Python environment (takes a minute);
REM after that it just opens the app.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup, then run this again.
    echo.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo First-time setup: creating environment and installing packages...
    echo This can take a minute or two. Please wait.
    python -m venv venv
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements-gui.txt
    if errorlevel 1 (
        echo.
        echo Setup failed. See the messages above.
        pause
        exit /b 1
    )
)

venv\Scripts\python.exe gui.py
if errorlevel 1 pause
