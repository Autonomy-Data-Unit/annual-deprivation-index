#!/usr/bin/env python3
"""ADI domain line-icons — true-vector, hand-authored on a 24px grid.

Three domain icons matching ADU's golden line-icon style:
  employment → briefcase   (UC claimant counts)
  crime      → shield      (police-recorded street crime)
  health     → heart + pulse (GP disease prevalence)

House rules (consistent across the set):
  * 24×24 viewBox, content within a 20px live area (2px margin).
  * 1.5px stroke, stroke = currentColor (themes on light/dark; ADU renders
    these golden by setting `color:#fbc441`).
  * round joins/caps for the organic forms; square grid alignment.
  * No fills — pure line icons.

These are authored as clean path data (geometric, not traced). Emits one SVG
per icon + an icons-preview.html montage (ink + golden, light + dark).

uv run python icons_gen.py
"""
from __future__ import annotations
from pathlib import Path

HERE = Path(__file__).resolve().parent
SW = 1.5  # stroke width

SVG_HEAD = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    f'stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round" '
    'role="img" aria-label="{label}">\n'
    '  <title>{label}</title>\n'
)
SVG_TAIL = "</svg>\n"


def briefcase() -> str:
    """Employment — a briefcase: body rect, lid, handle, centre clasp."""
    paths = [
        # body of the case (square corners — ADU house style on the box,
        # but slight round join reads friendlier; keep sharp for rigor)
        '  <rect x="3" y="8" width="18" height="12" rx="0"/>',
        # handle: two uprights + top bar above the case
        '  <path d="M9 8 V6.5 a1.5 1.5 0 0 1 1.5 -1.5 h3 a1.5 1.5 0 0 1 1.5 1.5 V8"/>',
        # divider line across the case front
        '  <path d="M3 13 H21"/>',
        # centre clasp
        '  <path d="M11 12.25 h2 v1.5 h-2 z"/>',
    ]
    return SVG_HEAD.format(label="Employment") + "\n".join(paths) + "\n" + SVG_TAIL


def shield() -> str:
    """Crime — a shield outline with an inner check/keyhole-free band.
    Classic crest: top edge straight, sides taper to a point at the bottom."""
    paths = [
        # shield body
        '  <path d="M12 3 L20 6 V11 C20 16 16.5 19.5 12 21 '
        'C7.5 19.5 4 16 4 11 V6 Z"/>',
        # inner accent: a horizontal strata band (ties to the data motif)
        '  <path d="M7.5 10.5 H16.5"/>',
        '  <path d="M9 13.5 H15"/>',
    ]
    return SVG_HEAD.format(label="Crime") + "\n".join(paths) + "\n" + SVG_TAIL


def health() -> str:
    """Health — a heart with an ECG pulse line crossing it."""
    paths = [
        # heart outline (two arcs meeting at a bottom point)
        '  <path d="M12 20 '
        'C12 20 4 14.5 4 9 '
        'C4 6.5 5.9 5 8 5 '
        'C9.7 5 11.2 6 12 7.5 '
        'C12.8 6 14.3 5 16 5 '
        'C18.1 5 20 6.5 20 9 '
        'C20 14.5 12 20 12 20 Z"/>',
        # ECG pulse across the heart
        '  <path d="M5 12 H9 L10.5 9 L13 14.5 L14.5 12 H19"/>',
    ]
    return SVG_HEAD.format(label="Health") + "\n".join(paths) + "\n" + SVG_TAIL


ICONS = {
    "employment": briefcase,
    "crime": shield,
    "health": health,
}


def preview_html() -> str:
    rows = []
    for name in ICONS:
        rows.append(
            f'<div class="cell"><object data="{name}.svg" type="image/svg+xml" '
            f'width="48" height="48"></object><span>{name}</span></div>')
    grid = "\n".join(rows)
    return f"""<!doctype html>
<meta charset="utf-8">
<title>ADI icons preview</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; }}
  .band {{ display:flex; gap:32px; padding:32px; align-items:center; }}
  .ink   {{ background:#f8f8fa; color:#333333; }}
  .gold  {{ background:#f8f8fa; color:#fbc441; }}
  .dark  {{ background:#333333; color:#ffffff; }}
  .darkgold {{ background:#333333; color:#fbc441; }}
  .cell {{ display:flex; flex-direction:column; align-items:center; gap:8px;
           font-size:12px; }}
  h3 {{ font-family:Georgia,serif; margin:24px 32px 0; }}
  .label {{ width:120px; font-weight:600; font-size:13px; }}
</style>
<h3>ADI domain line-icons — 24px grid, 1.5px stroke, currentColor</h3>
<div class="band ink"><span class="label">ink #333 / bg</span>{grid}</div>
<div class="band gold"><span class="label">golden #fbc441 / bg</span>{grid}</div>
<div class="band dark"><span class="label">paper / charcoal</span>{grid}</div>
<div class="band darkgold"><span class="label">golden / charcoal</span>{grid}</div>
"""


def main():
    for name, fn in ICONS.items():
        (HERE / f"{name}.svg").write_text(fn())
    (HERE / "icons-preview.html").write_text(preview_html())
    print("wrote", ", ".join(f"{n}.svg" for n in ICONS), "+ icons-preview.html")


if __name__ == "__main__":
    main()
