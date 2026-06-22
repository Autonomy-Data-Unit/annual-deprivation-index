#!/usr/bin/env bash
# Build web geometry from ONS LSOA 2021 boundaries:
#   - England LSOA, joined to LAD + Region lookups        -> intermediate
#   - LSOA  -> PMTiles vector tiles (tippecanoe)
#   - LAD   -> simplified GeoJSON (dissolve LSOA by LAD25CD)
#   - Region-> simplified GeoJSON (dissolve LAD by RGN25CD)
# Idempotent-ish: overwrites outputs. Requires mapshaper (npx) + tippecanoe.
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

IN_LSOA=store/inputs/lsoa_boundaries/lsoa_2021_bgc.geojson
LU_LAD=store/inputs/geo_lookups/lsoa21_to_lad25.csv
LU_RGN=store/inputs/geo_lookups/lad25_to_rgn25.csv
OUT=site/static/geo
TILES=site/static/tiles
TMP=site/scripts/.geo_tmp
mkdir -p "$OUT" "$TILES" "$TMP"

echo "[geo] 1/5 filter England LSOA + join LAD/Region lookups"
npx -y mapshaper "$IN_LSOA" \
  -filter "LSOA21CD.indexOf('E01')===0" \
  -join "$LU_LAD" keys=LSOA21CD,LSOA21CD fields=LAD25CD,LAD25NM \
  -join "$LU_RGN" keys=LAD25CD,LAD25CD fields=RGN25CD,RGN25NM \
  -filter-fields LSOA21CD,LSOA21NM,LAD25CD,LAD25NM,RGN25CD,RGN25NM \
  -o "$TMP/lsoa_eng.geojson" force

echo "[geo] 2/5 LSOA -> PMTiles (tippecanoe)"
# Keep only the code in tiles (name fetched from data on click); promoteId=LSOA21CD at runtime.
npx -y mapshaper "$TMP/lsoa_eng.geojson" -filter-fields LSOA21CD \
  -o "$TMP/lsoa_tiles_src.geojson" force
tippecanoe -o "$TILES/lsoa.pmtiles" -l lsoa \
  -Z4 -z12 --coalesce-densest-as-needed --simplification=10 \
  --no-tile-size-limit --hilbert --force \
  "$TMP/lsoa_tiles_src.geojson"

echo "[geo] 3/5 LSOA -> simplified LSOA GeoJSON (for low-zoom / fallback, optional)"
# (skipped: PMTiles is the LSOA source)

echo "[geo] 4/5 dissolve -> LAD GeoJSON"
npx -y mapshaper "$TMP/lsoa_eng.geojson" \
  -dissolve2 LAD25CD copy-fields=LAD25NM,RGN25CD,RGN25NM \
  -simplify 6% keep-shapes \
  -clean \
  -o "$OUT/lad.geojson" force

echo "[geo] 5/5 dissolve -> Region GeoJSON"
npx -y mapshaper "$OUT/lad.geojson" \
  -dissolve2 RGN25CD copy-fields=RGN25NM \
  -simplify 8% keep-shapes \
  -clean \
  -o "$OUT/region.geojson" force

echo "[geo] sizes:"
ls -lh "$TILES/lsoa.pmtiles" "$OUT/lad.geojson" "$OUT/region.geojson" | awk '{print "  ", $5, $9}'
echo "[geo] done"
