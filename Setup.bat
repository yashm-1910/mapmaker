@echo off
REM Double-click this file to (re)create the Conda environment defined by environment.yml
REM and install the mapmaker package into it -- the no-terminal way to set up Mapmaker
REM on a new machine, or after pulling changes to environment.yml/pyproject.toml.
setlocal
cd /d "%~dp0"

REM Override the environment with `Setup.bat my-environment`, or set
REM MAPMAKER_CONDA_ENV before starting this file. The default is `mapmaker`.
if not "%~1"=="" set "MAPMAKER_CONDA_ENV=%~1"
if not defined MAPMAKER_CONDA_ENV set "MAPMAKER_CONDA_ENV=mapmaker"

for /f "delims=" %%I in ('conda info --base 2^>nul') do set "CONDA_BASE=%%I"
if not defined CONDA_BASE (
    echo.
    echo Conda was not found. Install Miniconda or Anaconda, then re-run this file.
    echo.
    pause
    exit /b 1
)

REM env create fails if the env already exists, so update --prune instead when it does --
REM this keeps re-running this file after pulling changes a safe way to sync the env.
if exist "%CONDA_BASE%\envs\%MAPMAKER_CONDA_ENV%\" (
    echo Updating existing Conda environment "%MAPMAKER_CONDA_ENV%"...
    call conda env update -n "%MAPMAKER_CONDA_ENV%" -f environment.yml --prune
) else (
    echo Creating Conda environment "%MAPMAKER_CONDA_ENV%"...
    call conda env create -n "%MAPMAKER_CONDA_ENV%" -f environment.yml
)
if errorlevel 1 (
    echo.
    echo Could not create/update the Conda environment "%MAPMAKER_CONDA_ENV%".
    echo.
    pause
    exit /b 1
)

REM Actually activating the env (rather than calling its python.exe by path) runs
REM conda-forge's activate.d scripts, which set GDAL_DATA/PROJ_DATA and friends.
call "%CONDA_BASE%\condabin\conda.bat" activate "%MAPMAKER_CONDA_ENV%"
if errorlevel 1 (
    echo.
    echo Could not activate the Conda environment "%MAPMAKER_CONDA_ENV%".
    echo.
    pause
    exit /b 1
)

REM conda build pulls contextily from the default channel here and fails (it's
REM conda-forge only), so skip packaging and just pip-install straight from source.
REM --no-deps because every dependency is already pinned and installed via environment.yml.
echo Installing mapmaker into "%MAPMAKER_CONDA_ENV%"...
python -m pip install --no-deps -e .
if errorlevel 1 (
    echo.
    echo Could not install the mapmaker package.
    echo.
    pause
    exit /b 1
)

echo.
echo Done. Run Mapmaker.bat to open the app.
echo.
pause
