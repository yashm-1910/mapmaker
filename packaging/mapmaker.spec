# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build of Mapmaker.

Run it through Build.bat in the repo root (which creates the Conda build
environment first), or by hand from an activated build environment:

    pyinstaller packaging/mapmaker.spec --noconfirm

What comes out is dist/Mapmaker/ -- a folder holding two executables that share
one `_internal` payload:

    Mapmaker.exe      the window (no console box behind it)
    Mapmaker-cli.exe  the command line: Mapmaker-cli.exe --file book.xlsx

Two deliberate choices, both about the build behaving itself on other people's
machines:

  * onedir, not onefile. A onefile build is a self-extracting archive: it unpacks
    ~400 MB of GDAL/PROJ into a temp directory on every launch (slow, and it
    breaks on machines whose temp directory is locked down), and the pattern is
    close enough to how real malware ships that antivirus heuristics flag it
    routinely. A plain folder of DLLs next to an .exe is what ordinary Windows
    software looks like, starts instantly, and gives antivirus nothing to object to.
  * no UPX. Compressed executable sections are the single strongest generic
    antivirus signal there is -- almost nothing but packed malware uses them.
    Skipping UPX costs disk space and buys a build that does not get quarantined.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH is set by PyInstaller to the directory holding this file.
HERE = Path(SPECPATH).resolve()
ROOT = HERE.parent

APP_NAME = "Mapmaker"


# -- locating PROJ's and GDAL's data files ----------------------------------
#
# proj.db (every coordinate transform) and GDAL's projection tables (the basemap
# tiles) are files the app cannot run without, and where they live depends on how
# the build environment was made. There are two layouts, and they need opposite
# treatment -- getting this wrong is the single easiest way to produce a build
# that starts fine and then cannot draw a map:
#
#   Conda      one shared PROJ and one shared GDAL for the whole environment, in
#              <env>\Library\share\{proj,gdal}. Nothing in the bundle can find
#              those by itself, so they are copied in and pointed at with
#              PROJ_DATA/GDAL_DATA by the runtime hook. This is how Build.bat
#              builds, and it is the layout this app ships.
#
#   wheels     pyproj, rasterio and pyogrio each vendor their *own* PROJ/GDAL
#              build with its own data files, and each finds them relative to its
#              own package directory -- which PyInstaller's hooks already collect.
#              Setting PROJ_DATA here would be actively harmful: it forces every
#              library to read one package's proj.db, and their PROJ versions
#              disagree about the database schema, so GDAL rejects pyproj's file
#              ("DATABASE.LAYOUT.VERSION.MINOR ... comes from another PROJ
#              installation") and every basemap fetch fails.
#
# So: look for the shared layout only. Finding nothing is the wheel case, which
# is left to the per-package copies.

def _dir_containing(candidates, marker_names):
    """Return the first existing candidate directory that holds one of `marker_names`."""
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_dir() and any((path / marker).exists() for marker in marker_names):
            return path
    return None


def _is_shared(path: Path) -> bool:
    """True if `path` is an environment-wide data directory rather than one
    vendored inside a single site-packages package."""
    return "site-packages" not in path.parts


def _shared_proj_data():
    prefix = Path(sys.prefix)
    # An activated Conda environment exports PROJ_DATA (PROJ >=9.1) or PROJ_LIB;
    # trust those first, since they describe the very libraries being bundled.
    candidates = [os.environ.get("PROJ_DATA"), os.environ.get("PROJ_LIB")]
    candidates += [
        prefix / "Library" / "share" / "proj",  # conda-forge on Windows
        prefix / "share" / "proj",              # conda-forge elsewhere
    ]
    found = _dir_containing(candidates, ["proj.db"])
    return found if found and _is_shared(found) else None


def _shared_gdal_data():
    prefix = Path(sys.prefix)
    candidates = [
        os.environ.get("GDAL_DATA"),
        prefix / "Library" / "share" / "gdal",
        prefix / "share" / "gdal",
    ]
    # gdalvrt.xsd and header.dxf are present in every GDAL data directory and in
    # no other directory that might otherwise match by name.
    found = _dir_containing(candidates, ["gdalvrt.xsd", "header.dxf"])
    return found if found and _is_shared(found) else None


proj_data = _shared_proj_data()
gdal_data = _shared_gdal_data()


def _check_vendored(package: str, subdir: str, marker: str) -> bool:
    try:
        module = __import__(package)
    except Exception:
        return False
    return (Path(module.__file__).parent / subdir / marker).exists()


if proj_data and gdal_data:
    print(f"[mapmaker.spec] shared PROJ data: {proj_data}")
    print(f"[mapmaker.spec] shared GDAL data: {gdal_data}")
elif proj_data or gdal_data:
    # Half a shared environment means something is genuinely misconfigured -- the
    # mixture would give GDAL one PROJ and pyproj another, which is the failure
    # described above. Better to stop than to ship it.
    raise SystemExit(
        "Found a shared PROJ or GDAL data directory but not both "
        f"(PROJ: {proj_data}, GDAL: {gdal_data}).\n"
        "Build from the Conda environment created by Build.bat."
    )
else:
    # Wheel layout: each package carries its own copy. Confirm they are actually
    # there, since a build missing them fails only when a user asks for a map.
    if not _check_vendored("pyproj", "proj_dir/share/proj", "proj.db"):
        raise SystemExit(
            "No PROJ data found: neither a Conda environment's shared copy nor "
            "pyproj's own. Build.bat creates a Conda environment that has one."
        )
    if not _check_vendored("rasterio", "gdal_data", "gdalvrt.xsd"):
        raise SystemExit(
            "No GDAL data found: neither a Conda environment's shared copy nor "
            "rasterio's own. Build.bat creates a Conda environment that has one."
        )
    print(
        "[mapmaker.spec] no shared PROJ/GDAL environment; using each package's own "
        "vendored data files (wheel layout)."
    )


# -- what goes in the bundle -------------------------------------------------

datas = [
    # The footer logo, at the path mapmaker/config.py computes from __file__ --
    # which resolves inside the bundle exactly as it does in a source checkout,
    # so no frozen-build special case is needed in the package itself.
    (str(ROOT / "mapmaker" / "assets"), "mapmaker/assets"),
]

# Landed at the top of the bundle, where the runtime hook points PROJ/GDAL. Only
# in the shared-environment case -- see the long comment above.
if proj_data and gdal_data:
    datas += [
        (str(proj_data), "proj_data"),
        (str(gdal_data), "gdal_data"),
    ]

# matplotlib's fonts and style sheets, read from disk at draw time.
datas += collect_data_files("matplotlib")

hiddenimports = [
    *collect_submodules("mapmaker"),
    # geopandas picks its I/O engine at runtime; both candidates are imported by name.
    "pyogrio",
    "shapely",
    # openpyxl resolves the reader for a workbook's parts dynamically.
    *collect_submodules("openpyxl"),
    # pandas' Excel path and matplotlib's Agg backend, likewise selected by string.
    "pandas._libs.tslibs.base",
    "matplotlib.backends.backend_agg",
]

# Kept out on purpose: development-only packages that a Conda environment tends to
# drag in and that would otherwise add hundreds of megabytes of things the app
# never touches. Excluding them also removes their compiled extensions, which is
# fewer unexplained DLLs for a corporate antivirus to form an opinion about.
excludes = [
    "IPython", "ipykernel", "jupyter", "jupyter_client", "jupyter_core", "nbconvert",
    "nbformat", "nbclient", "notebook", "zmq", "tornado", "pytest", "setuptools",
    "pip", "conda", "conda_build", "sphinx", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "wx", "sqlalchemy", "scipy", "sklearn", "numba", "docutils",
    # matplotlib's interactive backends: render.py forces Agg, and pulling in a GUI
    # toolkit backend here would bundle a second, unused UI stack.
    "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_wxagg", "matplotlib.backends.backend_webagg",
]

runtime_hooks = [str(HERE / "runtime_hooks" / "rth_geodata.py")]
hookspath = [str(HERE / "hooks")]

# An .ico is required for the executables to carry an icon. make_icon.py draws
# one (Build.bat runs it first); a build without it simply gets Windows' default
# executable icon rather than failing.
icon_path = HERE / "build_assets" / "mapmaker.ico"
icon = str(icon_path) if icon_path.is_file() else None

# A version resource is what makes Windows' file-properties dialog show a real
# publisher and description instead of blanks. SmartScreen and most antivirus
# reputation systems weigh that; an unsigned executable with no version info at
# all is the profile they treat with the most suspicion.
version_file = HERE / "version_info.txt"
version = str(version_file) if version_file.is_file() else None


def _analysis(script: str) -> Analysis:
    """Analyse one entry script. Both executables get the same imports and data,
    so their collected payloads are identical and dedupe cleanly into one folder."""
    return Analysis(
        [str(HERE / script)],
        pathex=[str(ROOT)],
        binaries=[],
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=hookspath,
        hooksconfig={},
        runtime_hooks=runtime_hooks,
        excludes=excludes,
        noarchive=False,
        optimize=0,
    )


a_gui = _analysis("entry_gui.py")
a_cli = _analysis("entry_cli.py")

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # see the module docstring: UPX is an antivirus magnet
    console=False,      # windowed: no console box behind the app window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version,
)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name=f"{APP_NAME}-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,       # console: prints where it was run from, and the GUI can
                        # capture its output when it runs a render as a subprocess
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version,
)

# One COLLECT for both executables: the binaries and data files are the same on
# each side and are deduplicated by destination path, so the GDAL/PROJ payload is
# written once and shared.
coll = COLLECT(
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
