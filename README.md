 # mapmaker

 ## Metadata

- **Project:** mapmaker
- **Developer:** Yash Mahajan <yash.mahajan@dnv.com>
- **Approver:** Luis Baquero <luis.baquero@dnv.com>
- **Purpose:** QGIS print-layout-style map generator for wind energy datasets.
- **How to run / Usage:** See the "Setup" and "Run" sections below for installation and example commands.
- **Dependencies:** See [requirements.txt](requirements.txt) and [pyproject.toml](pyproject.toml) for runtime and build dependencies.
- **Secrets:** This project does not require environment secrets or credential files. Do NOT commit any secrets; use the repository-level guidance for approved secret stores if needed.
- **Version:** 0.1.0 (from `mapmaker.__version__`)
- **Changelog:** 2026-09-04 — Initial documented release entry.
- **Contact / Support:** Owner: Yash Mahajan <yash.mahajan@dnv.com>; Repository administrator: Luis Baquero <luis.baquero@dnv.com>.

QGIS print-layout-style map generator for wind energy datasets, driven by a single
Excel workbook -- no YAML, no separate data files.
Landscape PNGs on a white page, framed by an outer border with uniform margins:
the map (basemap + data + graticule + north arrow + inset overview) fills the
frame; legend, scale bar, CRS label, and author/date/copyright sit in a
dedicated footer strip below the frame, so nothing ever overlaps the map.


## Setup

```bash
conda env create -f environment.yml
conda activate mapmaker
```

Or double-click `Setup.bat` on Windows to create the environment and install the
package in one step.

## Run

```bash
python main.py --file data/mapmaker.xlsx
```

On Windows, double-click `Mapmaker.bat` to open the desktop application.

## Build the standalone Windows app

For handing Mapmaker to someone who has no Python and no Conda on their machine.
Double-click `Build.bat` (or run it from a terminal); it creates or updates the
same `mapmaker` environment used to run the tool, builds the app, and checks that
the result actually starts.

```bash
Build.bat
```

Or, from an already-activated environment:

```bash
conda activate mapmaker
set PYTHONPATH=%CD%
python packaging\make_icon.py
python -m PyInstaller packaging\mapmaker.spec --noconfirm --clean
```

`PYTHONPATH` is not optional there: the `mapmaker` package is never installed
into the environment, so without it PyInstaller cannot import what it is being
asked to bundle.

The result is `dist\Mapmaker\` — copy that **whole folder** to the target machine
and run `Mapmaker.exe` inside it. It contains:

| File | What it is |
| --- | --- |
| `Mapmaker.exe` | the window — this is the one to double-click |
| `Mapmaker-cli.exe` | the command line: `Mapmaker-cli.exe --file book.xlsx` |
| `_internal\` | Python, GDAL, PROJ and the rest; both executables share it |

Everything comes from conda-forge — the build uses no pip, and the `mapmaker`
package is not installed into the environment at all: PyInstaller reads it
straight out of the checkout.

Notes on handing it over:

- **Copy the folder, not just the .exe.** `Mapmaker.exe` on its own cannot start;
  it needs `_internal\` beside it. Zip the folder to send it.
- **Nothing needs installing** on the target machine, and it needs no admin
  rights — the folder runs from wherever it is put, including a network share or
  a USB stick.
- **Internet access is still required** for the OpenStreetMap basemap tiles. A
  machine without it renders the same maps on a plain background instead.
- **The executables are not code-signed.** On a machine that has never seen them,
  Windows SmartScreen may show a "Windows protected your PC" prompt the first
  time (More info → Run anyway). Signing them with a certificate is what removes
  that prompt for good; the build is otherwise deliberately shaped to avoid
  antivirus trouble — see the comments at the top of
  [packaging/mapmaker.spec](packaging/mapmaker.spec).