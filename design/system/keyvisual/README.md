# ADI key visual

Hero / share-card key visual: an **authentic England choropleth** built as TRUE
vector from the real boundary file and real 2024 Universal Credit claimant-rate
data, composed with the ADI lockup into an ONS-grade hero.

## Files

| File | What |
|---|---|
| `keyvisual_gen.py` | Generator. Reads the real data, projects, emits `<path>` per LAD. |
| `keyvisual-light.svg` / `.png` | Light variant (on `#f8f8fa`), 1200×630. |
| `keyvisual-dark.svg` / `.png` | Dark variant (on `#333`), 1200×630. |
| `og-image.png` | **Social/share card, exactly 1200×630** — the **dark** variant (chosen: highest contrast, most legible as a thumbnail). |

## Data sources (all real, from `site/static/`)

- `geo/lad.geojson` — 296 Local Authority Districts, `properties.LAD25CD`
  (239 Polygon + 57 MultiPolygon, both handled).
- `data/map/lad/employment/claimant_rate.json` — `values[last_year_index]`
  (2024) aligned to…
- `data/codes/lad.json` `codes` — the canonical area order.
- `data/manifest.json` → `domains.employment.metrics[0].scale.breaks` — the 6
  class breaks → 7 colour classes.

Joined by `LAD25CD`. No-data areas fall back to `--grey-3` (#eee).

## Colour

- Fills use the locked **neutral slate sequential ramp** (`--seq-1..7`):
  `#f3f5f7 #d7dde3 #b3bdc7 #8b97a4 #636f7d #424b56 #262c33`. Gold is **not** the
  map.
- ONE restrained golden accent: a single highlighted area —
  **Birmingham**, the LAD with the highest 2024 claimant rate (6.4%) — outlined
  with a thin `#fbc441` stroke. Plus the family golden hairline rule under the
  lockup.
- Area boundaries: white hairline on the light variant, ink hairline on dark.

## Projection

Equirectangular with a `cos(midLat)` x-correction (midLat ≈ 52.85°), y flipped,
fit-to-box preserving aspect — matches the site's `MiniChoropleth`. The map
occupies the left ~50%; the lockup + descriptor + legend sit on the right.

## Verification

Rendered at full 1200×630 and thumbnailed to ~600px and ~300px and inspected
(`_proofs/kv-*`): the silhouette reads unmistakably as England, the "ADI"
wordmark + descriptor stay legible at 300px, and the gold accent appears once.
Dark chosen for the OG card on the small-thumbnail legibility test.

Regenerate:

```bash
cd design/system/keyvisual && uv run --with fonttools --with uharfbuzz python keyvisual_gen.py
# then rasterize (var()/currentColor substituted for cairosvg):
uv run --with cairosvg --with pillow python - <<'PY'
import cairosvg, io; from PIL import Image; from pathlib import Path
for v in ['light','dark']:
    svg=Path(f'keyvisual-{v}.svg').read_text().replace('var(--adi-accent, #fbc441)','#fbc441')
    Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(),output_width=1200,output_height=630))).convert('RGB').save(f'keyvisual-{v}.png')
svg=Path('keyvisual-dark.svg').read_text().replace('var(--adi-accent, #fbc441)','#fbc441')
Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(),output_width=1200,output_height=630))).convert('RGB').save('og-image.png')
PY
```

> Note: the SVGs keep `currentColor` + `var(--adi-accent,#fbc441)` for the
> embedded mark; cairosvg can't resolve them, so the rasterizer substitutes the
> gold. The PNGs (incl. `og-image.png`) bake concrete colours — correct for a
> share card.
