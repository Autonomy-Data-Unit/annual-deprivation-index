# Methodology

This document describes the data processing methodology used by the Annual Deprivation Index v2 pipeline. It covers the three domain sub-indices (employment, crime, health), the geographic conversion from LSOA 2011 to LSOA 2021, and the aggregation to higher geographies.

## Overview

The ADI produces annual deprivation measurements for England at the Lower Layer Super Output Area (LSOA) level. It uses three independent domains — employment, crime, and health — each derived from publicly available administrative data. The pipeline outputs per-domain rates and absolute counts at four geography levels (LSOA, LAD, Region, England) but does not combine domains into a composite score.

All domain processing is performed in **LSOA 2011** vintage (the native geography of the source data), then converted to **LSOA 2021** via a population-weighted crosswalk in the final aggregation step.

## Year Coverage

The binding constraint on the earliest year is the GP-LSOA patient registration data, which is available from April 2014 onward. The default pipeline range is **2014--2025**.

| Source | Available from | Geography |
|---|---|---|
| Claimant counts (Nomis NM_162_1) | 2013 | LSOA 2011 only |
| Street crime (data.police.uk) | 2011 | LSOA 2011 |
| QOF prevalence (NHS Digital) | QOF 2013-14 | Per GP practice |
| GP-LSOA registrations (NHS Digital) | April 2014 | LSOA 2011 |
| LSOA 2011 mid-year population (Nomis NM_2010_1) | 2011--2020 | LSOA 2011 |
| LSOA 2021 mid-year population (Nomis NM_2014_1) | 2011--2024 | LSOA 2021 |

## Population Estimates

ONS mid-year population estimates provide the resident denominators. The pipeline queries the age dimension of the same two Nomis datasets for both the all-age population and the exact age bands used by QOF: 6+, 16+, 17+, 18+, and 50+. Nomis composes each band server-side from its single-year-of-age cells (with 90+ as the open-ended oldest group), so these are published population totals rather than estimated proportions.

- **LSOA 2011** populations from Nomis dataset NM_2010_1 (2011--2020) are used inside the three domain processors and to carry age-band quantities through the source-vintage crosswalk.
- **LSOA 2021** populations from Nomis dataset NM_2014_1 (2011--2024) weight split LSOAs and provide the all-age and eligible-age populations in final outputs.

The LSOA 2011 series ends in 2020. For later years the domain processors use its 2020 estimate because the claimant, crime and GP-registration sources are still coded to 2011 boundaries. The final aggregation replaces crosswalked populations with the target-vintage LSOA 2021 all-age or matching age-band estimate for the publication year. Split weights and final populations therefore come from the same year. The 2025 carry-forward policy described below applies identically to the all-age and age-band LSOA 2021 files.

Every final row carries related but distinct population fields:

- `pop` is the all-age ONS population summed over the LSOAs included in the release. It equals the complete published-area estimate only where the area does not contain one of the six excluded complex boundary-change LSOAs.
- Each count has a metric-specific `<count>_pop`: the denominator against which that count's rate is defined, summed only over LSOAs where the metric is available. For employment, crime and the original health `*_afflicted` metrics this is all-age population. For the new `*_qof_afflicted` metrics it is the condition's eligible-age population. The published identity is always `<count>_rate = <count> / <count>_pop`; a rate must never be divided by the row's `pop` without checking its own denominator.

Employment and crime counts are retained when the target-vintage population is introduced. They are source-event counts: changing the population base cannot change how many claimants or located incidents were counted, so only their denominator and rate change.

Health deliberately behaves differently. The QOF-weighted rate is the estimated health quantity; the original `*_afflicted` count is that rate multiplied by all-age resident population, while the additive `*_qof_afflicted` count is the QOF eligible-age rate multiplied by the matching resident age-band population. When a target population is introduced, each rate is held fixed and its count is re-derived against its own denominator. Holding either old modelled count instead would change the corresponding rate solely because a population estimate changed, despite no new health measurement. These are modelled representations of the same disease register, not raw QOF register counts, and must not be added together. If a metric is unavailable for some LSOAs, its aggregate count and metric-specific population both exclude them while `pop` continues to describe all included residents.

**Caveat on 2025.** The **LSOA-level** Nomis NM_2014_1 series publishes through mid-2024, so the pipeline explicitly carries that estimate forward for one year: every 2025 `pop` and metric-specific population is on the mid-2024 LSOA base. ONS has published mid-2025 estimates for England, regions and LADs, but mixing them with mid-2024 LSOAs would break the identity between geographic levels, so ADI consistently aggregates the carried-forward LSOAs at every level. Consequently ADI's England `pop` is 58,611,150 rather than the ONS mid-2025 figure of 58,834,812, a difference of 223,662 (0.38%) that also includes the six excluded complex-change LSOAs. The fallback is bounded to one year: stale, mislabelled or more-than-one-year-old responses raise `PopulationVintageError` rather than silently compounding the lag.

## Employment Domain

**Source:** The Claimant Count from the Nomis REST API (dataset NM_162_1, geography TYPE298 = LSOA 2011). It combines all Jobseeker's Allowance claimants with the relevant Universal Credit component: UC claimants recorded as not in employment from May 2013 to April 2015, then those in the `Searching for Work` conditionality regime from April 2015 onward. A person claiming both can appear in both components.

**Processing:**

1. Twelve monthly Claimant Count observations are downloaded for each calendar year.
2. Welsh LSOAs (codes starting with "W") are filtered out.
3. The monthly stock counts are averaged to an annual mean per LSOA; this is not a count of unique people during the year.
4. The annual mean is merged with the LSOA 2011 population and the intermediate rate is `claimant_count / pop`.
5. Final outputs add `claimant_count_pop`; the published rate is `claimant_count / claimant_count_pop`.

**Nearest-five rounding:** Nomis independently rounds every monthly observation to the nearest five; it does not return sub-five counts as blank suppressed cells in the audited 2014--2025 files. A published zero can therefore represent an unrounded integer from 0 to 2, while a published 5 can represent 3 to 7. Rounding can move an annual mean or an aggregate either upward or downward, with the largest relative effects in low-count areas. In the source audit, the conservative zero-only upper bound moved the England rate by at most 0.007 percentage points; among directly comparable unaffected LADs the largest observed absolute rate gap was 0.021 percentage points, while Stratford-on-Avon's low 2015 count differed from the independently rounded LAD value by 5.81% in relative terms.

**Unverified local source anomaly:** Forest of Dean 010C (`E01022273`) rises from a 0.7363% annual rate in 2023 to 9.9438% in 2024, then falls to 1.9172% in 2025. The rise is present in the current Nomis monthly source (55 in December 2023, peaking at 230 in July 2024, then returning to 15--20 by spring 2025), not introduced by averaging or the crosswalk. It affects both sexes and several age groups while the four neighbouring LSOAs remain stable; the direct Nomis parent-MSOA series carries the same rise. No reliable public local explanation was found, and NM_162_1 does not expose the stated benefit-type breakdown as an API dimension, so the value is retained but should be treated as a source-native, locally unverified anomaly rather than evidence of a pipeline defect.

**Intermediate output columns:** `LSOA11CD`, `LSOA11NM`, `claimant_count`, `pop`, `claimant_rate`. Final outputs additionally include `claimant_count_pop` and use it as the rate denominator.

## Crime Domain

**Source:** The data.police.uk monthly street archive supplies 13 police-recorded crime categories plus a separate anti-social behaviour (ASB) incident series. ASB is governed under the National Standard for Incident Recording rather than the main police-recorded crime collection, so it is published separately and excluded from the headline recorded-crime total. British Transport Police is excluded because it covers a national rail network whose passenger population is not comparable with resident-area populations.

Each archive is a ZIP file (~1.7 GB) containing a rolling 36-month window of incident-level data. The pipeline downloads December archives, selecting one every three years to minimise redundant downloads while ensuring full temporal coverage.

**Processing:**

1. The pipeline checks each English territorial force-year for 12 present, non-empty monthly street files and at least 90% LSOA geocoding among records that could belong to England. A force-year failing either test makes its inferred LAD/LSOA footprint unavailable rather than publishing a partial annual total.
2. Monthly territorial-force files are loaded, exact duplicate identified incidents are removed, and all records from unusable force-years are discarded. Incidents without an LSOA code are then dropped, recent LSOA 2021 police codes are mapped back to their LSOA 2011 parents, and Welsh LSOAs are filtered out.
3. Incidents are counted by LSOA into 13 recorded-crime columns and one separate ASB column.
4. Counts are left-joined from the LSOA 2011 population so a covered LSOA with no reported incidents receives zero, while an LSOA in an incomplete force footprint remains missing.
5. Intermediate rates use `count / pop`. Final outputs add a metric-specific `<crime_type>_pop`, and each published rate is `count / <crime_type>_pop`.

In the current 2014--2025 outputs, unavailable force footprints are: Avon and Somerset (2016--2019 and 2025), Staffordshire (2018), Lancashire, Thames Valley and Suffolk (2019), Greater Manchester (2019--2025), and Gloucestershire (2020--2022). Region and England rates remain available over the population covered by usable forces.

**Intermediate output columns:** `LSOA11CD`, `LSOA11NM`, 13 recorded-crime counts, one ASB incident count, `pop`, and 14 corresponding rates. Final outputs add one metric-specific population per series.

## Health Domain

The health domain is the most methodologically complex. It estimates LSOA-level disease prevalence by combining two NHS Digital datasets: practice-level QOF prevalence data and LSOA-level GP patient registration data.

### Data Sources

**QOF (Quality and Outcomes Framework):** Per-GP-practice disease register sizes and list populations. The site and downloads publish 22 health metrics: 21 canonical disease groups (AF, AST, CAN, CHD, CKD, COPD, DEM, DEP, DM, EP, HF, HYP, LD, MH, NDH, OB, OST, PAD, PC, RA, STIA) plus the historical CVD primary-prevention register (CVDPP), which is available for output years 2014--2020 and blank after its withdrawal. Two one-year source groups, SMOK and THY, remain in intermediate files but are excluded from publication. QOF years run April to March (e.g. QOF 2021-22 covers April 2021 to March 2022).

**GP-LSOA patient registrations:** Per-practice, per-LSOA patient counts showing how many patients from each LSOA are registered at each GP practice. The April edition is used, matching the QOF year boundary (e.g. QOF 2021-22 is paired with April 2022 registrations).

### QOF Normalisation

Raw QOF data has different column schemas across years. Four CSV eras are supported (2013-14 onward), with column mappings defined in `config/qof_schemas.toml`:

| Era | Years | Key differences |
|---|---|---|
| 1 | 2013-14 | Lowercase columns, `disease_register_size` |
| 2 | 2014-15 | cp1252 encoding |
| 3 | 2015-16 to 2019-20 | Column name change in 2019-20 (`INDICATOR_GROUP_CODE` to `GROUP_CODE`) |
| 4 | 2020-21 onward | `PRACTICE_LIST_SIZE` (not `PATIENT_`), multiple `PATIENT_LIST_TYPE` rows per practice, NDH disease group added |

The normalisation retains two denominator views. The explicit all-age practice list remains the denominator for the original, unchanged ADI whole-population burden rate. Where QOF publishes a disease against an eligible-age list, that row's own list size supplies a second QOF-comparable rate. `PATIENT_LIST_TYPE` identifies the band from 2015-16 onward; the 2014-15 mappings are pinned in `config/qof_schemas.toml` because that file contains the correct per-disease sizes without labels. QOF 2013-14 provides only one all-age list, so all age-restricted output columns are intentionally blank for output year 2014.

The normalised all-age output is pivoted to one row per practice with columns for each disease group's register size and the all-age practice list. Eligible-age list sizes are retained separately for only the disease-years where the source defines one.

**Duplicate disease codes in 2013-14:** The 2013-14 QOF data contains two rows per practice for "HF" (Heart Failure): a narrow subtype ("Heart Failure due to LVD", typically ~9 patients) and a broad category ("Heart Failure", typically ~48 patients). The LVD patients are a subset of the broader HF register. The pivot uses `aggfunc="max"` to select the broader register, which is consistent with later years that report a single HF row. For all other diseases and eras, each (practice, disease) pair has exactly one row, so the aggregation function has no effect.

### Prevalence Estimation

LSOA prevalence is estimated separately for each disease from GP practices for which QOF published both a usable disease register and a positive list population. Practices missing either value are not treated as zero.

For LSOA *i*, disease *d*, and the set of covered practices *C(i,d)*:

```
covered_patients(i,d) = sum_{k in C(i,d)} patients(i,k)
coverage(i,d) = covered_patients(i,d) / sum_{all k} patients(i,k)
weight(i,k,d) = patients(i,k) / covered_patients(i,d)
all_age_rate(i,d) = sum_{k in C(i,d)} [ weight(i,k,d) * register(k,d) / all_age_list(k) ]
qof_eligible_rate(i,d) = sum_{k in C(i,d)} [ weight(i,k,d) * register(k,d) / eligible_list(k,d) ]
```

The eligible-age expression is emitted only when QOF supplies a distinct age-restricted denominator for that disease-year. It uses the same covered practices, registration weights and coverage floor as the all-age expression.

The disease-specific weights sum to 1.0 **over the covered practices**, not over all registrations in the LSOA. Renormalising makes the covered practices representative of the uncovered ones rather than implicitly assigning zero prevalence to practices QOF omitted. That assumption becomes unreliable when coverage is thin, so the source estimate is withheld when covered practices represent less than **80%** of the LSOA's registrations for that disease. The intermediate `qof_coverage` column summarises the share of registrations at practices with a usable QOF list size; the threshold itself is applied per disease. `registration_coverage` is total GP registrations divided by ONS resident population. It can exceed 1 because practice lists and resident estimates are different administrative measures; it is reported for interpretation and is not thresholded.

The two modelled resident counts are completed against matching ONS denominators:

```
afflicted(i,d) = all_age_rate(i,d) * all_age_pop(i)
qof_afflicted(i,d) = qof_eligible_rate(i,d) * eligible_age_pop(i,d)
```

These are alternative representations of the same disease estimate, not separate groups of people: do not add or average them. They are modelled resident estimates, not observed patients or QOF register counts. An unavailable rate produces an unavailable count. Any estimated rate outside the possible interval [0, 1] is rejected to missing rather than clamped.

QOF practice-list totals exceed the included ONS resident population, by 3.6% in 2013-14 and 8.8% in 2024-25, so modelled resident estimates are generally below national QOF register totals. For example, QOF reports 9,711,491 hypertension registrations in 2024-25 while ADI estimates 9,056,490 affected residents (6.7% lower). The difference is principally the population-basis conversion, not missing disease cases.

Producing an LSOA resident estimate from practice-level QOF data requires two explicit representativeness assumptions:

1. **Practice prevalence is uniform across its served LSOAs.** QOF reports a disease rate for the practice as a whole, not separately for patients from each LSOA. The method applies that practice-wide rate to its registered patients in every LSOA it serves. This can be biased where a practice's patients differ systematically between LSOAs, for example by age, deprivation or care-home residence.
2. **GP registrations geographically represent residents.** After weighting those practice rates by the registered patients attributed to an LSOA, the resulting registration prevalence is assumed to represent everyone who lives there. This has two directions: excess or stale registrations are assumed to have the same prevalence as actual residents, and residents absent from the England-only registration file (including people with no GP and some border populations) are assumed to resemble represented registrants. The second assumption may be less credible for recent migrants, people in insecure housing, and people experiencing homelessness. If under-registered residents are less healthy, the method will bias prevalence downward; the available coverage totals cannot establish the direction or size of that bias.

`registration_coverage` shows the size of the registration-to-resident mismatch, and `qof_coverage` shows how much of the registration base was represented by practices with a usable QOF list. They make thin evidence visible but cannot test either assumption. The 80% suppression rule applies to disease-specific QOF practice coverage, not to `registration_coverage`.

Nine canonical groups have a QOF eligible-age denominator, but not in every year:

| Conditions | Eligible population | First output year |
|---|---|---:|
| CKD, DEP, EP | 18+ | 2015 |
| DM | 17+ | 2015 |
| OB | 16+ in 2015; 18+ from 2016 | 2015 |
| OST | 50+ | 2015 |
| RA | 16+ | 2015 |
| AST | 6+ | 2021 |
| NDH | 18+ | 2021 |

Thus seven conditions have an eligible-age rate in 2015--2020 and nine in 2021--2025. Every eligible-age column is blank in 2014 because QOF 2013-14 did not publish a distinct eligible-age denominator. AST used the all-age list through 2019-20 and switched to 6+ in 2020-21; NDH was introduced in 2020-21. The original all-age columns remain unchanged and continue to provide an unbroken 2014--2025 whole-population view where the condition itself exists.

**Age-restricted is not age-standardised.** Restriction removes people who are outside the QOF eligibility range from the denominator; it does not reweight the eligible population to a common age distribution. The new rate is the estimated share of eligible residents with the recorded condition. It does not support the claim that differences between places or years have been adjusted for age structure. In 2024-25, for example, England osteoporosis is 0.450% of all residents and 1.201% of residents aged 50+, compared with NHS England's published 50+ prevalence of 1.198%.

### Temporal Interpolation

After all QOF years are processed, only short **interior** gaps are filled:

- Interior gaps of one or two consecutive years are linearly interpolated between the observations on both sides.
- Leading and trailing gaps are left missing; the pipeline does not extrapolate beyond the observed series.
- Gaps longer than two years are left missing.

Interpolation is performed independently for each LSOA, disease and denominator view. All-age and eligible-age rates therefore retain their own anchors; afflicted counts are completed later against the matching current-year population.

**Intermediate output columns:** `LSOA11CD`, `pop`, 24 source-group `{disease}_prevalence_rate` and `{disease}_afflicted` pairs, the available `{disease}_qof_prevalence_rate` columns, `qof_coverage`, and `registration_coverage`. The 24 source groups comprise the 21 canonical groups plus CVDPP, SMOK and THY. The eligible-age columns are rates only at this stage because the aggregate node owns the corresponding resident age-band populations.

### Publishing-stage health adjustments

Before site JSON and download bundles are written, implausible one-year LSOA spikes are rejected to missing rather than capped (eight epilepsy values in 2016 and seven heart-failure values in 2021), and all higher geographies are rebuilt from the remaining LSOAs. The known single-year QOF basis changes for depression in 2024 and osteoporosis in 2015 are corrected in both denominator views while retaining each view's proper population. Each public count has its own `<count>_pop`; areas without a usable or interpolated value contribute to neither count nor denominator. CVDPP is retained for its seven-year source window, while the one-year SMOK and THY groups are omitted, leaving 22 conditions plus the nine additive QOF eligible-age representations.

## LSOA 2011 to LSOA 2021 Crosswalk

All three domain processors output data in LSOA 2011 vintage. The aggregate node converts each output year to LSOA 2021 using the ONS exact-fit lookup (`LSOA11_LSOA21_LAD22_EW_LU`) and an output-year-specific population crosswalk:

| Change | LSOA 2011 | LSOA 2021 | Count | Method |
|---|---|---|---|---|
| Unchanged (U) | 1 | 1 | 33,647 | Direct mapping, weight = 1.0 |
| Split (S) | 1 | 2+ | 861 old to 1,900 new | Weight by each target's LSOA 2021 population share in the publication year |
| Merged (M) | 2+ | 1 | 239 old to 119 new | Sum values, weight = 1.0 per source LSOA |
| Complex (X) | n | m | 6 | Excluded |

Split weights are rebuilt for every publication year from the same LSOA 2021 population frame that becomes the final `pop`. This keeps the split numerator and denominator on one population vintage.

**Disaggregation procedure:**

1. Join each LSOA 2011 row to the crosswalk for that output year.
2. Multiply absolute counts and their associated intermediate populations by the crosswalk weight. Rates are never disaggregated directly.
3. Reaggregate weighted values by LSOA 2021 with `min_count=1`, so an all-missing metric remains missing rather than becoming zero.
4. Replace crosswalked populations with that year's target-vintage LSOA 2021 all-age and age-band populations. Employment and crime counts remain fixed; each health count is re-derived so its all-age or eligible-age rate remains fixed.
5. At LSOA level, assign each count its mapped denominator when measured and missing otherwise, then compute `rate = count / <count>_pop`.

The six complex-change source LSOAs and their six target LSOAs are excluded, so the release contains 33,749 of England's 33,755 LSOA 2021 areas. The absent targets are `E01035581` (St Albans 021C), `E01035582` (Stevenage 013A), `E01035608` (Welwyn Hatfield 017C), `E01035609` (East Hertfordshire 019C), `E01035624` (Gateshead 029D), and `E01035637` (Northumberland 043F). Their combined population is 8,929--9,279 across 2014--2025 (0.0153%--0.0168% of England; 8,951 in 2024), exactly accounting for the difference between ADI's included-LSOA England population and the raw Nomis LSOA total in every year. The local effect is larger: the six affected LADs are St Albans, Stevenage, Welwyn Hatfield, East Hertfordshire, Gateshead and Northumberland, with Stevenage's 2021 denominator 1.90% below its complete ONS total.

## Geographic Aggregation

The LSOA 2021 outputs are rolled up through ONS lookup tables to:

- **LAD (Local Authority District):** 296 areas.
- **Region:** 9 English regions.
- **England:** one national total.

At each level the pipeline sums counts, full `pop`, and every metric-specific `<count>_pop` separately with `min_count=1`. A published rate is always `count / <count>_pop`. It is therefore the population-weighted rate over measured LSOAs; `pop` remains the full area population and can be larger when a metric has incomplete coverage.

## Output Structure

Final pipeline outputs are organised by geography level and domain:

```
store/outputs/{run_name}/
  lsoa/{domain}/{domain}_{year_key}.csv
  lad/{domain}/{domain}_{year_key}.csv
  region/{domain}/{domain}_{year_key}.csv
  england/{domain}/{domain}_{year_key}.csv
```

Every count is accompanied by its own metric-specific population and reproducible rate, while `pop` records the summed all-age population of the release's included LSOAs. Health outputs additionally publish `registration_coverage` and `qof_coverage`. The health domain uses QOF year keys (e.g. `health_2021_22.csv`); employment and crime use calendar years (e.g. `claimant_counts_2022.csv`, `crime_2022.csv`). The site/download publishing step applies the documented health quality adjustments and omits SMOK and THY, publishing 22 conditions and nine additional QOF eligible-age metric triples where source denominators exist.

## Known Limitations

- **Claimant Count definition and rounding:** The measure is JSA plus the relevant UC component, not the total UC caseload and not unique people over a year. Nomis rounds each monthly stock independently to the nearest five, so low-count annual means can be rounded upward or downward.

- **Crime source and coverage:** Missing-LSOA incidents are dropped, force-years below 12 non-empty months or 90% LSOA geocoding are withheld, and British Transport Police is excluded because passenger exposure is not a resident denominator. ASB is separate from the 13-category recorded-crime total. Aggregate rates use metric-specific covered populations.

- **QOF coverage and interpolation:** Covered-practice weights are renormalised and source estimates below 80% disease-specific registration coverage are withheld. Interior gaps of at most two years may be interpolated, but endpoint and longer gaps remain missing. `registration_coverage` reports registrations relative to residents but does not impose another floor.

- **QOF measurement and comparability:** QOF reflects GP-diagnosed and recorded disease, so it understates underdiagnosed conditions and varies with recording practice. Modelled health counts use ONS resident populations and do not equal QOF register counts. They assume each practice's overall QOF prevalence applies uniformly across the LSOAs it serves and that GP registrations geographically represent all residents; the coverage indicators expose evidence gaps but cannot verify either assumption. For nine conditions, the original rate is a share of all residents and the additive `*_qof_afflicted_rate` is a share of the condition's eligible-age residents. The latter is QOF-comparable but age-restricted, **not age-standardised**: local age structure within the eligible group remains. NHS Digital also warns that 2020-21 implementation changes affect comparisons, particularly for obesity, asthma and COPD; this is not evidence of a uniform fall across all conditions.

- **Health quality exclusions:** Impossible prevalence rates and documented implausible EP/HF spikes are rejected to missing. Depression 2024 and osteoporosis 2015 are interpolated only where both adjacent-year anchors exist. Aggregate metric populations exclude missing LSOAs.

- **Population availability:** Domain processing uses the 2020 LSOA 2011 population after 2020, but target-vintage outputs use per-year LSOA 2021 population through 2024. Because the LSOA-level series has not yet published mid-2025, the 2025 release carries mid-2024 forward for one year and aggregates that consistent base at every level, despite mid-2025 upper-geography estimates being available.

- **Complex LSOA changes:** Six many-to-many boundary changes are excluded, leaving 33,749 of 33,755 English LSOA 2021 areas and about 9,000 residents outside the published population base. This affects six LADs and reaches 1.90% of Stevenage's complete 2021 population.

- **Forest of Dean claimant anomaly:** Forest of Dean 010C's 2024 claimant spike is present across current Nomis monthly, sex, age and parent-MSOA series and absent from neighbouring LSOAs. Its local cause remains unverified, so it is retained with that warning.
