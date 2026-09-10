"""Draw packaging/build_assets/mapmaker.ico -- the Windows application icon.

The artwork is generated here in code rather than loaded from an image file, for
two reasons:

  * Provenance. Nothing is traced, downloaded, or adapted from someone else's
    icon set, so there is no licence or attribution to track and nothing that
    could turn into a copyright question later. The shapes below are plain
    geometry -- a rounded square, four graticule lines, a tower and three blades.
  * It is not assets/logo.png. That file is the placeholder logo stamped into
    each map's footer, and it says "YOUR LOGO" -- fine as a footer placeholder a
    user is expected to replace, wrong as the identity of the application itself.

The mark is a map tile (rounded square, graticule) with a wind turbine standing
on it: what the tool draws, on what it draws it on.

Run by Build.bat before PyInstaller; harmless to run directly:

    python packaging/make_icon.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

# The sizes Windows actually asks for: 16/32 in Explorer lists and the taskbar,
# 48 for medium icons, 256 for the extra-large view and the properties dialog.
ICON_SIZES = [16, 20, 24, 32, 48, 64, 128, 256]

# Every size is drawn at this multiple and then reduced, which is what gives the
# diagonal blade edges clean anti-aliasing instead of staircases.
SUPERSAMPLE = 8

# Below this, a 1px-wide graticule line and a tapered blade turn to mush. The
# small sizes get a simplified drawing instead of a shrunken detailed one -- the
# whole reason each size is rendered separately rather than downsampled from 256.
DETAIL_CUTOFF = 32

# How far the rotor is turned off the two-blades-up pose. Enough that the third
# blade clears the tower and the rotor looks caught mid-turn, small enough that
# the turbine still stands upright rather than looking knocked over. Raising this
# to 30 puts a blade flat along the horizontal; lowering it to 0 merges the third
# blade into the mast. See the long comment in draw_icon().
ROTOR_TILT_DEGREES = 18
ROTOR_ANGLES = tuple(base + ROTOR_TILT_DEGREES for base in (30, 150, 270))

BACKGROUND = (23, 61, 84, 255)     # deep slate blue -- reads as a map at a glance
GRATICULE = (255, 255, 255, 48)    # faint, so it never competes with the turbine
TURBINE = (255, 255, 255, 255)

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "packaging" / "build_assets" / "mapmaker.ico"


def _blade(draw: ImageDraw.ImageDraw, s: float, hub: tuple[float, float], degrees: float,
           length: float, root_w: float, tip_w: float) -> None:
    """One tapered blade, as a quad running out from the hub at `degrees`.

    Coordinates arrive as fractions of the icon's side so the same numbers work
    at every size; `s` converts them to pixels.
    """
    rad = math.radians(degrees)
    # Screen y grows downward, so the sine is negated to make positive angles
    # point up -- otherwise the rotor would be drawn upside down.
    dx, dy = math.cos(rad), -math.sin(rad)
    nx, ny = -dy, dx  # unit normal, for the blade's width
    hx, hy = hub
    tx, ty = hx + dx * length, hy + dy * length
    draw.polygon(
        [
            ((hx + nx * root_w) * s, (hy + ny * root_w) * s),
            ((tx + nx * tip_w) * s, (ty + ny * tip_w) * s),
            ((tx - nx * tip_w) * s, (ty - ny * tip_w) * s),
            ((hx - nx * root_w) * s, (hy - ny * root_w) * s),
        ],
        fill=TURBINE,
    )


def draw_icon(size: int) -> Image.Image:
    """Render one square icon at `size` pixels."""
    detailed = size >= DETAIL_CUTOFF
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # The tile. Rounded like every other modern Windows app icon, and inset
    # slightly so the corners are not clipped by the icon's own bounding box.
    inset = 0.02 * s
    draw.rounded_rectangle(
        [inset, inset, s - inset, s - inset],
        radius=0.20 * s,
        fill=BACKGROUND,
    )

    if detailed:
        # Graticule: the lat/lon grid mapmaker draws on every map. Drawn on its
        # own layer and then masked by the tile shape, so the lines stop at the
        # rounded corners instead of cutting across them.
        grid = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grid)
        line_w = max(1, int(0.014 * s))
        for frac in (0.28, 0.72):
            gdraw.line([(frac * s, 0), (frac * s, s)], fill=GRATICULE, width=line_w)
            gdraw.line([(0, frac * s), (s, frac * s)], fill=GRATICULE, width=line_w)
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [inset, inset, s - inset, s - inset], radius=0.20 * s, fill=255
        )
        # Multiply the grid's own alpha by the tile mask and composite it, rather
        # than Image.paste(grid, mask): paste *replaces* the destination pixels,
        # alpha included, so the grid layer's transparent areas would punch the
        # tile background back out to nothing and leave the turbine floating.
        grid.putalpha(ImageChops.multiply(grid.getchannel("A"), mask))
        img.alpha_composite(grid)

    # The turbine, in fractions of the side.
    #
    # The proportions matter more than they look. An earlier version used a wide
    # tapered tower with the blades meeting at its very top, and the result read
    # unmistakably as an aeroplane -- fuselage plus swept-back wings. What breaks
    # that reading is a genuinely thin tower and a rotor that clearly sits in
    # front of it: a distinct hub cap, and blades whose roots start outside the
    # tower's width rather than growing out of it.
    hub = (0.50, 0.41)
    hx, hy = hub

    # Tower: near-parallel-sided and narrow, running from behind the hub to near
    # the bottom of the tile, with a slight flare at the base.
    base_y, base_w, top_w = 0.84, 0.030, 0.016
    draw.polygon(
        [
            ((hx - top_w) * s, hy * s),
            ((hx + top_w) * s, hy * s),
            ((hx + base_w) * s, base_y * s),
            ((hx - base_w) * s, base_y * s),
        ],
        fill=TURBINE,
    )

    # Rotor: three blades 120 degrees apart. The angle they sit at is the whole
    # difference between this reading as a turbine and reading as something else,
    # and two obvious poses both fail:
    #
    #   one blade up, two swept down-and-out (90/210/330) is a fuselage with
    #       wings -- it reads as an aeroplane, not a turbine;
    #   two blades up, one straight down (30/150/270) puts the third blade
    #       exactly on top of the vertical tower, where it disappears -- rotor
    #       and mast merge into a plain letter Y.
    #
    # A slight tilt off the two-up-one-down pose fixes both: nothing is
    # symmetric about the tower, and the downward blade sits just beside the
    # mast rather than on it, so the hub reads as a hub and the whole thing
    # reads as a rotor caught mid-turn.
    #
    # At small sizes the blades are shorter and blunter, which survives the
    # reduction; a faithfully thin blade would simply disappear.
    length = 0.33 if detailed else 0.30
    root_w = 0.030 if detailed else 0.044
    tip_w = 0.010 if detailed else 0.026
    for degrees in ROTOR_ANGLES:
        _blade(draw, s, hub, degrees, length, root_w, tip_w)

    # Hub cap, drawn last so it covers where the three blade roots overlap and
    # reads as the nacelle sitting in front of the tower.
    hub_r = (0.052 if detailed else 0.062) * s
    draw.ellipse([hx * s - hub_r, hy * s - hub_r, hx * s + hub_r, hy * s + hub_r], fill=TURBINE)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    images = [draw_icon(size) for size in ICON_SIZES]

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    # append_images is what puts each separately-drawn size into the .ico. Saving
    # with `sizes=` instead would keep only the first image and downscale it,
    # throwing away the small-size versions drawn above.
    images[-1].save(
        TARGET,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        append_images=images[:-1],
    )
    print(f"Wrote {TARGET} ({', '.join(f'{s}x{s}' for s in ICON_SIZES)})")

    # A PNG of the largest size next to it, for README screenshots or to use as
    # the window icon later. Costs nothing and saves regenerating the artwork.
    preview = TARGET.with_suffix(".png")
    images[-1].save(preview, format="PNG")
    print(f"Wrote {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
