#!/usr/bin/env python3
"""ADI mark + lockup generator — single source of truth (true vector).

The ADI mark is a square outline tile holding an N×N grid of small squares in a
graded neutral ramp (the "choropleth grid" / small-area-data motif), with two
cells tipped the Autonomy golden accent.

Design rules baked in here:
  * Every dimension is a ratio of one base unit U (the outer tile side), so the
    whole thing scales exactly and stays on a clean grid.
  * Ink (the tile outline) renders with `currentColor`; the golden accent is
    `var(--adi-accent, #fbc441)` so the mark themes on light AND dark.
  * Sharp corners only (ADU house style) — no rounded rects.
  * A 3×3 variant is provided for tiny sizes (favicon ≤ 16px) where a 4×4 grid
    silts up; the gold cells move to keep the same diagonal read.

Wordmark in the lockups is OUTLINED from IBM Plex (HarfBuzz shaping → fontTools
outlines) so the SVG carries no font dependency. "ADI" is set in IBM Plex Serif
Bold (matches the ASPECTT serif wordmark feel); the descriptor "Annual
Deprivation Index" in IBM Plex Sans Medium.

Run:  uv run --with fonttools --with uharfbuzz python mark_gen.py
Emits into the script's own directory:
  adi-mark.svg, adi-mark-favicon.svg (3×3),
  adi-lockup-light.svg, adi-lockup-dark.svg
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent

ACCENT = "var(--adi-accent, #fbc441)"

# Neutral sequential SLATE ramp (matches tokens.css --seq-*). Index 0 = pale.
SEQ = ["#f3f5f7", "#d7dde3", "#b3bdc7", "#8b97a4",
       "#636f7d", "#424b56", "#262c33"]

FONT_DIR = Path("/usr/share/texlive/texmf-dist/fonts/opentype/ibm/plex")
FONT_SERIF_BOLD = FONT_DIR / "IBMPlexSerif-Bold.otf"
FONT_SANS_MEDIUM = FONT_DIR / "IBMPlexSans-Medium.otf"
FONT_SANS_REGULAR = FONT_DIR / "IBMPlexSans-Regular.otf"


# ---------------------------------------------------------------------------
# Mark geometry
# ---------------------------------------------------------------------------
@dataclass
class MarkParams:
    """All geometry as ratios of the base unit U (outer tile side)."""
    U: float = 100.0          # base unit: outer tile side
    n: int = 4                # grid is n×n
    outline_w: float = 0.045  # tile outline stroke, ×U
    pad: float = 0.135        # inset from tile edge to grid, ×U
    gap: float = 0.055        # gap between cells, ×U (fraction of grid span)
    # which cells are golden, as (row, col) 0-indexed from top-left.
    # Two cells on the leading diagonal-ish — reads as a highlighted strata.
    gold_cells: tuple = ((1, 2), (2, 1))
    # graded grey assignment: a diagonal gradient pale(top-left)→dark(bottom-right)
    # so the grid reads as a choropleth surface, not random noise.

    @property
    def grid_origin(self) -> float:
        return self.U * self.pad

    @property
    def grid_span(self) -> float:
        return self.U * (1 - 2 * self.pad)

    @property
    def cell(self) -> float:
        g = self.grid_span
        gap = g * self.gap
        return (g - gap * (self.n - 1)) / self.n

    @property
    def step(self) -> float:
        return self.cell + self.grid_span * self.gap


def _grey_for(r: int, c: int, n: int) -> str:
    """Diagonal pale→dark gradient over the ramp, skipping the very palest so
    cells stay visible on white. Normalised diagonal position → ramp index."""
    t = (r + c) / (2 * (n - 1))           # 0 (top-left) .. 1 (bottom-right)
    # map into ramp indices 1..5 (avoid #f3f5f7 which vanishes on white, and the
    # darkest which would fight the outline)
    lo, hi = 1, 5
    idx = round(lo + t * (hi - lo))
    return SEQ[idx]


def mark_cells_svg(p: MarkParams) -> str:
    """Inner <rect> elements for the grid (no outer tile)."""
    out = []
    o = p.grid_origin
    cell = p.cell
    step = p.step
    gold = set(p.gold_cells)
    for r in range(p.n):
        for c in range(p.n):
            x = o + c * step
            y = o + r * step
            if (r, c) in gold:
                fill = ACCENT
            else:
                fill = _grey_for(r, c, p.n)
            out.append(
                f'    <rect x="{x:.3f}" y="{y:.3f}" '
                f'width="{cell:.3f}" height="{cell:.3f}" fill="{fill}"/>'
            )
    return "\n".join(out)


def mark_svg(p: MarkParams, *, size: int | None = None,
             with_xmlns: bool = True) -> str:
    """Full standalone mark SVG. Outline uses currentColor; gold via var."""
    U = p.U
    sw = U * p.outline_w
    half = sw / 2
    vb = f"0 0 {U:.0f} {U:.0f}"
    dims = ""
    if size:
        dims = f' width="{size}" height="{size}"'
    xmlns = ' xmlns="http://www.w3.org/2000/svg"' if with_xmlns else ""
    # outer tile: a stroked square, inset by half the stroke so the stroke sits
    # fully inside the viewBox (no clipping at edges).
    tile = (
        f'  <rect x="{half:.3f}" y="{half:.3f}" '
        f'width="{U - sw:.3f}" height="{U - sw:.3f}" '
        f'fill="none" stroke="currentColor" stroke-width="{sw:.3f}"/>'
    )
    return (
        f'<svg{xmlns} viewBox="{vb}"{dims} role="img" '
        f'aria-label="ADI">\n'
        f'  <title>ADI — Annual Deprivation Index</title>\n'
        f'{tile}\n'
        f'{mark_cells_svg(p)}\n'
        f'</svg>\n'
    )


# ---------------------------------------------------------------------------
# Font outlining (HarfBuzz shaping → fontTools glyph outlines → SVG path)
# ---------------------------------------------------------------------------
def _shape_to_path(text: str, font_path: Path, font_size: float):
    """Return (path_d, advance_width) with the baseline at y=0, x growing right.
    Glyph outlines are flipped to SVG's y-down space."""
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen

    data = font_path.read_bytes()
    hb_face = hb.Face(data)
    hb_font = hb.Font(hb_face)
    upem = hb_face.upem
    scale = font_size / upem

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {"kern": True, "liga": True})

    infos = buf.glyph_infos
    positions = buf.glyph_positions

    tt = TTFont(font_path)
    glyf = tt.getGlyphSet()
    order = tt.getGlyphOrder()

    parts = []
    x_cursor = 0.0
    for info, pos in zip(infos, positions):
        gid = info.codepoint
        gname = order[gid]
        pen = SVGPathPen(glyf)
        glyf[gname].draw(pen)
        d = pen.getCommands()
        ox = (x_cursor + pos.x_offset) * scale
        oy = (pos.y_offset) * scale
        if d:
            # glyph outline is in font units, y-up; flip y and scale, translate.
            # transform: x' = ox + x*scale ; y' = oy - y*scale
            parts.append(
                f'<g transform="translate({ox:.3f},{-oy:.3f}) '
                f'scale({scale:.5f},{-scale:.5f})">'
                f'<path d="{d}"/></g>'
            )
        x_cursor += pos.x_advance
    advance = x_cursor * scale
    return "".join(parts), advance


def _shape_caps_tracked(text: str, font_path: Path, font_size: float,
                        tracking_em: float):
    """Like _shape_to_path but adds letter-spacing (tracking) between glyphs,
    for the letter-spaced caps wordmark feel. Returns (svg_group, advance)."""
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen

    data = font_path.read_bytes()
    hb_face = hb.Face(data)
    hb_font = hb.Font(hb_face)
    upem = hb_face.upem
    scale = font_size / upem

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {"kern": True})

    tt = TTFont(font_path)
    glyf = tt.getGlyphSet()
    order = tt.getGlyphOrder()
    track = tracking_em * font_size

    parts = []
    x_cursor = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gname = order[info.codepoint]
        pen = SVGPathPen(glyf)
        glyf[gname].draw(pen)
        d = pen.getCommands()
        ox = x_cursor + pos.x_offset * scale
        if d:
            parts.append(
                f'<g transform="translate({ox:.3f},0) '
                f'scale({scale:.5f},{-scale:.5f})"><path d="{d}"/></g>'
            )
        x_cursor += pos.x_advance * scale + track
    return "".join(parts), x_cursor


# ---------------------------------------------------------------------------
# Lockup
# ---------------------------------------------------------------------------
def lockup_svg(dark: bool = False) -> str:
    """Mark + 'ADI' wordmark + 'Annual Deprivation Index' descriptor.

    Layout in a coordinate space where the mark is M tall on the left, and the
    text block sits to its right, vertically centred. Ink = currentColor so the
    light/dark variants differ only in the wrapping color + background note.
    """
    p = MarkParams()
    M = 100.0                       # mark drawn at 100×100 then placed
    gap_mark_text = 34.0            # gap between mark and text

    # Type sizes (in the same user units as the 100-unit mark).
    adi_size = 70.0                 # "ADI" serif bold cap height-ish
    desc_size = 19.0                # descriptor sans

    adi_path, adi_w = _shape_to_path("ADI", FONT_SERIF_BOLD, adi_size)
    # Descriptor on two lines to match the locked reference.
    d1_path, d1_w = _shape_to_path("Annual", FONT_SANS_MEDIUM, desc_size)
    d2_path, d2_w = _shape_to_path("Deprivation Index", FONT_SANS_MEDIUM,
                                   desc_size)
    desc_w = max(d1_w, d2_w)

    text_w = adi_w + 14.0 + desc_w
    text_block_w = adi_w + 14.0 + desc_w

    # Vertical metrics. Mark centred on the text block.
    mark_x = 0.0
    mark_y = 0.0
    text_x = M + gap_mark_text

    # "ADI" baseline placed so the caps are vertically centred against the mark.
    # Cap height of Plex Serif ~0.66 em. Centre the cap band on the mark centre.
    adi_cap = adi_size * 0.66
    adi_baseline = mark_y + M / 2 + adi_cap / 2

    # Descriptor sits to the right of ADI, two lines, centred on the mark too.
    desc_x = text_x + adi_w + 16.0
    desc_cap = desc_size * 0.70
    line_gap = desc_size * 1.18
    # centre the two-line block on the mark centre
    block_h = line_gap + desc_cap
    desc_top_baseline = mark_y + M / 2 - block_h / 2 + desc_cap
    d1_baseline = desc_top_baseline
    d2_baseline = desc_top_baseline + line_gap

    total_w = desc_x + desc_w
    total_h = M
    pad = 6.0
    vb_w = total_w + pad * 2
    vb_h = total_h + pad * 2

    # descriptor colour: a muted grey in the reference ("Annual / Deprivation
    # Index" is lighter than ADI). Use currentColor at reduced opacity so it
    # themes.
    desc_fill = 'fill="currentColor" fill-opacity="0.78"'

    mark = mark_svg(p, with_xmlns=False)
    # strip the outer <svg> wrapper from mark and re-place it via <g>
    inner = mark.split(">", 1)[1].rsplit("</svg>", 1)[0]
    # remove title for embedding
    inner = inner.replace(
        "  <title>ADI — Annual Deprivation Index</title>\n", "")

    bg_note = "dark" if dark else "light"
    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vb_w:.2f} {vb_h:.2f}" '
        f'role="img" aria-label="ADI — Annual Deprivation Index">')
    svg.append(f'  <title>ADI — Annual Deprivation Index ({bg_note})</title>')
    svg.append(f'  <g transform="translate({pad:.2f},{pad:.2f})">')
    svg.append(f'    <g transform="translate({mark_x:.2f},{mark_y:.2f})">')
    svg.append(inner.rstrip())
    svg.append("    </g>")
    # ADI wordmark
    svg.append(
        f'    <g transform="translate({text_x:.2f},{adi_baseline:.2f})" '
        f'fill="currentColor">{adi_path}</g>')
    # descriptor
    svg.append(
        f'    <g transform="translate({desc_x:.2f},{d1_baseline:.2f})" '
        f'{desc_fill}>{d1_path}</g>')
    svg.append(
        f'    <g transform="translate({desc_x:.2f},{d2_baseline:.2f})" '
        f'{desc_fill}>{d2_path}</g>')
    svg.append("  </g>")
    svg.append("</svg>\n")
    return "\n".join(svg)


def favicon_mark_svg() -> str:
    """3×3 simplified mark for tiny sizes. One bold gold cell + graded greys,
    chunkier cells so it survives at 16px."""
    p = MarkParams(n=3, pad=0.12, gap=0.06, gold_cells=((1, 1),))
    return mark_svg(p, with_xmlns=True)


# ---------------------------------------------------------------------------
def main():
    p = MarkParams()
    (HERE / "adi-mark.svg").write_text(mark_svg(p))
    (HERE / "adi-mark-favicon.svg").write_text(favicon_mark_svg())
    (HERE / "adi-lockup-light.svg").write_text(lockup_svg(dark=False))
    (HERE / "adi-lockup-dark.svg").write_text(lockup_svg(dark=True))
    print("wrote:")
    for f in ["adi-mark.svg", "adi-mark-favicon.svg",
              "adi-lockup-light.svg", "adi-lockup-dark.svg"]:
        print("  ", HERE / f)


if __name__ == "__main__":
    main()
