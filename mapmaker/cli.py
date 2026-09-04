"""CLI entry point for mapmaker.

Installed as the `mapmaker` console script (see pyproject.toml's
`[project.scripts]`), so once the package is installed this works from any
directory:

    mapmaker --file data/mapmaker.xlsx
    mapmaker --file data/mapmaker.xlsx --map-type turbines

Running from a source checkout without installing works the same way via the
thin wrapper at the repo root: `python main.py --file ...`.
"""
from __future__ import annotations

import argparse
import sys

from mapmaker import config as config_mod
from mapmaker.render import build_grid_map, build_turbine_map, build_wind_farm_map

BUILDERS = {
    "wind_farms": build_wind_farm_map,
    "turbines": build_turbine_map,
    "grid_cells": build_grid_map,
}


def main() -> None:
    """Parse CLI args and render one map per data sheet present in the workbook."""
    parser = argparse.ArgumentParser(
        description="Generate QGIS-style maps from a single Excel workbook (data + config sheets)."
    )
    parser.add_argument("--file", required=True, help="Path to the mapmaker workbook (.xlsx)")
    parser.add_argument(
        "--map-type", choices=list(BUILDERS), default=None,
        help="Render only this map type (default: every data sheet present in the workbook)",
    )
    args = parser.parse_args()

    configs = config_mod.load_workbook_configs(args.file)
    if not configs:
        sys.exit(
            f"{args.file} has none of the expected data sheets "
            f"({', '.join(config_mod.MAP_TYPES)}); nothing to render."
        )

    map_types = [args.map_type] if args.map_type else list(configs)
    for map_type in map_types:
        cfg = configs.get(map_type)
        if cfg is None:
            sys.exit(f"{args.file} has no '{map_type}' sheet.")
        # `enabled` (a config row, e.g. scope=turbines, key=enabled, value=false) lets a
        # map type's data/config stay in the workbook without being rendered every run --
        # only honored for the "render everything present" default; an explicit
        # --map-type always renders regardless, since that's a direct request.
        if not args.map_type and not cfg.get("enabled", True):
            print(f"Skipped (enabled=false): {map_type}")
            continue
        out = BUILDERS[map_type](cfg)
        for p in out if isinstance(out, list) else [out]:
            print(f"Saved: {p}")


if __name__ == "__main__":
    main()
