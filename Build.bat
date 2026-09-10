@echo off
REM Double-click this file to build the standalone Windows app -- the no-terminal
REM way to turn this source checkout into something you can hand to someone who
REM has no Python and no Conda on their machine.
REM
REM It builds and nothing else: it expects the `mapmaker` Conda environment to
REM exist already, and stops with instructions if it does not. Setting the
REM environment up is Setup.bat's job, and keeping one script responsible for
REM that means building does not quietly reinstall packages underneath you.
REM
REM What it does, in order:
REM   1. activates the existing `mapmaker` environment
REM   2. draws the .exe icon, but only if packaging\build_assets\mapmaker.ico
REM      is not already there -- the artwork does not change between builds
REM   3. runs PyInstaller against packaging\mapmaker.spec
REM
REM Careful with parentheses in the echo lines below: every one of them sits
REM inside an `if errorlevel 1 ( ... )` block, and cmd ends the block at the
REM first unescaped `)` it sees -- including one in the middle of a message.
REM That is a syntax error, and a syntax error kills the script outright, so a
REM double-clicked window closes before reaching any `pause`. Write messages
REM without parentheses rather than escaping them as ^( and ^).
REM
REM It uses the same `mapmaker` environment as Setup.bat and Mapmaker.bat, so the
REM .exe is necessarily built against the very libraries the tool is run and
REM tested with. The packaging tools come from environment.yml along with
REM everything else; if PyInstaller is missing, re-run Setup.bat to pick it up.
REM
REM Everything comes from conda-forge; nothing here uses pip. The package itself
REM is not installed at all -- PyInstaller reads it straight out of this folder,
REM which is why PYTHONPATH is set below.
REM
REM The result is dist\Mapmaker\ -- copy that whole folder to the target machine
REM and run Mapmaker.exe inside it. See README.md for what to hand over.
setlocal
cd /d "%~dp0"

REM Override the environment with `Build.bat my-environment`, or set
REM MAPMAKER_CONDA_ENV before starting this file. The default is `mapmaker`.
REM Same variable as Setup.bat and Mapmaker.bat, so overriding it once applies
REM to setting up, building and running alike.
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

REM Building never creates or changes the environment -- that is Setup.bat's job.
REM Checking for it here turns "the environment is missing" into one clear line
REM rather than a confusing failure from conda activate further down.
if not exist "%CONDA_BASE%\envs\%MAPMAKER_CONDA_ENV%\" (
    echo.
    echo The Conda environment "%MAPMAKER_CONDA_ENV%" was not found.
    echo Run Setup.bat first to create it, then re-run this file.
    echo.
    pause
    exit /b 1
)

REM Actually activating the env (rather than calling its python.exe by path) runs
REM conda-forge's activate.d scripts, which set GDAL_DATA/PROJ_DATA -- and those are
REM exactly the two paths packaging/mapmaker.spec copies into the build, so the
REM executable ends up carrying the same data files this environment resolved.
call "%CONDA_BASE%\condabin\conda.bat" activate "%MAPMAKER_CONDA_ENV%"
if errorlevel 1 (
    echo.
    echo Could not activate the Conda environment "%MAPMAKER_CONDA_ENV%".
    echo.
    pause
    exit /b 1
)

REM The mapmaker package is never installed into the environment, so put this
REM folder on the import path instead -- PyInstaller and its hooks import the
REM package to work out what it needs.
set "PYTHONPATH=%CD%"

REM The icon is generated artwork that only changes when make_icon.py changes, and
REM it is not committed, so draw it once on a fresh checkout and leave it alone
REM afterwards. Delete packaging\build_assets\mapmaker.ico to force a redraw.
if not exist "packaging\build_assets\mapmaker.ico" (
    echo.
    echo Drawing the application icon...
    python packaging\make_icon.py
    if errorlevel 1 (
        echo.
        echo Could not draw the application icon. See packaging\make_icon.py.
        echo.
        pause
        exit /b 1
    )
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
