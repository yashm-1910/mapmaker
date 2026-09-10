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