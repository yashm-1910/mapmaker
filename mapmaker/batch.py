"""Run several map configs, with per-job overrides, from one batch YAML file."""
from __future__ import annotations

from pathlib import Path

from . import config as config_mod
from .render import build_grid_map, build_turbine_map, build_wind_farm_map

BUILDERS = {
    "wind_farms": build_wind_farm_map,
    "turbines": build_turbine_map,
    "grid_cells": build_grid_map,
}


def run_batch(batch_path: str | Path) -> list[Path]:
    """Run every job listed in a batch YAML (each job's own config + overrides), in order.

    Each job needs a `config:` path (relative to `batch_path`) and may include an
    `overrides:` mapping deep-merged on top of that config. Prints one line per job as
    it completes and returns the list of output PNG paths, in job order.
    """
    batch_path = Path(batch_path)
    raw = config_mod.load_yaml(batch_path)
    jobs = raw.get("jobs", [])
    if not jobs:
        raise ValueError(f"No 'jobs' found in batch config {batch_path}")

    results = []
    for i, job in enumerate(jobs):
        cfg_path = batch_path.parent / job["config"]
        cfg = config_mod.load_config(cfg_path)
        overrides = job.get("overrides", {})
        cfg = config_mod.deep_merge(cfg, overrides)
        cfg = config_mod.resolve_date(cfg)

        map_type = cfg.get("map_type")
        builder = BUILDERS.get(map_type)
        if not builder:
            raise ValueError(f"Job {i} ({cfg_path}): unknown/missing map_type={map_type!r}")

        out = builder(cfg)
        label = job.get("name", cfg_path.stem)
        print(f"[batch {i + 1}/{len(jobs)}] {label} -> {out}")
        results.append(out)

    return results
