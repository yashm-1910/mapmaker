"""Configuration loading: YAML on top of sane defaults, with `base:` inheritance."""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Built-in defaults. Any field omitted from a user's YAML falls back to this.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    "map_type": None,  # "wind_farms" | "turbines" | "grid_cells"
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
        "logo_path": "",
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
        "alpha": 1.0,
        "headers": {"User-Agent": "mapmaker-tuhh/1.0 (contact: replace-with-your-email)"},
    },
    "graticule": {
        "show": True,
        "n_ticks": 5,               # tick/cross density per axis
        "format": "decimal",        # "decimal" | "dms"
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
    "footer": {
        "show": True,
        "height_fraction": 0.09,  # keep the footer band close to the bottom border
        "column_widths": [1.0, 1.3, 1.4, 2.1],  # legend | scale bar | CRS | date-author-copyright+logo
        "fontsize": 8,
        "text_color": "0.15",
    },
    "export": {
        "output_dir": "output",
        "filename": "map.png",
        "transparent": False,
    },
    "data": {
        "wind_farms_file": "data/wind_farms.xlsx",
        "turbines_file": "data/turbines.xlsx",
        "grid_cells_file": "data/grid_cells.xlsx",
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


def load_yaml(path: str | Path) -> dict:
    """Read a YAML file into a plain dict (empty dict if the file has no content)."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_merged_dict(path: str | Path) -> dict:
    """Load one config file, recursively merging in its `base:` config (if any) and DEFAULTS."""
    path = Path(path)
    raw = load_yaml(path)
    base_name = raw.pop("base", None)
    merged = copy.deepcopy(DEFAULTS)
    if base_name:
        base_path = path.parent / base_name
        merged = deep_merge(merged, _load_merged_dict(base_path))
    merged = deep_merge(merged, raw)
    return merged


def resolve_date(cfg: dict) -> dict:
    """Replace cfg["date"] with today's date (in place) if it's unset or "auto"."""
    if cfg.get("date") in (None, "auto", ""):
        cfg["date"] = dt.date.today().isoformat()
    return cfg


def load_config(path: str | Path) -> dict:
    """Load a map config YAML, merged with any `base:` config and the built-in defaults."""
    path = Path(path)
    cfg = _load_merged_dict(path)
    cfg = resolve_date(cfg)
    cfg["_config_dir"] = str(path.parent)
    return cfg


def resolve_path(cfg: dict, p: str | Path | None) -> Path | None:
    """Resolve a possibly-relative path against the directory of the loaded config file."""
    if not p:
        return None
    pp = Path(p)
    if pp.is_absolute():
        return pp
    return Path(cfg.get("_config_dir", ".")) / pp
