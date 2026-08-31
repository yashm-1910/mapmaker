"""Shared cartographic chrome: graticule/ticks, compass rose, scale bar, inset map, footer."""
from __future__ import annotations

import math
import warnings
from pathlib import Path

import contextily as cx
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from pyproj import CRS, Geod, Transformer

from . import config as config_mod

# ---------------------------------------------------------------------------
# Graticule: QGIS-style cross ticks at grid intersections + mirrored frame labels
# ---------------------------------------------------------------------------


def _nice_step(span: float, n: int) -> float:
    """Round `span / n` up to a "nice" number (1/2/2.5/5 x a power of ten) for tick spacing."""
    if span <= 0:
        return 1.0
    raw = span / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _ticks_in_range(vmin: float, vmax: float, step: float) -> list[float]:
    """List the multiples of `step` that fall within [vmin, vmax]."""
    start = math.ceil(vmin / step) * step
    ticks = []
    v = start
    while v <= vmax + 1e-9:
        ticks.append(round(v, 8))
        v += step
    return ticks


def _fmt_coord(value: float, kind: str, fmt: str, hemisphere: bool = True) -> str:
    """Format a lon/lat value as a decimal-degree or DMS string, optionally hemisphere-suffixed
    (e.g. "5.90°E"); with `hemisphere=False` the sign is kept instead (e.g. "-5.90°")."""
    hemi = ("E" if value >= 0 else "W") if kind == "lon" else ("N" if value >= 0 else "S")
    sign = "" if (hemisphere or value >= 0) else "-"
    suffix = hemi if hemisphere else ""
    v = abs(value)
    if fmt == "dms":
        d = int(v)
        m_full = (v - d) * 60
        m = int(m_full)
        s = (m_full - m) * 60
        return f"{sign}{d}°{m:02d}'{s:04.1f}\"{suffix}"
    return f"{sign}{v:.2f}°{suffix}"


def _is_geographic_crs(crs) -> bool:
    """True for a lon/lat CRS like EPSG:4326; False for a projected CRS like a UTM zone."""
    try:
        return CRS.from_user_input(crs).is_geographic
    except Exception:
        return "4326" in str(crs).upper()


def _add_native_graticule(
    ax, extent: tuple[float, float, float, float], n_ticks_x: int, n_ticks_y: int,
    fontsize: float, color: str, frame: bool,
) -> None:
    """Grid ticks in the map's own projected coordinate units (e.g. UTM meters/eastings
    and northings) instead of lon/lat -- a straight, rectilinear easting/northing grid,
    matching how a projected CRS is conventionally gridded (reprojecting a lon/lat
    graticule onto a projected CRS would draw meridians as slightly curved lines and
    label ticks in the wrong unit for that CRS)."""
    xmin, xmax, ymin, ymax = extent
    x_step = _nice_step(xmax - xmin, n_ticks_x)
    y_step = _nice_step(ymax - ymin, n_ticks_y)
    xs_sorted = _ticks_in_range(xmin, xmax, x_step) or [xmin, xmax]
    ys_sorted = _ticks_in_range(ymin, ymax, y_step) or [ymin, ymax]

    cross_pts = [(x, y) for x in xs_sorted for y in ys_sorted]
    if cross_pts:
        xs, ys = zip(*cross_pts)
        ax.plot(xs, ys, marker="+", markersize=7, markeredgewidth=0.9, linestyle="None",
                 color=color, zorder=5)

    ax.set_xticks(xs_sorted)
    ax.set_xticklabels([f"{x:,.0f} m" for x in xs_sorted], fontsize=fontsize)
    ax.set_yticks(ys_sorted)
    ax.set_yticklabels([f"{y:,.0f} m" for y in ys_sorted], fontsize=fontsize, rotation=90, va="center")
    ax.tick_params(colors="black", labelsize=fontsize, direction="out", length=4,
                    top=True, labeltop=True, right=True, labelright=True)
    if frame:
        for spine in ax.spines.values():
            spine.set_edgecolor("black")
            spine.set_linewidth(0.9)
    else:
        for spine in ax.spines.values():
            spine.set_visible(False)


def add_graticule(
    ax,
    crs,
    extent: tuple[float, float, float, float],
    n_ticks: int = 5,
    n_ticks_x: int | None = None,
    n_ticks_y: int | None = None,
    fmt: str = "decimal",
    fontsize: float = 8,
    color: str = "0.35",
    linewidth: float = 0.6,
    linestyle=None,
    frame: bool = True,
    hemisphere: bool = True,
) -> None:
    """Draw small cross ticks at each graticule intersection, with coordinate labels
    mirrored on all four sides of the frame -- matching a classic QGIS print layout
    grid (rather than full gridlines spanning the whole map). `n_ticks_x`/`n_ticks_y`
    set the horizontal (longitude) / vertical (latitude) tick density independently;
    either left `None` falls back to the shared `n_ticks`.

    For a projected `crs` (e.g. a UTM zone), ticks are drawn and labeled in that CRS's
    own native units (meters) instead of lon/lat -- see `_add_native_graticule`; `fmt`
    and `hemisphere` only apply to a geographic CRS."""
    n_ticks_x = n_ticks if n_ticks_x is None else n_ticks_x
    n_ticks_y = n_ticks if n_ticks_y is None else n_ticks_y
    if not _is_geographic_crs(crs):
        _add_native_graticule(ax, extent, n_ticks_x, n_ticks_y, fontsize, color, frame)
        return

    xmin, xmax, ymin, ymax = extent
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    lons, lats = [], []
    for x in np.linspace(xmin, xmax, 20):
        for y in (ymin, ymax):
            lo, la = to_ll.transform(x, y)
            lons.append(lo)
            lats.append(la)
    for y in np.linspace(ymin, ymax, 20):
        for x in (xmin, xmax):
            lo, la = to_ll.transform(x, y)
            lons.append(lo)
            lats.append(la)
    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)

    lon_step = _nice_step(lon_max - lon_min, n_ticks_x)
    lat_step = _nice_step(lat_max - lat_min, n_ticks_y)
    lon_ticks = _ticks_in_range(lon_min, lon_max, lon_step)
    lat_ticks = _ticks_in_range(lat_min, lat_max, lat_step)

    tol_x = (xmax - xmin) * 0.003
    tol_y = (ymax - ymin) * 0.003

    xticks: dict[float, float] = {}
    yticks: dict[float, float] = {}
    cross_pts = []
    for lon in lon_ticks:
        for lat in lat_ticks:
            x, y = to_xy.transform(lon, lat)
            if xmin - tol_x <= x <= xmax + tol_x and ymin - tol_y <= y <= ymax + tol_y:
                cross_pts.append((x, y))
                if abs(lat - lat_ticks[0]) < 1e-9:
                    xticks[x] = lon
                if abs(lon - lon_ticks[0]) < 1e-9:
                    yticks[y] = lat

    if cross_pts:
        xs, ys = zip(*cross_pts)
        ax.plot(xs, ys, marker="+", markersize=7, markeredgewidth=0.9, linestyle="None",
                 color=color, zorder=5)

    xs_sorted = sorted(xticks) or [xmin, xmax]
    ys_sorted = sorted(yticks) or [ymin, ymax]
    if not xticks:
        xticks = {xmin: to_ll.transform(xmin, ymin)[0], xmax: to_ll.transform(xmax, ymin)[0]}
    if not yticks:
        yticks = {ymin: to_ll.transform(xmin, ymin)[1], ymax: to_ll.transform(xmin, ymax)[1]}

    ax.set_xticks(xs_sorted)
    ax.set_xticklabels([_fmt_coord(xticks[x], "lon", fmt, hemisphere) for x in xs_sorted], fontsize=fontsize)
    ax.set_yticks(ys_sorted)
    ax.set_yticklabels([_fmt_coord(yticks[y], "lat", fmt, hemisphere) for y in ys_sorted], fontsize=fontsize, rotation=90, va="center")
    ax.tick_params(colors="black", labelsize=fontsize, direction="out", length=4,
                    top=True, labeltop=True, right=True, labelright=True)
    if frame:
        for spine in ax.spines.values():
            spine.set_edgecolor("black")
            spine.set_linewidth(0.9)
    else:
        for spine in ax.spines.values():
            spine.set_visible(False)


# ---------------------------------------------------------------------------
# North arrow: simple arrow with an "N" label
# ---------------------------------------------------------------------------


def _corner_xy(location: str, inset: float) -> tuple[float, float]:
    """Axes-fraction (x, y) for a named corner ("upper/lower left/right"), inset from the edges."""
    x = inset if "left" in location else 1 - inset
    y = inset if "lower" in location else 1 - inset
    return x, y


def add_north_arrow(ax, location: str = "lower right", size: float = 0.05, color: str = "black") -> None:
    """Draw a simple north-pointing arrow with an "N" label in one corner of `ax`."""
    x, y = _corner_xy(location, size * 1.3 + 0.02)
    arrow_len = size * 2.2
    y_bottom, y_top = y - arrow_len / 2, y + arrow_len / 2
    ax.annotate(
        "", xy=(x, y_top), xytext=(x, y_bottom), xycoords="axes fraction", textcoords="axes fraction",
        arrowprops=dict(arrowstyle="-|>", color=color, lw=2, mutation_scale=18), zorder=10,
    )
    ax.text(
        x, y_top + 0.015, "N", transform=ax.transAxes, ha="center", va="bottom",
        fontsize=13, fontweight="bold", color=color, zorder=10,
    )


# ---------------------------------------------------------------------------
# Scale bar: rendered into its own footer panel, sized from the map's true
# on-page geographic scale (not overlaid on the basemap).
# ---------------------------------------------------------------------------


def compute_dx(crs, center_lon: float, center_lat: float) -> float:
    """Meters represented by one data unit at the map center."""
    crs_str = str(crs).upper()
    if "4326" in crs_str:
        geod = Geod(ellps="WGS84")
        _, _, dist = geod.inv(center_lon, center_lat, center_lon + 1.0, center_lat)
        return dist
    if "3857" in crs_str:
        return math.cos(math.radians(center_lat))
    return 1.0


def _nice_scale_length(target: float) -> float:
    """Round `target` up to a "nice" scale-bar length (1/2/5 x a power of ten)."""
    if target <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(target))
    for m in (1, 2, 5, 10):
        if target <= m * mag:
            return m * mag
    return 10 * mag


def draw_scalebar_panel(
    fig,
    panel_ax,
    map_ax,
    crs,
    extent: tuple[float, float, float, float],
    length_fraction: float = 0.7,
    font_size: float = 8,
    units: str = "auto",
) -> None:
    """Draw a segmented scale bar into `panel_ax`, sized from `map_ax`'s true printed
    geographic scale (its actual rendered pixel width vs. its data extent), not a
    fraction of `panel_ax` itself. `length_fraction` targets roughly that fraction of
    `panel_ax`'s own width before the length is rounded to a nice round number.
    """
    panel_ax.axis("off")
    panel_ax.set_xlim(0, 1)
    panel_ax.set_ylim(0, 1)

    xmin, xmax, ymin, ymax = extent
    center_lon, center_lat = (xmin + xmax) / 2, (ymin + ymax) / 2
    dx = compute_dx(crs, center_lon, center_lat)

    fig.canvas.draw()  # resolve aspect-ratio letterboxing before measuring the map's true size
    map_bbox_px = map_ax.get_window_extent()
    panel_bbox_px = panel_ax.get_window_extent()
    map_width_in = map_bbox_px.width / fig.dpi
    panel_width_in = panel_bbox_px.width / fig.dpi
    if map_width_in <= 0 or panel_width_in <= 0:
        return

    real_world_width_m = (xmax - xmin) * dx
    meters_per_inch = real_world_width_m / map_width_in
    target_len_m = meters_per_inch * panel_width_in * length_fraction

    display_unit = ("km" if target_len_m >= 1000 else "m") if units in (None, "auto") else units
    unit_factor = 1000.0 if display_unit == "km" else 1.0

    nice_len_display = _nice_scale_length(target_len_m / unit_factor)
    nice_len_m = nice_len_display * unit_factor
    bar_len_in = nice_len_m / meters_per_inch
    bar_frac = min(bar_len_in / panel_width_in, 0.78)

    # Labels sit above the bar, with the unit appended to the final value only
    # (e.g. "1,000" ... "2,000 m") -- no "0" label at the start, matching a
    # classic QGIS print-layout scale bar. The block as a whole bottom-aligns
    # with the other footer columns (legend / CRS / date-author).
    n_segments = 2
    seg_frac = bar_frac / n_segments
    x0, y0, h = 0.04, 0.06, 0.17
    for i in range(n_segments):
        color = "black" if i % 2 == 0 else "white"
        panel_ax.add_patch(Rectangle((x0 + i * seg_frac, y0), seg_frac, h,
                                      facecolor=color, edgecolor="black", linewidth=0.8, zorder=5))
    panel_ax.add_patch(Rectangle((x0, y0), bar_frac, h, fill=False, edgecolor="black", linewidth=0.8))

    for i in range(1, n_segments + 1):
        val = (nice_len_display / n_segments) * i
        label = f"{val:,.0f}"
        if i == n_segments:
            label = f"{label} {display_unit}"
        panel_ax.text(x0 + i * seg_frac, y0 + h + 0.05, label, ha="center", va="bottom", fontsize=font_size)


# ---------------------------------------------------------------------------
# Inset / overview map -- bounding box only, no other decoration
# ---------------------------------------------------------------------------


def _resolve_provider(name: str | None):
    """Resolve a dotted provider name (e.g. "CartoDB.Positron") to a contextily TileProvider."""
    if not name:
        return cx.providers.OpenStreetMap.Mapnik
    obj = cx.providers
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


def add_inset_map(
    ax,
    extent: tuple[float, float, float, float],
    crs,
    zoom_out_factor: float = 8,
    location: str = "lower left",
    size: float = 0.28,
    basemap_provider=None,
    bbox_edgecolor: str = "red",
    bbox_linewidth: float = 2.2,
    basemap_headers: dict | None = None,
    basemap_zoom_adjust: int = 0,
    min_bbox_frac: float = 0.05,
):
    """Add a small overview-map inset to `ax`, zoomed out `zoom_out_factor` times around the
    same center, with a bounding-box outline marking the main map's ROI (`extent`). The inset
    sits flush in one corner (`location`) and is the only element that draws a bounding box.
    Returns the inset Axes.
    """
    xmin, xmax, ymin, ymax = extent
    w, h = xmax - xmin, ymax - ymin
    cx_, cy_ = (xmin + xmax) / 2, (ymin + ymax) / 2
    zf = max(zoom_out_factor, 1.01)
    inset_extent = (cx_ - w * zf / 2, cx_ + w * zf / 2, cy_ - h * zf / 2, cy_ + h * zf / 2)

    # Flush against the frame edge (no gap) -- the inset should touch the map's
    # corner exactly, like a QGIS print-layout overview map.
    anchors = {
        "upper right": [1 - size, 1 - size, size, size],
        "upper left": [0.0, 1 - size, size, size],
        "lower right": [1 - size, 0.0, size, size],
        "lower left": [0.0, 0.0, size, size],
    }
    bbox = anchors.get(location, anchors["lower left"])
    axins = ax.inset_axes(bbox, zorder=9)
    axins.set_xlim(inset_extent[0], inset_extent[1])
    axins.set_ylim(inset_extent[2], inset_extent[3])
    axins.set_xticks([])
    axins.set_yticks([])
    for spine in axins.spines.values():
        spine.set_edgecolor("black")
        spine.set_linewidth(1.2)

    if basemap_provider is not False and basemap_provider is not None:
        try:
            cx.add_basemap(axins, crs=crs, source=basemap_provider, attribution=False, headers=basemap_headers,
                           zoom_adjust=basemap_zoom_adjust or None)
        except Exception as e:  # pragma: no cover - network dependent
            warnings.warn(f"Inset basemap fetch failed ({e}); using flat fill instead.")
            axins.set_facecolor("#dce6f2")
    else:
        axins.set_facecolor("#dce6f2")

    # Enforce a minimum on-screen size for the ROI box so it stays legible even
    # when zoom_out_factor makes the true ROI a tiny sliver of the inset.
    inset_w, inset_h = inset_extent[1] - inset_extent[0], inset_extent[3] - inset_extent[2]
    draw_w = max(w, inset_w * min_bbox_frac)
    draw_h = max(h, inset_h * min_bbox_frac)
    rect = Rectangle(
        (cx_ - draw_w / 2, cy_ - draw_h / 2), draw_w, draw_h,
        fill=False, edgecolor=bbox_edgecolor, linewidth=bbox_linewidth, zorder=10,
    )
    axins.add_patch(rect)
    return axins


# ---------------------------------------------------------------------------
# Footer: legend / scale bar / CRS / author-date-attribution+logo, all outside
# the map frame so nothing ever overlaps the map content.
# ---------------------------------------------------------------------------


def add_footer(
    fig,
    gs_cell,
    cfg: dict,
    map_ax,
    crs,
    extent: tuple[float, float, float, float],
    legend_handles=None,
    legend_title: str = "Legend",
    extra_lines: list[str] | None = None,
):
    """Build the footer strip below the map: legend / scale bar / CRS / date-author-copyright+logo,
    laid out as four bottom-aligned columns (`cfg["footer"]["column_widths"]`) inside `gs_cell`.
    Returns the underlying 1x4 SubgridSpec.
    """
    footer_cfg = cfg.get("footer", {})
    fontsize = footer_cfg.get("fontsize", 8)
    # str() guards against a grayscale value like "0.15" round-tripping through the
    # workbook's config sheet as a float (0.15) -- matplotlib only accepts grayscale
    # as a string, not a bare float, and 0.15 is otherwise indistinguishable from any
    # other numeric setting when the sheet is parsed (see config.py::_parse_scalar).
    text_color = str(footer_cfg.get("text_color", "0.15"))
    column_widths = footer_cfg.get("column_widths", [1.0, 1.3, 1.4, 2.1])

    sub = gs_cell.subgridspec(1, 4, width_ratios=column_widths, wspace=0.03)

    # -- legend --------------------------------------------------------------
    # All four footer columns bottom-align, sitting right on the page's bottom
    # border with no empty strip beneath them; the map above absorbs whatever
    # slack is left instead.
    ax_legend = fig.add_subplot(sub[0])
    ax_legend.axis("off")
    if legend_handles and cfg.get("legend", {}).get("show", True):
        leg = ax_legend.legend(
            handles=legend_handles, loc="lower left", bbox_to_anchor=(0.0, 0.0), frameon=False,
            fontsize=fontsize, title=legend_title, title_fontsize=fontsize + 1,
            borderaxespad=0, borderpad=0.15, handletextpad=0.6, labelspacing=0.45,
        )
        leg.get_title().set_ha("left")

    # -- scale bar -----------------------------------------------------------
    ax_scale = fig.add_subplot(sub[1])
    sb_cfg = cfg.get("scalebar", {})
    if sb_cfg.get("show", True):
        draw_scalebar_panel(
            fig, ax_scale, map_ax, crs, extent, length_fraction=sb_cfg.get("length_fraction", 0.7),
            font_size=fontsize, units=sb_cfg.get("units", "auto"),
        )
    else:
        ax_scale.axis("off")

    # -- CRS label -----------------------------------------------------------
    ax_crs = fig.add_subplot(sub[2])
    ax_crs.axis("off")
    ax_crs.set_xlim(0, 1)
    ax_crs.set_ylim(0, 1)
    if crs:
        ax_crs.text(0.0, 0.0, f"Coordinate Reference System\n{crs}", transform=ax_crs.transAxes,
                    ha="left", va="bottom", fontsize=fontsize, color=text_color, linespacing=1.6)

    # -- date / author / attribution + logo -----------------------------------
    ax_meta = fig.add_subplot(sub[3])
    ax_meta.axis("off")
    ax_meta.set_xlim(0, 1)
    ax_meta.set_ylim(0, 1)

    company_cfg = cfg.get("company", {})
    logo_path = config_mod.resolve_path(cfg, company_cfg.get("logo_path"))
    if logo_path and Path(logo_path).exists():
        img = plt.imread(str(logo_path))
        # Logo anchors to the bottom-right corner rather than spanning/centering
        # the full column height, so it doesn't compete with the top-aligned text.
        # `company.logo_scale` grows/shrinks it from that corner (base size at 1.0),
        # clamped so it can never exceed the meta column it lives in.
        base_w, base_h = 0.26, 0.45
        scale = company_cfg.get("logo_scale", 1.0)
        logo_w = min(base_w * scale, 1.0)
        logo_h = min(base_h * scale, 1.0)
        logo_ax = ax_meta.inset_axes([1.0 - logo_w, 0.0, logo_w, logo_h])
        logo_ax.imshow(img)
        logo_ax.axis("off")

    lines = []
    if cfg.get("date"):
        lines.append(f"Date: {cfg['date']}")
    if cfg.get("author"):
        lines.append(f"Author: {cfg['author']}")
    attribution = cfg.get("attribution", {})
    attr_text = attribution.get("text") if isinstance(attribution, dict) else attribution
    if attr_text:
        lines.append(attr_text)
    if extra_lines:
        lines.extend(str(x) for x in extra_lines)
    if cfg.get("notes"):
        lines.extend(str(x) for x in cfg["notes"])

    ax_meta.text(0.02, 0.0, "\n".join(lines), transform=ax_meta.transAxes, ha="left", va="bottom",
                 fontsize=fontsize, color=text_color, linespacing=1.6, wrap=True)

    return sub
