"""Build the three map types: wind farm locations, turbine positions, ERA5/MERRA2 grid cells."""
from __future__ import annotations

import copy
import math
import re
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

# Matches a UTM EPSG code: 326xx (northern hemisphere, zones 01-60) or 327xx (southern).
_UTM_EPSG_RE = re.compile(r"EPSG:32([67])(\d{2})$")


def _utm_zone_epsg(lon: float, lat: float) -> str:
    """The EPSG code of the UTM zone that best covers (lon, lat)."""
    zone = int((lon + 180) / 6) % 60 + 1
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def _warn_utm_zone_mismatch(crs, gdf_4326: gpd.GeoDataFrame) -> None:
    """Warn if `crs` is a UTM zone but the data (still in EPSG:4326 at this point, before
    reprojection) doesn't actually sit within/near that zone. Each UTM zone only covers a
    6-degree-wide longitude band around its own central meridian -- data spanning much more
    than that, or centered well outside the zone, will be increasingly distorted the further
    it sits from that meridian. Only fires for a UTM `crs`; any other projected or geographic
    CRS isn't zone-limited in this way, so nothing to check.
    """
    m = _UTM_EPSG_RE.search(str(crs).upper())
    if m is None or gdf_4326.empty:
        return
    zone = int(m.group(2))
    zone_center_lon = zone * 6 - 183

    minx, miny, maxx, maxy = gdf_4326.total_bounds
    lon_span = maxx - minx
    center_lon, center_lat = (minx + maxx) / 2, (miny + maxy) / 2

    if lon_span > 6 or abs(center_lon - zone_center_lon) > 3:
        recommended = _utm_zone_epsg(center_lon, center_lat)
        warnings.warn(
            f"map.crs={crs!r} is UTM zone {zone} (central meridian {zone_center_lon}°E), but "
            f"the data spans {lon_span:.1f}° of longitude centered near {center_lon:.1f}°E -- "
            f"distances/shapes will be increasingly distorted away from that zone's central "
            f"meridian. Consider {recommended} instead, or a non-UTM CRS (e.g. EPSG:3857 or "
            f"EPSG:4326) if the data genuinely spans multiple UTM zones."
        )

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


# A compass ring of candidate label placements around a point, each (dx, dy) in points
# (annotation offset units) plus the (ha, va) alignment that anchors the text box to that
# offset -- tried in this order by `_place_labels`. The first entry matches the old fixed
# default (label to the upper-right of the point).
_LABEL_CANDIDATES = [
    (7, 4, "left", "bottom"),     # E / NE
    (7, -5, "left", "top"),       # SE
    (-7, 4, "right", "bottom"),   # W / NW
    (-7, -5, "right", "top"),     # SW
    (0, 9, "center", "bottom"),   # N
    (0, -9, "center", "top"),     # S
    (9, -1, "left", "center"),    # E, level
    (-9, -1, "right", "center"),  # W, level
]


def _label_bbox(anchor_x, anchor_y, dx_pt, dy_pt, ha, va, w, h, pt_to_px):
    """Pixel-space bounding box of a label anchored at (anchor_x, anchor_y) + (dx_pt, dy_pt)
    (points, converted via `pt_to_px`), aligned per matplotlib's `ha`/`va` semantics."""
    x = anchor_x + dx_pt * pt_to_px
    y = anchor_y + dy_pt * pt_to_px
    x0 = x if ha == "left" else (x - w if ha == "right" else x - w / 2)
    y0 = y if va == "bottom" else (y - h if va == "top" else y - h / 2)
    return x0, x0 + w, y0, y0 + h


def _boxes_overlap(a, b) -> bool:
    ax0, ax1, ay0, ay1 = a
    bx0, bx1, by0, by1 = b
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def _place_labels(
    fig, ax, extent: tuple[float, float, float, float], items: list[tuple[float, float, str]],
    fontsize: float, inset_cfg: dict, declutter: bool = True,
) -> None:
    """Draw a label for every item in `items` (a list of `(x, y, text)`) -- never dropped, only
    reoriented: for each point, `_LABEL_CANDIDATES` is tried in order and the first placement
    that overlaps neither an already-placed label nor the inset map is used; if every candidate
    conflicts, the one with the fewest conflicts wins. `items` order sets priority (earlier
    points get first pick of the candidate ring, so on a crowded map the more prominent points
    keep the tidiest placement). Set `declutter=False` to always use the single default
    placement instead (fast, but labels can visually overlap on dense maps).
    """
    if not declutter:
        for x, y, text in items:
            if not text:
                continue
            dx, dy, ha, va = _LABEL_CANDIDATES[0]
            ax.annotate(text, (x, y), textcoords="offset points", xytext=(dx, dy), ha=ha, va=va,
                        fontsize=fontsize, color="0.05", zorder=7,
                        path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
        return

    # Estimate each label's pixel-space bounding box from the map panel's actual rendered
    # size (like the scale bar does) plus a rough average character width -- cheap and good
    # enough for picking a non-overlapping orientation, without a real text-layout engine.
    fig.canvas.draw()
    bbox_px = ax.get_window_extent()
    xmin, xmax, ymin, ymax = extent
    px_per_x = bbox_px.width / ((xmax - xmin) or 1e-9)
    px_per_y = bbox_px.height / ((ymax - ymin) or 1e-9)
    pt_to_px = fig.dpi / 72.0
    char_w = fontsize * pt_to_px * 0.58
    line_h = fontsize * pt_to_px * 1.3

    inset_rect = None
    if inset_cfg.get("show", True):
        size = inset_cfg.get("size", 0.28)
        fx, fy = {
            "upper right": (1 - size, 1 - size), "upper left": (0.0, 1 - size),
            "lower right": (1 - size, 0.0), "lower left": (0.0, 0.0),
        }.get(inset_cfg.get("location", "lower left"), (0.0, 0.0))
        inset_rect = (
            bbox_px.x0 + fx * bbox_px.width, bbox_px.x0 + (fx + size) * bbox_px.width,
            bbox_px.y0 + fy * bbox_px.height, bbox_px.y0 + (fy + size) * bbox_px.height,
        )

    placed: list[tuple[float, float, float, float]] = []
    for x, y, text in items:
        if not text:
            continue
        w, h = char_w * len(text), line_h
        anchor_x = bbox_px.x0 + (x - xmin) * px_per_x
        anchor_y = bbox_px.y0 + (y - ymin) * px_per_y

        best = None
        best_conflicts = None
        for dx, dy, ha, va in _LABEL_CANDIDATES:
            box = _label_bbox(anchor_x, anchor_y, dx, dy, ha, va, w, h, pt_to_px)
            conflicts = sum(1 for p in placed if _boxes_overlap(box, p))
            if inset_rect is not None and _boxes_overlap(box, inset_rect):
                conflicts += 1
            if conflicts == 0:
                best = (dx, dy, ha, va, box)
                break
            if best_conflicts is None or conflicts < best_conflicts:
                best_conflicts = conflicts
                best = (dx, dy, ha, va, box)

        dx, dy, ha, va, box = best
        placed.append(box)
        ax.annotate(text, (x, y), textcoords="offset points", xytext=(dx, dy), ha=ha, va=va,
                    fontsize=fontsize, color="0.05", zorder=7,
                    path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])


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
                zoom_adjust=basemap_cfg.get("zoom_adjust", 0) or None,
                alpha=basemap_cfg.get("alpha", 1.0), attribution=False,
                headers=basemap_cfg.get("headers"),
            )
        except Exception as e:  # pragma: no cover - network dependent
            warnings.warn(f"Basemap fetch failed ({e}); continuing without a basemap.")
            ax_map.set_facecolor("#eef3f8")

    grat = cfg.get("graticule", {})
    if grat.get("show", True):
        elements.add_graticule(
            ax_map, crs, extent, n_ticks=grat.get("n_ticks", 5),
            n_ticks_x=grat.get("n_ticks_x"), n_ticks_y=grat.get("n_ticks_y"),
            fmt=grat.get("format", "decimal"),
            fontsize=grat.get("fontsize", 8), color=str(grat.get("color", "0.35")),
            linewidth=grat.get("linewidth", 0.6), frame=grat.get("frame", True),
            hemisphere=grat.get("hemisphere_labels", True),
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
            basemap_zoom_adjust=basemap_cfg.get("zoom_adjust", 0),
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
    out_path = out_dir / (cfg["export"].get("filename") or f"{cfg['map_type']}.png")
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
    path = Path(cfg["_workbook_path"])
    gdf = data_io.read_wind_farms(path)
    _warn_utm_zone_mismatch(cfg["map"]["crs"], gdf)
    gdf = gdf.to_crs(cfg["map"]["crs"])

    fig, ax, footer_gs, target_aspect = _new_figure(cfg)
    style = cfg.get("style", {})
    # `status` is an optional data column -- name/lon/lat alone are enough to plot a wind
    # farm. Without it, every point falls into one "Wind Farm" category colored `color`;
    # add a `status` column and a `style.status_colors` map to split it out by category.
    default_color = style.get("color", "#2166ac")
    status_colors = style.get("status_colors", {})
    farm_colors = style.get("farm_colors", {})
    legend_labels = style.get("legend_labels", {})
    size_field = style.get("size_field", "capacity_mw")
    base_size = style.get("base_marker_size", 45)
    size_scale = style.get("size_scale", 0.5)
    marker = style.get("marker", "o")
    legend_label = style.get("legend_label", "Wind Farm")

    # Three coloring/grouping modes, in priority order: `farm_colors` gives each named
    # farm its own distinct color and its own legend entry (regardless of `status`);
    # otherwise an optional `status` column splits farms into status categories (colored
    # via `status_colors`); otherwise every farm shares one category/color.
    if farm_colors:
        category_series = gdf["name"]
        color_map = farm_colors
    elif "status" in gdf.columns:
        category_series = gdf["status"]
        color_map = status_colors
    else:
        category_series = pd.Series([legend_label] * len(gdf))
        color_map = {}

    handles = []
    for category in sorted(category_series.unique()):
        sub = gdf[category_series == category]
        color = color_map.get(category, default_color)
        sizes = base_size + sub[size_field] * size_scale if size_field in sub.columns else base_size
        ax.scatter(
            sub.geometry.x, sub.geometry.y, s=sizes, marker=marker, color=color, edgecolor="black",
            linewidth=0.6, alpha=0.95, zorder=6,
        )
        handles.append(Line2D([0], [0], marker=marker, color="w", markerfacecolor=color,
                               markeredgecolor="black", markersize=8, label=legend_labels.get(category, category)))

    if style.get("label_points", True) and "name" in gdf.columns:
        label_fontsize = style.get("label_fontsize", 9)
        extent_for_labels = _compute_extent(gdf, cfg, target_aspect)
        # Label bigger farms first (by size_field, if present) so a crowded map keeps the
        # more prominent farms labeled when smaller/nearby ones get dropped for overlapping.
        order = gdf.sort_values(size_field, ascending=False) if size_field in gdf.columns else gdf
        items = [(row.geometry.x, row.geometry.y, str(row["name"])) for _, row in order.iterrows()]
        _place_labels(fig, ax, extent_for_labels, items, label_fontsize, cfg.get("inset_map", {}),
                      declutter=style.get("declutter_labels", True))

    # Stats like farm count / total capacity can be surfaced via extra_footer_lines
    # (see _finalize / elements.add_footer) or cfg["notes"] -- left out of the
    # rendered footer for now per current design; documented in README.md.
    return _finalize(fig, ax, cfg, gdf, footer_gs, target_aspect,
                      legend_handles=handles, legend_title=cfg.get("legend", {}).get("title", "Legend"))


# ---------------------------------------------------------------------------
# Map type 2: turbine positions within a wind farm
# ---------------------------------------------------------------------------


def build_turbine_map(cfg: dict) -> Path | list[Path]:
    """Render the turbine-positions map (map_type: turbines) and return the saved PNG path.

    If `cfg["data"]["selected_farm"]` is left unset and the data has more than one distinct
    `farm_name`, no single farm is implied -- instead this renders one map per farm
    automatically (each a normal recursive call with `selected_farm` pinned and the
    filename suffixed by a slug of the farm name) and returns a list of paths, in
    farm-name order, instead of a single Path.
    """
    path = Path(cfg["_workbook_path"])
    farm_name = cfg["data"].get("selected_farm")

    if farm_name is None:
        all_farms = pd.read_excel(path, sheet_name="turbines").get("farm_name")
        farm_names = sorted(all_farms.dropna().unique()) if all_farms is not None else []
        if len(farm_names) > 1:
            base_filename = cfg["export"].get("filename") or "turbines.png"
            stem, suffix = Path(base_filename).stem, Path(base_filename).suffix or ".png"
            paths = []
            for name in farm_names:
                farm_cfg = copy.deepcopy(cfg)
                farm_cfg["data"]["selected_farm"] = name
                slug = str(name).strip().lower().replace(" ", "_")
                farm_cfg["export"]["filename"] = f"{stem}_{slug}{suffix}"
                paths.append(build_turbine_map(farm_cfg))
            return paths

    gdf = data_io.read_turbines(path, farm_name=farm_name)
    _warn_utm_zone_mismatch(cfg["map"]["crs"], gdf)
    gdf = gdf.to_crs(cfg["map"]["crs"])

    fig, ax, footer_gs, target_aspect = _new_figure(cfg)
    style = cfg.get("style", {})
    marker_color = style.get("color", "#2166ac")
    marker_size = style.get("marker_size", 55)
    marker = style.get("marker", "o")
    # An explicit style.legend_label always wins; otherwise the legend names the wind
    # farm itself (more useful than a generic "Turbine" once maps are split per farm)
    # falling back to "Turbine" only if there's no farm_name to use either.
    label = style.get("legend_label") or farm_name or "Turbine"

    ax.scatter(gdf.geometry.x, gdf.geometry.y, s=marker_size, marker=marker, color=marker_color,
               edgecolor="black", linewidth=0.6, zorder=6)
    handles = [Line2D([0], [0], marker=marker, color="w", markerfacecolor=marker_color,
                       markeredgecolor="black", markersize=8, label=label)]

    if style.get("label_points", True) and "turbine_id" in gdf.columns:
        label_fontsize = style.get("label_fontsize", 8)
        extent_for_labels = _compute_extent(gdf, cfg, target_aspect)
        items = [(row.geometry.x, row.geometry.y, str(row["turbine_id"])) for _, row in gdf.iterrows()]
        _place_labels(fig, ax, extent_for_labels, items, label_fontsize, cfg.get("inset_map", {}),
                      declutter=style.get("declutter_labels", True))

    # Stats like farm name / turbine count / capacity can be surfaced via
    # extra_footer_lines (see _finalize / elements.add_footer) or cfg["notes"] --
    # left out of the rendered footer for now per current design; see README.md.
    return _finalize(fig, ax, cfg, gdf, footer_gs, target_aspect,
                      legend_handles=handles, legend_title=cfg.get("legend", {}).get("title", "Legend"))


# ---------------------------------------------------------------------------
# Map type 3: ERA5 / MERRA2 analysis grid cells -- plain diamond points, no
# filled grid polygons.
# ---------------------------------------------------------------------------


def build_grid_map(cfg: dict) -> Path | list[Path]:
    """Render the ERA5/MERRA2 grid-cells map (map_type: grid_cells) and return the saved PNG path.

    If the `grid_cells` sheet has an optional `farm_name` column (grouping cells into
    per-location reanalysis comparisons, e.g. one ERA5/MERRA2 subgrid per wind farm) and
    `cfg["data"]["selected_farm"]` is left unset, this renders one map per distinct
    `farm_name` automatically -- same recursive-split pattern as build_turbine_map --
    and returns a list of paths instead of a single Path. Leave the column out (or set
    `data.selected_farm`) to render a single combined grid map as before.
    """
    path = Path(cfg["_workbook_path"])
    farm_name = cfg["data"].get("selected_farm")

    if farm_name is None:
        all_farms = pd.read_excel(path, sheet_name="grid_cells").get("farm_name")
        farm_names = sorted(all_farms.dropna().unique()) if all_farms is not None else []
        if len(farm_names) > 1:
            base_filename = cfg["export"].get("filename") or "grid_cells.png"
            stem, suffix = Path(base_filename).stem, Path(base_filename).suffix or ".png"
            paths = []
            for name in farm_names:
                farm_cfg = copy.deepcopy(cfg)
                farm_cfg["data"]["selected_farm"] = name
                slug = str(name).strip().lower().replace(" ", "_")
                farm_cfg["export"]["filename"] = f"{stem}_{slug}{suffix}"
                paths.append(build_grid_map(farm_cfg))
            return paths

    datasets = cfg["data"].get("selected_datasets")
    gdf = data_io.read_grid_cells(path, datasets=datasets, farm_name=farm_name)
    _warn_utm_zone_mismatch(cfg["map"]["crs"], gdf)
    gdf = gdf.to_crs(cfg["map"]["crs"])

    fig, ax, footer_gs, target_aspect = _new_figure(cfg)
    style = cfg.get("style", {})
    dataset_colors = style.get("dataset_colors", {"ERA5": "#3182bd", "MERRA2": "#e6550d"})
    default_marker = style.get("marker", "D")
    dataset_markers = style.get("dataset_markers", {})
    legend_labels = style.get("legend_labels", {})
    marker_size = style.get("marker_size", 14)

    handles = []
    for dataset in sorted(gdf["dataset"].unique()):
        sub = gdf[gdf["dataset"] == dataset]
        color = dataset_colors.get(dataset, "#555555")
        marker = dataset_markers.get(dataset, default_marker)
        ax.scatter(sub.geometry.x, sub.geometry.y, s=marker_size, marker=marker, color=color,
                   edgecolor="black", linewidth=0.25, zorder=6)
        handles.append(Line2D([0], [0], marker=marker, color="w", markerfacecolor=color,
                               markeredgecolor="black", markersize=7,
                               label=legend_labels.get(dataset, f"{dataset} grid")))

    # Optional single reference point (e.g. the wind farm this grid comparison is
    # centered on), folded into the extent so the map frame accounts for it even if it
    # sits near a grid edge. Its position/label come from a `dataset: reference` row in
    # the `grid_cells` sheet if one matches this farm (see data_io.read_grid_reference_point)
    # -- naturally one reference point per farm, matched by farm_name, no extra config
    # needed. Falls back to `cfg["reference_point"]`'s own name/lon/lat (e.g. for a
    # workbook with no farm_name column at all); `show`/`marker`/`color`/`size`/
    # `label_fontsize` always come from config either way.
    ref = dict(cfg.get("reference_point", {}))
    data_ref = data_io.read_grid_reference_point(path, farm_name)
    if data_ref:
        ref["lon"], ref["lat"] = data_ref["lon"], data_ref["lat"]
        ref["name"] = data_ref["name"] or ref.get("name")

    show_ref = ref.get("show", False) and ref.get("lon") is not None and ref.get("lat") is not None
    if show_ref and not data_ref and farm_name and ref.get("name") and str(ref["name"]).strip().lower() != str(farm_name).strip().lower():
        show_ref = False
    extent_gdf = gdf
    if show_ref:
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
