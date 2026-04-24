# Annual Deprivation Index v2

A productionised pipeline for computing an **Annual Deprivation Index** (ADI) for England at the LSOA level. It complements the government's [Index of Multiple Deprivation](https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019) (IMD), which is only updated every few years, by using annually-available administrative data sources to produce yearly measurements from 2014 onward.

The pipeline produces three independent domain sub-indices:

| Domain | Source | Metric |
|---|---|---|
| **Employment** | Universal Credit claimant counts ([Nomis](https://www.nomisweb.co.uk/datasets/ucjsa)) | Claimant rate per LSOA |
| **Crime** | Police-recorded street crime ([data.police.uk](https://data.police.uk/data/archive/)) | Per-capita rates across 14 crime types |
| **Health** | GP disease prevalence ([QOF](https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data)) weighted by [GP-LSOA patient registrations](https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice) | Estimated prevalence rates for 21 disease groups |

Outputs are available at four geography levels: **LSOA** (32,844), **LAD** (296), **Region** (9), and **England** (1). The pipeline does not combine domains into a single composite score; that is left to downstream analysis.

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Run the full pipeline (2014-2024) — downloads all data, processes, and aggregates
uv run run-pipeline default

# Run a quick test (2022-2023 only)
uv run run-pipeline test
```

No API keys or authentication are required. All data sources are publicly available. The first run downloads several GB of raw data (especially crime archives); subsequent runs are idempotent and skip existing files.

## Pipeline Architecture

The pipeline consists of 13 nodes orchestrated by [netrun](https://github.com/lukastk/netrun):

```
fetch_populations ──────────┐
fetch_claimant_counts ──────┤
fetch_crime ────────────────┼─> join_fetch ─> broadcast_ready ─┬─> process_claimant_counts ─┐
fetch_qof ──────────────────┤                                  ├─> process_crime ────────── ├─> join_domains ─> aggregate
fetch_gp_catchments ────────┤                                  └─> process_health ───────── ┘
fetch_geo ──────────────────┘
```

**Fetch nodes** (6, parallel) download raw data from Nomis, data.police.uk, NHS Digital, and ONS. All are idempotent.

**Process nodes** (3, parallel) transform raw data into per-LSOA rates in LSOA 2011 vintage. The health node is the most complex, estimating LSOA-level disease prevalence by weighting GP-practice-level QOF data by patient registrations.

**Aggregate node** converts from LSOA 2011 to LSOA 2021 using a population-weighted crosswalk, then rolls up to LAD, Region, and England.

## Project Structure

```
├── config/
│   ├── netrun.json              # Pipeline DAG definition
│   ├── run_defs.toml            # Run configurations (year range, LSOA vintage)
│   └── qof_schemas.toml         # QOF column mappings per year era
├── pts/adi/nodes/               # Node source notebooks (.pct.py) — edit these
├── nbs/adi/nodes/               # Auto-generated .ipynb notebooks
├── src/adi/
│   ├── nodes/                   # Auto-generated .py modules (from pts/)
│   ├── run_pipeline.py          # CLI entry point
│   ├── const.py                 # Path constants
│   └── utils/                   # Shared utilities (Nomis, ONS, scraping, QOF, geo)
├── nbs/analysis/                # Analysis notebooks
└── store/                       # Runtime data (gitignored)
    ├── inputs/                  #   Downloaded raw data
    ├── pipeline/{run_name}/     #   Intermediate outputs (LSOA 2011)
    └── outputs/{run_name}/      #   Final outputs (LSOA 2021, all geographies)
```

Node code is managed with [nblite](https://github.com/lukastk/nblite): edit `.pct.py` files in `pts/`, then sync with `nbl export --reverse && nbl export`.

## Configuration

Run definitions live in `config/run_defs.toml`:

```toml
[defaults]
lsoa_vintage = "2021"
year_start = 2014
year_end = 2024

[runs.test]
year_start = 2022
year_end = 2023
```

## Output Format

Final outputs are CSV files organised by geography and domain:

```
store/outputs/{run_name}/
├── lsoa/
│   ├── claimant_counts/     # LSOA11CD, claimant_count, pop, claimant_rate
│   ├── crime/               # LSOA11CD, {14 crime types}, pop, {14 rates}
│   └── health/              # LSOA11CD, {21 disease}_prevalence_rate, ...
├── lad/
├── region/
└── england/
```

All outputs include absolute counts and populations alongside rates, enabling further aggregation.

## Data Sources

- **Claimant counts**: [Nomis](https://www.nomisweb.co.uk/datasets/ucjsa) Universal Credit dataset `NM_162_1` at LSOA 2011
- **Street crime**: [data.police.uk](https://data.police.uk/data/archive/) monthly archives
- **QOF prevalence**: [NHS Digital](https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data) Quality and Outcomes Framework
- **GP-LSOA registrations**: [NHS Digital](https://digital.nhs.uk/data-and-information/publications/statistical/patients-registered-at-a-gp-practice) (available from April 2014)
- **LSOA populations**: Nomis mid-year estimates (`NM_2010_1` for LSOA 2011, `NM_2014_1` for LSOA 2021)
- **Geographic lookups & boundaries**: [ONS Open Geography Portal](https://geoportal.statistics.gov.uk/)

## Tech Stack

- **Python 3.12+** with **uv** for package management
- **netrun** for pipeline orchestration
- **nblite** for literate programming (notebook/script/module sync)
- **pandas** / **numpy** / **scipy** for data processing
- **httpx** + **beautifulsoup4** for async downloads and web scraping
- **geopandas** for boundary data
