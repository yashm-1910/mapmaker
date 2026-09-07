@echo off
REM Double-click this file to open the Mapmaker window from a source checkout --
REM the no-code way to run the tool without touching a terminal.
REM
REM Once the package is installed (pip install . / conda install), the same window is
REM available anywhere as the `mapmaker-gui` command and this file isn't needed.
setlocal
cd /d "%~dp0"

REM Prefer the project's own virtual environment if there is one, so the launcher
REM works whether or not the user has activated it first.
if exist ".venv\Scripts\pythonw.exe" (
    set "PY=.venv\Scripts\python.exe"
    set "PYW=.venv\Scripts\pythonw.exe"
) else (
    set "PY=python"
    set "PYW=pythonw"
)

REM Check the dependencies up front with the console python: pythonw writes no output
REM anywhere, so without this a missing package would just mean no window ever appears.
"%PY%" -c "import mapmaker.gui" 2>nul
if errorlevel 1 (
    echo.
    echo Mapmaker could not start -- its Python packages are not installed.
    echo.
    echo From this folder, run:  pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM pythonw runs the window with no console box behind it.
start "" "%PYW%" -m mapmaker.gui
