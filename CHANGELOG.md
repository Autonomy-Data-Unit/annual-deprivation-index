# Changelog

## 2026-09-02 — corrected 2014–2025 data release

This is a **breaking historical revision**, not an append-only annual update. All years should be downloaded again and any analysis based on an earlier extract should be rerun. The comparison below uses commit `b152edf` as the pre-run baseline.

### At a glance

- The complete 2014–2025 series was reprocessed after corrections to population crosswalking, QOF coverage, police-force coverage, and endpoint interpolation.
- Every published count now has an explicit metric-specific coverage population. Rates must be calculated from that population, not automatically from the row's full-area `pop`.
- In the England and nine Region series, **124 area–metric series have at least one changed trend direction**, comprising **147 adjacent-year reversals** relative to `b152edf`. Of these, 82 have an absolute old or new movement of at least 0.1 incidents per 1,000 for crime or 0.01 percentage points for employment/health. The complete list is below.
- Missing source coverage is now blank rather than zero or a plausible-looking extrapolation. This creates intentional gaps, detailed below.
- Health year labels are unchanged but are now stated explicitly: health year `2021` means QOF 2020-21, not calendar year 2021.

## What changed

### Population and geographic conversion

LSOA 2011 source data is still converted to LSOA 2021 before publication, but split-LSOA weights are now calculated from the **same year's LSOA 2021 population** that is published in `pop`. Previously, a later population frame could be used to split an earlier year's count. Rates and trends can therefore change in every year, not only from 2021 onward.

The target-vintage population is now year-specific through 2024. The source has no 2025 LSOA estimate, so 2025 deliberately repeats the 2024 population. The release continues to omit six complex many-to-many boundary-change LSOAs and contains 33,749 of England's 33,755 LSOA 2021 areas.

### Count, population, and rate schema

`pop` now means the full all-age ONS population represented by the published row (the included LSOAs; see the six-area exclusion above). Each metric is a three-column group:

```text
<count>        metric count or modelled count
<count>_pop    population covered by that count
<count>_rate   <count> / <count>_pop
```

For example, use `Burglary / Burglary_pop`, `DEP_afflicted / DEP_afflicted_pop`, and `claimant_count / claimant_count_pop`. Do **not** substitute `pop` when `<count>_pop` is smaller: at higher geographies that difference means some LSOAs had no usable observation. A missing observation is represented by all three metric fields being blank; numeric zero remains a real published value.

Counts retain enough decimal places to reproduce the published eight-decimal download rate. Fractional employment counts arise because the measure is the mean of 12 monthly stocks; fractional crime counts can arise from geographic apportionment; and fractional health counts are modelled estimates rather than observed people.

### Download locations and shape

Four level-specific archives are published on the site's Download page:

```text
adi-england.zip
adi-region.zip
adi-lad.zip
adi-lsoa.zip
```

Each contains long-by-year employment, crime and health CSVs, a data dictionary, a geography lookup, and a README. The domain tables are keyed by `code`, `name`, and `year` and contain 12 rows per area: 12 England rows, 108 Region rows, 3,552 LAD rows, or 404,988 LSOA rows. The source-shaped wide, one-file-per-year tables remain under `store/outputs/default/{level}/{domain}/` for pipeline auditing; council analysts should normally use the downloadable long tables and their dictionaries.

The downloadable crime table contains the 14 component types. The site's “All street crime” series is derived by summing those 14 counts and dividing by their shared coverage population; it is not an additional CSV column.

### Employment

The metric is now labelled **Claimant Count**, not Universal Credit claimant rate. Nomis dataset `NM_162_1` combines Jobseeker's Allowance with the relevant Universal Credit component and independently rounds each monthly stock to the nearest five. The annual value is the mean of those 12 rounded monthly stocks, not a count of unique claimants and not a sum of monthly values.

### Crime

- British Transport Police is excluded because rail-passenger exposure is not represented by a resident population denominator.
- An English territorial force-year is accepted only when all 12 monthly street files are present and non-empty. Partial years are blanked over the affected force footprint rather than annualised or published as a low total.
- Counts and coverage populations are now aggregated together, so Region and England rates remain available over the LSOAs actually covered.

### Health

- QOF prevalence weights are renormalised over practices that published a usable disease register and positive list size; a missing practice is no longer implicitly assigned zero prevalence.
- A disease-specific LSOA estimate is withheld below 80% GP-registration coverage.
- Only one- or two-year **interior** gaps are interpolated. Leading and trailing gaps are no longer extrapolated beyond the observed series.
- Prevalence outside `[0, 1]` is rejected to missing rather than clamped.
- Eight implausible LSOA epilepsy values in 2016 and seven heart-failure values in 2021 are rejected at publication, and higher geographies are rebuilt from the remaining LSOAs.
- Depression in 2023-24 and osteoporosis in 2014-15 have known one-year source-basis anomalies. Their publication-year values are replaced with the mean of the two adjacent LSOA rates only where both anchors exist, then reaggregated upward.
- CVD primary prevention (`CVDPP`), smoking (`SMOK`) and hypothyroidism (`THY`) are omitted from the site and downloads because they do not provide a complete 2014–2025 prevalence series. The published health set contains 21 conditions.

See [METHODOLOGY.md](METHODOLOGY.md) and the data dictionary in each archive for definitions and source-specific caveats.

## Newly explicit blank coverage

| Domain / metric | Years | Blank coverage | Interpretation |
|---|---:|---|---|
| All 14 crime types | 2019–2021 and 2023–2025 | 1,702 LSOAs in 10 Greater Manchester LADs | Greater Manchester's force-year inputs are incomplete. |
| All 14 crime types | 2022 | 2,774 LSOAs in 23 LADs: the 10 Greater Manchester LADs, 12 Devon & Cornwall Police LADs, and City of London | These force-years are incomplete. Region/England values use the smaller metric-specific covered population. |
| All 20 pre-NDH health conditions | 2014 | 64 LSOAs | No usable leading observation; endpoint extrapolation has been removed. |
| All 21 health conditions | 2024 | Braintree 005C (1 LSOA) | No usable source estimate in that year. |
| All 21 health conditions | 2025 | Braintree 005C and Isles of Scilly 001A (2 LSOAs) | No usable trailing observation. Isles of Scilly therefore has a wholly blank LAD health row in 2025. |
| `NDH` | 2014–2020 | All areas | The QOF group was not yet collected. It is blank, not zero. |
| `NDH` | 2021 | 16 LSOAs | No usable estimate in the first collected year. |
| `EP` | 2016 | 8 LSOAs | Implausible one-year spikes rejected to missing. |
| `HF` | 2021 | 7 LSOAs | Implausible one-year spikes rejected to missing. |
| `DEP` | 2024 (QOF 2023-24) | 2 LSOAs: Braintree 005C and Isles of Scilly 001A | The anomalous source year is replaced only when both adjacent anchors exist. |
| `OST` | 2015 (QOF 2014-15) | 64 LSOAs | The anomalous source year is replaced only when both adjacent anchors exist. |
| `CVDPP`, `SMOK`, `THY` | Release-wide | Columns removed from public site/download data | Incomplete historical groups, not zero-prevalence conditions. |

The 2022 Devon & Cornwall footprint comprises Plymouth, Torbay, Cornwall, Isles of Scilly, East Devon, Exeter, Mid Devon, North Devon, South Hams, Teignbridge, Torridge and West Devon. Greater Manchester comprises Bolton, Bury, Manchester, Oldham, Rochdale, Salford, Stockport, Tameside, Trafford and Wigan.

## Trend-direction restatement

### Method

The audit compared all 4,440 rate values in the 370 England/Region area–metric series (10 geographies × 37 metrics × 12 years). The `b152edf` side was reconstructed with that commit's aggregation and publishing corrections. The current side uses the reprocessed store outputs plus the current publication-stage health exclusions and reaggregation. “Reversal” means that the two finite adjacent-year differences have strictly opposite signs; a transition involving a blank or exact zero difference is not counted.

There are **147 reversed adjacent-year comparisons across 124 distinct series**:

| Geography/domain | Reversed comparisons | Distinct series |
|---|---:|---:|
| England — Claimant Count | 0 | 0 |
| Regions — Claimant Count | 2 | 2 |
| England — crime | 7 | 7 |
| Regions — crime | 48 | 39 |
| England — health | 6 | 5 |
| Regions — health | 84 | 71 |
| **Total** | **147** | **124** |

The release has 9 reversals at the 2020→2021 boundary and 6 at 2024→2025. The 2025 cases are not caused by a new population estimate: 2025 uses exactly the 2024 population. Health intervals in the complete table use QOF financial-year labels; employment and crime use calendar years.

The 147 changes combine several corrections and should not be attributed to population denominators alone. Employment is affected principally by same-year population crosswalking. Crime also reflects incomplete-force rejection and BTP exclusion. Health also reflects QOF renormalisation, the coverage floor, source-outlier rejection, and removal of endpoint extrapolation.

The largest restatements include:

| Geography | Metric and interval | `b152edf` movement | Current movement |
|---|---|---:|---:|
| North West | Anti-social behaviour, 2018→2019 | -5.11614 per 1,000 | +0.16193 per 1,000 |
| South West | All street crime, 2021→2022 | -3.40175 per 1,000 | +4.78402 per 1,000 |
| North East | All street crime, 2021→2022 | +0.23636 per 1,000 | -1.74011 per 1,000 |
| North West | Criminal damage and arson, 2019→2020 | +0.88874 per 1,000 | -0.56750 per 1,000 |
| West Midlands | Hypertension, QOF 2015-16→2016-17 | -0.82819 percentage points | +0.06931 percentage points |
| South West | Hypertension, QOF 2017-18→2018-19 | -0.78264 percentage points | +0.10253 percentage points |
| South West | Vehicle crime, 2022→2023 | +0.12016 per 1,000 | -0.77931 per 1,000 |
| North West | Public order, 2019→2020 | +0.67854 per 1,000 | -0.10516 per 1,000 |

A reversal does not by itself establish statistical or policy significance. Some are very small; the full table is provided so analysts can apply their own materiality rule rather than having changes silently filtered for them.

## What analysts should rerun

1. **Replace, do not append to, earlier extracts.** Re-download all four level archives needed by the analysis because corrections affect historical years.
2. **Update schema assumptions.** Use each `<count>_pop` as that count's denominator. Treat a blank count/rate/population triple as unavailable, never as zero.
3. **Rerun every time comparison.** This includes year-on-year changes, pre/post comparisons, trend regressions, interrupted time series, growth rates and charts. Do not carry forward previously computed directions: 147 England/Region adjacent comparisons changed sign.
4. **Rerun ranks, thresholds and area selections.** Recalculate regional/LAD/LSOA ranks, deciles, “most changed” lists, alerts, and cohorts selected from a rate cutoff.
5. **Rerun geographic aggregation.** Sum counts and metric-specific covered populations separately, then divide. Do not average LSOA rates and do not divide a partially covered count by full `pop`.
6. **Review coverage before comparing crime years.** Greater Manchester is unavailable from 2019 onward, and the South West has reduced coverage in 2022. A Region or England rate can therefore describe a different covered footprint in adjacent years.
7. **Keep health periods distinct.** A health value labelled `2021` is QOF 2020-21; employment and crime `2021` are calendar-year measures. Align periods explicitly before joining domains.
8. **Recheck models using health endpoints or the affected QOF groups.** Do not recreate endpoint extrapolations, and remove references to `CVDPP`, `SMOK` or `THY` from public-release analyses.

## Validation and residual issues

The extended whole-series validator was run against the current `store/outputs/default` on 2026-09-02:

```text
uv run python scripts/validate_outputs.py
SUMMARY: 25 BLOCKER, 105 WARN, 1 INFO
```

The earlier expected count of 28 blockers is stale: commit `17027bc` removed invalid health endpoint extrapolation, reducing the run from 28 to 25 blockers without changing the 105 warnings. The raw-store blocker classification is:

| Raw-store blocker class | Findings | Release disposition |
|---|---:|---|
| Depression 2023-24 and osteoporosis 2014-15 source-basis anomalies | 18 | Known and documented; corrected at the publication stage from flanking LSOA observations. |
| Hinckley and Bosworth epilepsy spike | 1 | Known in issue #66; removed by the publication-stage LSOA spike rejection. |
| Dartford `CVDPP` anomaly | 1 | Known in issue #66; `CVDPP` is not part of the public 21-condition release. |
| Dacorum/Hertsmere/Dorset palliative-care and East Staffordshire/Rutland obesity reversals | 3 grouped findings covering 5 LADs | Known in issue #66 and still present; these remain unresolved source-plausibility concerns. |
| London anti-social behaviour in 2020 | 1 | Known COVID-period recorded-crime event; retained for review rather than silently altered. |
| South West bicycle theft in 2022 | 1 | Explained by the documented Devon & Cornwall coverage exclusion; adjacent-year footprints are not directly comparable. |

No **new, previously untracked** blocker class was found. This is not an unconditional clean bill of health: the five LAD health anomalies represented by three grouped findings remain open in issue #66 and should be accepted explicitly or resolved before relying on those local series.

Checks beyond the headline anomaly count found no rate/count/coverage-population identity failures, incoherent partial triples, out-of-range current pipeline health rates, area-set losses, additivity failures, or split-family inconsistencies. The crime blank masks match the named force footprints exactly; all 2025 populations match 2024 exactly as documented. A broader extremes review found the already-filed Forest of Dean 010C Claimant Count spike (issue #27), COVID-related 2020 claimant jumps from very small baselines, and very high resident-denominated crime rates in central commercial LSOAs; it found no additional release-blocking pattern.

## Complete reversal table

Positive values mean an increase and negative values a decrease. Crime changes are incidents per 1,000 residents in the metric's covered population; employment and health changes are percentage points. The figures show the movement within each release, not the difference between the two rates in a single year.

#### Claimant Count (2)

| Geography | Metric | Interval | `b152edf` change | Current change | Unit |
|---|---|---:|---:|---:|---|
| North East | `Claimant Count` | 2023→2024 | +0.02276 | -0.00978 | percentage points |
| North West | `Claimant Count` | 2020→2021 | +0.00124 | -0.02079 | percentage points |

#### Crime (55)

| Geography | Metric | Interval | `b152edf` change | Current change | Unit |
|---|---|---:|---:|---:|---|
| England | `Anti-social behaviour` | 2023→2024 | +0.00399 | -0.17698 | incidents per 1,000 |
| England | `Bicycle theft` | 2015→2016 | -0.04314 | +0.03363 | incidents per 1,000 |
| England | `Burglary` | 2022→2023 | +0.02052 | -0.13477 | incidents per 1,000 |
| England | `Other crime` | 2022→2023 | +0.02550 | -0.02180 | incidents per 1,000 |
| England | `Other theft` | 2022→2023 | +0.05284 | -0.15948 | incidents per 1,000 |
| England | `Robbery` | 2023→2024 | +0.00082 | -0.01349 | incidents per 1,000 |
| England | `Theft from the person` | 2015→2016 | -0.00548 | +0.07406 | incidents per 1,000 |
| North East | `Burglary` | 2023→2024 | +0.05601 | -0.01364 | incidents per 1,000 |
| North East | `Other crime` | 2021→2022 | +0.01382 | -0.02295 | incidents per 1,000 |
| North East | `Public order` | 2021→2022 | +0.10007 | -0.07803 | incidents per 1,000 |
| North East | `Shoplifting` | 2020→2021 | +0.02464 | -0.00653 | incidents per 1,000 |
| North East | `Shoplifting` | 2024→2025 | -0.00485 | +0.00290 | incidents per 1,000 |
| North East | `All street crime` | 2019→2020 | -0.27337 | +0.35232 | incidents per 1,000 |
| North East | `All street crime` | 2021→2022 | +0.23636 | -1.74012 | incidents per 1,000 |
| North West | `Anti-social behaviour` | 2018→2019 | -5.11614 | +0.16194 | incidents per 1,000 |
| North West | `Bicycle theft` | 2015→2016 | -0.02205 | +0.00547 | incidents per 1,000 |
| North West | `Bicycle theft` | 2024→2025 | -0.00952 | +0.00571 | incidents per 1,000 |
| North West | `Criminal damage and arson` | 2019→2020 | +0.88874 | -0.56750 | incidents per 1,000 |
| North West | `Public order` | 2019→2020 | +0.67854 | -0.10516 | incidents per 1,000 |
| North West | `Vehicle crime` | 2022→2023 | +0.02899 | -0.02096 | incidents per 1,000 |
| Yorkshire and The Humber | `Anti-social behaviour` | 2015→2016 | -0.08429 | +0.05606 | incidents per 1,000 |
| Yorkshire and The Humber | `Possession of weapons` | 2023→2024 | +0.01140 | -0.00107 | incidents per 1,000 |
| East Midlands | `Anti-social behaviour` | 2023→2024 | +0.03330 | -0.15445 | incidents per 1,000 |
| West Midlands | `Anti-social behaviour` | 2023→2024 | +0.01124 | -0.12817 | incidents per 1,000 |
| West Midlands | `Bicycle theft` | 2015→2016 | -0.03598 | +0.01143 | incidents per 1,000 |
| West Midlands | `Other theft` | 2015→2016 | -0.05754 | +0.02116 | incidents per 1,000 |
| West Midlands | `Possession of weapons` | 2022→2023 | +0.00939 | -0.01483 | incidents per 1,000 |
| East of England | `Bicycle theft` | 2015→2016 | -0.11274 | +0.04080 | incidents per 1,000 |
| East of England | `Bicycle theft` | 2021→2022 | +0.01373 | -0.04143 | incidents per 1,000 |
| East of England | `Drugs` | 2016→2017 | +0.00249 | -0.01011 | incidents per 1,000 |
| East of England | `Other theft` | 2015→2016 | -0.07410 | +0.00218 | incidents per 1,000 |
| East of England | `Theft from the person` | 2014→2015 | -0.00570 | +0.00065 | incidents per 1,000 |
| East of England | `Theft from the person` | 2023→2024 | +0.00351 | -0.00533 | incidents per 1,000 |
| East of England | `All street crime` | 2024→2025 | -0.07457 | +0.41537 | incidents per 1,000 |
| London | `Criminal damage and arson` | 2015→2016 | -0.02503 | +0.08707 | incidents per 1,000 |
| London | `Other crime` | 2016→2017 | +0.02192 | -0.00141 | incidents per 1,000 |
| London | `Other crime` | 2020→2021 | -0.01122 | +0.00467 | incidents per 1,000 |
| London | `Theft from the person` | 2015→2016 | -0.30699 | +0.10406 | incidents per 1,000 |
| London | `Violence and sexual offences` | 2018→2019 | +0.01458 | -0.03139 | incidents per 1,000 |
| London | `Violence and sexual offences` | 2019→2020 | -0.49818 | +0.05288 | incidents per 1,000 |
| South East | `Anti-social behaviour` | 2023→2024 | +0.08202 | -0.04514 | incidents per 1,000 |
| South East | `Bicycle theft` | 2015→2016 | -0.03367 | +0.13180 | incidents per 1,000 |
| South East | `Robbery` | 2023→2024 | +0.00022 | -0.00938 | incidents per 1,000 |
| South West | `Criminal damage and arson` | 2020→2021 | +0.02279 | -0.04538 | incidents per 1,000 |
| South West | `Criminal damage and arson` | 2021→2022 | -0.38981 | +0.06966 | incidents per 1,000 |
| South West | `Other crime` | 2022→2023 | +0.02792 | -0.01592 | incidents per 1,000 |
| South West | `Other theft` | 2024→2025 | -0.04983 | +0.02954 | incidents per 1,000 |
| South West | `Possession of weapons` | 2021→2022 | +0.00724 | -0.02620 | incidents per 1,000 |
| South West | `Public order` | 2024→2025 | -0.08623 | +0.01019 | incidents per 1,000 |
| South West | `Robbery` | 2022→2023 | +0.10284 | -0.02622 | incidents per 1,000 |
| South West | `Theft from the person` | 2016→2017 | +0.00232 | -0.00595 | incidents per 1,000 |
| South West | `Theft from the person` | 2022→2023 | +0.07687 | -0.01291 | incidents per 1,000 |
| South West | `Vehicle crime` | 2022→2023 | +0.12016 | -0.77931 | incidents per 1,000 |
| South West | `Violence and sexual offences` | 2019→2020 | -0.01012 | +0.05705 | incidents per 1,000 |
| South West | `All street crime` | 2021→2022 | -3.40175 | +4.78402 | incidents per 1,000 |

#### Health (90)

| Geography | Metric | Interval | `b152edf` change | Current change | Unit |
|---|---|---:|---:|---:|---|
| England | `AF` | 2019-20→2020-21 | -0.00320 | +0.00076 | percentage points |
| England | `CHD` | 2018-19→2019-20 | +0.01756 | -0.00887 | percentage points |
| England | `CKD` | 2015-16→2016-17 | -0.01209 | +0.01818 | percentage points |
| England | `EP` | 2015-16→2016-17 | -0.00588 | +0.00513 | percentage points |
| England | `EP` | 2016-17→2017-18 | -0.00054 | +0.00007 | percentage points |
| England | `HYP` | 2015-16→2016-17 | -0.01724 | +0.09841 | percentage points |
| North East | `CKD` | 2020-21→2021-22 | +0.00310 | -0.00079 | percentage points |
| North East | `HYP` | 2013-14→2014-15 | -0.00982 | +0.00196 | percentage points |
| North East | `RA` | 2021-22→2022-23 | +0.00041 | -0.00118 | percentage points |
| North West | `CKD` | 2016-17→2017-18 | +0.00387 | -0.00337 | percentage points |
| North West | `COPD` | 2018-19→2019-20 | -0.00078 | +0.00212 | percentage points |
| North West | `EP` | 2020-21→2021-22 | +0.00034 | -0.00068 | percentage points |
| North West | `RA` | 2013-14→2014-15 | -0.00121 | +0.00010 | percentage points |
| North West | `RA` | 2020-21→2021-22 | +0.00106 | -0.00051 | percentage points |
| North West | `RA` | 2021-22→2022-23 | +0.00021 | -0.00038 | percentage points |
| East Midlands | `AF` | 2019-20→2020-21 | -0.00392 | +0.00111 | percentage points |
| East Midlands | `CHD` | 2018-19→2019-20 | +0.01552 | -0.02206 | percentage points |
| East Midlands | `CKD` | 2018-19→2019-20 | +0.02977 | -0.02176 | percentage points |
| East Midlands | `DEM` | 2016-17→2017-18 | +0.00036 | -0.00143 | percentage points |
| East Midlands | `EP` | 2015-16→2016-17 | -0.06615 | +0.00581 | percentage points |
| East Midlands | `HYP` | 2017-18→2018-19 | -0.05721 | +0.11146 | percentage points |
| East Midlands | `PC` | 2017-18→2018-19 | -0.00368 | +0.00347 | percentage points |
| East Midlands | `STIA` | 2017-18→2018-19 | -0.00602 | +0.01616 | percentage points |
| East Midlands | `STIA` | 2019-20→2020-21 | -0.00001 | +0.00296 | percentage points |
| West Midlands | `AST` | 2015-16→2016-17 | -0.28348 | +0.04631 | percentage points |
| West Midlands | `AST` | 2016-17→2017-18 | +0.31960 | -0.00043 | percentage points |
| West Midlands | `CHD` | 2016-17→2017-18 | +0.17379 | -0.02161 | percentage points |
| West Midlands | `CKD` | 2013-14→2014-15 | +0.00703 | -0.00030 | percentage points |
| West Midlands | `CKD` | 2015-16→2016-17 | -0.19791 | +0.05312 | percentage points |
| West Midlands | `COPD` | 2015-16→2016-17 | -0.07941 | +0.02875 | percentage points |
| West Midlands | `DEM` | 2015-16→2016-17 | -0.02936 | +0.01361 | percentage points |
| West Midlands | `DM` | 2015-16→2016-17 | -0.20870 | +0.10584 | percentage points |
| West Midlands | `EP` | 2015-16→2016-17 | -0.03615 | +0.00097 | percentage points |
| West Midlands | `HF` | 2015-16→2016-17 | -0.00882 | +0.03613 | percentage points |
| West Midlands | `HYP` | 2015-16→2016-17 | -0.82819 | +0.06930 | percentage points |
| West Midlands | `LD` | 2015-16→2016-17 | -0.01133 | +0.01308 | percentage points |
| West Midlands | `MH` | 2015-16→2016-17 | -0.01793 | +0.02514 | percentage points |
| West Midlands | `OB` | 2015-16→2016-17 | -0.20785 | +0.34898 | percentage points |
| West Midlands | `PAD` | 2016-17→2017-18 | +0.01712 | -0.01642 | percentage points |
| West Midlands | `PC` | 2015-16→2016-17 | -0.01843 | +0.02741 | percentage points |
| West Midlands | `RA` | 2014-15→2015-16 | +0.00065 | -0.00052 | percentage points |
| West Midlands | `RA` | 2015-16→2016-17 | -0.03420 | +0.00414 | percentage points |
| West Midlands | `STIA` | 2015-16→2016-17 | -0.08370 | +0.02126 | percentage points |
| East of England | `AF` | 2019-20→2020-21 | -0.00363 | +0.00027 | percentage points |
| East of England | `CHD` | 2018-19→2019-20 | +0.00394 | -0.00680 | percentage points |
| East of England | `STIA` | 2019-20→2020-21 | -0.00181 | +0.00052 | percentage points |
| London | `AST` | 2015-16→2016-17 | -0.01528 | +0.00064 | percentage points |
| London | `CKD` | 2013-14→2014-15 | +0.00079 | -0.00327 | percentage points |
| London | `DEM` | 2018-19→2019-20 | -0.00068 | +0.00079 | percentage points |
| London | `EP` | 2018-19→2019-20 | -0.00012 | +0.00089 | percentage points |
| London | `RA` | 2016-17→2017-18 | -0.00025 | +0.00146 | percentage points |
| London | `STIA` | 2015-16→2016-17 | -0.00001 | +0.00330 | percentage points |
| South East | `AF` | 2016-17→2017-18 | -0.01340 | +0.08445 | percentage points |
| South East | `AST` | 2016-17→2017-18 | -0.27896 | +0.01570 | percentage points |
| South East | `CHD` | 2018-19→2019-20 | +0.00144 | -0.00296 | percentage points |
| South East | `CHD` | 2022-23→2023-24 | +0.00027 | -0.00251 | percentage points |
| South East | `CKD` | 2016-17→2017-18 | -0.09872 | +0.01203 | percentage points |
| South East | `COPD` | 2016-17→2017-18 | -0.02670 | +0.03283 | percentage points |
| South East | `DEM` | 2016-17→2017-18 | -0.03346 | +0.00349 | percentage points |
| South East | `DM` | 2016-17→2017-18 | -0.12123 | +0.10386 | percentage points |
| South East | `EP` | 2016-17→2017-18 | -0.02274 | +0.00200 | percentage points |
| South East | `HYP` | 2016-17→2017-18 | -0.46228 | +0.17457 | percentage points |
| South East | `LD` | 2016-17→2017-18 | -0.00572 | +0.01288 | percentage points |
| South East | `MH` | 2016-17→2017-18 | -0.01710 | +0.01935 | percentage points |
| South East | `OB` | 2015-16→2016-17 | -0.01162 | +0.01343 | percentage points |
| South East | `OB` | 2016-17→2017-18 | -0.17301 | +0.09439 | percentage points |
| South East | `PAD` | 2023-24→2024-25 | +0.00001 | -0.00013 | percentage points |
| South East | `PC` | 2016-17→2017-18 | -0.01762 | +0.01933 | percentage points |
| South East | `RA` | 2016-17→2017-18 | -0.01567 | +0.00882 | percentage points |
| South East | `STIA` | 2016-17→2017-18 | -0.05265 | +0.02286 | percentage points |
| South West | `AF` | 2017-18→2018-19 | -0.04376 | +0.10360 | percentage points |
| South West | `AST` | 2017-18→2018-19 | -0.20944 | +0.16557 | percentage points |
| South West | `CHD` | 2017-18→2018-19 | -0.21094 | +0.02171 | percentage points |
| South West | `CKD` | 2017-18→2018-19 | -0.18256 | +0.02050 | percentage points |
| South West | `CKD` | 2018-19→2019-20 | +0.17647 | -0.03500 | percentage points |
| South West | `CKD` | 2020-21→2021-22 | +0.00225 | -0.00611 | percentage points |
| South West | `COPD` | 2017-18→2018-19 | -0.07730 | +0.05018 | percentage points |
| South West | `DEM` | 2017-18→2018-19 | -0.03015 | +0.01628 | percentage points |
| South West | `DM` | 2017-18→2018-19 | -0.17431 | +0.13929 | percentage points |
| South West | `HF` | 2018-19→2019-20 | +0.03359 | -0.02850 | percentage points |
| South West | `HYP` | 2017-18→2018-19 | -0.78264 | +0.10252 | percentage points |
| South West | `LD` | 2017-18→2018-19 | -0.01031 | +0.01722 | percentage points |
| South West | `LD` | 2018-19→2019-20 | +0.02697 | -0.00130 | percentage points |
| South West | `MH` | 2017-18→2018-19 | -0.02500 | +0.01891 | percentage points |
| South West | `MH` | 2018-19→2019-20 | +0.00785 | -0.03792 | percentage points |
| South West | `OB` | 2017-18→2018-19 | -0.23679 | +0.29906 | percentage points |
| South West | `PAD` | 2017-18→2018-19 | -0.02088 | +0.01459 | percentage points |
| South West | `PAD` | 2018-19→2019-20 | +0.02835 | -0.00815 | percentage points |
| South West | `RA` | 2017-18→2018-19 | -0.02399 | +0.01906 | percentage points |
| South West | `STIA` | 2017-18→2018-19 | -0.11135 | +0.03637 | percentage points |
