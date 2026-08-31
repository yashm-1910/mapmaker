"""Read map input data from the mapmaker workbook's sheets into GeoDataFrames."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def read_wind_farms(path: str | Path) -> gpd.GeoDataFrame:
    """Load wind farm point locations from the workbook's `wind_farms` sheet.

    Required columns: name, lon, lat.
    Optional columns (used if present, ignored otherwise): capacity_mw (marker sizing,
    see style.size_field), status (per-category coloring, see style.status_colors).
    Any other columns (e.g. country) are read but not used for rendering.
    Returns a GeoDataFrame of Point geometries in EPSG:4326.
    """
    df = pd.read_excel(path, sheet_name="wind_farms")
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def read_turbines(path: str | Path, farm_name: str | None = None) -> gpd.GeoDataFrame:
    """Load turbine point locations from the workbook's `turbines` sheet, optionally
    filtered to one farm.

    Required columns: turbine_id, lon, lat, and farm_name (only if `farm_name` is passed).
    Any other columns (e.g. hub_height_m, rotor_diameter_m, capacity_mw) are read but not
    used for rendering.
    Returns a GeoDataFrame of Point geometries in EPSG:4326.

    Raises ValueError if `farm_name` is given but matches no rows.
    """
    df = pd.read_excel(path, sheet_name="turbines")
    if farm_name:
        df = df[df["farm_name"] == farm_name].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No turbines found for farm_name={farm_name!r} in {path}")
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


REFERENCE_DATASET = "reference"  # sentinel `dataset` value marking a reference-point row


def _is_reference_row(dataset_col: pd.Series) -> pd.Series:
    """True where `dataset` marks a reference-point row rather than a real grid cell."""
    return dataset_col.astype(str).str.strip().str.lower() == REFERENCE_DATASET


def read_grid_cells(
    path: str | Path, datasets: list[str] | None = None, farm_name: str | None = None
) -> gpd.GeoDataFrame:
    """Load reanalysis grid cell center points from the workbook's `grid_cells` sheet,
    optionally filtered by dataset and/or farm.

    Required columns: dataset, cell_id, lon, lat, plus farm_name (only if `farm_name` is
    passed) -- an optional column grouping cells into per-location comparisons, e.g. one
    ERA5/MERRA2 subgrid per wind farm; see render.py::build_grid_map for the auto-split
    behavior when more than one farm_name is present. Cells are rendered as plain diamond
    points (no filled grid polygons), so only the cell center coordinate is needed.

    Rows with `dataset` == "reference" are reference points (see `read_grid_reference_point`),
    not plotted grid cells, and are always excluded here regardless of `datasets`.
    Returns a GeoDataFrame of Point geometries in EPSG:4326.

    Raises ValueError if `datasets`/`farm_name` are given but match no rows.
    """
    df = pd.read_excel(path, sheet_name="grid_cells")
    df = df[~_is_reference_row(df["dataset"])].reset_index(drop=True)
    if datasets:
        df = df[df["dataset"].isin(datasets)].reset_index(drop=True)
    if farm_name:
        df = df[df["farm_name"] == farm_name].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No grid cells found for datasets={datasets!r}, farm_name={farm_name!r} in {path}")
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def read_grid_reference_point(path: str | Path, farm_name: str | None = None) -> dict | None:
    """Look up one named reference point from the `grid_cells` sheet's `dataset` == "reference"
    rows, e.g. the wind farm an ERA5/MERRA2 comparison is centered on.

    A reference row shares the sheet's usual columns (farm_name, dataset, lon, lat); its own
    `farm_name` doubles as the point's label, so no separate name column is needed -- put a row
    like `farm_name=Nordsee Alpha, dataset=reference, lon=6.35, lat=54.65` alongside that farm's
    ERA5/MERRA2 rows. If `farm_name` is given, only a reference row for that farm matches; if
    `farm_name` is None (a workbook with no per-farm split), the first reference row found is
    used regardless of its own farm_name.

    Returns `{"name": ..., "lon": ..., "lat": ...}`, or `None` if no matching row exists (the
    caller then falls back to `cfg["reference_point"]`'s own `name`/`lon`/`lat`, if any -- see
    render.py::build_grid_map).
    """
    df = pd.read_excel(path, sheet_name="grid_cells")
    if "dataset" not in df.columns:
        return None
    ref_rows = df[_is_reference_row(df["dataset"])]
    if farm_name is not None and "farm_name" in ref_rows.columns:
        ref_rows = ref_rows[ref_rows["farm_name"] == farm_name]
    if ref_rows.empty:
        return None
    row = ref_rows.iloc[0]
    name = row.get("farm_name") if "farm_name" in ref_rows.columns else None
    return {
        "name": None if pd.isna(name) else name,
        "lon": float(row["lon"]),
        "lat": float(row["lat"]),
    }
