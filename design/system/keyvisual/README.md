# ADI key visual

Hero / share-card key visual: an **authentic England choropleth** built as TRUE
vector from the real boundary file and the latest Claimant Count rate data in
the current site export, composed with the ADI lockup into an ONS-grade hero.

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
- `data/map/lad/employment/claimant_rate.json` — the first and last published
  years are read from `years`; values come from the latest year's row and align to…
- `data/codes/lad.json` `codes` — the canonical area order.
- `data/manifest.json` → `domains.employment.metrics[0].scale.breaks` — the 6
  class breaks → 7 colour classes.

Joined by `LAD25CD`. No-data areas fall back to `--grey-3` (#eee).

## Colour

- Fills use the locked **neutral slate sequential ramp** (`--seq-1..7`):
  `#f3f5f7 #d7dde3 #b3bdc7 #8b97a4 #636f7d #424b56 #262c33`. Gold is **not** the
  map.
- ONE restrained golden accent: the generator finds whichever LAD has the
  highest claimant rate in the latest published year and outlines it with a thin
  `#fbc441` stroke. The highlighted LAD and value are data-derived, not fixed.
  Plus the family golden hairline rule under the lockup.
- Area boundaries: white hairline on the light variant, ink hairline on dark.

## Projection

Equirectangular with a `cos(midLat)` x-correction (midLat ≈ 52.85°), y flipped,
fit-to-box preserving aspect — matches the site's `MiniChoropleth`. The map
occupies the left ~50%; the lockup + descriptor + legend sit on the right.

## Verification

Inspect regenerated assets at full 1200×630 and in the tracked
`../_proofs/kv-*` thumbnails at 600px and 300px: the silhouette should read
unmistakably as England, the "ADI" wordmark and descriptor should stay legible
at 300px, and the gold accent should appear once. The dark variant is used for
the OG card because it remains the most legible thumbnail. The general
`../_proofs/render_proofs.py` script does not generate these key-visual proofs;
the final block below creates them reproducibly from the full-size PNGs.

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

proofs=Path('../_proofs')
for v in ['light','dark']:
    image=Image.open(f'keyvisual-{v}.png').convert('RGB')
    for width in [600,300]:
        height=round(image.height*width/image.width)
        image.resize((width,height),Image.Resampling.LANCZOS).save(proofs/f'kv-{v}-{width}.png')
PY
```

> Note: the SVGs keep `currentColor` + `var(--adi-accent,#fbc441)` for the
> embedded mark; cairosvg can't resolve them, so the rasterizer substitutes the
> gold. The PNGs (incl. `og-image.png`) bake concrete colours — correct for a
> share card.
