"""CLI entry point for mapmaker.

Usage:
    python main.py --config configs/wind_farms.yaml
    python main.py --config configs/turbines.yaml
    python main.py --config configs/grid_cells.yaml
    python main.py --batch configs/batch.yaml
"""
from __future__ import annotations

import argparse
import sys

from mapmaker import config as config_mod
from mapmaker.batch import run_batch
from mapmaker.render import build_grid_map, build_turbine_map, build_wind_farm_map

BUILDERS = {
    "wind_farms": build_wind_farm_map,
    "turbines": build_turbine_map,
    "grid_cells": build_grid_map,
}


def main() -> None:
    """Parse CLI args and dispatch to either a single map render or a batch run."""
    parser = argparse.ArgumentParser(description="Generate QGIS-style maps from Excel data and YAML config.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", help="Path to a single map config YAML")
    group.add_argument("--batch", help="Path to a batch config YAML")
    args = parser.parse_args()

    if args.batch:
        run_batch(args.batch)
        return

    cfg = config_mod.load_config(args.config)
    map_type = cfg.get("map_type")
    builder = BUILDERS.get(map_type)
    if not builder:
        sys.exit(f"Config {args.config} is missing a valid map_type (got {map_type!r}); "
                  f"expected one of {list(BUILDERS)}")
    out = builder(cfg)
    for p in out if isinstance(out, list) else [out]:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()
