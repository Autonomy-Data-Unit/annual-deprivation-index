# CLAUDE.md

## Project Overview

**annual-deprivation-index-v2** (ADI v2) is a productionised rewrite of the Annual Deprivation Index, a multi-domain deprivation index for England that provides **annual** measurements at the LSOA (Lower Layer Super Output Area) level. It complements the government's Index of Multiple Deprivation (IMD), which is only updated every few years, by using annually-available administrative data sources.

The pipeline produces three independent domain sub-indices — **employment** (Universal Credit claimant counts), **crime** (police-recorded street crime), and **health** (GP-level disease prevalence mapped to LSOAs via patient registration data) — output as a multi-index at four geography levels (LSOA, LAD, Region, England). The pipeline does not combine these into a single composite score; that is left to downstream analysis.

The old repo at `/Users/lukas/dev/20250623_000000_rLaVV__annual-deprivation-index/old_repo/` used manual Jupyter notebooks and spatial intersection for health estimation. This rewrite uses **netrun** for orchestration, **nblite** for literate programming, and direct GP-LSOA patient registration data (no spatial computation needed).

## Year Coverage

The binding constraint is the GP-LSOA patient registration data (starts April 2014):

| Domain | Source | Available from | LSOA Vintage |
|---|---|---|---|
| Claimant counts | Nomis `NM_162_1` | 2013 | LSOA 2011 only (historical data unavailable at LSOA 2021) |
| Crime | data.police.uk | 2011 | LSOA 2011 |
| Health (QOF) | NHS Digital | QOF 2013-14 onward (CSV) | Per-practice (no LSOA) |
| Health (GP-LSOA) | NHS Digital | April 2014 onward | LSOA 2011 (LSOA 2021 only from April 2025) |
| Population (LSOA 2011) | Nomis `NM_2010_1` | 2011-2020 | LSOA 2011 |
| Population (LSOA 2021) | Nomis `NM_2014_1` | 2011-2024 | LSOA 2021 |

**Earliest year with all three domains: 2014.** Default `year_start` is 2014.

For years 2021+, LSOA 2011 population data is unavailable from Nomis; the pipeline falls back to the 2020 estimate.

## Data Sources

### Employment Domain: Claimant Counts

- **Source:** [Nomis](https://www.nomisweb.co.uk/datasets/ucjsa) — Universal Credit claimant counts
- **Dataset:** `NM_162_1`, geography `TYPE298` (LSOA 2011). Historical data is only available at LSOA 2011.
- **Download:** Nomis REST API, paginated at 25k rows. No auth required.
- **Granularity:** Monthly counts per LSOA, averaged to annual by the processing node.
- **Notes:** Welsh LSOAs filtered. Nomis suppresses counts below 5 (returned as empty); treated as 0.

### Crime Domain

- **Source:** [data.police.uk](https://data.police.uk/data/archive/)
- **Download:** Archive ZIPs at `https://data.police.uk/data/archive/{YYYY}-{MM}.zip` (~1.6 GB each, 36-month rolling window). No auth required.
- **Granularity:** Per-incident with LSOA 2011 codes, aggregated to annual counts per LSOA per crime type (14 types).

### Health Domain

Two data sources are combined:

**QOF (Quality and Outcomes Framework):**
- **Source:** [NHS Digital](https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data)
- **Download:** Scrape publication pages with `httpx` + `BeautifulSoup` (server-side rendered, no JS). Download CSV ZIP files.
- **Content:** Per-GP-practice disease register counts and list populations. 21 disease subdomains (AF, AST, CAN, CHD, CKD, COPD, DEM, DEP, DM, EP, HF, HYP, LD, MH, NDH, OB, OST, PAD, PC, RA, STIA). Disease codes change across years (see `config/qof_schemas.toml`).

**GP-LSOA Patient Registrations:**
- **Source:** [NHS Digital Patients Registered at a GP Practice](https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice)
- **Download:** Same scraping approach. Download the LSOA-level ZIP for each April edition.
- **Content:** Per-practice, per-LSOA patient counts (`PRACTICE_CODE, LSOA_CODE, patients`). Tells us exactly how many patients from each LSOA are registered at each GP.
- **Available:** April 2014 onward. Column names vary across eras (normalised by `fetch_gp_catchments`).

### Reference Data

- **LSOA populations:** Nomis REST API. Both LSOA 2011 (`NM_2010_1`, 2011-2020) and LSOA 2021 (`NM_2014_1`, 2011-2024). The 2020 LSOA 2011 file is always downloaded as a fallback.
- **LSOA boundaries:** ONS ArcGIS REST API. Generalised Clipped (BGC) version, 35,672 LSOA 2021 features.
- **Geographic lookups:** ONS ArcGIS REST API. `LSOA21_WD25_LAD25_EW_LU_v2` (LSOA to LAD), `LAD25_RGN25_EN_LU_v2` (LAD to Region).
- **LSOA crosswalk:** ONS `LSOA11_LSOA21_LAD22_EW_LU_v5` (exact-fit with change indicators U/S/M/X).

## Pipeline Architecture

13 nodes, 14 edges. All nodes are async function nodes running on the main thread.

### Node Graph

```
fetch_populations ──────────┐
fetch_claimant_counts ──────┤
fetch_crime ────────────────┼─> join_fetch ─> broadcast_ready ─┬─> process_claimant_counts ─┐
fetch_qof ──────────────────┤                                  ├─> process_crime ────────── ├─> join_domains ─> aggregate
fetch_gp_catchments ────────┤                                  └─> process_health ───────── ┘
fetch_geo ──────────────────┘
```

### Fetch Nodes (6, parallel, `run_on_init`)

All idempotent — skip files that already exist. Use `asyncio.gather()` for within-node parallelism.

| Node | Source | What it downloads |
|---|---|---|
| `fetch_populations` | Nomis API | LSOA 2021 populations (all years) + LSOA 2011 populations (2011-2020, always includes 2020 fallback) |
| `fetch_claimant_counts` | Nomis API | Monthly claimant counts at LSOA 2011, one CSV per year |
| `fetch_crime` | data.police.uk | December archives, extracted in place |
| `fetch_qof` | NHS Digital (scraped) | QOF prevalence CSV ZIPs, one per year |
| `fetch_gp_catchments` | NHS Digital (scraped) | LSOA-level GP patient registrations, one CSV per April edition |
| `fetch_geo` | ONS ArcGIS API | LSOA boundaries, LSOA-to-LAD, LAD-to-Region, LSOA crosswalk, OA crosswalk, OA-to-LSOA |

### Processing Nodes (3)

All output in **LSOA 2011** vintage (source data constraint). Include both absolute counts and populations for crosswalk compatibility.

**`process_claimant_counts`**: Load monthly Nomis data, filter Welsh LSOAs, average to annual, merge with LSOA 2011 population, compute `claimant_rate = count / pop`. Output: `LSOA11CD, LSOA11NM, claimant_count, pop, claimant_rate`.

**`process_crime`**: Concatenate monthly per-force street CSVs, filter Welsh/null LSOAs, aggregate by LSOA and crime type, merge with population, compute per-capita rates. Output: `LSOA11CD, LSOA11NM, {14 crime type counts}, pop, {14 crime type rates}`.

**`process_health`**: The most complex node. Steps:
1. **Normalise QOF data** using config-driven schema mapping (`config/qof_schemas.toml`)
2. **Load GP-LSOA patient registrations** for the matching April edition
3. **Estimate LSOA prevalence**: For each LSOA, weight = (patients from this LSOA at GP k) / (total patients at GP k). LSOA prevalence = weighted average of each GP's disease register / list population.
4. **Temporal interpolation** across years (vectorised): fill NaN gaps of ≤2 consecutive years via linear interpolation (interior) or linear regression extrapolation (leading/trailing).

Output: `LSOA11CD, {21 disease}_prevalence_rate, {21 disease}_afflicted, list_pop, pop`.

### Aggregate Node

1. **Build crosswalk**: LSOA 2011 → LSOA 2021 using exact-fit lookup. Unchanged (U): weight 1.0. Splits (S): weight by LSOA 2021 population proportion. Merges (M): weight 1.0 (values summed). Complex (X): excluded.
2. **Apply crosswalk**: Disaggregate absolute counts using weights, reaggregate to LSOA 2021, recompute rates.
3. **Geographic aggregation**: Sum counts and populations to LAD (296), Region (9), England (1). Recompute rates at each level.
4. **Output**: `store/outputs/{run_name}/{lsoa,lad,region,england}/{domain}/{file}.csv`

### Storage Convention

- **`store/inputs/`** — Downloaded raw data (run-independent, idempotent)
- **`store/pipeline/{run_name}/`** — Intermediate outputs in LSOA 2011 vintage
- **`store/outputs/{run_name}/`** — Final outputs in LSOA 2021 vintage at all geography levels

## Project Structure

```
├── CLAUDE.md
├── pyproject.toml
├── nblite.toml
├── config/
│   ├── netrun.json              # 13-node pipeline DAG
│   ├── run_defs.toml            # Run definitions (year_start, year_end, lsoa_vintage)
│   └── qof_schemas.toml         # QOF column mappings per year era
│
│   ## nblite-managed (edit pts/, export to nbs/ and src/)
├── pts/adi/nodes/               # Node notebooks (.pct.py) — EDIT THESE
│   ├── fetch_populations.pct.py
│   ├── fetch_claimant_counts.pct.py
│   ├── fetch_crime.pct.py
│   ├── fetch_qof.pct.py
│   ├── fetch_gp_catchments.pct.py
│   ├── fetch_geo.pct.py
│   ├── process_claimant_counts.pct.py
│   ├── process_crime.pct.py
│   ├── process_health.pct.py
│   └── aggregate.pct.py
├── nbs/adi/nodes/               # Auto-generated .ipynb
├── src/adi/nodes/               # Auto-generated .py modules
│
│   ## Plain Python (edit src/ directly)
├── src/adi/
│   ├── __init__.py
│   ├── const.py                 # Path constants
│   ├── run_pipeline.py          # Pipeline runner + CLI entry point
│   └── utils/
│       ├── nomis.py             # Nomis REST API client (paginated async)
│       ├── ons.py               # ONS ArcGIS REST API client (paginated async)
│       ├── scrape.py            # NHS Digital page scraping + police.uk URLs (async)
│       ├── qof.py               # QOF schema loading (stubs)
│       └── geo.py               # LSOA crosswalk + geographic aggregation
├── src/dev_utils/               # set_node_func_args, show_node_vars
│
├── store/                       # Runtime data (gitignored)
└── dev/                         # Agent context, recipes, templates
```

## Tech Stack

- **Python 3.12+**, **uv** — Package management
- **netrun** (>=0.5.0) — Pipeline orchestration
- **nblite** (>=1.1.12) — Literate programming
- **pandas** — Data manipulation
- **numpy** — Numerical operations
- **scipy** — Linear regression for temporal interpolation
- **httpx** — Async HTTP for all downloads and scraping
- **beautifulsoup4** — HTML parsing for NHS Digital pages
- **geopandas** / **shapely** — LSOA boundary download (not used for health estimation)
- **openpyxl** / **xlrd** — Available for Excel file reading

## Running the Pipeline

```bash
uv run run-pipeline default     # Full run (2014-2024)
uv run run-pipeline test        # Quick test (2022-2023)
```

Run definitions in `config/run_defs.toml`:
```toml
[defaults]
lsoa_vintage = "2021"
year_start = 2014
year_end = 2024

[runs.test]
year_start = 2022
year_end = 2023
```

## Development Workflow

### Where to edit code

- **Node code:** Edit `.pct.py` files in `pts/adi/nodes/`, then run `nbl export --reverse && nbl export`
- **Utilities:** Edit directly in `src/adi/utils/`
- **Constants / runner:** Edit directly in `src/adi/`

### Key commands

```bash
nbl export --reverse && nbl export   # Sync notebooks after editing .pct.py
uv run netrun validate -c config/netrun.json   # Validate pipeline graph
uv run run-pipeline test             # Quick integration test
```

### Node function conventions

- All nodes use `async def main(ctx, print, ...) -> bool` with `#|export_as_func true`
- Return `True` (required for netrun `out` port creation)
- Access config via `ctx.vars["var_name"]` (never `.get()`)
- Use bare `await` in notebooks (never `asyncio.run()`)

## LSOA Vintage and Crosswalk

Domain processors output in **LSOA 2011** (source data constraint). The `aggregate` node converts to **LSOA 2021** using a population-weighted crosswalk:

| Change | Count | Method |
|---|---|---|
| Unchanged (U) | 33,647 | Direct 1:1 mapping, weight = 1.0 |
| Split (S) | 861 → 1,900 | Weight by LSOA 2021 population proportion |
| Merged (M) | 239 → 119 | Sum values, weight = 1.0 |
| Complex (X) | 6 → 6 | Excluded |

Crosswalk is applied to **absolute counts and populations separately**. Rates are recomputed after disaggregation. Never disaggregate rates directly.

## QOF Schema Normalisation

Raw QOF data has different column schemas across years. The mapping is config-driven via `config/qof_schemas.toml`. Four CSV eras (2013-14 onward):

| Era | Years | Key differences |
|---|---|---|
| 1 | 2013-14 | Lowercase columns, `disease_register_size`, duplicate HF rows |
| 2 | 2014-15 | cp1252 encoding |
| 3 | 2015-20 | `INDICATOR_GROUP_CODE` → `GROUP_CODE` in 2019-20 |
| 4 | 2020+ | `PRACTICE_LIST_SIZE` (not `PATIENT_`), multiple `PATIENT_LIST_TYPE`, `NDH` added |

Pre-2013 (Excel format) is not supported; the GP-LSOA data doesn't exist for those years anyway.

## Conventions

- **No silent fallbacks:** Use `d["key"]`, never `.get(key, default)`.
- **Node variables:** Defaults in `run_defs.toml`, types in `netrun.json`. Access via `ctx.vars["var_name"]`.
- **Idempotent nodes:** All fetch and process nodes skip work if output already exists.
- **Counts + populations:** Domain outputs always include absolute counts AND population columns, never just rates.
