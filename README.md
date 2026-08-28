# mapmaker

QGIS print-layout-style, YAML-configured map generator for wind energy datasets.
Landscape PNGs on a white page, framed by an outer border with uniform margins:
the map (basemap + data + graticule + north arrow + inset overview) fills the
frame; legend, scale bar, CRS label, and author/date/copyright sit in a
dedicated footer strip below the frame, so nothing ever overlaps the map.

## Map types

1. **Wind farm locations** (`map_type: wind_farms`) — point map of farms, colored
   by status, sized by capacity.
2. **Turbine positions** (`map_type: turbines`) — turbine layout within one farm,
   uniform-colored points with ID labels.
3. **ERA5 / MERRA-2 grid cells** (`map_type: grid_cells`) — plain diamond points
   at each cell center, one color per dataset (no filled grid polygons).

Point marker shape (`style.marker`, any matplotlib marker code) and size are
configurable per map; defaults are round points for wind farms/turbines and
diamonds for the reanalysis grids.

## Setup

Requires Python 3.10+. From the project root:

```bash
python -m venv .venv

# activate it:
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows (cmd.exe)
.venv\Scripts\Activate.ps1       # Windows (PowerShell)

pip install -r requirements.txt
python scripts/generate_test_data.py   # writes data/*.xlsx + assets/logo.png
```

(Already have a virtualenv, conda env, or other Python set up? Just `pip install
-r requirements.txt` into it and skip the `venv` step.)

## Run

```bash
python main.py --config configs/wind_farms.yaml
python main.py --config configs/turbines.yaml
python main.py --config configs/grid_cells.yaml
python main.py --batch  configs/batch.yaml
```

Outputs land in `output/`.

## Data (Excel)

Only the **required** columns need to be present; anything else in the sheet is read but
ignored unless it matches one of the **optional** columns below.

- `data/wind_farms.xlsx` — required: `name, lon, lat`. Optional: `capacity_mw` (marker
  sizing, `style.size_field`), `status` (per-category coloring, `style.status_colors`).
- `data/turbines.xlsx` — required: `turbine_id, lon, lat`, plus `farm_name` if you filter
  by `data.selected_farm`. Other columns (hub height, rotor diameter, capacity, ...) are
  fine to include for your own records but nothing currently renders them.
- `data/grid_cells.xlsx` — required: `dataset, cell_id, lon, lat` (one row per grid cell
  center; cells render as plain diamond points, not filled polygons, so no cell-boundary
  columns are needed). The wind farm a grid map is centered on is *not* read from this
  file — see `reference_point` below.

See `mapmaker/data_io.py` for the exact column contract each `read_*` function enforces.

## Configuration (YAML)

`configs/default.yaml` documents every option (author, date, OSM attribution,
company logo, CRS, basemap provider, graticule/tick density, legend, scale
bar, compass-rose north arrow, inset map with zoom-out + ROI bounding box,
footer layout, export). A specific config sets `base: default.yaml` and a
`map_type`, then only overrides what it needs — see `configs/wind_farms.yaml`,
`turbines.yaml`, `grid_cells.yaml`. `configs/batch.yaml` shows running several
jobs (e.g. one turbine map per farm) in a single command, each with its own
overrides.

`title` / `subtitle` are omitted from the default configs on purpose: if a
config doesn't set them, no title is drawn and the map reclaims that vertical
space — set them explicitly per config/job when you want one.

## Layout notes

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
  controls how tall the footer band is (default `0.09`; the wind-farm map's
  3-entry legend is the tallest content across the demo configs and is what
  sets the practical floor — go lower only if your legends/text are shorter),
  and `footer.column_widths` (default `[1.0, 1.3, 1.4, 2.1]`) controls the
  relative width of the legend / scale bar / CRS / date-author-copyright+logo
  columns. All four columns bottom-align to the page's bottom border, like a
  row of footnotes — any leftover slack ends up as space above the footer
  content (next to the map), not as a trailing empty strip below it.
- **Every chrome element can be switched off independently**: `basemap.show`,
  `graticule.show`, `legend.show`, `scalebar.show`, `north_arrow.show`,
  `inset_map.show`, and `footer.show` are all `true`/`false` toggles — e.g.
  set `inset_map.show: false` in a config/override to drop the overview inset
  entirely with no other changes needed.
- **North arrow and the inset overview map sit inside the map frame**, each in
  a configurable corner (`north_arrow.location`, `inset_map.location`). Being
  opaque, whichever corner they occupy visually covers any data underneath —
  same as in QGIS. Point labels are nudged away from the inset's corner
  automatically, but the point marker itself can still be covered if it falls
  deep inside that corner. Pick a corner that's empty for your dataset (see
  the comments in `configs/wind_farms.yaml` and `configs/turbines.yaml`,
  which both do this); for data that fills its whole bounding box (e.g. a
  full turbine grid or a wall-to-wall reanalysis grid), add extra
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
  sides of the frame, matching a classic QGIS print-layout grid.
- **`reference_point` (grid_cells maps only)** marks the wind farm an ERA5/MERRA2
  comparison is centered on: a single named circle point, e.g.
  ```yaml
  reference_point:
    show: true
    name: "Nordsee Alpha"
    lon: 6.35
    lat: 54.65
  ```
  Its coordinates come from the config, not `grid_cells.xlsx` (it isn't part of the
  reanalysis grid, so it doesn't belong in that data file). `show: false` (the default)
  omits it entirely; `marker`, `color`, `size`, `label_fontsize` are all overridable. It's
  included in the map's extent calculation, so the frame adjusts to keep it visible even
  if it sits near the edge of the grid.

## Footer metadata

The rendered footer currently shows only what was asked for: **author,
date, copyright (OSM attribution), and coordinate reference system** — plus
the legend and scale bar. The plumbing for more supports it without any code
changes needed:

- **`cfg["notes"]`** (a YAML list under the top level, default `[]`) — any
  strings here are appended to the date/author/copyright block. E.g.:
  ```yaml
  notes:
    - "Internal draft -- not for distribution"
  ```
- **`extra_footer_lines`** — `_finalize()` in `mapmaker/render.py` and
  `elements.add_footer()` both already accept an `extra_footer_lines` /
  `extra_lines` list. Each `build_*` function in `render.py` has a comment
  showing where stats like farm count, turbine count, or total capacity used
  to be assembled (`extra = [...]`) before being passed through; reinstate
  that pattern for any per-map dataset stats you want back in the footer.
- **`company.name`** — set in config but intentionally not rendered as text
  right now (only `company.logo_path` shows, as the logo image). Add a line
  for it in `elements.add_footer`'s `lines` list if you want the company name
  spelled out as well as shown via the logo.

## Basemap notes

- Default provider is `OpenStreetMap.Mapnik`. Their tile server enforces a
  usage policy requiring a descriptive `User-Agent` (set under
  `basemap.headers`) — without one it silently serves a "blocked" placeholder
  tile instead of erroring. Replace the contact email in that header with
  your own before heavy/production use.
- Swap `basemap.provider` to any dotted path into `contextily.providers`
  (e.g. `CartoDB.Positron`, `Esri.WorldGrayCanvas`) for a different look.

## Code layout

`mapmaker/render.py` builds each figure as a 2-row GridSpec (map row, footer
row) inside an outer bordered page. The footer splits into legend / scale bar
/ CRS / date-author-copyright+logo panels. `mapmaker/elements.py` holds the
reusable chrome: graticule/ticks, north arrow, scale bar, inset map, footer
panels.
