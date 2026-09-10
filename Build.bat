@echo off
REM Double-click this file to build the standalone Windows app -- the no-terminal
REM way to turn this source checkout into something you can hand to someone who
REM has no Python and no Conda on their machine.
REM
REM What it does, in order:
REM   1. creates (or updates) the Conda environment defined by environment-build.yml
REM   2. draws the .exe icon (packaging\make_icon.py)
REM   3. runs PyInstaller against packaging/mapmaker.spec
REM
REM Everything comes from conda-forge; nothing here uses pip. The package itself
REM is not installed at all -- PyInstaller reads it straight out of this folder,
REM which is why PYTHONPATH is set below.
REM
REM The result is dist\Mapmaker\ -- copy that whole folder to the target machine
REM and run Mapmaker.exe inside it. See README.md for what to hand over.
setlocal
cd /d "%~dp0"

REM Override the environment with `Build.bat my-build-env`, or set
REM MAPMAKER_BUILD_ENV before starting this file. The default is `mapmaker-build`.
if not "%~1"=="" set "MAPMAKER_BUILD_ENV=%~1"
if not defined MAPMAKER_BUILD_ENV set "MAPMAKER_BUILD_ENV=mapmaker-build"

for /f "delims=" %%I in ('conda info --base 2^>nul') do set "CONDA_BASE=%%I"
if not defined CONDA_BASE (
    echo.
    echo Conda was not found. Install Miniconda or Anaconda, then re-run this file.
    echo.
    pause
    exit /b 1
)

REM env create fails if the env already exists, so update --prune instead when it
REM does -- this keeps re-running this file after pulling changes a safe way to
REM sync the build environment.
if exist "%CONDA_BASE%\envs\%MAPMAKER_BUILD_ENV%\" (
    echo Updating existing Conda environment "%MAPMAKER_BUILD_ENV%"...
    call conda env update -n "%MAPMAKER_BUILD_ENV%" -f environment-build.yml --prune
) else (
    echo Creating Conda environment "%MAPMAKER_BUILD_ENV%"...
    call conda env create -n "%MAPMAKER_BUILD_ENV%" -f environment-build.yml
)
if errorlevel 1 (
    echo.
    echo Could not create/update the Conda environment "%MAPMAKER_BUILD_ENV%".
    echo.
    pause
    exit /b 1
)

REM Actually activating the env (rather than calling its python.exe by path) runs
REM conda-forge's activate.d scripts, which set GDAL_DATA/PROJ_DATA -- and those are
REM exactly the two paths packaging/mapmaker.spec copies into the build, so the
REM executable ends up carrying the same data files this environment resolved.
call "%CONDA_BASE%\condabin\conda.bat" activate "%MAPMAKER_BUILD_ENV%"
if errorlevel 1 (
    echo.
    echo Could not activate the Conda environment "%MAPMAKER_BUILD_ENV%".
    echo.
    pause
    exit /b 1
)

REM The mapmaker package is never installed into the environment, so put this
REM folder on the import path instead -- PyInstaller and its hooks import the
REM package to work out what it needs.
set "PYTHONPATH=%CD%"

echo.
echo Drawing the application icon...
python packaging\make_icon.py
if errorlevel 1 (
    echo.
    echo Could not draw the application icon (packaging\make_icon.py).
    echo.
    pause
    exit /b 1
)

REM A stale dist\Mapmaker from an earlier build would keep files that are no
REM longer part of the app (an old DLL, a renamed data file) and ship them to
REM users; --clean does the same for PyInstaller's own cache.
echo.
echo Building the application (this takes a few minutes)...
if exist "dist\Mapmaker\" rmdir /s /q "dist\Mapmaker"
pyinstaller packaging\mapmaker.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo The build failed. The PyInstaller output above says why.
    echo.
    pause
    exit /b 1
)

REM Prove the result actually runs before calling the build a success: a frozen
REM app that is missing a hidden import or a data file builds perfectly happily
REM and only fails when a user double-clicks it. --help exercises the import of
REM the whole rendering stack (GDAL, PROJ, matplotlib) without needing a workbook.
echo.
echo Checking the built application starts...
"dist\Mapmaker\Mapmaker-cli.exe" --help >nul
if errorlevel 1 (
    echo.
    echo The app was built but does not start. Run this for the full error:
    echo     dist\Mapmaker\Mapmaker-cli.exe --help
    echo.
    pause
    exit /b 1
)

echo.
echo Done. The app is in:
echo     %CD%\dist\Mapmaker
echo.
echo Copy that whole folder to the target machine and run Mapmaker.exe inside it.
echo.
pause
