# mapmaker

QGIS print-layout-style map generator for wind energy datasets, driven by a single
Excel workbook -- no YAML, no separate data files.
Landscape PNGs on a white page, framed by an outer border with uniform margins:
the map (basemap + data + graticule + north arrow + inset overview) fills the
frame; legend, scale bar, CRS label, and author/date/copyright sit in a
dedicated footer strip below the frame, so nothing ever overlaps the map.

## Map types

1. **Wind farm locations** (`wind_farms` sheet) — point map of farms. Colored by an
   optional `status` column, or by `style.farm_colors.<name>` (one distinct color per
   farm, takes priority over `status`), or one uniform color if neither is set.
2. **Turbine positions** (`turbines` sheet) — turbine layout within one farm. If the
   sheet holds more than one `farm_name`, mapmaker renders one map per farm
   automatically; add a `data.selected_farm` row (`settings_advanced`) to render just
   one. Uniform-colored by default, or colored by any column via `style.color_field`
   (e.g. a turbine type/model, or an existing numeric column like `rotor_diameter_m`
   used categorically) — see Config option reference.
3. **ERA5 / MERRA-2 grid cells** (`grid_cells` sheet) — plain diamond/circle points at
   each cell center, one color per dataset (no filled grid polygons). Same per-farm
   auto-split as turbines. An optional `label` column labels individual cells (blank
   cells stay unlabeled — most grids have far too many cells to label every one).

Each map type is only rendered if its sheet is present in the workbook *and* its
`enabled` setting isn't `false` (see below) — leave a sheet out, or just disable it,
if you don't need that map. Point marker shape (`style.marker`, any matplotlib marker
code) and size are configurable per map type; defaults are round points for wind
farms/turbines and diamonds for the reanalysis grids.

## Setup

Requires Python 3.10+. Two ways to get it running, depending on whether you're
developing mapmaker itself or just using it:

**Developing from source** (editing the code, regenerating demo data, etc.) — from
the project root:

```bash
python -m venv .venv

# activate it:
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows (cmd.exe)
.venv\Scripts\Activate.ps1       # Windows (PowerShell)

pip install -r requirements.txt
python scripts/generate_test_data.py   # writes data/mapmaker.xlsx + assets/logo.png
```

(Already have a virtualenv, conda env, or other Python set up? Just `pip install
-r requirements.txt` into it and skip the `venv` step.)

**Installing it as a package** (to run it from anywhere, or on a machine that
doesn't have this source checkout) — see Packaging below.

## Run

```bash
python main.py --file data/mapmaker.xlsx
python main.py --file data/mapmaker.xlsx --map-type turbines   # just one map type
```

Installed as a package instead (see Packaging)? The same thing is available
anywhere as the `mapmaker` command, with identical arguments:
`mapmaker --file data/mapmaker.xlsx`.

Every data sheet present in the workbook (`wind_farms` / `turbines` / `grid_cells`)
renders in one command, skipping any map type whose `enabled` setting is `false`
(an explicit `--map-type` always renders regardless — it's a direct request); outputs
land in `output/`.

## Packaging

mapmaker is a proper installable Python package (`pyproject.toml`, `mapmaker/cli.py`
as the entry point) — the source layout under `## Setup`/`## Run` above still works
unchanged for local development, this is for producing something installable
elsewhere, or just having the `mapmaker` command available anywhere on your own
machine instead of running `python main.py` from inside this checkout.

- **pip**, from the project root:
  ```bash
  pip install .          # regular install
  pip install -e .       # editable install -- code edits take effect without reinstalling
  ```
  Either way this registers the `mapmaker` console command and makes `import mapmaker`
  work from any directory, not just this one. To build distributable files instead of
  installing directly (a wheel + source distribution under `dist/`):
  ```bash
  pip install build
  python -m build
  ```
  Dependencies come from `requirements.txt` (read at build time via
  `[tool.setuptools.dynamic]` in `pyproject.toml`, so there's only one list to keep
  in sync, not two) — exact-pinned rather than loose-ranged, since this is an
  internal tool installed directly by its own users rather than a library other
  packages depend on, so reproducibility matters more here than resolver flexibility.
- **conda**, from the project root (needs the `conda-build` package:
  `conda install conda-build`):
  ```bash
  conda build conda-recipe/
  conda install --use-local mapmaker
  ```
  `conda-recipe/meta.yaml` builds from this local checkout and installs via pip
  under the hood (`pip install . --no-deps`), pulling its run dependencies from
  conda-forge equivalents of `requirements.txt` (`matplotlib-base` instead of
  `matplotlib`, since this tool only ever saves PNGs and never opens an interactive
  window, so it doesn't need matplotlib's GUI-backend packages). It wasn't
  build-tested against a live conda-forge channel while writing this (no conda
  installed in that environment) — if a pinned version isn't available on the
  channel you build against, relax that one line to `>=` or drop the pin.

Both paths bundle `mapmaker/assets/logo.png` (the default footer logo — see
`company.logo_path` above) inside the installed package itself, so it's available
regardless of where or how mapmaker ends up installed.

This is set up for **building and installing locally/internally** — no PyPI or
conda-forge account, license file, or public-channel submission is included, since
none of that is needed unless you later decide to publish this beyond your own
machine/organization.

## The workbook (one Excel file for everything)

`data/mapmaker.xlsx` (generated by `scripts/generate_test_data.py`, or build your own)
holds every sheet mapmaker needs:

- **`wind_farms`** — required: `name, lon, lat`. Optional: `capacity_mw` (marker
  sizing, `style.size_field`), `status` (per-category coloring, `style.status_colors`).
- **`turbines`** — required: `turbine_id, lon, lat`, plus `farm_name` if the sheet
  holds more than one farm. Other columns (hub height, rotor diameter, capacity, a
  turbine type/model, ...) are fine to include for your own records, and any of them
  can double as `style.color_field` to color by (see Map types above).
- **`grid_cells`** — required: `dataset, cell_id, lon, lat`, plus `farm_name` if the
  sheet holds more than one location, plus an optional `label` column (one row per
  grid cell center; cells render as plain diamond/circle points, not filled polygons,
  so no cell-boundary columns are needed). A row with `dataset = reference` (instead
  of e.g. `ERA5`/`MERRA2`) marks a named reference point rather than a grid cell — see
  `reference_point` in Layout notes.
- **`settings_basic`** / **`settings_advanced`** — every rendering setting, as
  `Map | key | value | description` rows. Both sheets share the same schema and are
  read together (a `config` sheet also still works, e.g. for a single-sheet workbook);
  splitting them is purely organizational:
  - **`settings_basic`** — what you'd plausibly change often: titles, author/date,
    company/logo, colors and other `style.*` appearance, on/off toggles for every
    chrome element, each map type's own `enabled` switch, and output filenames.
  - **`settings_advanced`** — fine-tuning knobs you'd rarely touch: page margins,
    DPI, tick density, inset/bbox sizing, footer column ratios, basemap technical
    params, and which farm/dataset to render when you don't want the auto-split.

  Columns:
  - `Map` — blank (or `*`) applies the setting to every map type; set it to
    `Portfolio Map`, `Turbine Map`, or `ERA5/MERRA2 Map` to override just that one
    (the older internal names — `wind_farms`, `turbines`, `grid_cells` — and an
    older `scope` column header both still work, for backward compatibility). **A
    setting that's the same for every map type gets one global (blank) row — it
    isn't repeated per type.** Only settings that genuinely need to differ (or are
    inherently type-specific, like `style.*` or `export.filename`) get their own
    row per map type; the mechanism still supports overriding literally any key for
    any single map type, this just keeps the shipped example from cluttering itself
    with redundant identical rows. Copy the pattern from
    `scripts/generate_test_data.py`'s `BASIC_ROWS`/`ADVANCED_ROWS` for your own
    workbook: one row per setting, scoped only where the value actually needs to
    differ (that script writes the internal names for readability and relabels
    them to the friendly names above when it builds the sheet).
  - `key` — a dotted path into the settings, e.g. `footer.height_fraction`,
    `style.marker_size`, `basemap.provider`, `style.farm_colors.Nordsee Alpha`.
  - `value` — parsed automatically: `true`/`false` → boolean, a number → int/float,
    a comma-separated cell (e.g. `1.0, 1.3, 1.4, 2.1`) → a list, anything else →
    string. Leave a row out entirely (or leave `value` blank) to use the built-in
    default for that setting. **Every color/marker row has an in-cell dropdown** —
    click the cell and use the arrow to pick a value instead of typing one; see
    `style_reference` below. You're never limited to what's in the dropdown, though
    — typing anything else (a precise hex code, an uncommon matplotlib marker) works
    exactly as before and isn't blocked.
  - `description` — free text for a human reading the workbook; mapmaker's parser
    ignores this column entirely, so put whatever's useful there.

  Any setting left out of both sheets falls back to the built-in default — see
  `mapmaker/config.py`'s `DEFAULTS` for the full list and what each one does, or the
  Config option reference below. `scripts/generate_test_data.py`'s `BASIC_ROWS` /
  `ADVANCED_ROWS` are a complete worked example of literally every option, each with
  its own description.
- **`style_reference`** — a visible lookup sheet, purely for humans (and the
  dropdowns above, which pull their list from it): a curated set of named
  matplotlib colors, each with an actual color swatch next to it, and a table of
  common matplotlib marker codes with what each one looks like (`o` circle, `D`
  diamond, `^` triangle, ...) plus a link to matplotlib's full marker reference for
  anything not listed. Named colors are used instead of hex throughout — a color
  name means something at a glance, a hex code doesn't. The two exceptions are
  `style.farm_colors.*`/`style.category_colors.*`, which keep their exact
  Okabe-Ito colorblind-safe hex values on purpose (see Map types above) rather
  than an approximate named color.

Paths inside the workbook (`company.logo_path`, `export.output_dir`) are resolved
relative to the workbook's own directory unless given as absolute paths.
`company.logo_path` is the one exception with its own built-in default: leave it
unset and mapmaker falls back to its own logo bundled inside the `mapmaker` package
itself (`mapmaker/assets/logo.png`, a neutral "YOUR LOGO" placeholder) rather than
looking for anything next to the workbook — this is what makes the footer logo work
out of the box for a pip/conda install, where nothing is guaranteed to sit alongside
a given workbook the way `mapmaker/`'s own files always sit alongside each other.
Set `company.logo_path` to your own logo's path to override it, or to an explicitly
blank value to turn the footer logo off entirely instead of falling back.

See `mapmaker/data_io.py` for the exact column contract each `read_*` function enforces,
and `mapmaker/config.py::load_workbook_configs` for exactly how the settings sheets are parsed.

`title` / `subtitle` are omitted by default: if the settings sheets don't set them,
no title is drawn and the map reclaims that vertical space — add `title`/`subtitle`
rows (global or per map type) when you want one.

## Config option reference

Every `key` you can put in `settings_basic`/`settings_advanced`, grouped the same way
as `mapmaker/config.py`'s `DEFAULTS`. "Sheet" shows where the shipped demo workbook
puts that setting (purely a convention — either sheet works for any key); "Applies to"
shows which map type(s) actually use it (global rows with a blank `Map` column are read
by every map type, but a setting a given map type doesn't use is simply ignored).

### General

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `enabled` | basic | `true` | all | Set `false` (per map type) to skip rendering it entirely, without removing its sheet/settings from the workbook. |
| `author` | basic | `Unknown Author` | all | "Author: ..." line in the footer. |
| `date` | basic | `auto` | all | `auto` -> today's date (ISO); or set an explicit string, e.g. `2026-09-01`. |
| `title` | basic | *(empty)* | all | Figure title. Left blank, no title is drawn and the map reclaims that space. |
| `subtitle` | basic | *(empty)* | all | Smaller line under the title. Only shown if `title` is also set. |
| `notes` | basic | `[]` | all | Comma-separated cell -> list of extra free-text lines appended to the footer. |
| `attribution.text` | basic | `© OpenStreetMap (OSM)` | all | Copyright line in the footer. |

### `company.*` — footer logo

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `company.name` | basic | *(empty)* | all | Stored but not currently drawn as text (only the logo image shows) — see Footer metadata. |
| `company.logo_path` | basic | *(mapmaker's own bundled logo)* | all | Path to a logo image, resolved relative to the workbook's own directory (or absolute). Unset falls back to a placeholder logo bundled inside the `mapmaker` package itself, not to nothing — see "The workbook" above. Set explicitly blank to turn the footer logo off. |
| `company.logo_scale` | basic | `1.0` | all | Multiplier on the logo's footer size, anchored to the bottom-right corner (e.g. `1.5` = 50% bigger). |

### `map.*` — page/canvas and data extent

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `map.crs` | basic | `EPSG:4326` | all | Coordinate reference system used for plotting and the basemap. Any `pyproj`-recognized CRS works, including a projected/UTM zone, e.g. `EPSG:32631` (UTM 31N) — data is reprojected from its lon/lat source columns automatically, and the graticule switches to that CRS's native units (meters, for UTM); see Layout notes, including the UTM zone-mismatch warning. |
| `map.figsize` | advanced | `13, 8` | all | Page size in inches, `width, height` (landscape). |
| `map.dpi` | advanced | `300` | all | Resolution (dots per inch) of the exported PNG. |
| `map.background_color` | advanced | `white` | all | Page/figure background color. |
| `map.padding_fraction` | advanced | `0.12` | all | Extra breathing room padded around the data extent (fraction of the data span) — lower to zoom in tighter on the data, raise to zoom out and show more surrounding context. |
| `map.extent` | advanced | *(auto)* | all | `xmin, xmax, ymin, ymax` to force an exact extent instead of deriving one from the data. |

### `basemap.*` — OpenStreetMap/XYZ tile layer

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `basemap.show` | basic | `true` | all | Toggle the basemap on/off. |
| `basemap.provider` | basic | `OpenStreetMap.Mapnik` | all | Dotted path into `contextily.providers`, e.g. `CartoDB.Positron`/`Esri.WorldGrayCanvas` for a muted look, or `Esri.WorldShadedRelief`/`OpenTopoMap`/`Esri.WorldTopoMap` for terrain/relief — see Basemap notes. A full `{x}`/`{y}`/`{z}` tile URL is also accepted and used as-is. |
| `basemap.zoom` | advanced | `auto` | all | Tile zoom level; leave `auto` or set a fixed integer for explicit control. |
| `basemap.zoom_adjust` | advanced | `1` | all | Bumps the auto-computed zoom level up by this many levels for sharper tiles (each `+1` ~doubles detail); `0` = contextily's own auto choice as-is. Also applies to the inset map's basemap. |
| `basemap.alpha` | advanced | `1.0` | all | Basemap opacity, `0`-`1`. |
| `basemap.headers.User-Agent` | advanced | `mapmaker-tuhh/1.0 (...)` | all | HTTP header sent with tile requests — OSM requires a descriptive `User-Agent` or it visibly renders a "blocked" placeholder tile. Replace the contact email before heavy/production use. |
| `basemap.interpolation` | advanced | `bilinear` | all | How the basemap's fixed-resolution tile pixels are resampled up to print size; try `lanczos` for crisper-looking tile text/lines — see Basemap notes. |
| `basemap.timeout` | advanced | `15` | all | Seconds to wait for a tile server before giving up on that tile and falling back to a flat fill — see Basemap notes. |

### `graticule.*` — coordinate grid ticks

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `graticule.show` | basic | `true` | all | Toggle the coordinate grid/ticks on/off. |
| `graticule.n_ticks` | advanced | `5` | all | Approximate number of tick/cross lines per axis; shared fallback for both axes when `n_ticks_x`/`n_ticks_y` aren't set. |
| `graticule.n_ticks_x` | advanced | *(none)* | all | Horizontal-axis tick density, independent of the vertical axis. Falls back to `graticule.n_ticks` if unset. |
| `graticule.n_ticks_y` | advanced | *(none)* | all | Vertical-axis tick density, independent of the horizontal axis. Falls back to `graticule.n_ticks` if unset. |
| `graticule.format` | advanced | `decimal` | all | `decimal` (e.g. `5.90°`) or `dms` (degrees/minutes/seconds, e.g. `5°54'00.0"`). Only applies when `map.crs` is geographic — a projected CRS like UTM always shows native-unit ticks instead. |
| `graticule.hemisphere_labels` | advanced | `true` | all | `true` appends `E`/`N`/`W`/`S`; `false` drops the letter and keeps a `-` sign for west/south instead. |
| `graticule.fontsize` | advanced | `10` | all | Tick label font size. |
| `graticule.color` | advanced | `0.35` | all | Tick/cross mark color. |
| `graticule.linewidth` | advanced | `0.6` | all | Tick/cross mark line width. |
| `graticule.frame` | advanced | `true` | all | Draw the black frame/spines around the map panel. |

### `legend.*` / `scalebar.*` / `north_arrow.*` — chrome in the footer/map

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `legend.show` | basic | `true` | all | Toggle the legend panel on/off. |
| `legend.title` | basic | `Legend` | all | Legend panel heading. |
| `scalebar.show` | basic | `true` | all | Toggle the scale bar on/off. |
| `scalebar.units` | advanced | `auto` | all | `auto` (m below 1 km, else km), or force `m`/`km`. |
| `scalebar.length_fraction` | advanced | `0.55` | all | Target fraction of the scale bar panel's width the bar should roughly fill before rounding to a nice number. |
| `north_arrow.show` | basic | `true` | all | Toggle the compass rose on/off. |
| `north_arrow.location` | advanced | `lower right` | all | Corner inside the map frame: `upper left`/`upper right`/`lower left`/`lower right`. |
| `north_arrow.size` | advanced | `0.045` | all | Arrow size, as a fraction of the map panel. |

### `inset_map.*` — overview inset

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `inset_map.show` | basic | `true` | all | Toggle the overview inset on/off. |
| `inset_map.location` | advanced | `lower left` | all | Corner inside the map frame (same 4 options as `north_arrow.location`). Pick a corner empty of data — the inset is opaque and covers anything beneath it. |
| `inset_map.size` | advanced | `0.28` | all | Inset size as a fraction of the map panel. |
| `inset_map.zoom_out_factor` | advanced | `8` | all | How many times wider/taller the inset's view is than the main map's extent. |
| `inset_map.bbox_edgecolor` | advanced | `red` | all | Color of the ROI bounding box drawn on the inset. |
| `inset_map.bbox_linewidth` | advanced | `2.2` | all | Line width of that ROI bounding box. |
| `inset_map.min_bbox_frac` | advanced | `0.05` | all | Floors the ROI box to at least this fraction of the inset's width/height, so it stays visible at a large `zoom_out_factor`. The demo raises this per map type where a bigger `zoom_out_factor` would otherwise shrink the box to a barely-visible sliver. |

### `reference_point.*` — single named point (grid_cells only)

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `reference_point.show` | basic | `false` | grid_cells | Toggle the reference point on/off. |
| `reference_point.name` | advanced | *(empty)* | grid_cells | Fallback label, only used if the sheet has no matching `dataset = reference` row — normally the point's own `farm_name` row in `grid_cells` supplies the label instead (see Layout notes). |
| `reference_point.lon` / `.lat` | advanced | *(none)* | grid_cells | Fallback coordinates, same rule — normally sourced from the sheet's `dataset = reference` row for the current farm. |
| `reference_point.marker` | advanced | `o` | grid_cells | Marker shape, any matplotlib marker code. |
| `reference_point.color` | advanced | `#d62728` | grid_cells | Marker color. |
| `reference_point.size` | advanced | `70` | grid_cells | Marker size. |
| `reference_point.label_fontsize` | advanced | `9` | grid_cells | Font size of the name label. |

### `footer.*` — footer strip layout

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `footer.show` | basic | `true` | all | Toggle the whole footer strip on/off. |
| `footer.height_fraction` | advanced | `0.09` | all | How tall the footer band is, as a fraction of the page. Raise it if your legend has many entries (e.g. `style.farm_colors` giving every farm its own row) — the demo raises `wind_farms` to `0.24` for exactly this reason. |
| `footer.column_widths` | advanced | `1.0, 1.3, 1.4, 2.1` | all | Relative widths of the legend / scale bar / CRS / date-author-copyright+logo columns. |
| `footer.fontsize` | advanced | `8` | all | Footer text size. |
| `footer.text_color` | advanced | `0.15` | all | Footer text color. |

### `export.*` — output file

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `export.output_dir` | advanced | `../output` | all | Output folder, resolved relative to the workbook's own directory. |
| `export.filename` | basic | *(empty)* | all | Left empty, defaults to `<map_type>.png` (or `<map_type>_<farm-slug>.png` per auto-split map). |
| `export.transparent` | advanced | `false` | all | Export with a transparent background instead of `map.background_color`. |

### `data.*` — which rows to plot

| Key | Sheet | Default | Applies to | What it does |
|---|---|---|---|---|
| `data.selected_farm` | advanced | *(none)* | turbines, grid_cells | Pin the render to one `farm_name` instead of auto-rendering one map per farm. |
| `data.selected_datasets` | advanced | *(none)* | grid_cells | Comma-separated list of `dataset` values to include; unset renders every dataset present. |

### `style.*` — per-map-type appearance (no shared defaults; each map type reads its own keys)

**`wind_farms`** (all in `settings_basic`):

| Key | Default | What it does |
|---|---|---|
| `style.marker` | `o` | Marker shape, any matplotlib marker code (`o` circle, `D` diamond, `^` triangle, ...). |
| `style.color` | `#2166ac` | Marker color used when there's no `status` column (or for statuses/farms missing from `status_colors`/`farm_colors`). |
| `style.status_colors.<status>` | *(none)* | Per-status color, only used if the `wind_farms` sheet has a `status` column, e.g. `style.status_colors.Operational = #2ca25f`. Ignored if `farm_colors` is set (see below). |
| `style.farm_colors.<name>` | *(none)* | Per-farm color, keyed by the farm's own `name` — gives each wind farm its own distinct color and its own legend entry, overriding `status`-based grouping entirely once any row is set. E.g. `style.farm_colors.Nordsee Alpha = darkorange` (pick from the `style_reference` dropdown, or a precise hex code). With many farms this needs a taller `footer.height_fraction` to fit every legend entry (see Layout notes) — the demo enables this for all 10 farms, using exact colorblind-safe hex values rather than named colors (see `style_reference` in "The workbook" above). |
| `style.legend_labels.<status-or-name>` | *(none)* | Overrides one legend entry's displayed text — keyed by `status` value normally, or by farm `name` when `farm_colors` is in use — without changing its color/grouping. E.g. `style.legend_labels.Nordsee Alpha = Nordsee Alpha (flagship)`. |
| `style.size_field` | `capacity_mw` | Optional numeric column that scales marker size; omit the column to fall back to a fixed size. |
| `style.base_marker_size` | `45` | Base marker size before size-field scaling. |
| `style.size_scale` | `0.5` | Multiplier applied to `size_field`'s value before adding it to `base_marker_size`. |
| `style.label_points` | `true` | Draw each farm's `name` next to its point. |
| `style.label_fontsize` | `9` | Point label font size. |
| `style.declutter_labels` | `true` | Reorient a label around its point (instead of a fixed spot) if needed to avoid overlapping another label — never dropped (see Layout notes). Farms are placed in `size_field` order (biggest first) so, when it's crowded, the more prominent farms get first pick of the tidiest spot. |
| `style.legend_label` | `Wind Farm` | Legend entry label used when there's no `status` column and `farm_colors` isn't set. |

**`turbines`** (all in `settings_basic`):

| Key | Default | What it does |
|---|---|---|
| `style.marker` | `o` | Marker shape. |
| `style.color` | `#2166ac` | Uniform marker color, used when `color_field` isn't set. |
| `style.marker_size` | `55` | Marker size. |
| `style.label_points` | `true` | Draw each turbine's `turbine_id` next to its point. |
| `style.label_fontsize` | `8` | Point label font size. |
| `style.declutter_labels` | `true` | Same overlap-avoiding reorientation as `wind_farms` above, in `turbine_id` order. |
| `style.color_field` | *(none)* | Column to color turbines by instead of one uniform color — any column works, numeric or text (e.g. a `turbine_type` column, or reusing `rotor_diameter_m`'s own values categorically). Each distinct value gets its own color and legend entry. |
| `style.category_colors.<value>` | *(none)* | Explicit color for one `color_field` category. Any category left out still gets colored automatically from a built-in colorblind-safe palette, so `color_field` works with zero color configuration too — the demo leaves one of its three turbine types unlisted to prove this. |
| `style.legend_labels.<value>` | *(none)* | Renames one `color_field` category's legend text without changing its color. |
| `style.legend_label` | *(the split's `farm_name`, else `Turbine`)* | Legend entry label used only when `color_field` isn't set. An explicit value here always wins; otherwise it defaults to the map's own wind farm name (see Map types) so a split-per-farm turbine map doesn't just say "Turbine" in every legend. |

**`grid_cells`** (all in `settings_basic`):

| Key | Default | What it does |
|---|---|---|
| `style.marker` | `D` | Fallback marker shape for any dataset not listed in `dataset_markers`. |
| `style.dataset_markers.<dataset>` | *(none)* | Per-dataset marker shape override, e.g. `style.dataset_markers.ERA5 = D`, `style.dataset_markers.MERRA2 = o` — lets each reanalysis dataset use its own icon. |
| `style.dataset_colors.<dataset>` | `ERA5=steelblue, MERRA2=chocolate` | Per-dataset color. |
| `style.legend_labels.<dataset>` | *(none)* | Overrides one dataset's legend text (default `"<dataset> grid"`, e.g. `"ERA5 grid"`) without changing its color/marker, e.g. `style.legend_labels.ERA5 = ERA5 (0.25°)`. |
| `style.marker_size` | `14` | Marker size (shared across datasets). |
| `style.label_points` | `true` | Draw a label next to any row whose `label` column is non-blank (see the `grid_cells` sheet); rows with a blank `label` show only their point, unlabeled. Has no effect if the sheet has no `label` column at all. |
| `style.label_fontsize` | `7` | Point label font size. |
| `style.declutter_labels` | `true` | Same overlap-avoiding reorientation as `wind_farms`/`turbines` above. |

`scripts/generate_test_data.py`'s `BASIC_ROWS`/`ADVANCED_ROWS` are a complete worked
example of every key above, each with its own description, and `mapmaker/config.py`'s
`DEFAULTS` dict is the source of truth if this table and the code ever drift.

## Layout notes

- **Point labels decluttered automatically** (`wind_farms`/`turbines`/`grid_cells`,
  `style.declutter_labels`, default `true`): every point still gets a label — none are
  ever dropped. Instead, `render.py::_place_labels` tries a ring of 8 candidate
  placements around each point (N/S/E/W and the diagonals), estimating each candidate's
  on-page bounding box from the map panel's real rendered pixel size (like the scale
  bar does), and uses the first one that doesn't overlap an already-placed label or the
  inset map; if every candidate would overlap something, it falls back to whichever
  candidate overlaps the least. Labels are placed in priority order (wind farms:
  biggest `size_field` first; turbines/grid_cells: sheet order), so on a crowded map the
  higher-priority points get first pick of the tidiest spot. Set
  `style.declutter_labels: false` to always use the single default placement
  (upper-right of the point) instead, ignoring overlaps entirely.
- **Outer page border with uniform margins.** A thin rectangle frames the
  whole page (`render.py::_add_page_border`). Margins are defined in *inches*
  (`OUTER_MARGIN_IN`, `SIDE_PAD_IN`, `BOTTOM_PAD_IN`, `TITLE_BAND_IN` at the
  top of `mapmaker/render.py`) and converted to the correct figure-fraction
  per axis (`_page_margins`) — so the white space outside the border, and the
  gap from the border to the map's top/left/right edges, are genuinely equal
  in absolute terms even on a non-square landscape figure (equal *fractions*
  of a wider-than-tall canvas would otherwise give unequal margins). When a
  title is set it's drawn in that same top margin band, still `SIDE_PAD_IN`
  below the border.
- **Legend and scale bar render outside the map frame**, in their own footer
  panels — their size never depends on how much of the map's data happens to
  sit in some corner, so they can never collide with map content. The scale
  bar is computed from the map axes' *true* printed geographic scale (using
  the actual rendered pixel width of the map panel), not just a visual guess.
- **Footer layout is user-configurable** and kept close to the bottom border
  by default (no tall empty strip below it): `footer.height_fraction`
  controls how tall the footer band is (default `0.09`, enough for a short
  legend; the demo raises it to `0.24` for `wind_farms` since `style.farm_colors`
  gives all 10 farms their own legend entry — raise it similarly whenever a
  legend has many entries, e.g. many `status_colors`/`farm_colors`/`color_field`
  categories), and `footer.column_widths` (default `[1.0, 1.3, 1.4, 2.1]`) controls the
  relative width of the legend / scale bar / CRS / date-author-copyright+logo
  columns. All four columns bottom-align to the page's bottom border, like a
  row of footnotes — any leftover slack ends up as space above the footer
  content (next to the map), not as a trailing empty strip below it.
- **Every chrome element can be switched off independently**: `basemap.show`,
  `graticule.show`, `legend.show`, `scalebar.show`, `north_arrow.show`,
  `inset_map.show`, and `footer.show` are all `true`/`false` toggles — e.g.
  add an `inset_map.show = false` row to drop the overview inset entirely
  with no other changes needed. The same pattern extends to whole map types:
  `enabled = false` (scoped to `Portfolio Map`/`Turbine Map`/`ERA5/MERRA2 Map`)
  skips rendering that map type altogether, without touching its sheet or settings.
- **North arrow and the inset overview map sit inside the map frame**, each in
  a configurable corner (`north_arrow.location`, `inset_map.location`). Being
  opaque, whichever corner they occupy visually covers any data underneath —
  same as in QGIS. Point labels are nudged away from the inset's corner
  automatically, but the point marker itself can still be covered if it falls
  deep inside that corner. Pick a corner that's empty for your dataset (see
  the `wind_farms`/`turbines` rows in `scripts/generate_test_data.py`'s
  `ADVANCED_ROWS`, which both do this); for data that fills its whole bounding
  box (e.g. a full turbine grid or a wall-to-wall reanalysis grid), add extra
  `map.padding_fraction` and/or shrink `inset_map.size` so real corners stay
  clear. **Inset size is fully user-configurable** via `inset_map.size` (a
  fraction of the map panel, e.g. `0.28` = 28%) — bigger for more overview
  context, smaller to minimize what it covers. Its ROI bounding box is
  drawn at `inset_map.bbox_linewidth`/`bbox_edgecolor`, and is floored to at
  least `inset_map.min_bbox_frac` of the inset's size so it stays visible
  even at a large `zoom_out_factor`.
- **Extent padding matches the landscape panel's aspect ratio**: instead of
  padding lon/lat symmetrically, `render.py::_compute_extent` expands
  whichever dimension is short (in real-world distance, accounting for the
  `cos(lat)` correction in geographic CRSs) so the data fills a landscape
  panel without large empty side margins.
- **Graticule** draws small `+` cross ticks at each grid intersection (not
  full lines across the map) with coordinate labels mirrored on all four
  sides of the frame, matching a classic QGIS print-layout grid. Horizontal
  and vertical tick density can be set independently via
  `graticule.n_ticks_x`/`graticule.n_ticks_y` — useful when the map panel is much
  wider than it is tall (or vice versa) and one shared `n_ticks` would otherwise
  leave one axis too sparse or the other too crowded; either left unset falls back
  to the shared `graticule.n_ticks`. Note the actual tick count is only
  approximate either way — spacing is rounded to a "nice" number (`elements.py::_nice_step`)
  rather than hit exactly.
- **Projected/UTM coordinate systems work via `map.crs`** — it isn't limited to
  `EPSG:4326`. Set it to any CRS `pyproj` recognizes, e.g. `EPSG:32631` for UTM zone
  31N (covers the North Sea demo data); pick the zone that covers your own data's
  longitude. Turbine/farm/grid-cell coordinates are still entered as plain lon/lat in
  the workbook — `data_io.py`'s `read_*` functions always build points in `EPSG:4326`
  first and then reproject to `map.crs`, so nothing about the data sheets changes. The
  basemap and scale bar adapt automatically; the CRS label in the footer shows the
  projected code.
  - **Graticule ticks switch to the CRS's own native units for a projected `crs`**
    (`elements.py::_is_geographic_crs` / `_add_native_graticule`): a UTM map gets a
    straight easting/northing grid labeled in meters (e.g. `600,000 m`) instead of
    reprojected lon/lat meridians — `graticule.format`/`hemisphere_labels` only apply
    when `map.crs` is geographic (like the default `EPSG:4326`); `n_ticks`/`n_ticks_x`/
    `n_ticks_y` still control tick density either way.
  - **UTM is zone-based** — each zone only covers a 6°-wide longitude band around its
    own central meridian, and distances/shapes get increasingly distorted the further
    data sits from that meridian. If `map.crs` is a UTM EPSG code (`326xx`/`327xx`) and
    the data spans more than ~6° of longitude, or is centered more than 3° from that
    zone's meridian, mapmaker prints a `warnings.warn` naming the zone actually implied
    by the data's own center (`render.py::_warn_utm_zone_mismatch`/`_utm_zone_epsg`) —
    switch to that zone, or fall back to a non-UTM CRS (`EPSG:3857` or `EPSG:4326`) if
    the data genuinely spans multiple zones.
- **`reference_point` (grid_cells maps only)** marks the wind farm an ERA5/MERRA2
  comparison is centered on: a single named circle point. Toggle/style it via
  `reference_point.show`/`.marker`/`.color`/`.size`/`.label_fontsize` (`show` defaults
  to `false`, so it's omitted unless you turn it on). Its **position and label come
  from the `grid_cells` sheet itself**, not settings: add one row per farm with
  `dataset` set to `reference` (a reserved value, never plotted as a grid cell)
  alongside that farm's ERA5/MERRA2 rows, e.g.:
  ```
  farm_name       dataset     cell_id   lon    lat
  Nordsee Alpha   reference             6.35   54.65
  Nordsee Alpha   ERA5        ERA5-0001 ...    ...
  Nordsee Alpha   MERRA2      ...       ...    ...
  ```
  The row's own `farm_name` doubles as the on-map label, so if the sheet auto-splits
  into one map per farm (see Map types above), each split automatically picks up *its
  own* farm's reference row — no per-farm config needed, and a distant farm's point
  never leaks into another farm's extent. It's included in the map's extent calculation,
  so the frame adjusts to keep it visible even if it sits near the edge of the grid.
  For a workbook with no `farm_name` column at all (a single combined grid map), you can
  instead set `reference_point.name`/`.lon`/`.lat` directly in settings as a fallback —
  used only when the sheet has no matching `reference` row.

## Footer metadata

The rendered footer currently shows only what was asked for: **author,
date, copyright (OSM attribution), and coordinate reference system** — plus
the legend and scale bar. The plumbing for more supports it without any code
changes needed:

- **`notes`** — a settings row with key `notes` and a comma-separated value is parsed
  as a list; each entry is appended to the date/author/copyright block. E.g. a row
  `key=notes, value=Internal draft -- not for distribution`.
- **`extra_footer_lines`** — `_finalize()` in `mapmaker/render.py` and
  `elements.add_footer()` both already accept an `extra_footer_lines` /
  `extra_lines` list. Each `build_*` function in `render.py` has a comment
  showing where stats like farm count, turbine count, or total capacity used
  to be assembled (`extra = [...]`) before being passed through; reinstate
  that pattern for any per-map dataset stats you want back in the footer.
- **`company.name`** — set via settings but intentionally not rendered as text
  right now (only `company.logo_path` shows, as the logo image). Add a line
  for it in `elements.add_footer`'s `lines` list if you want the company name
  spelled out as well as shown via the logo.
- **`company.logo_scale`** (default `1.0`) — multiplier on the logo's size in
  the footer. The logo anchors to the bottom-right corner of its column and
  grows/shrinks from that corner, so scaling it up never shifts the
  date/author/copyright text above it; it's clamped so it can't outgrow the
  column itself. E.g. `logo_scale: 1.5` for a 50% bigger logo.

## Basemap notes

- Default provider is `OpenStreetMap.Mapnik`. Their tile server enforces a
  usage policy requiring a descriptive `User-Agent` (set under
  `basemap.headers`) — without one it visibly renders an "Access blocked"
  placeholder tile (not a silent failure, and not specific to any one
  provider — it's OSM's own tile policy). Replace the contact email in that
  header with your own before heavy/production use.
- Swap `basemap.provider` to any dotted path into `contextily.providers`
  (e.g. `CartoDB.Positron`, `Esri.WorldGrayCanvas`) for a different look. A
  full tile URL template containing `{x}`/`{y}`/`{z}` also works directly
  (e.g. a Mapbox/private tile URL with your own API key already in it) —
  useful for **Google's terrain-hybrid tiles**: Google doesn't publish a
  simple XYZ endpoint the way OSM/Carto/Esri do, so this only works via
  Google's paid Maps Platform Tiles API (session-token auth, more involved
  than one URL) or one of the well-known unofficial tile hosts
  (`mt1.google.com/vt/lyrs=y&...`) that many hobby tools use — the
  latter works technically but isn't an approved integration path per
  Google's ToS, so it's not wired in or shipped as a demo default; point
  `basemap.provider` at either yourself if you want it.
- **Terrain/relief basemaps** work the same way, no code change needed — set
  `basemap.provider` to `Esri.WorldShadedRelief` (clean hillshade), `OpenTopoMap`
  (colored elevation + contours + roads/labels), or `Esri.WorldTopoMap` (topographic
  map style); all three are free and need no API key, confirmed working end-to-end.
  Note that over low-relief terrain (e.g. the Dutch/German coast in the demo
  data) `OpenTopoMap`'s hillshading is subtle and it can look close to plain
  `OpenStreetMap.Mapnik` at a glance — that's the actual terrain, not a bug;
  `Esri.WorldShadedRelief` makes the relief more visually obvious everywhere.
- **If a basemap "just doesn't work"** (hangs rather than erroring): some free
  tile providers throttle or silently drop requests from datacenter/cloud IPs,
  and without a timeout that can hang the whole render forever instead of
  falling back to a flat fill. `basemap.timeout` (default `15` seconds) caps
  how long any single tile request waits before giving up and falling back —
  lower it for faster failover, raise it only if you're on a genuinely slow
  connection.
- **Improving basemap resolution** (getting more real detail, e.g. actual road
  labels visible at a given zoom): `basemap.zoom_adjust` (default `1`) bumps the tile
  zoom level up from contextily's own auto-computed choice — each `+1` roughly
  doubles the tile detail/resolution in each dimension (more, smaller tiles
  covering the same extent) at the cost of more tiles to download. Raise it
  further (e.g. `2` or `3`) for sharper basemaps, especially on zoomed-in
  turbine-scale maps; set it to `0` to use contextily's auto zoom as-is. It
  also applies to the inset overview map's basemap. `map.dpi` (default `300`)
  controls the exported PNG's resolution independently — raise it for a
  higher-resolution print/export, though it doesn't by itself fetch more
  detailed tiles the way `zoom_adjust` does. You can also set `basemap.zoom`
  directly to a fixed integer (instead of `auto`) if you want explicit control
  over the tile zoom level rather than an auto+adjust offset.
- **Improving basemap image/text *sharpness*** (as opposed to more detail being
  visible at all): this is a resampling issue, not a detail issue — OSM tiles are a
  fixed 256x256px raster, so displaying them at a large print size/DPI stretches
  those pixels, and matplotlib's `interpolation` mode controls how that stretch is
  smoothed. `basemap.interpolation` (default `bilinear`) can be set to `lanczos` for
  a crisper look at hard edges/text (at some risk of ringing artifacts); `zoom_adjust`
  above still matters more for genuine sharpness, since fetching a higher-resolution
  tile in the first place beats resampling the same one more cleverly.

## Code layout

`mapmaker/config.py` loads the workbook's `settings_basic`/`settings_advanced` (and/or
a single `config`) sheets into per-map-type settings dicts (`load_workbook_configs`),
merged over the built-in `DEFAULTS`. `mapmaker/data_io.py` reads the
`wind_farms`/`turbines`/`grid_cells` sheets into GeoDataFrames. `mapmaker/render.py`
builds each figure as a 2-row GridSpec (map row, footer row) inside an outer bordered
page. The footer splits into legend / scale bar / CRS / date-author-copyright+logo
panels. `mapmaker/elements.py` holds the reusable chrome: graticule/ticks, north
arrow, scale bar, inset map, footer panels. `mapmaker/cli.py` is the installed
`mapmaker` console command (see Packaging above); the repo-root `main.py` is a thin
wrapper around it for running from a source checkout without installing.
