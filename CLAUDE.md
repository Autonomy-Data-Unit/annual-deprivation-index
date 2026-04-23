# CLAUDE.md

## Project Overview

**annual-deprivation-index-v2** (ADI v2) is a productionised rewrite of the Annual Deprivation Index, a multi-domain deprivation index for England that provides **annual** measurements at the LSOA (Lower Layer Super Output Area) level. It complements the government's Index of Multiple Deprivation (IMD), which is only updated every few years, by using annually-available administrative data sources.

The pipeline produces three independent domain sub-indices — **employment** (Universal Credit claimant counts), **crime** (police-recorded street crime), and **health** (GP-level disease prevalence mapped to LSOAs via spatial intersection with catchment areas) — output as a multi-index. The pipeline does not combine these into a single composite score; that is left to downstream analysis.

The old repo lives at `/Users/lukas/dev/20250623_000000_rLaVV__annual-deprivation-index/old_repo/` and consisted of a sequence of manually-run Jupyter notebooks (Python + R). This rewrite restructures the pipeline using **netrun** for orchestration and **nblite** for literate programming.

## Data Sources

### Employment Domain: Claimant Counts

- **Source:** [Nomis](https://www.nomisweb.co.uk/datasets/ucjsa) — Universal Credit claimant counts
- **Nomis dataset ID:** `NM_162_1`
- **Download method:** Nomis REST API (no auth required, 25k cell limit per request — paginate)
- **API example:** `https://www.nomisweb.co.uk/api/v01/dataset/NM_162_1.data.csv?geography=TYPE151&time=latest&gender=0&age=0&measure=1&measures=20100&select=geography_code,geography_name,date_name,obs_value`
- **Granularity:** Monthly counts per LSOA, averaged to annual
- **Available from:** 2013 onward
- **Supports LSOA 2021:** Yes (`geography=TYPE151`)
- **Output per LSOA:** `claimant_count`, `claimant_rate` (count / population)
- **Notes:** Welsh LSOAs (codes starting with 'W') are excluded. Rate can exceed 1.0.

### Crime Domain

- **Source:** [data.police.uk](https://data.police.uk/data/archive/) — street-level crime data
- **Download method:** Direct archive download, no auth required
- **URL pattern:** `https://data.police.uk/data/archive/{YYYY}-{MM}.zip` (redirects to S3)
- **Granularity:** Per-incident with LSOA codes, aggregated to annual counts per crime type per LSOA
- **Available from:** 2011 onward (December 2010)
- **Crime types (14):** Anti-social behaviour, Bicycle theft, Burglary, Criminal damage and arson, Drugs, Other crime, Other theft, Possession of weapons, Public order, Robbery, Shoplifting, Theft from the person, Vehicle crime, Violence and sexual offences
- **Output per LSOA:** count and per-capita rate for each crime type
- **Notes:** Each archive contains ~36 months of rolling data (~1.6 GB). Archives overlap; the pipeline must deduplicate. Crime data currently reports LSOA 2011 codes. Welsh LSOAs excluded.

### Health Domain: Quality and Outcomes Framework (QOF)

- **Source:** [NHS Digital QOF](https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data) — GP practice-level disease prevalence
- **Download method:** Scrape publication pages with `requests` + `BeautifulSoup` (pages are server-side rendered, no JS needed). Download links follow `https://files.digital.nhs.uk/{hex}/{hex}/{filename}`. No auth required.
- **Publication page pattern:** `https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data/{YYYY-YY}`
- **Granularity:** Per GP practice, per disease domain. Must be spatially mapped to LSOAs using GP catchment areas.
- **Available from:** 2006-07 onward
- **Output per LSOA:** `{disease}_prevalence_rate`, `{disease}_afflicted` for each subdomain

#### QOF Column Mapping Across Years

Raw QOF data has **5 distinct column schemas**. A consolidated mapping config (`config/qof_schemas.toml`) maps each year to its column names:

| Era | Years | Practice Code | Register | List Pop | Disease Code | Encoding | Notes |
|---|---|---|---|---|---|---|---|
| Pre-2013 | 2006-13 | varies | varies | varies | varies | varies | Excel format, different disease codes (`MENT`, `DEP1`, `CVD-PP`, `HFLVD`) |
| Era 1 | 2013-14 | `practicecode` | `disease_register_size` | `practice_listsize` | `indicator_group` | UTF-8 | Duplicate HF rows; extra groups SMOK, THY |
| Era 2 | 2014-15 | `PRACTICE_CODE` | `REGISTER_SIZE` | `PRACTICE_LIST_SIZE` | `INDICATOR_GROUP_CODE` | **cp1252** | Windows encoding |
| Era 3 | 2015-20 | `PRACTICE_CODE` | `REGISTER` | `PATIENT_LIST_SIZE` | `INDICATOR_GROUP_CODE` / `GROUP_CODE` | UTF-8 | 2019-20 switches to `GROUP_CODE` |
| Era 4 | 2020-22 | `PRACTICE_CODE` | `REGISTER` | `PRACTICE_LIST_SIZE` | `GROUP_CODE` | UTF-8 | Multiple `PATIENT_LIST_TYPE` per practice; `CVDPP` removed, `NDH` added |

Disease group codes also change over time: `SMOK`/`THY` only in 2013-14; `CVDPP` dropped and `NDH` added in 2020-21; pre-2013 uses entirely different codes.

### GP Catchment Areas

- **Source:** [NHS Digital GP data collections](https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice)
- **Download method:** Same scraping approach as QOF (server-side rendered pages, `requests` + `BeautifulSoup`)
- **Publication page pattern:** `https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice/{month-year}`
- **Format:** KML (2020 data) or GeoJSON (2023 data)
- **Purpose:** Defines the geographic footprint of each GP practice, used to spatially map QOF data to LSOAs
- **Notes:** Some entries have implausibly large catchment areas and must be filtered (e.g. "LANCELOT MEDICAL CENTRE" at 17.5 billion sq meters). The old repo used 2020 catchment areas for years 2011-2020 and switched to 2023 catchment areas for 2021+. NHS Digital publishes both LSOA 2011 and LSOA 2021 versions.

### Reference Data

- **LSOA populations (mid-year estimates):** Nomis REST API. Two datasets: `NM_2010_1` (LSOA 2011, mid-2011 to mid-2020, no longer updated) and `NM_2014_1` (LSOA 2021, mid-2011 to mid-2024, actively updated). Query pattern: `https://www.nomisweb.co.uk/api/v01/dataset/{ID}.data.csv?geography={TYPE}&date=latest&gender=0&c_age=200&measures=20100`
- **LSOA boundaries:** ONS Open Geography Portal ArcGIS REST API. Paginate at 2k records. Services: `Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5` (LSOA 2021 generalised clipped, 35,672 records) and `LSOA_Dec_2011_Boundaries_Generalised_Clipped_BGC_EW_V3` (LSOA 2011, 34,753 records). Use the Generalised Clipped (BGC) version for analysis.
- **Geographic lookup tables:** ONS ArcGIS REST API. Key services: `LSOA21_WD25_LAD25_EW_LU_v2` (LSOA 2021 to LAD 2025), `LSOA11_LSOA21_LAD22_EW_LU_v5` (exact-fit crosswalk with change indicators).
- **LSOA crosswalk data:** See "LSOA Vintage and Crosswalk" section below.
- **IMD data:** IMD 2015 and IMD 2019 for validation/comparison only (not part of the pipeline output).

## Pipeline Architecture

The pipeline is defined as a **netrun** graph. All nodes are async function nodes running on the main thread. Async is used for I/O-bound operations (file reads, network requests); computation runs synchronously.

### Node Graph

```
fetch_data ──> broadcast_data_ready ──┬──> process_claimant_counts ──┐
                                      ├──> process_crime ─────────── ├──> join_domains ──> aggregate
                                      └──> process_health ────────── ┘
```

**7 nodes total** (5 function nodes + 1 broadcast + 1 join):

#### `fetch_data`

Downloads and caches all raw data sources to `store/inputs/`. Uses async I/O for parallel downloads. Idempotent: skips files already present.

Data to fetch:
- Claimant count CSVs from Nomis REST API
- Crime archives from data.police.uk
- QOF prevalence data scraped from NHS Digital publication pages
- GP catchment area geodata scraped from NHS Digital
- LSOA population estimates from Nomis REST API
- LSOA boundary GeoJSON from ONS ArcGIS REST API
- Geographic lookup tables from ONS ArcGIS REST API
- LSOA crosswalk data (OA-level lookups and populations) from ONS ArcGIS REST API

#### `broadcast_data_ready`

Infrastructure node (netrun broadcast factory). Fan-out from `fetch_data` to the three processing nodes.

#### `process_claimant_counts`

Reads raw claimant count CSVs and LSOA population data from `store/inputs/`. For each year:
1. Parse LSOA codes, remove Welsh LSOAs
2. Average monthly counts to annual
3. Merge with population data to compute `claimant_rate = claimant_count / pop`
4. Save per-year CSV to `store/pipeline/{run_name}/claimant_counts/`

Output is in **source LSOA vintage** (whatever the Nomis data reports).

#### `process_crime`

Reads raw street crime data and LSOA population data from `store/inputs/`. For each year:
1. Concatenate all monthly per-force CSVs
2. Remove non-England entries
3. Aggregate counts by LSOA and crime type
4. Compute per-capita rates
5. Save per-year CSV to `store/pipeline/{run_name}/crime/`

Output is in **source LSOA vintage** (currently LSOA 2011 from police.uk).

#### `process_health`

The most complex node. Reads QOF data, GP catchment areas, LSOA boundaries, and population data from `store/inputs/`. Steps:

1. **Parse QOF data:** Load raw files and apply the column mapping from `config/qof_schemas.toml` to produce a standardised schema (practice code, list population, disease domain prevalences). Both raw and standardised data are kept.
2. **Clean GP catchment areas:** Load geodata, compute polygon areas (spherical geometry), remove outlier practices with implausibly large catchment areas.
3. **Compute LSOA-GP spatial intersections:** For each LSOA, find nearby GP catchment areas (by centroid distance), compute geometric intersection areas. Cache as `.npy` for reuse.
4. **Estimate LSOA health prevalence:** Distribute GP patient populations to LSOAs proportionally by intersection area. For LSOAs with no GP overlap, fill from spatial neighbours (iterative averaging).
5. **Interpolate missing data:** Fill temporal gaps in health subdomains using linear interpolation (interior gaps) or linear regression extrapolation (boundary gaps), max gap size 2 consecutive years.
6. Save per-year CSV to `store/pipeline/{run_name}/health/`

Output is in **source LSOA vintage** (whichever boundary shapefile was used for the spatial intersection).

#### `join_domains`

Infrastructure node (netrun join factory). Synchronisation barrier: waits for all three processing nodes to complete.

#### `aggregate`

Reads domain outputs from `store/pipeline/{run_name}/`. For each year:
1. **Convert LSOA vintage:** Apply OA-level population-weighted crosswalk to convert all domains to the target LSOA vintage (configured via `lsoa_vintage`). See "LSOA Vintage and Crosswalk" section.
2. **Aggregate** to four geography levels: LSOA (identity), LAD, Region, England
   - Sum absolute counts across constituent areas
   - Recompute rates from summed counts / summed populations
3. Save final multi-index outputs to `store/outputs/`

Domain outputs must include **both absolute counts and populations** (not just rates), since rates cannot be disaggregated correctly — numerator and denominator must be disaggregated separately and the rate recomputed.

### Storage Convention

Three tiers mirroring the AISI project:
- **`store/inputs/`** — Run-independent raw/downloaded data
- **`store/pipeline/{run_name}/`** — Run-specific intermediate outputs (in source LSOA vintage)
- **`store/outputs/`** — Final output files (in target LSOA vintage)

## Project Structure

```
├── CLAUDE.md                        # This file
├── nblite.toml                      # nblite export pipeline config
├── pyproject.toml                   # Package config (uv)
├── config/
│   ├── netrun.json                  # Pipeline DAG definition
│   └── run_defs.toml                # Run definitions (year ranges, data paths, etc.)
│
│   ## nblite-managed (edit pts/, export to nbs/ and src/)
├── pts/adi/nodes/                   # Node notebooks (.pct.py) — EDIT THESE
├── nbs/adi/nodes/                   # Node notebooks (.ipynb, auto-generated)
├── src/adi/nodes/                   # Node modules (.py, auto-generated)
│
│   ## Plain Python (edit src/ directly)
├── src/adi/
│   ├── __init__.py
│   ├── const.py                     # Path constants
│   ├── run_pipeline.py              # Pipeline runner
│   └── utils/                       # Shared utilities
│       ├── __init__.py
│       ├── geo.py                   # Spatial intersection, polygon area, neighbour fill
│       ├── qof.py                   # QOF data parsing across year formats
│       └── data.py                  # Data loading/downloading helpers
│
├── store/                           # Runtime data (gitignored)
│   ├── inputs/                      # Downloaded raw data
│   ├── pipeline/{run_name}/         # Run-specific intermediates
│   └── outputs/                     # Final outputs
│
└── dev/                             # Development utilities
    ├── agent-context/               # netrun & nblite reference docs
    ├── recipes/                     # netrun-ui recipes
    ├── scripts/
    └── templates/                   # Node notebook template
```

## Tech Stack

- **Python 3.12+**
- **uv** — Package management
- **netrun** — Flow-based pipeline orchestration
- **nblite** (>=1.1.12) — Notebook-driven literate programming
- **pandas** — Data manipulation
- **geopandas** / **shapely** — Spatial operations (LSOA-GP intersections, boundary operations)
- **numpy** — Numerical operations, intersection caching
- **aiohttp** / **httpx** — Async HTTP for data downloads
- **openpyxl** / **xlrd** — Reading QOF Excel files (pre-2013 years)
- **requests** / **beautifulsoup4** — Scraping NHS Digital publication pages for download URLs

## Development Workflow

### Where to edit code

- **Node code:** Edit `.pct.py` files in `pts/adi/nodes/`, then run `nbl export --reverse && nbl export`
- **Shared utilities:** Edit directly in `src/adi/utils/`
- **Constants:** Edit directly in `src/adi/const.py`
- **Pipeline runner:** Edit directly in `src/adi/run_pipeline.py`
- **`__init__.py` files:** Edit directly in `src/` (nblite skips dunder files)

### nblite commands

```bash
nbl export                    # Export nbs -> pts -> src
nbl export --reverse          # Sync pts changes back to nbs
nbl test                      # Test notebooks execute
nbl new pts/adi/nodes/foo.pct.py  # Create new node notebook
```

### Running the pipeline

```bash
uv run run-pipeline [run_name]
```

### Validating config changes

```bash
uv run netrun validate -c config/netrun.json
```

## LSOA Vintage and Crosswalk

The pipeline supports configurable LSOA vintage (2011 or 2021) via `lsoa_vintage` in `run_defs.toml`. Domain processors output data in **source vintage** (whatever their data source reports). The `aggregate` node converts everything to the **target vintage** before outputting.

### The 2011→2021 Boundary Changes

96.8% of LSOAs are unchanged between 2011 and 2021:

| Change Type | Code | LSOA 2011 | LSOA 2021 |
|---|---|---|---|
| Unchanged | U | 33,647 | 33,647 |
| Split | S | 861 → | 1,900 |
| Merged | M | 239 → | 119 |
| Complex | X | 6 → | 6 |

Most splits are 1-into-2 (728 of 861). Almost all merges are 2-into-1 (118 of 119). Complex changes (6 LSOAs) involve local authority boundary redesigns and cannot be mapped exactly.

### Crosswalk Method: OA-Level Population Apportionment

We use the ONS gold-standard approach: Output Area (OA) level population-weighted apportionment. This produces a sparse proportions table:

| source_lsoa | target_lsoa | weight |
|---|---|---|
| E01000001 | E01000001 | 1.0 |
| E01000010 | E01034474 | 0.63 |
| E01000010 | E01034475 | 0.37 |

**Construction steps:**
1. Download OA-to-LSOA lookups for both vintages (`OA_LSOA_MSOA_EW_DEC_2021_LU_v3` and equivalent 2011 lookup)
2. Download OA 2011-to-2021 exact-fit lookup (`OA11_OA21_LAD22_EW_LU_Exact_fit_V3`, 175k+ rows with change indicators)
3. Download OA-level population (Census 2021)
4. For each source LSOA, trace through its constituent OAs to target LSOAs, weighting by OA population

This table is computed **once** during `fetch_data` and cached in `store/inputs/crosswalk/`. For unchanged LSOAs (96.8%), it's a single row with weight 1.0, so application is efficient.

**Applying the crosswalk** (in `aggregate` node): For each domain, disaggregate absolute counts using the weights, then reaggregate to target LSOAs. Recompute rates from disaggregated numerators and denominators. Do NOT disaggregate rates directly.

Complex (X) changes (6 LSOAs) are excluded with a warning.

### ONS Data Sources for Crosswalk

All available via ONS ArcGIS REST API (no auth, paginate at 2k records):

| Table | Service Name | Purpose |
|---|---|---|
| LSOA exact-fit lookup | `LSOA11_LSOA21_LAD22_EW_LU_v5` | Change indicators (U/S/M/X), 35,796 rows |
| OA exact-fit lookup | `OA11_OA21_LAD22_EW_LU_Exact_fit_V3` | OA-level mapping, 175k+ rows |
| OA-to-LSOA 2021 | `OA_LSOA_MSOA_EW_DEC_2021_LU_v3` | OA21 → LSOA21 membership |
| LSOA 2021 to LAD | `LSOA21_WD25_LAD25_EW_LU_v2` | For geographic aggregation |

## Key Algorithms

### Spatial Health Estimation

GP catchment areas are polygons defining each practice's geographic footprint. To estimate LSOA-level disease prevalence:

1. For each LSOA, find the ~2000 nearest GP catchment areas by centroid distance (Mercator projection)
2. Compute geometric intersection area between the LSOA polygon and each GP catchment polygon
3. Distribute GP patients to the LSOA proportionally by `intersection_area / total_catchment_area`
4. Compute weighted prevalence: `sum(afflicted_weighted) / sum(list_pop_weighted)`
5. For LSOAs with zero GP overlap: iteratively assign the average prevalence of spatially adjacent LSOAs

### Spherical Polygon Area

GP catchment area filtering uses spherical area computation (Green's Theorem on a sphere, radius 6,378,137m) rather than planar approximation, since catchment areas span significant latitudes across England.

### Temporal Interpolation (Health Domain)

Health subdomains have missing data across years (some diseases not tracked in some years, some practices missing). Gaps are filled by:
- **Interior gaps (max 2 consecutive):** Linear interpolation between surrounding values
- **Leading/trailing gaps:** Linear regression extrapolation from nearest available data points
- NaN boundaries (subdomain not tracked that year) are not interpolated across

### QOF Schema Normalisation

Raw QOF data is normalised using a config-driven approach. Each year's schema is defined in `config/qof_schemas.toml`:

```toml
[years.2013_14]
practice_code_col = "practicecode"
register_col = "disease_register_size"
list_pop_col = "practice_listsize"
disease_code_col = "indicator_group"
encoding = "utf-8"
file_pattern = "PREVALENCE_1314.csv"

[years.2020_21]
practice_code_col = "PRACTICE_CODE"
register_col = "REGISTER"
list_pop_col = "PRACTICE_LIST_SIZE"
disease_code_col = "GROUP_CODE"
encoding = "utf-8"
file_pattern = "QOF2021_v2/PREVALENCE_2021_v2.csv"
list_type_filter = "TOTAL"
```

A single parser function reads the config for a given year, applies the column mapping, and outputs the standardised schema: `practice_code, list_pop, {disease_code_1}, {disease_code_2}, ...`. If the config-driven approach proves insufficient for some years (e.g. the pre-2013 Excel formats), separate processing nodes per year range can be used instead.

## Conventions

### No Silent Fallbacks

Use direct key access (`d["key"]`), never `.get(key, default)`, for data expected to exist. Missing data should fail loudly.

### Node Variables

All node variable defaults go in `config/run_defs.toml`, not in `config/netrun.json`. The JSON only declares names and types. Access via `ctx.vars["var_name"]` in node code.

### Top-level await

Notebooks run in an async context. Use bare `await` for async calls, never `asyncio.run()`.

## Reference: Old Repository

The original implementation is at `/Users/lukas/dev/20250623_000000_rLaVV__annual-deprivation-index/old_repo/`.

Helper files: `crime_helpers.py` (crime aggregation), `health_helpers.py` (spatial intersection, polygon area, health domain computation).
