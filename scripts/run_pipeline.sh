#!/usr/bin/env bash
# Ensure the ADI data store is populated and run the pipeline idempotently.
#
# The pipeline (`uv run run-pipeline default`) is itself idempotent — every fetch
# and process node skips work whose output already exists. This wrapper adds a
# guard so that, when the final outputs are ALREADY present, we do NOT invoke the
# pipeline at all (which would otherwise let the fetch nodes try to re-download
# the ~31 GB of raw inputs that are only needed to recompute missing outputs).
#
# Usage:
#   scripts/run_pipeline.sh            # no-op if outputs already complete
#   scripts/run_pipeline.sh --force    # always run the pipeline (idempotent)
#
# To (re)build everything from scratch you need the raw inputs in store/inputs/.
# If you only have the outputs (e.g. copied via rig-cp), that's enough for the
# website; you do not need to run the pipeline at all.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root
FORCE=0; [[ "${1:-}" == "--force" ]] && FORCE=1

RUN=default
OUT="store/outputs/$RUN"

# Heuristic completeness check: outputs exist for the full year range at LSOA level.
outputs_complete() {
  [[ -d "$OUT/lsoa/claimant_counts" ]] || return 1
  local n_cc n_cr n_he
  n_cc=$(ls "$OUT/lsoa/claimant_counts"/*.csv 2>/dev/null | wc -l)
  n_cr=$(ls "$OUT/lsoa/crime"/*.csv 2>/dev/null | wc -l)
  n_he=$(ls "$OUT/lsoa/health"/*.csv 2>/dev/null | wc -l)
  # default range 2014–2024 → 11 claimant + 11 crime files; health is NHS-year files
  [[ "$n_cc" -ge 11 && "$n_cr" -ge 11 && "$n_he" -ge 10 ]]
}

if [[ $FORCE -eq 0 ]] && outputs_complete; then
  echo "[pipeline] outputs already complete in $OUT — nothing to do."
  echo "[pipeline] (use --force to re-run the idempotent pipeline anyway)"
  exit 0
fi

if [[ ! -d store/inputs ]] && [[ $FORCE -eq 1 || ! -d "$OUT" ]]; then
  cat >&2 <<'EOF'
[pipeline] store/inputs/ is missing, so the pipeline would need to download the
raw data (several GB). If you only need the website, copy the outputs instead:

  rig-cp <data-machine>:.../store/outputs/default ./store/outputs/

Otherwise, ensure inputs are present (or let the fetch nodes download them) and
re-run with --force.
EOF
  exit 1
fi

echo "[pipeline] running idempotent pipeline (run=$RUN)…"
uv run run-pipeline "$RUN"
echo "[pipeline] done."
