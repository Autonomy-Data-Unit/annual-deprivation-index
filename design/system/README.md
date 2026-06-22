# ADI Design System

Production design assets for the **Annual Deprivation Index (ADI)**, a data
product of the **Autonomy Data Unit (ADU)** at the Autonomy Institute. ADI sits
under the ADU / ASPECTT family system — charcoal header, white letter-spaced
wordmark, golden hairline rule, square-outline mark, quiet white cards, golden
line-icons — extended for ADI's geographic + temporal + multi-domain data.

Design direction is **locked: Direction A — choropleth grid** (see
`_dev/design/orchestration/DECISIONS.md`). All assets here are TRUE vector,
generated parametrically (single source of truth), themeable, and verified by
rendering.

## Layout

```
design/system/
├── tokens/   tokens.css            — palette, type scale, spacing, ramps
├── logo/     mark_gen.py           — parametric mark + lockup generator
│             adi-mark.svg          — 4×4 choropleth-grid mark
│             adi-mark-favicon.svg  — 3×3 simplified mark (tiny sizes)
│             adi-lockup-light.svg  — mark + ADI wordmark + descriptor (light bg)
│             adi-lockup-dark.svg   — same, for charcoal backgrounds
├── favicon/  favicon_gen.py        — derives favicons from the mark
│             favicon.svg, favicon-16.png, favicon-32.png,
│             apple-touch-icon-180.png
├── icons/    icons_gen.py          — domain line-icons
│             employment.svg crime.svg health.svg
│             icons-preview.html
├── _proofs/  render_proofs.py + rendered PNG proofs
└── README.md
```

Regenerate everything:

```bash
cd design/system/logo    && uv run --with fonttools --with uharfbuzz python mark_gen.py
cd design/system/favicon && uv run --with cairosvg --with pillow --with fonttools --with uharfbuzz python favicon_gen.py
cd design/system/icons   && uv run python icons_gen.py
cd design/system/_proofs && uv run --with cairosvg --with pillow python render_proofs.py
```

## Theming contract

Every asset is themeable by the same contract:

- **Ink renders with `currentColor`** — set `color` on the SVG (or a parent) to
  retint. Use `#333` (`--ink`) on light, `#fff` (`--paper`) on dark.
- **The golden accent is `var(--adi-accent, #fbc441)`** — overridable, defaults
  to the Autonomy golden. Used SPARINGLY (two cells in the mark; never the map).

The mark, lockups and icons all work on **light (`#fff` / `#f8f8fa`) and dark
(`#333`) backgrounds** — verified in `_proofs/`.

> Note: `var()` and `currentColor` are CSS features. `cairosvg` (used for the
> PNG proofs) doesn't resolve them, so the proof scripts substitute concrete
> colours at render time. The shipped SVGs keep the themeable handles. The
> baked PNG favicons use concrete colours by design (browser chrome can't theme).

## Choropleth ramps

The map data surface uses a **neutral sequential ramp**; golden is reserved for
UI accents and is **never** the base map colour. Change maps use a **diverging
ramp** that is deliberately not golden.

### Sequential — cool slate (pale → charcoal)

A single restrained hue with a slight blue cast, so the data surface reads quiet
and ONS-like, distinct from both the warm golden accent and from neutral UI
greys. 7 steps; use the 5-step subset (1, 2, 4, 6, 7) for coarse legends.

| Step | Hex | Token |
|---|---|---|
| 1 (lowest) | `#f3f5f7` | `--seq-1` |
| 2 | `#d7dde3` | `--seq-2` |
| 3 | `#b3bdc7` | `--seq-3` |
| 4 | `#8b97a4` | `--seq-4` |
| 5 | `#636f7d` | `--seq-5` |
| 6 | `#424b56` | `--seq-6` |
| 7 (highest) | `#262c33` | `--seq-7` |

No-data fill: `--map-nodata` (`#eeeeee`). Area boundaries: `--map-stroke`
(white on light, ink on dark).

### Diverging — teal ←→ rust (for change maps)

For signed change (e.g. ADI claimant-rate Δ, or IMD-rank Δ). Teal = improvement
/ fall, neutral grey midpoint = no change, rust = worsening / rise. Colour-blind
-safe teal/orange family, muted to sit under the quiet surface. Not golden — the
accent stays a UI colour.

| Step | Hex | Token | Meaning |
|---|---|---|---|
| −3 | `#1f6f6b` | `--div-neg-3` | strong improvement |
| −2 | `#4f9a93` | `--div-neg-2` | |
| −1 | `#97c4bf` | `--div-neg-1` | |
| 0 | `#eceef0` | `--div-0` | no change |
| +1 | `#e0b48f` | `--div-pos-1` | |
| +2 | `#c77f4d` | `--div-pos-2` | |
| +3 | `#9c4a22` | `--div-pos-3` | strong worsening |

### Domain hues (labels only)

Restrained tints to label the three domains in chips / legends — **not** the
choropleth surface: employment `#b8860b` (ochre), crime `#6b5b95`
(slate-violet), health `#2f7d6f` (teal). See `--domain-*` in `tokens.css`.

## Type

- **IBM Plex Serif Bold** — the "ADI" wordmark (matches the ASPECTT serif feel).
- **IBM Plex Sans Medium** — the "Annual Deprivation Index" descriptor.
- **IBM Plex Sans** — body, UI, data labels, numerals; **IBM Plex Mono** for
  tabular figures.

Wordmark text in the lockups is **outlined** (HarfBuzz shaping → fontTools
outlines), so the SVGs carry no font dependency. The site still needs the IBM
Plex web fonts loaded for body/UI text.

## Logo usage

- `adi-mark.svg` — the standalone 4×4 mark. Use at ≥ 24px. Themeable.
- For favicons and any use ≤ 16px, use the **3×3 variant** (`adi-mark-favicon.svg`
  / the favicon PNGs) — the 4×4 grid silts up below ~20px (verified).
- `adi-lockup-light.svg` on light surfaces; `adi-lockup-dark.svg` on the
  charcoal header. Keep clear space ≥ the mark's outline tile around the lockup.
- Sharp corners only. Do not round the mark or add a drop shadow.

## Favicon legibility

Verified by rendering at true 16/32px and inspecting pixels (`_proofs/`):
the 3×3 mark with a single gold centre cell is legible at 16px; the 4×4 mark is
not, and is reserved for ≥ 24px and the 180px apple-touch icon.
