"""Read map input data from Excel workbooks into GeoDataFrames."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def read_wind_farms(path: str | Path) -> gpd.GeoDataFrame:
    """Load wind farm point locations from an Excel workbook.

    Required columns: name, lon, lat.
    Optional columns (used if present, ignored otherwise): capacity_mw (marker sizing,
    see style.size_field), status (per-category coloring, see style.status_colors).
    Any other columns (e.g. country) are read but not used for rendering.
    Returns a GeoDataFrame of Point geometries in EPSG:4326.
    """
    df = pd.read_excel(path)
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def read_turbines(path: str | Path, farm_name: str | None = None) -> gpd.GeoDataFrame:
    """Load turbine point locations from an Excel workbook, optionally filtered to one farm.

    Required columns: turbine_id, lon, lat, and farm_name (only if `farm_name` is passed).
    Any other columns (e.g. hub_height_m, rotor_diameter_m, capacity_mw) are read but not
    used for rendering.
    Returns a GeoDataFrame of Point geometries in EPSG:4326.

    Raises ValueError if `farm_name` is given but matches no rows.
    """
    df = pd.read_excel(path)
    if farm_name:
        df = df[df["farm_name"] == farm_name].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No turbines found for farm_name={farm_name!r} in {path}")
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def read_grid_cells(path: str | Path, datasets: list[str] | None = None) -> gpd.GeoDataFrame:
    """Load reanalysis grid cell center points from an Excel workbook, optionally filtered by dataset.

    Required columns: dataset, cell_id, lon, lat. Cells are rendered as plain diamond
    points (no filled grid polygons), so only the cell center coordinate is needed --
    see render.py::build_grid_map.
    Returns a GeoDataFrame of Point geometries in EPSG:4326.

    Raises ValueError if `datasets` is given but matches no rows.
    """
    df = pd.read_excel(path)
    if datasets:
        df = df[df["dataset"].isin(datasets)].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No grid cells found for datasets={datasets!r} in {path}")
    geometry = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
