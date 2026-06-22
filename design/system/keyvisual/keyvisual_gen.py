#!/usr/bin/env python3
"""ADI key visual — authentic England choropleth hero, TRUE vector.

Reads the REAL boundary file + REAL 2024 Universal Credit claimant-rate values
and emits clean <path> per LAD, coloured by the locked neutral slate sequential
ramp (gold is NOT the map). Composes a proper hero: choropleth motif + ADI
lockup + descriptor + ONE restrained golden accent (a single highlighted area
with a thin gold outline). Light and dark variants.

Data (relative to repo `site/static/`):
  geo/lad.geojson                              296 LADs, props.LAD25CD
  data/map/lad/employment/claimant_rate.json   {years, values[year][areaIdx]}
  data/codes/lad.json                          {codes, names}  (canonical order)
  data/manifest.json   domains.employment.metrics[0].scale.breaks (6 → 7 classes)

Projection matches the site's MiniChoropleth: equirectangular with a
cos(midLat) x-correction, y flipped, fit to a target box.

uv run --with fonttools --with uharfbuzz python keyvisual_gen.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                       # annual-deprivation-index/
STATIC = REPO / "site" / "static"
sys.path.insert(0, str(HERE.parent / "logo"))
from mark_gen import MarkParams, mark_svg, _shape_to_path, \
    FONT_SERIF_BOLD, FONT_SANS_MEDIUM, FONT_SANS_REGULAR  # noqa: E402

# Locked neutral slate sequential ramp (tokens.css --seq-*). 7 classes.
SEQ = ["#f3f5f7", "#d7dde3", "#b3bdc7", "#8b97a4",
       "#636f7d", "#424b56", "#262c33"]
GOLD = "#fbc441"
GOLD_DEEP = "#eab843"
INK = "#333333"
PAPER = "#ffffff"
BG = "#f8f8fa"
GREY1 = "#898989"
NODATA = "#eeeeee"


def load_data():
    geo = json.loads((STATIC / "geo" / "lad.geojson").read_text())
    cr = json.loads(
        (STATIC / "data/map/lad/employment/claimant_rate.json").read_text())
    codes = json.loads((STATIC / "data/codes/lad.json").read_text())
    manifest = json.loads((STATIC / "data/manifest.json").read_text())
    breaks = manifest["domains"]["employment"]["metrics"][0]["scale"]["breaks"]
    last_idx = len(cr["years"]) - 1
    code_to_val = {}
    for i, code in enumerate(codes["codes"]):
        code_to_val[code] = cr["values"][last_idx][i]
    code_to_name = dict(zip(codes["codes"], codes["names"]))
    return geo, code_to_val, code_to_name, breaks, cr["years"][last_idx]


def class_of(v: float, breaks: list[float]) -> int:
    """Return ramp index 0..len(breaks) for value v."""
    for i, b in enumerate(breaks):
        if v < b:
            return i
    return len(breaks)


class Projector:
    """Equirectangular with cos(midLat) correction, fit to a box (w,h) with
    padding, preserving aspect. Matches MiniChoropleth."""
    def __init__(self, geo, w, h, pad):
        minx = miny = 1e9
        maxx = maxy = -1e9
        def walk(c):
            nonlocal minx, miny, maxx, maxy
            if isinstance(c[0], (int, float)):
                minx = min(minx, c[0]); maxx = max(maxx, c[0])
                miny = min(miny, c[1]); maxy = max(maxy, c[1])
            else:
                for cc in c:
                    walk(cc)
        for f in geo["features"]:
            walk(f["geometry"]["coordinates"])
        self.midlat = (miny + maxy) / 2
        self.kx = math.cos(math.radians(self.midlat))
        # projected extents
        px_min, px_max = minx * self.kx, maxx * self.kx
        gw = px_max - px_min
        gh = maxy - miny
        avail_w = w - 2 * pad
        avail_h = h - 2 * pad
        self.s = min(avail_w / gw, avail_h / gh)
        # centre within box
        self.ox = pad + (avail_w - gw * self.s) / 2
        self.oy = pad + (avail_h - gh * self.s) / 2
        self.px_min = px_min
        self.maxy = maxy
        self.w, self.h = w, h

    def pt(self, lon, lat):
        x = self.ox + (lon * self.kx - self.px_min) * self.s
        y = self.oy + (self.maxy - lat) * self.s   # flip y
        return x, y


def ring_to_path(ring, proj) -> str:
    pts = [proj.pt(lon, lat) for lon, lat in ring]
    # round to 1dp to keep file small; drop consecutive dupes
    d = []
    last = None
    for i, (x, y) in enumerate(pts):
        xy = (round(x, 1), round(y, 1))
        if xy == last:
            continue
        d.append(("M" if i == 0 else "L") + f"{xy[0]} {xy[1]}")
        last = xy
    return " ".join(d) + " Z"


def feature_path(feat, proj) -> str:
    g = feat["geometry"]
    parts = []
    if g["type"] == "Polygon":
        for ring in g["coordinates"]:
            parts.append(ring_to_path(ring, proj))
    else:  # MultiPolygon
        for poly in g["coordinates"]:
            for ring in poly:
                parts.append(ring_to_path(ring, proj))
    return " ".join(parts)


# ---------------------------------------------------------------------------
def build_map_svg(geo, code_to_val, breaks, proj, *, highlight_code=None,
                  dark=False) -> tuple[str, str | None]:
    """Return (group_of_paths, highlight_path_d). Fills use the slate ramp;
    boundaries are a hairline in the surface colour so areas separate cleanly."""
    stroke = INK if dark else PAPER
    paths = []
    hl_d = None
    for f in geo["features"]:
        code = f["properties"]["LAD25CD"]
        d = feature_path(f, proj)
        v = code_to_val.get(code)
        if v is None:
            fill = NODATA
        else:
            fill = SEQ[class_of(v, breaks)]
        paths.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="0.4"/>')
        if code == highlight_code:
            hl_d = d
    return "\n".join(paths), hl_d


def compose(dark: bool) -> str:
    geo, code_to_val, code_to_name, breaks, year = load_data()

    W, H = 1200, 630
    # Map occupies the left ~55%; text block on the right.
    map_box_w = 600
    proj = Projector(geo, map_box_w, H, pad=70)

    # Choose the highlight: the LAD with the highest 2024 claimant rate present
    # in the geometry — the single golden accent. (One area, thin gold outline.)
    geo_codes = {f["properties"]["LAD25CD"] for f in geo["features"]}
    cand = {c: v for c, v in code_to_val.items() if c in geo_codes}
    highlight_code = max(cand, key=cand.get)
    highlight_name = code_to_name[highlight_code]
    highlight_val = cand[highlight_code]

    map_group, hl_d = build_map_svg(
        geo, code_to_val, breaks, proj, highlight_code=highlight_code,
        dark=dark)

    ink = PAPER if dark else INK
    sub = "#bdbdbd" if dark else GREY1
    bg = INK if dark else BG

    # ---- Text block (right) ----
    tx = map_box_w + 36
    # ADI lockup mark + wordmark
    mp = MarkParams()
    mark_inner = mark_svg(mp, with_xmlns=False)
    mark_inner = mark_inner.split(">", 1)[1].rsplit("</svg>", 1)[0]
    mark_inner = mark_inner.replace(
        "  <title>ADI — Annual Deprivation Index</title>\n", "")
    mark_size = 64

    adi_path, adi_w = _shape_to_path("ADI", FONT_SERIF_BOLD, 88)
    desc1, _ = _shape_to_path("Annual Deprivation Index",
                              FONT_SANS_MEDIUM, 30)
    sub1, _ = _shape_to_path(f"England · Lower-layer Super Output Areas",
                             FONT_SANS_REGULAR, 19)
    sub2, _ = _shape_to_path("Employment · Crime · Health · "
                             "2014–2024", FONT_SANS_REGULAR, 19)
    cap, _ = _shape_to_path(
        f"Universal Credit claimant rate, {year}", FONT_SANS_MEDIUM, 17)
    hlcap, _ = _shape_to_path(
        f"{highlight_name} · {highlight_val*100:.1f}%",
        FONT_SANS_REGULAR, 16)

    # vertical rhythm
    y_mark = 150
    y_adi_base = y_mark + 56          # ADI cap band aligned to mark centre-ish
    y_desc = y_adi_base + 58
    y_sub1 = y_desc + 44
    y_sub2 = y_sub1 + 28
    y_rule = y_sub2 + 30
    y_legend = y_rule + 40
    y_cap = y_legend - 14

    # golden hairline rule (family cue)
    rule = (f'<rect x="{tx}" y="{y_rule}" width="430" height="2" '
            f'fill="{GOLD}"/>')

    # legend: 7 slate swatches + labels (low → high)
    sw = 30
    leg = [f'<g transform="translate({tx},{y_legend})">']
    for i, c in enumerate(SEQ):
        leg.append(f'<rect x="{i*sw}" y="0" width="{sw}" height="14" '
                   f'fill="{c}" stroke="{bg}" stroke-width="0.5"/>')
    low, _ = _shape_to_path("lower", FONT_SANS_REGULAR, 14)
    high, _ = _shape_to_path("higher", FONT_SANS_REGULAR, 14)
    leg.append(f'<g transform="translate(0,32)" fill="{sub}">{low}</g>')
    leg.append(f'<g transform="translate({7*sw},32)" '
               f'text-anchor="end"><g transform="translate(-46,0)" '
               f'fill="{sub}">{high}</g></g>')
    leg.append("</g>")
    legend = "\n".join(leg)

    # highlight outline on the map (the one golden accent)
    hl = ""
    if hl_d:
        hl = (f'<path d="{hl_d}" fill="none" stroke="{GOLD}" '
              f'stroke-width="2.5" stroke-linejoin="round"/>')

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="ADI — Annual Deprivation Index, England choropleth">')
    parts.append(f'<title>ADI — Annual Deprivation Index</title>')
    parts.append(f'<rect width="{W}" height="{H}" fill="{bg}"/>')
    # map
    parts.append(f'<g>{map_group}</g>')
    parts.append(hl)
    # caption under highlight area name (top-right of map block)
    parts.append(
        f'<g transform="translate({tx},{y_cap})" fill="{sub}">{cap}</g>')
    # mark
    parts.append(
        f'<g transform="translate({tx},{y_mark}) '
        f'scale({mark_size/100.0})" style="color:{ink}">{mark_inner}</g>')
    # ADI wordmark
    parts.append(
        f'<g transform="translate({tx+mark_size+22},{y_adi_base})" '
        f'fill="{ink}">{adi_path}</g>')
    # descriptor
    parts.append(
        f'<g transform="translate({tx},{y_desc})" fill="{ink}">{desc1}</g>')
    # subtitles
    parts.append(
        f'<g transform="translate({tx},{y_sub1})" fill="{sub}">{sub1}</g>')
    parts.append(
        f'<g transform="translate({tx},{y_sub2})" fill="{sub}">{sub2}</g>')
    parts.append(rule)
    parts.append(legend)
    # highlight caption near the legend
    parts.append(
        f'<g transform="translate({tx},{y_legend+70})" fill="{sub}">'
        f'<g transform="translate(0,0)">'
        f'<rect x="0" y="-11" width="11" height="11" fill="none" '
        f'stroke="{GOLD}" stroke-width="2"/>'
        f'<g transform="translate(18,0)" fill="{sub}">{hlcap}</g></g></g>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def main():
    (HERE / "keyvisual-light.svg").write_text(compose(dark=False))
    (HERE / "keyvisual-dark.svg").write_text(compose(dark=True))
    print("wrote keyvisual-light.svg, keyvisual-dark.svg")


if __name__ == "__main__":
    main()
