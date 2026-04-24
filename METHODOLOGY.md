# Methodology

This document describes the data processing methodology used by the Annual Deprivation Index v2 pipeline. It covers the three domain sub-indices (employment, crime, health), the geographic conversion from LSOA 2011 to LSOA 2021, and the aggregation to higher geographies.

## Overview

The ADI produces annual deprivation measurements for England at the Lower Layer Super Output Area (LSOA) level. It uses three independent domains — employment, crime, and health — each derived from publicly available administrative data. The pipeline outputs per-domain rates and absolute counts at four geography levels (LSOA, LAD, Region, England) but does not combine domains into a composite score.

All domain processing is performed in **LSOA 2011** vintage (the native geography of the source data), then converted to **LSOA 2021** via a population-weighted crosswalk in the final aggregation step.

## Year Coverage

The binding constraint on the earliest year is the GP-LSOA patient registration data, which is available from April 2014 onward. The default pipeline range is **2014--2024**.

| Source | Available from | Geography |
|---|---|---|
| Claimant counts (Nomis NM_162_1) | 2013 | LSOA 2011 only |
| Street crime (data.police.uk) | 2011 | LSOA 2011 |
| QOF prevalence (NHS Digital) | QOF 2013-14 | Per GP practice |
| GP-LSOA registrations (NHS Digital) | April 2014 | LSOA 2011 |
| LSOA 2011 mid-year population (Nomis NM_2010_1) | 2011--2020 | LSOA 2011 |
| LSOA 2021 mid-year population (Nomis NM_2014_1) | 2011--2024 | LSOA 2021 |

## Population Estimates

ONS mid-year population estimates are used as the denominator for all rate calculations. Two series are downloaded:

- **LSOA 2011** populations from Nomis dataset NM_2010_1 (2011--2020). Used by all three domain processors.
- **LSOA 2021** populations from Nomis dataset NM_2014_1 (2011--2024). Used for crosswalk weighting and as the denominator in final outputs.

The LSOA 2011 population series ends in 2020. For years beyond 2020, the pipeline falls back to the 2020 estimate. This is a known approximation; LSOA-level population shifts between 2020 and later years are not reflected in the domain processing step, though they are captured in the LSOA 2021 populations used after the crosswalk.

## Employment Domain

**Source:** Universal Credit claimant counts from the Nomis REST API (dataset NM_162_1, geography TYPE298 = LSOA 2011).

**Processing:**

1. Monthly claimant counts are downloaded for each year (12 months per LSOA).
2. Welsh LSOAs (codes starting with "W") are filtered out.
3. Monthly counts are averaged to produce an annual mean claimant count per LSOA.
4. The annual count is merged with the LSOA 2011 mid-year population estimate for that year.
5. The claimant rate is computed as: `claimant_rate = claimant_count / pop`.

**Suppressed counts:** Nomis suppresses counts below 5, returning them as empty values. These are treated as zero when computing the annual average. This introduces a small downward bias in LSOAs with very low claimant counts, but affects only LSOAs where the true monthly count is between 1 and 4.

**Output columns:** `LSOA11CD`, `LSOA11NM`, `claimant_count`, `pop`, `claimant_rate`.

## Crime Domain

**Source:** Police-recorded street crime data from data.police.uk monthly archives.

Each archive is a ZIP file (~1.7 GB) containing a rolling 36-month window of incident-level data. The pipeline downloads December archives, selecting one every three years to minimise redundant downloads while ensuring full temporal coverage.

**Processing:**

1. All monthly per-force street crime CSVs for a given calendar year are loaded and concatenated.
2. Incidents with missing LSOA codes are dropped. Welsh LSOAs are filtered out.
3. Incidents are counted by LSOA and crime type, producing a wide-format table with one column per crime type (14 types: Anti-social behaviour, Bicycle theft, Burglary, Criminal damage and arson, Drugs, Other crime, Other theft, Possession of weapons, Public order, Robbery, Shoplifting, Theft from the person, Vehicle crime, Violence and sexual offences).
4. The crime counts are merged with the LSOA 2011 population via a left join from the population table, so that LSOAs with zero reported crimes are included with zero counts rather than being dropped.
5. Per-capita rates are computed for each crime type: `rate = count / pop`.

**Output columns:** `LSOA11CD`, `LSOA11NM`, `{crime_type}` (14 count columns), `pop`, `{crime_type}_rate` (14 rate columns).

## Health Domain

The health domain is the most methodologically complex. It estimates LSOA-level disease prevalence by combining two NHS Digital datasets: practice-level QOF prevalence data and LSOA-level GP patient registration data.

### Data Sources

**QOF (Quality and Outcomes Framework):** Per-GP-practice disease register sizes and list populations. Covers 21 disease groups: AF, AST, CAN, CHD, CKD, COPD, DEM, DEP, DM, EP, HF, HYP, LD, MH, NDH, OB, OST, PAD, PC, RA, STIA. QOF years run April to March (e.g. QOF 2021-22 covers April 2021 to March 2022).

**GP-LSOA patient registrations:** Per-practice, per-LSOA patient counts showing how many patients from each LSOA are registered at each GP practice. The April edition is used, matching the QOF year boundary (e.g. QOF 2021-22 is paired with April 2022 registrations).

### QOF Normalisation

Raw QOF data has different column schemas across years. Four CSV eras are supported (2013-14 onward), with column mappings defined in `config/qof_schemas.toml`:

| Era | Years | Key differences |
|---|---|---|
| 1 | 2013-14 | Lowercase columns, `disease_register_size` |
| 2 | 2014-15 | cp1252 encoding |
| 3 | 2015-16 to 2019-20 | Column name change in 2019-20 (`INDICATOR_GROUP_CODE` to `GROUP_CODE`) |
| 4 | 2020-21 onward | `PRACTICE_LIST_SIZE` (not `PATIENT_`), multiple `PATIENT_LIST_TYPE` rows per practice, NDH disease group added |

For era 4, only rows where `PATIENT_LIST_TYPE = "TOTAL"` are used for list population, to avoid double-counting across patient subgroups.

The normalised output is pivoted to one row per practice with columns for each disease group's register size and the practice list population.

**Duplicate disease codes in 2013-14:** The 2013-14 QOF data contains two rows per practice for "HF" (Heart Failure): a narrow subtype ("Heart Failure due to LVD", typically ~9 patients) and a broad category ("Heart Failure", typically ~48 patients). The LVD patients are a subset of the broader HF register. The pivot uses `aggfunc="max"` to select the broader register, which is consistent with later years that report a single HF row. For all other diseases and eras, each (practice, disease) pair has exactly one row, so the aggregation function has no effect.

### Prevalence Estimation

LSOA-level prevalence is estimated as a weighted average of GP-practice-level prevalence rates, where the weights reflect the proportion of each LSOA's patients registered at each practice.

For each LSOA *i* and disease *d*:

```
prevalence_rate(i, d) = sum_k [ weight(i,k) * register(k,d) / list_pop(k) ]
```

where:

- `weight(i, k) = patients(i, k) / total_patients(i)` is the fraction of LSOA *i*'s GP-registered patients who are at practice *k*
- `patients(i, k)` is the number of patients from LSOA *i* registered at practice *k* (from the GP-LSOA registration data)
- `total_patients(i) = sum_k patients(i, k)` is the total number of GP-registered patients from LSOA *i* across all practices
- `register(k, d)` is the disease register size for disease *d* at practice *k* (from QOF)
- `list_pop(k)` is the total registered patient list at practice *k* (from QOF)

The weights sum to 1.0 per LSOA, so the result is a proper weighted average of practice-level prevalence rates. This avoids the need for spatial intersection: the GP-LSOA registration data directly tells us which LSOAs each practice serves.

**Afflicted counts** are then derived by scaling the prevalence rate by the LSOA's ONS mid-year population estimate:

```
afflicted(i, d) = prevalence_rate(i, d) * pop(i)
```

This uses the ONS general population rather than the GP-registered list population. The prevalence rate captures the disease burden as measured through GP registrations; multiplying by ONS population expresses this as an estimated count relative to the LSOA's total resident population. This ensures consistency with the employment and crime domains, which also use ONS population as their denominator, and produces rates that remain well-calibrated after the LSOA crosswalk and geographic aggregation steps.

### Temporal Interpolation

Not all 21 disease groups are tracked in every QOF year (e.g. NDH was added in 2020-21). After processing all QOF years, a temporal interpolation step fills gaps:

- **Interior gaps** of 1--2 consecutive missing years: filled by linear interpolation between the flanking values.
- **Leading gaps** of 1--2 years: extrapolated backward using linear regression on the first 2+ valid values.
- **Trailing gaps** of 1--2 years: extrapolated forward using linear regression on the last 2+ valid values.
- **Gaps longer than 2 consecutive years:** left as NaN (insufficient data for reliable interpolation).

Interpolation is applied independently to each (LSOA, disease) time series. After interpolating prevalence rates, afflicted counts are recomputed as `prevalence_rate * pop`.

**Output columns:** `LSOA11CD`, `{disease}_prevalence_rate` (21 columns), `{disease}_afflicted` (21 columns), `pop`.

## LSOA 2011 to LSOA 2021 Crosswalk

All three domain processors output data in LSOA 2011 vintage, matching the source data. The aggregate node converts to LSOA 2021 using the ONS exact-fit lookup table (`LSOA11_LSOA21_LAD22_EW_LU`), which classifies each LSOA relationship as one of four change types:

| Change | LSOA 2011 | LSOA 2021 | Count | Method |
|---|---|---|---|---|
| Unchanged (U) | 1 | 1 | 33,647 | Direct mapping, weight = 1.0 |
| Split (S) | 1 | 2+ | 861 old to 1,900 new | Weight by LSOA 2021 population proportion |
| Merged (M) | 2+ | 1 | 239 old to 119 new | Sum values, weight = 1.0 per input LSOA |
| Complex (X) | n | m | 6 | Excluded |

**Disaggregation procedure:**

1. Each LSOA 2011 row is joined with the crosswalk, producing one or more LSOA 2021 rows.
2. Absolute counts and population are multiplied by the crosswalk weight. For unchanged and merged LSOAs, the weight is 1.0 (no splitting). For split LSOAs, the weight distributes the LSOA 2011 value proportionally to the LSOA 2021 populations of the resulting areas.
3. Rows are reaggregated by LSOA 2021 code (summing weighted counts and populations).
4. Rates are recomputed from the disaggregated numerators and denominators. Rates are never disaggregated directly.

The 6 complex-change LSOAs are excluded from the output.

## Geographic Aggregation

After the crosswalk, data is aggregated from LSOA 2021 to three higher geographies using ONS lookup tables:

- **LAD (Local Authority District):** 296 areas. LSOA-to-LAD lookup (`LSOA21_WD25_LAD25_EW_LU`).
- **Region:** 9 English regions. LAD-to-Region lookup (`LAD25_RGN25_EN_LU`).
- **England:** Single national total.

At each level, absolute counts and populations are summed, and rates are recomputed as `count / pop`. This ensures rates at higher geographies are properly population-weighted averages of LSOA-level rates, not simple arithmetic means.

## Output Structure

Final outputs are organised by geography level and domain:

```
store/outputs/{run_name}/
  lsoa/{domain}/{domain}_{year_key}.csv
  lad/{domain}/{domain}_{year_key}.csv
  region/{domain}/{domain}_{year_key}.csv
  england/{domain}/{domain}_{year_key}.csv
```

All output files include both absolute counts and population alongside rates, enabling further aggregation or recomputation by downstream consumers. The health domain uses QOF year keys (e.g. `health_2021_22.csv`); employment and crime use calendar years (e.g. `claimant_counts_2022.csv`, `crime_2022.csv`).

## Known Limitations

- **LSOA 2011 population fallback:** For years after 2020, the LSOA 2011 mid-year population series is unavailable from Nomis. The pipeline uses the 2020 estimate as a fallback. Population changes at the LSOA 2011 level between 2020 and later years are not captured in the domain processing step, though they are reflected in the LSOA 2021 populations used after the crosswalk.

- **Suppressed claimant counts:** Nomis suppresses monthly counts below 5, which are treated as zero. This biases claimant rates slightly downward for LSOAs with very low counts.

- **Crime data completeness:** Some police forces have periods of incomplete reporting. Incidents with missing LSOA codes are dropped. The pipeline does not attempt to impute unreported crimes.

- **QOF coverage variation:** Not all disease groups are tracked in every year. The temporal interpolation fills gaps of up to 2 consecutive years, but longer gaps remain as missing data. Disease group definitions may also shift slightly across QOF eras.

- **Complex LSOA changes:** The 6 LSOAs with complex (many-to-many) boundary changes between LSOA 2011 and LSOA 2021 are excluded from the output.

- **Health prevalence as a proxy:** QOF prevalence reflects conditions diagnosed and recorded by GPs. It underestimates true prevalence for conditions that are underdiagnosed (e.g. dementia, depression) and may be influenced by variation in GP recording practices across areas.
