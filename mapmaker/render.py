"""Build the three map types: wind farm locations, turbine positions, ERA5/MERRA2 grid cells."""
from __future__ import annotations

import math
import warnings
from pathlib import Path

import contextily as cx
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from shapely.geometry import Point

from . import config as config_mod
from . import data_io
from . import elements

# ---------------------------------------------------------------------------
# Shared figure / layout plumbing
# ---------------------------------------------------------------------------
#
# Page layout, like a QGIS print-layout page:
#
#   canvas edge --OUTER_MARGIN_IN--> outer border rectangle --SIDE_PAD_IN--> content
#
# All margins are defined in *inches* (not figure-fraction) and converted to
# fractions per-axis from the actual figsize, so a landscape figure (wider
# than tall) still gets an equal ABSOLUTE margin on every side -- the same
# fraction on a wider vs. taller dimension would otherwise produce unequal
# margins. OUTER_MARGIN_IN is identical on all four sides; SIDE_PAD_IN too,
# except the map's own top edge shrinks further to make room for an optional
# title -- the title then sits in that reclaimed band, still SIDE_PAD_IN below
# the border's top. The bottom uses a smaller BOTTOM_PAD_IN instead, so footer
# content sits close to the bottom border rather than leaving a tall blank
# strip beneath it.

OUTER_MARGIN_IN = 0.08
SIDE_PAD_IN = 0.42
BOTTOM_PAD_IN = 0.16
TITLE_BAND_IN = 0.45


def _page_margins(figsize: list[float]) -> dict[str, float]:
    """Convert the fixed inch-based page margins (OUTER_MARGIN_IN etc.) into the figure-fraction
    left/right/top/bottom values `_new_figure`'s GridSpec needs for this specific `figsize`, so the
    margins are equal in absolute terms regardless of the figure's aspect ratio."""
    fig_w, fig_h = figsize
    outer_x, outer_y = OUTER_MARGIN_IN / fig_w, OUTER_MARGIN_IN / fig_h
    side_x, side_y = SIDE_PAD_IN / fig_w, SIDE_PAD_IN / fig_h
    return {
        "left": outer_x + side_x,
        "right": 1 - (outer_x + side_x),
        "bottom": outer_y + BOTTOM_PAD_IN / fig_h,
        "top_no_title": 1 - (outer_y + side_y),
        "top_with_title": 1 - (outer_y + side_y) - TITLE_BAND_IN / fig_h,
        "outer_x": outer_x,
        "outer_y": outer_y,
    }


def _add_page_border(fig, figsize: list[float]) -> None:
    """Draw the thin outer rectangle framing the whole page, `OUTER_MARGIN_IN` inside the canvas edge."""
    m = _page_margins(figsize)
    fig.add_artist(Rectangle(
        (m["outer_x"], m["outer_y"]), 1 - 2 * m["outer_x"], 1 - 2 * m["outer_y"],
        transform=fig.transFigure, fill=False, edgecolor="black", linewidth=1.1, zorder=20,
    ))


def _new_figure(cfg: dict):
    """Create the figure and its map/footer GridSpec row(s) for one map render.

    Returns (fig, ax_map, footer_gs, target_aspect), where footer_gs is None if the footer
    is disabled, and target_aspect is the map row's width/height ratio in inches -- used by
    `_compute_extent` so the data extent fills the panel without large empty side margins.
    """
    figsize = cfg["map"].get("figsize", [13, 8])
    dpi = cfg["map"].get("dpi", 300)
    footer_cfg = cfg.get("footer", {})
    footer_frac = footer_cfg.get("height_fraction", 0.09) if footer_cfg.get("show", True) else 0.0
    has_title = bool(cfg.get("title")) or bool(cfg.get("subtitle"))
    m = _page_margins(figsize)
    top = m["top_with_title"] if has_title else m["top_no_title"]

    fig = plt.figure(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor(cfg["map"].get("background_color", "white"))

    if footer_frac > 0:
        gs = fig.add_gridspec(
            2, 1, height_ratios=[1 - footer_frac, footer_frac], hspace=0.06,
            left=m["left"], right=m["right"], top=top, bottom=m["bottom"],
        )
        ax_map = fig.add_subplot(gs[0])
        footer_gs = gs[1]
        map_row_frac = (1 - footer_frac)
    else:
        gs = fig.add_gridspec(1, 1, left=m["left"], right=m["right"], top=top, bottom=m["bottom"])
        ax_map = fig.add_subplot(gs[0])
        footer_gs = None
        map_row_frac = 1.0

    ax_map.set_facecolor(cfg["map"].get("background_color", "white"))

    map_width_in = figsize[0] * (m["right"] - m["left"])
    map_height_in = figsize[1] * (top - m["bottom"]) * map_row_frac
    target_aspect = map_width_in / map_height_in if map_height_in > 0 else 1.4

    return fig, ax_map, footer_gs, target_aspect


def _add_title(fig, cfg: dict) -> None:
    """Draw the figure title/subtitle if set in cfg; draws nothing (and reclaims the space) if not."""
    title = cfg.get("title")
    subtitle = cfg.get("subtitle")
    if title:
        fig.suptitle(title, fontsize=16, fontweight="bold", y=0.975)
    if subtitle:
        fig.text(0.5, 0.935, subtitle, ha="center", fontsize=11, color="0.2")


def _label_offset(x: float, y: float, extent: tuple[float, float, float, float], inset_cfg: dict):
    """Pick an annotation offset that steers point labels away from the inset map's corner."""
    default = ((6, 4), "left")
    if not inset_cfg.get("show", True):
        return default
    xmin, xmax, ymin, ymax = extent
    xf = (x - xmin) / ((xmax - xmin) or 1)
    yf = (y - ymin) / ((ymax - ymin) or 1)
    loc = inset_cfg.get("location", "lower left")
    margin = inset_cfg.get("size", 0.28) + 0.07
    in_inset = (
        (loc == "upper right" and xf > 1 - margin and yf > 1 - margin)
        or (loc == "upper left" and xf < margin and yf > 1 - margin)
        or (loc == "lower right" and xf > 1 - margin and yf < margin)
        or (loc == "lower left" and xf < margin and yf < margin)
    )
    if in_inset:
        return (-8, -10), "right"
    return default


def _compute_extent(gdf, cfg: dict, target_aspect: float = 1.4) -> tuple[float, float, float, float]:
    """Data bounds padded so the resulting extent's *real-world* aspect ratio matches the
    landscape figure panel -- avoids both a cropped map and large empty side margins."""
    ext = cfg["map"].get("extent")
    if ext:
        return tuple(ext)

    minx, miny, maxx, maxy = gdf.total_bounds
    lon_span = (maxx - minx) or 0.02
    lat_span = (maxy - miny) or 0.02
    mean_lat = (miny + maxy) / 2
    crs = cfg["map"]["crs"]

    if "4326" in str(crs).upper():
        x_scale = math.cos(math.radians(mean_lat))  # real km per degree of lon vs. lat
    else:
        x_scale = 1.0

    real_w = lon_span * x_scale
    real_h = lat_span
    desired_real_w = max(real_w, real_h * target_aspect)
    desired_real_h = max(real_h, real_w / target_aspect)

    desired_lon_span = desired_real_w / x_scale
    desired_lat_span = desired_real_h

    cx_, cy_ = (minx + maxx) / 2, (miny + maxy) / 2
    pad = cfg["map"].get("padding_fraction", 0.12)
    half_lon = desired_lon_span / 2 * (1 + pad)
    half_lat = desired_lat_span / 2 * (1 + pad)
    return (cx_ - half_lon, cx_ + half_lon, cy_ - half_lat, cy_ + half_lat)


def _finalize(fig, ax_map, cfg: dict, gdf_for_extent, footer_gs, target_aspect: float,
              legend_handles=None, legend_title="Legend", extra_footer_lines=None) -> Path:
    """Finish a map: set the extent, draw the basemap/graticule/north-arrow/inset/title/footer,
    save the figure to `cfg["export"]`, and return the output path. Shared by all three
    `build_*_map` functions after they've plotted their own data onto `ax_map`.
    """
    crs = cfg["map"]["crs"]
    extent = _compute_extent(gdf_for_extent, cfg, target_aspect)
    xmin, xmax, ymin, ymax = extent
    ax_map.set_xlim(xmin, xmax)
    ax_map.set_ylim(ymin, ymax)

    if "4326" in str(crs).upper():
        mean_lat = (ymin + ymax) / 2
        ax_map.set_aspect(1 / max(math.cos(math.radians(mean_lat)), 1e-6))
    else:
        ax_map.set_aspect("equal")

    basemap_cfg = cfg.get("basemap", {})
    provider = elements._resolve_provider(basemap_cfg.get("provider")) if basemap_cfg.get("show", True) else None
    if basemap_cfg.get("show", True):
        try:
            cx.add_basemap(
                ax_map, crs=crs, source=provider, zoom=basemap_cfg.get("zoom", "auto"),
                alpha=basemap_cfg.get("alpha", 1.0), attribution=False,
                headers=basemap_cfg.get("headers"),
            )
        except Exception as e:  # pragma: no cover - network dependent
            warnings.warn(f"Basemap fetch failed ({e}); continuing without a basemap.")
            ax_map.set_facecolor("#eef3f8")

    grat = cfg.get("graticule", {})
    if grat.get("show", True):
        elements.add_graticule(
            ax_map, crs, extent, n_ticks=grat.get("n_ticks", 5), fmt=grat.get("format", "decimal"),
            fontsize=grat.get("fontsize", 8), color=grat.get("color", "0.35"),
            linewidth=grat.get("linewidth", 0.6), frame=grat.get("frame", True),
        )
    else:
        ax_map.set_xticks([])
        ax_map.set_yticks([])

    na = cfg.get("north_arrow", {})
    if na.get("show", True):
        elements.add_north_arrow(ax_map, location=na.get("location", "lower right"), size=na.get("size", 0.045))

    ins = cfg.get("inset_map", {})
    if ins.get("show", True):
        elements.add_inset_map(
            ax_map, extent, crs, zoom_out_factor=ins.get("zoom_out_factor", 8),
            location=ins.get("location", "lower left"), size=ins.get("size", 0.28),
            basemap_provider=provider, bbox_edgecolor=ins.get("bbox_edgecolor", "red"),
            bbox_linewidth=ins.get("bbox_linewidth", 2.2), basemap_headers=basemap_cfg.get("headers"),
            min_bbox_frac=ins.get("min_bbox_frac", 0.05),
        )

    _add_title(fig, cfg)

    if footer_gs is not None and cfg.get("footer", {}).get("show", True):
        elements.add_footer(
            fig, footer_gs, cfg, ax_map, crs, extent, legend_handles=legend_handles,
            legend_title=legend_title, extra_lines=extra_footer_lines,
        )

    _add_page_border(fig, cfg["map"].get("figsize", [13, 8]))

    out_dir = config_mod.resolve_path(cfg, cfg["export"].get("output_dir", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / cfg["export"].get("filename", "map.png")
    fig.savefig(
        out_path, dpi=cfg["map"].get("dpi", 300), facecolor=fig.get_facecolor(),
        transparent=cfg["export"].get("transparent", False),
    )
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Map type 1: wind farm locations
# ---------------------------------------------------------------------------


def build_wind_farm_map(cfg: dict) -> Path:
    """Render the wind-farm-locations map (map_type: wind_farms) and return the saved PNG path."""
    path = config_mod.resolve_path(cfg, cfg["data"]["wind_farms_file"])
    gdf = data_io.read_wind_farms(path).to_crs(cfg["map"]["crs"])

    fig, ax, footer_gs, target_aspect = _new_figure(cfg)
    style = cfg.get("style", {})
    # `status` is an optional data column -- name/lon/lat alone are enough to plot a wind
    # farm. Without it, every point falls into one "Wind Farm" category colored `color`;
    # add a `status` column and a `style.status_colors` map to split it out by category.
    default_color = style.get("color", "#2166ac")
    status_colors = style.get("status_colors", {})
    size_field = style.get("size_field", "capacity_mw")
    base_size = style.get("base_marker_size", 45)
    size_scale = style.get("size_scale", 0.5)
    marker = style.get("marker", "o")
    legend_label = style.get("legend_label", "Wind Farm")

    status_series = gdf["status"] if "status" in gdf.columns else pd.Series([legend_label] * len(gdf))
    handles = []
    for status in sorted(status_series.unique()):
        sub = gdf[status_series == status]
        color = status_colors.get(status, default_color)
        sizes = base_size + sub[size_field] * size_scale if size_field in sub.columns else base_size
        ax.scatter(
            sub.geometry.x, sub.geometry.y, s=sizes, marker=marker, color=color, edgecolor="black",
            linewidth=0.6, alpha=0.95, zorder=6,
        )
        handles.append(Line2D([0], [0], marker=marker, color="w", markerfacecolor=color,
                               markeredgecolor="black", markersize=8, label=status))

    if style.get("label_points", True) and "name" in gdf.columns:
        label_fontsize = style.get("label_fontsize", 9)
        extent_for_labels = _compute_extent(gdf, cfg, target_aspect)
        for _, row in gdf.iterrows():
            xytext, ha = _label_offset(row.geometry.x, row.geometry.y, extent_for_labels, cfg.get("inset_map", {}))
            ax.annotate(
                str(row["name"]), (row.geometry.x, row.geometry.y), textcoords="offset points",
                xytext=xytext, ha=ha, fontsize=label_fontsize, color="0.05", zorder=7,
                path_effects=[pe.withStroke(linewidth=2.2, foreground="white")],
            )

    # Stats like farm count / total capacity can be surfaced via extra_footer_lines
    # (see _finalize / elements.add_footer) or cfg["notes"] -- left out of the
    # rendered footer for now per current design; documented in README.md.
    return _finalize(fig, ax, cfg, gdf, footer_gs, target_aspect,
                      legend_handles=handles, legend_title=cfg.get("legend", {}).get("title", "Legend"))


# ---------------------------------------------------------------------------
# Map type 2: turbine positions within a wind farm
# ---------------------------------------------------------------------------


def build_turbine_map(cfg: dict) -> Path:
    """Render the turbine-positions map (map_type: turbines) and return the saved PNG path."""
    path = config_mod.resolve_path(cfg, cfg["data"]["turbines_file"])
    farm_name = cfg["data"].get("selected_farm")
    gdf = data_io.read_turbines(path, farm_name=farm_name).to_crs(cfg["map"]["crs"])

    fig, ax, footer_gs, target_aspect = _new_figure(cfg)
    style = cfg.get("style", {})
    marker_color = style.get("color", "#2166ac")
    marker_size = style.get("marker_size", 55)
    marker = style.get("marker", "o")
    label = style.get("legend_label", "Turbine")

    ax.scatter(gdf.geometry.x, gdf.geometry.y, s=marker_size, marker=marker, color=marker_color,
               edgecolor="black", linewidth=0.6, zorder=6)
    handles = [Line2D([0], [0], marker=marker, color="w", markerfacecolor=marker_color,
                       markeredgecolor="black", markersize=8, label=label)]

    if style.get("label_points", True) and "turbine_id" in gdf.columns:
        label_fontsize = style.get("label_fontsize", 8)
        extent_for_labels = _compute_extent(gdf, cfg, target_aspect)
        for _, row in gdf.iterrows():
            xytext, ha = _label_offset(row.geometry.x, row.geometry.y, extent_for_labels, cfg.get("inset_map", {}))
            ax.annotate(
                str(row["turbine_id"]), (row.geometry.x, row.geometry.y), textcoords="offset points",
                xytext=xytext, ha=ha, fontsize=label_fontsize, color="0.05", zorder=7,
                path_effects=[pe.withStroke(linewidth=2, foreground="white")],
            )

    # Stats like farm name / turbine count / capacity can be surfaced via
    # extra_footer_lines (see _finalize / elements.add_footer) or cfg["notes"] --
    # left out of the rendered footer for now per current design; see README.md.
    return _finalize(fig, ax, cfg, gdf, footer_gs, target_aspect,
                      legend_handles=handles, legend_title=cfg.get("legend", {}).get("title", "Legend"))


# ---------------------------------------------------------------------------
# Map type 3: ERA5 / MERRA2 analysis grid cells -- plain diamond points, no
# filled grid polygons.
# ---------------------------------------------------------------------------


def build_grid_map(cfg: dict) -> Path:
    """Render the ERA5/MERRA2 grid-cells map (map_type: grid_cells) and return the saved PNG path."""
    path = config_mod.resolve_path(cfg, cfg["data"]["grid_cells_file"])
    datasets = cfg["data"].get("selected_datasets")
    gdf = data_io.read_grid_cells(path, datasets=datasets).to_crs(cfg["map"]["crs"])

    fig, ax, footer_gs, target_aspect = _new_figure(cfg)
    style = cfg.get("style", {})
    dataset_colors = style.get("dataset_colors", {"ERA5": "#3182bd", "MERRA2": "#e6550d"})
    marker_size = style.get("marker_size", 14)
    marker = style.get("marker", "D")

    handles = []
    for dataset in sorted(gdf["dataset"].unique()):
        sub = gdf[gdf["dataset"] == dataset]
        color = dataset_colors.get(dataset, "#555555")
        ax.scatter(sub.geometry.x, sub.geometry.y, s=marker_size, marker=marker, color=color,
                   edgecolor="black", linewidth=0.25, zorder=6)
        handles.append(Line2D([0], [0], marker=marker, color="w", markerfacecolor=color,
                               markeredgecolor="black", markersize=7, label=f"{dataset} grid"))

    # Optional single reference point (e.g. the wind farm this grid comparison is
    # centered on) -- sourced from `cfg["reference_point"]` rather than the grid data
    # file, since it's one point, not part of the reanalysis grid itself. Folded into
    # the extent so the map frame accounts for it even if it sits near a grid edge.
    ref = cfg.get("reference_point", {})
    extent_gdf = gdf
    if ref.get("show", False) and ref.get("lon") is not None and ref.get("lat") is not None:
        ref_point = gpd.GeoSeries([Point(ref["lon"], ref["lat"])], crs="EPSG:4326").to_crs(cfg["map"]["crs"])
        rx, ry = ref_point.iloc[0].x, ref_point.iloc[0].y
        ref_marker = ref.get("marker", "o")
        ref_color = ref.get("color", "#d62728")
        ax.scatter([rx], [ry], s=ref.get("size", 70), marker=ref_marker, color=ref_color,
                   edgecolor="black", linewidth=0.7, zorder=8)
        if ref.get("name"):
            ax.annotate(
                str(ref["name"]), (rx, ry), textcoords="offset points", xytext=(6, 4), ha="left",
                fontsize=ref.get("label_fontsize", 9), color="0.05", zorder=9,
                path_effects=[pe.withStroke(linewidth=2.2, foreground="white")],
            )
        handles.append(Line2D([0], [0], marker=ref_marker, color="w", markerfacecolor=ref_color,
                               markeredgecolor="black", markersize=8, label=ref.get("name") or "Reference point"))
        extent_gdf = gpd.GeoDataFrame(geometry=pd.concat([gdf.geometry, ref_point], ignore_index=True), crs=gdf.crs)

    # Per-dataset cell counts can be surfaced via extra_footer_lines (see
    # _finalize / elements.add_footer) or cfg["notes"] -- left out of the
    # rendered footer for now per current design; see README.md.
    return _finalize(fig, ax, cfg, extent_gdf, footer_gs, target_aspect,
                      legend_handles=handles, legend_title=cfg.get("legend", {}).get("title", "Legend"))
