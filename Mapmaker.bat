@echo off
REM Double-click this file to open the Mapmaker window from a source checkout --
REM the no-code way to run the tool without touching a terminal.
REM
REM The Conda environment is defined by environment.yml in this folder.
setlocal
cd /d "%~dp0"

REM Override the environment with `Mapmaker.bat my-environment`, or set
REM MAPMAKER_CONDA_ENV before starting this file. The default is `mapmaker`.
if not "%~1"=="" set "MAPMAKER_CONDA_ENV=%~1"
if not defined MAPMAKER_CONDA_ENV set "MAPMAKER_CONDA_ENV=mapmaker"

for /f "delims=" %%I in ('conda info --base 2^>nul') do set "CONDA_BASE=%%I"
if not defined CONDA_BASE (
    echo.
    echo Conda was not found. Install Conda, then run: conda env create -f environment.yml
    echo.
    pause
    exit /b 1
)

set "PYW=%CONDA_BASE%\envs\%MAPMAKER_CONDA_ENV%\pythonw.exe"
if not exist "%PYW%" (
    echo.
    echo The Conda environment "%MAPMAKER_CONDA_ENV%" was not found.
    echo From this folder, run: conda env create -f environment.yml
    echo.
    pause
    exit /b 1
)

REM Actually activating the env (rather than just calling its python.exe by path) runs
REM conda-forge's activate.d scripts, which set GDAL_DATA/PROJ_DATA and friends -- geopandas
REM and contextily depend on GDAL/PROJ finding their data files, and some of their native code
REM aborts the whole process instead of raising a catchable error when those aren't set.
call "%CONDA_BASE%\condabin\conda.bat" activate "%MAPMAKER_CONDA_ENV%"
if errorlevel 1 (
    echo.
    echo Could not activate the Conda environment "%MAPMAKER_CONDA_ENV%".
    echo.
    pause
    exit /b 1
)

REM Check the dependencies up front with the console python: pythonw writes no output
REM anywhere, so without this a missing package would just mean no window ever appears.
python -c "import mapmaker.gui" 2>nul
if errorlevel 1 (
    echo.
    echo Mapmaker could not start -- its Python packages are not installed.
    echo.
    echo From this folder, run: conda env update -f environment.yml --prune
    echo.
    pause
    exit /b 1
)

REM pythonw runs the window with no console box behind it.
start "" pythonw -m mapmaker.gui
