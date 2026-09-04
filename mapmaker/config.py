"""Configuration loading: built-in defaults, overridden by the `config` sheet of a
single mapmaker workbook (see `load_workbook_configs`). No YAML files involved --
one Excel workbook (data sheets + a `config` sheet) is sufficient for everything.
"""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd

MAP_TYPES = ["wind_farms", "turbines", "grid_cells"]

# Bundled inside the package itself (mapmaker/assets/logo.png) rather than resolved
# relative to a workbook's own directory -- this is what makes `company.logo_path`
# work out of the box for a pip/conda install, where the only thing guaranteed to
# exist next to mapmaker's own code is mapmaker's own package directory, not
# whatever folder a user's workbook happens to live in. Computed from __file__
# (not importlib.resources) since a plain on-disk PNG next to the package's Python
# files works identically whether run from source or from an installed (unzipped)
# wheel -- no need for the more involved resource-loading API this doesn't require.
DEFAULT_LOGO_PATH = str(Path(__file__).resolve().parent / "assets" / "logo.png")

# Friendly display names for the settings sheets' scope column -- purely cosmetic;
# `MAP_TYPES` above (and data-sheet tab names, --map-type, output filenames) stay the
# internal wind_farms/turbines/grid_cells identifiers everywhere else in the code.
MAP_TYPE_LABELS: dict[str, str] = {
    "wind_farms": "Portfolio Map",
    "turbines": "Turbine Map",
    "grid_cells": "ERA5/MERRA2 Map",
}
_LABEL_TO_MAP_TYPE: dict[str, str] = {label.lower(): mt for mt, label in MAP_TYPE_LABELS.items()}

# ---------------------------------------------------------------------------
# Built-in defaults. Any setting not present in the workbook's `config` sheet
# falls back to this.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    "map_type": None,  # "wind_farms" | "turbines" | "grid_cells"
    "enabled": True,  # set false (per map type, via a scoped row) to skip rendering it entirely
    "author": "Unknown Author",
    "date": "auto",  # "auto" -> today's date, or an explicit string
    "title": "",
    "subtitle": "",
    "notes": [],  # extra free-text lines shown in the footer
    "attribution": {
        "text": "© OpenStreetMap (OSM)",
    },
    "company": {
        "name": "",
        # Defaults to mapmaker's own bundled placeholder logo (see DEFAULT_LOGO_PATH
        # above) so the footer always has something sensible to show out of the box.
        # Set a `company.logo_path` row to point at your own logo instead -- relative
        # paths resolve against the workbook's own directory (see resolve_path
        # below), or use an absolute path. Set it to an explicitly blank value to
        # turn the logo off entirely rather than falling back to the bundled one.
        "logo_path": DEFAULT_LOGO_PATH,
        "logo_scale": 1.0,  # multiplier on the logo's base footer size, anchored bottom-right
    },
    "map": {
        "crs": "EPSG:4326",
        "figsize": [13, 8],  # landscape; the map panel's aspect drives extent padding, see render.py
        "dpi": 300,
        "background_color": "white",
        "padding_fraction": 0.12,
        "extent": None,  # [xmin, xmax, ymin, ymax] override; else derived from data
    },
    "basemap": {
        "show": True,
        # OpenStreetMap's tile.openstreetmap.org enforces a usage policy that requires
        # a descriptive, non-anonymous User-Agent (see `headers` below) -- without one,
        # requests get a "blocked" placeholder tile instead of an HTTP error.
        # Swap `provider` to any dotted path into contextily.providers, e.g.
        # "CartoDB.Positron" or "Esri.WorldGrayCanvas", for a more muted basemap look.
        "provider": "OpenStreetMap.Mapnik",
        "zoom": "auto",
        # Bumps the auto-computed tile zoom level up by this many levels, fetching
        # sharper/more-detailed tiles for the same extent (each +1 roughly doubles
        # tile resolution in each dimension). 0 = contextily's own auto choice.
        "zoom_adjust": 1,
        "alpha": 1.0,
        "headers": {"User-Agent": "mapmaker-tuhh/1.0 (contact: replace-with-your-email)"},
        # matplotlib's imshow resampling used when the (fixed-resolution) basemap tiles are
        # scaled up to the map panel's print size -- "bilinear" is the safe default; try
        # "lanczos" for crisper-looking tile text/lines (at the cost of possible ringing
        # artifacts on hard edges). Raising zoom_adjust helps more than this does, since it
        # fetches genuinely more detailed tiles instead of just resampling the same ones.
        "interpolation": "bilinear",
        # contextily passes this straight to `requests.get(..., timeout=...)`; without it,
        # a tile server that's slow, rate-limiting, or silently dropping requests (some
        # providers -- notably OpenTopoMap -- throttle or block traffic from datacenter/cloud
        # IP ranges) hangs the whole render indefinitely instead of failing over to a flat
        # fill. Seconds per tile request; lower it for faster failover, raise it on a slow link.
        "timeout": 15,
    },
    "graticule": {
        "show": True,
        "n_ticks": 5,               # tick/cross density, shared fallback for both axes
        "n_ticks_x": None,          # horizontal (longitude) tick density; None -> falls back to n_ticks
        "n_ticks_y": None,          # vertical (latitude) tick density; None -> falls back to n_ticks
        "format": "decimal",        # "decimal" | "dms"
        "hemisphere_labels": True,  # e.g. "5.90°E" vs "5.90°" (sign kept for W/S) if False
        "fontsize": 10,
        "color": "0.35",
        "linewidth": 0.6,
        "frame": True,
    },
    # Legend now renders outside the map, in its own footer panel -- it never
    # overlaps map content regardless of how many entries it has.
    "legend": {
        "show": True,
        "title": "Legend",
    },
    # Scale bar also renders outside the map, in its own footer panel, sized from
    # the map's true printed scale. `length_fraction` is the fraction of that
    # footer panel's width the bar should roughly target before rounding to a
    # nice number.
    "scalebar": {
        "show": True,
        "units": "auto",  # "auto" | "m" | "km"
        "length_fraction": 0.55,
    },
    "north_arrow": {
        "show": True,
        "location": "lower right",
        "size": 0.045,
    },
    "inset_map": {
        "show": True,
        "location": "lower left",
        "size": 0.28,
        "zoom_out_factor": 8,
        "bbox_edgecolor": "red",
        "bbox_linewidth": 2.2,
        "min_bbox_frac": 0.05,  # ROI box is floored to this fraction of the inset's width/height
    },
    # Optional single reference point (e.g. the wind farm a grid_cells map's ERA5/MERRA2
    # comparison is centered on), sourced from config -- not from the grid data sheet,
    # since it's one point rather than part of the reanalysis grid. Only used by
    # map_type: grid_cells; ignored otherwise. See render.py::build_grid_map.
    "reference_point": {
        "show": False,
        "name": "",
        "lon": None,
        "lat": None,
        "marker": "o",
        "color": "#d62728",
        "size": 70,
        "label_fontsize": 9,
    },
    "footer": {
        "show": True,
        "height_fraction": 0.09,  # keep the footer band close to the bottom border
        "column_widths": [1.0, 1.3, 1.4, 2.1],  # legend | scale bar | CRS | date-author-copyright+logo
        "fontsize": 8,
        "text_color": "0.15",
    },
    "export": {
        "output_dir": "../output",  # relative to the workbook's own directory, e.g. data/mapmaker.xlsx -> output/
        "filename": "",  # empty -> defaults to "<map_type>.png" (see render.py)
        "transparent": False,
    },
    "data": {
        "selected_farm": None,
        "selected_datasets": None,
    },
    "style": {},
}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` onto a deep copy of `base`."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_scalar(raw: Any) -> Any:
    """Coerce one raw `config` sheet cell value into a Python bool/int/float/None/list/str."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw
    text = str(raw).strip()
    low = text.lower()
    if low in ("", "none", "null"):
        return None
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if "," in text:
        return [_parse_scalar(part) for part in text.split(",")]
    return text


def _set_dotted(target: dict, dotted_key: str, value: Any) -> None:
    """Set `target["a"]["b"]["c"] = value` for a dotted key `"a.b.c"`, creating dicts as needed."""
    parts = [p.strip() for p in dotted_key.split(".") if p.strip()]
    if not parts:
        return
    node = target
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def resolve_date(cfg: dict) -> dict:
    """Replace cfg["date"] with today's date (in place) if it's unset or "auto"."""
    if cfg.get("date") in (None, "auto", ""):
        cfg["date"] = dt.date.today().isoformat()
    return cfg


# Sheet names read as config/settings sheets, in this order (later ones can override
# earlier ones on a literal key clash, though in the shipped layout they're disjoint
# by convention -- "settings_basic" for what you'd tweak often, "settings_advanced" for
# fine-tuning knobs you'd rarely touch; "config" is accepted too for a single-sheet
# workbook or backward compatibility with an older one).
CONFIG_SHEET_NAMES = ["config", "settings_basic", "settings_advanced"]


def load_workbook_configs(path: str | Path) -> dict[str, dict]:
    """Build one merged config dict per map type that has a matching data sheet in the
    workbook (`wind_farms`, `turbines`, `grid_cells`), read from whichever of
    `CONFIG_SHEET_NAMES` are present. Each such sheet has the same three columns (a
    fourth, `description`, is allowed and ignored by the parser -- it's there purely
    for a human reading the workbook): `Map` (blank/`*` = applies to every map type, or
    a friendly map name from `MAP_TYPE_LABELS` -- e.g. "Portfolio Map" -- to override
    just that one; the internal wind_farms/turbines/grid_cells identifiers are also
    accepted for backward compatibility, as is the older `scope` column header), `key`
    (a dotted path into the settings, e.g. `footer.height_fraction`, `style.marker_size`),
    and `value`.

    Returns a dict {map_type: cfg}, in `MAP_TYPES` order, for whichever map types are
    present -- including one whose `enabled` setting resolves to `False`; the caller
    (see main.py) is responsible for skipping those rather than this function omitting
    them, so a disabled map type's config is still inspectable/loadable. Each cfg has
    `_workbook_path` / `_config_dir` set for resolving other relative paths (e.g.
    `company.logo_path`) against the workbook's own directory.
    """
    path = Path(path)
    xl = pd.ExcelFile(path)

    global_overrides: dict = {}
    scoped_overrides: dict[str, dict] = {mt: {} for mt in MAP_TYPES}
    for sheet_name in CONFIG_SHEET_NAMES:
        if sheet_name not in xl.sheet_names:
            continue
        cfg_df = pd.read_excel(path, sheet_name=sheet_name)
        for _, row in cfg_df.iterrows():
            key = row.get("key")
            if key is None or (isinstance(key, float) and pd.isna(key)) or not str(key).strip():
                continue
            value = _parse_scalar(row.get("value"))
            scope = row.get("Map")
            if scope is None or (isinstance(scope, float) and pd.isna(scope)):
                scope = row.get("scope")  # older/single-sheet workbooks
            scope = str(scope).strip() if scope is not None and not pd.isna(scope) else ""
            scope = _LABEL_TO_MAP_TYPE.get(scope.lower(), scope)
            target = scoped_overrides[scope] if scope in scoped_overrides else global_overrides
            _set_dotted(target, str(key).strip(), value)

    configs: dict[str, dict] = {}
    for map_type in MAP_TYPES:
        if map_type not in xl.sheet_names:
            continue
        cfg = copy.deepcopy(DEFAULTS)
        cfg = deep_merge(cfg, global_overrides)
        cfg = deep_merge(cfg, scoped_overrides[map_type])
        cfg["map_type"] = map_type
        cfg = resolve_date(cfg)
        cfg["_workbook_path"] = str(path)
        cfg["_config_dir"] = str(path.parent)
        configs[map_type] = cfg
    return configs


def resolve_path(cfg: dict, p: str | Path | None) -> Path | None:
    """Resolve a possibly-relative path (e.g. a logo or output dir) against the workbook's directory."""
    if not p:
        return None
    pp = Path(p)
    if pp.is_absolute():
        return pp
    return Path(cfg.get("_config_dir", ".")) / pp
