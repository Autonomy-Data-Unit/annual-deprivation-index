#!/usr/bin/env bash
# Build the ADI website and deploy it to the adu-apps AppGarden.
#   → https://adi.apps.autonomy.work
#
# Steps: build web data/assets (idempotent) → npm build → appgarden deploy.
#
# Usage:
#   scripts/deploy.sh                 # build + deploy
#   scripts/deploy.sh --force-data    # also rebuild geometry/data from the store
#   scripts/deploy.sh --build-only    # build, don't deploy
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

FORCE_DATA=0; BUILD_ONLY=0
for a in "$@"; do
  case "$a" in
    --force-data) FORCE_DATA=1 ;;
    --build-only) BUILD_ONLY=1 ;;
    *) echo "unknown arg: $a" >&2; exit 1 ;;
  esac
done

APP=adi
SERVER=adu-apps
SUBDOMAIN=adi

# 1. web data + assets
if [[ $FORCE_DATA -eq 1 ]]; then
  bash site/scripts/build_web.sh --force
else
  bash site/scripts/build_web.sh
fi

# 2. install + build the SvelteKit site
echo "[deploy] installing deps + building site…"
cd site
if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
npm run build
cd ..

echo "[deploy] build size:"; du -sh site/build | sed 's/^/  /'

if [[ $BUILD_ONLY -eq 1 ]]; then
  echo "[deploy] --build-only: skipping deploy. Output in site/build/"
  exit 0
fi

# 3. deploy to AppGarden (static)
echo "[deploy] deploying '$APP' to $SUBDOMAIN.apps.autonomy.work via $SERVER…"
appgarden deploy --server "$SERVER" --name "$APP" --method static \
  --source site/build --subdomain "$SUBDOMAIN"

echo "[deploy] done → https://$SUBDOMAIN.apps.autonomy.work"
