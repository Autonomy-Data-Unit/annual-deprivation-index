#!/usr/bin/env bash
# Build all web data + assets the ADI site needs from the ADI store:
#   - geometry (PMTiles + GeoJSON)  [slow; skipped if already present unless --force]
#   - compact JSON data (map values, area profiles, dashboard, imd)
#   - copy locked design assets (favicons, brand SVGs) into static/
# Safe to re-run. Requires: store/outputs/default populated; node (npx), tippecanoe, uv.
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root
FORCE=0; [[ "${1:-}" == "--force" ]] && FORCE=1

if [[ ! -d store/outputs/default/lsoa ]]; then
  echo "ERROR: store/outputs/default not found. Populate the store first:" >&2
  echo "  scripts/run_pipeline.sh        # or rig-cp the store from the data machine" >&2
  exit 1
fi

# 1. geometry (expensive — skip if present)
if [[ $FORCE -eq 1 || ! -f site/static/tiles/lsoa.pmtiles ]]; then
  echo "[web] building geometry (PMTiles + GeoJSON)…"
  bash site/scripts/build_geo.sh
else
  echo "[web] geometry present — skipping (use --force to rebuild)"
fi

# 2. compact web data
if [[ $FORCE -eq 1 || ! -f site/static/data/manifest.json || ! -f site/static/data/imd.json || ! -f site/static/data/area/lad.json ]]; then
  echo "[web] building compact data…"
  uv run --with pandas --with numpy --with scipy python -u site/scripts/build_data.py
else
  echo "[web] compact data present — skipping (use --force to rebuild)"
fi

# 3. design assets → static
echo "[web] copying design assets…"
mkdir -p site/static/brand
cp design/system/logo/adi-mark.svg design/system/logo/adi-mark-favicon.svg \
   design/system/logo/adi-lockup-light.svg design/system/logo/adi-lockup-dark.svg site/static/brand/
cp design/system/favicon/favicon.svg design/system/favicon/favicon-32.png \
   design/system/favicon/favicon-16.png design/system/favicon/apple-touch-icon-180.png site/static/
cp design/system/keyvisual/og-image.png site/static/og-image.png
cp design/system/keyvisual/keyvisual-light.png design/system/keyvisual/keyvisual-dark.png site/static/brand/ 2>/dev/null || true
cp design/system/tokens/tokens.css site/src/lib/styles/tokens.css

echo "[web] done. static payload:"
du -sh site/static/data site/static/tiles site/static/geo 2>/dev/null | sed 's/^/  /'
