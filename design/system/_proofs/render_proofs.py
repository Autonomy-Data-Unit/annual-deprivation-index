#!/usr/bin/env python3
"""Render all SVG assets to PNG proofs at real sizes, on light AND dark
backgrounds, and assemble montages for visual verification.

uv run --with cairosvg --with pillow python render_proofs.py
"""
from __future__ import annotations
from pathlib import Path
import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent      # design/system
PROOFS = Path(__file__).resolve().parent
PROOFS.mkdir(exist_ok=True)

LIGHT = (255, 255, 255, 255)
BG = (248, 248, 250, 255)      # --bg
DARK = (51, 51, 51, 255)       # --ink
INK = "#333333"
PAPER = "#ffffff"
ACCENT = "#fbc441"

def _resolve(svg: str, color: str) -> str:
    """cairosvg can't parse CSS var()/currentColor in fills — resolve them for
    proofing only. The shipped SVGs keep the themeable var()/currentColor."""
    svg = svg.replace("var(--adi-accent, #fbc441)", ACCENT)
    svg = svg.replace("var(--adi-accent,#fbc441)", ACCENT)
    svg = svg.replace('style="color:CC"', "")  # guard
    return svg.replace("<svg ", f'<svg style="color:{color}" ', 1)

def render(svg_path: Path, out: Path, size: int, bg, color: str):
    """Rasterize an SVG at `size`px square onto a solid bg, with currentColor
    resolved to `color` by wrapping the svg root style."""
    svg = _resolve(svg_path.read_text(), color)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size,
                           output_height=size, background_color="rgba(0,0,0,0)")
    fg = Image.open(__import__("io").BytesIO(png)).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), bg)
    canvas.alpha_composite(fg)
    canvas.convert("RGB").save(out)
    return canvas

def render_w(svg_path: Path, out: Path, width: int, bg, color: str):
    """Render preserving aspect ratio at given pixel width."""
    svg = _resolve(svg_path.read_text(), color)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=width,
                           background_color="rgba(0,0,0,0)")
    fg = Image.open(__import__("io").BytesIO(png)).convert("RGBA")
    canvas = Image.new("RGBA", fg.size, bg)
    canvas.alpha_composite(fg)
    canvas.convert("RGB").save(out)
    return canvas

def montage(images, out, cols, pad=16, bgcol=(230, 230, 234)):
    if not images:
        return
    cell_w = max(im.width for im in images)
    cell_h = max(im.height for im in images)
    rows = (len(images) + cols - 1) // cols
    W = cols * cell_w + (cols + 1) * pad
    H = rows * cell_h + (rows + 1) * pad
    canvas = Image.new("RGB", (W, H), bgcol)
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (cell_w + pad) + (cell_w - im.width) // 2
        y = pad + r * (cell_h + pad) + (cell_h - im.height) // 2
        canvas.paste(im.convert("RGB"), (x, y))
    canvas.save(out)

def main():
    logo = ROOT / "logo"
    fav = ROOT / "favicon"
    icons = ROOT / "icons"

    # --- Mark at many sizes on light + dark ---
    imgs = []
    for size in [256, 64, 32, 16]:
        imgs.append(render(logo / "adi-mark.svg",
                           PROOFS / f"mark-{size}-light.png", size, BG, INK))
    for size in [256, 64, 32, 16]:
        imgs.append(render(logo / "adi-mark.svg",
                           PROOFS / f"mark-{size}-dark.png", size, DARK, PAPER))
    montage([Image.open(PROOFS / f"mark-{s}-light.png") for s in [256,64,32,16]]
            + [Image.open(PROOFS / f"mark-{s}-dark.png") for s in [256,64,32,16]],
            PROOFS / "_montage-mark.png", cols=4)

    # --- Favicon 3x3 variant at tiny sizes ---
    for size in [32, 16]:
        render(logo / "adi-mark-favicon.svg",
               PROOFS / f"favmark-{size}-light.png", size, PAPER, INK)
        render(logo / "adi-mark-favicon.svg",
               PROOFS / f"favmark-{size}-dark.png", size, DARK, PAPER)
    # compare 4x4 vs 3x3 at 16/32
    cmp = []
    for s in [16, 32]:
        cmp.append(Image.open(PROOFS / f"mark-{s}-light.png").resize((128,128), Image.NEAREST))
        cmp.append(Image.open(PROOFS / f"favmark-{s}-light.png").resize((128,128), Image.NEAREST))
    montage(cmp, PROOFS / "_montage-favicon-compare.png", cols=2)

    # --- Lockups ---
    render_w(logo / "adi-lockup-light.svg", PROOFS / "lockup-light.png",
             900, BG, INK)
    render_w(logo / "adi-lockup-dark.svg", PROOFS / "lockup-dark.png",
             900, DARK, PAPER)
    # small lockup (header height ~ 40px tall)
    render_w(logo / "adi-lockup-light.svg", PROOFS / "lockup-light-sm.png",
             360, BG, INK)
    li = Image.open(PROOFS / "lockup-light.png")
    ld = Image.open(PROOFS / "lockup-dark.png")
    montage([li, ld], PROOFS / "_montage-lockup.png", cols=1)

    print("rendered proofs to", PROOFS)

if __name__ == "__main__":
    main()
