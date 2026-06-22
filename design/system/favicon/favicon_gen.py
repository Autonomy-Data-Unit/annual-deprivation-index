#!/usr/bin/env python3
"""Generate favicon assets from the ADI mark.

Favicons render in browser chrome where currentColor / CSS vars don't apply,
so these bake concrete colours: charcoal ink (#333) outline, white tile field,
golden accent cell, on a white rounded-free square. Derived from the SAME
parametric mark geometry (mark_gen) — single source of truth.

  favicon.svg          — scalable, 3×3 (legible when the browser downscales)
  favicon-16.png       — 3×3 (4×4 silts up at 16px; verified)
  favicon-32.png       — 3×3
  apple-touch-icon-180.png — full 4×4 mark on a white field with safe padding

uv run --with cairosvg --with pillow --with fonttools --with uharfbuzz python favicon_gen.py
"""
from __future__ import annotations
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "logo"))
from mark_gen import MarkParams, mark_svg, _grey_for, SEQ  # noqa: E402

import cairosvg
from PIL import Image

INK = "#333333"
GOLD = "#fbc441"
PAPER = "#ffffff"

def _concrete(svg: str) -> str:
    """Resolve themeable handles to concrete favicon colours."""
    svg = svg.replace("var(--adi-accent, #fbc441)", GOLD)
    svg = svg.replace("currentColor", INK)
    return svg

def favicon_svg(n: int = 3, field: bool = True) -> str:
    """A self-contained favicon SVG: optional white field behind the mark, then
    the mark with concrete colours."""
    if n == 3:
        p = MarkParams(n=3, pad=0.12, gap=0.06, gold_cells=((1, 1),))
    else:
        p = MarkParams()
    body = _concrete(mark_svg(p, with_xmlns=True))
    if not field:
        return body
    # insert a white field rect just after the opening <svg ...> tag
    head, rest = body.split(">", 1)
    field_rect = f'>\n  <rect x="0" y="0" width="{p.U:.0f}" height="{p.U:.0f}" fill="{PAPER}"/>'
    return head + field_rect + rest

def to_png(svg: str, size: int, out: Path, bg=None):
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size,
                           output_height=size,
                           background_color="rgba(0,0,0,0)")
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    if bg is not None:
        canvas = Image.new("RGBA", (size, size), bg)
        canvas.alpha_composite(img)
        img = canvas
    img.convert("RGB" if bg else "RGBA").save(out)

def apple_touch_svg() -> str:
    """180px touch icon: full 4×4 mark, white field, ~14% safe padding so the
    mark isn't flush to the rounded mask iOS applies."""
    p = MarkParams()
    U = p.U
    pad = U * 0.16
    inner = _concrete(mark_svg(p, with_xmlns=False))
    inner = inner.split(">", 1)[1].rsplit("</svg>", 1)[0]
    inner = inner.replace(
        "  <title>ADI — Annual Deprivation Index</title>\n", "")
    side = U + pad * 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {side:.0f} {side:.0f}">\n'
        f'  <rect width="{side:.0f}" height="{side:.0f}" fill="{PAPER}"/>\n'
        f'  <g transform="translate({pad:.2f},{pad:.2f})">\n{inner}\n  </g>\n'
        f'</svg>\n'
    )

def main():
    (HERE / "favicon.svg").write_text(favicon_svg(n=3, field=True))
    svg3 = favicon_svg(n=3, field=True)
    to_png(svg3, 16, HERE / "favicon-16.png", bg=(255, 255, 255, 255))
    to_png(svg3, 32, HERE / "favicon-32.png", bg=(255, 255, 255, 255))
    to_png(apple_touch_svg(), 180, HERE / "apple-touch-icon-180.png",
           bg=(255, 255, 255, 255))
    print("wrote favicon.svg, favicon-16.png, favicon-32.png, "
          "apple-touch-icon-180.png")

if __name__ == "__main__":
    main()
