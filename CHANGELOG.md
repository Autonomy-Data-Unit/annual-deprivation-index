# Changelog

## 2026-09-02 — corrected 2014–2025 data release

This is a **breaking historical revision**, not an append-only annual update. Replace earlier extracts and rerun existing analysis. The comparison below uses commit `b152edf` as the pre-run baseline.

**How to identify the corrected release.** This dated changelog entry is the canonical restatement record; no semantic version is being assigned retrospectively to earlier unversioned archives. A corrected archive contains `recorded_count`, `registration_coverage`, `qof_coverage`, and historical `CVDPP`. Any archive without that schema is superseded even if its filename is identical. Preserve the archive README's generated date with analytical provenance, and record this `2026-09-02` release in derived outputs.

### The decisions that can change an existing result

- **The old headline crime measure was wrong for “police-recorded crime”.** It added anti-social behaviour (ASB) to 13 police-recorded crime categories even though ASB is a separately governed incident series. The headline now excludes ASB; ASB remains downloadable and selectable on its own. On the refreshed data, the old 14-series sum showed England rising **15.8% from 2014 to 2018**, whereas the corrected 13-category recorded-crime measure rises **43.0%**. An analysis quoting the former headline trend mixed two different collections and must be rebuilt.
- Incomplete police force-years and force-years with less than 90% LSOA geocoding are now withheld, rather than being presented as complete annual observations. The number of wholly blank LAD crime rows by year is **0, 0, 5, 5, 14, 47, 16, 16, 16, 10, 10, 15** for 2014–2025.
- Every metric count now has a metric-specific coverage population. Use `<count>_pop`, not automatically the row's `pop`, as its denominator.
- The public health set now contains **22 metrics**: CVD primary prevention (`CVDPP`) is restored for the seven output years 2014–2020 and blank after withdrawal.
- Health estimates now publish `registration_coverage` and `qof_coverage`; QOF practice weights are renormalised, thin disease-specific QOF coverage is withheld, and series endpoints are no longer extrapolated.
- Across the common pre-run/current England and Region measures, **145 area–metric series have at least one changed trend direction**, comprising **194 strict adjacent-year reversals**. The former 147/124 figures are stale. The full comparison appears below.

## What changed

### Crime: replace every analysis of the former headline

The downloadable and site headline is now **Police-recorded street crime (excludes ASB)**:

```text
recorded_count       sum of 13 police-recorded crime categories
recorded_count_pop   population covered by those categories
recorded_count_rate  recorded_count / recorded_count_pop
```

`Anti-social behaviour` has its own count, coverage population and rate and must not be added to `recorded_count` when describing recorded crime. This is a definition correction, not a cosmetic rename. Previously published headline values cannot be interpreted as a recorded-crime series, because they combined the main police-recorded crime collection with ASB incidents governed under the National Standard for Incident Recording.

The input treatment also changed:

- British Transport Police is excluded entirely: its relevant exposure is rail passengers, not the resident population used by ADI.
- A territorial force-year is accepted only if all 12 monthly street files are present and non-empty and at least 90% of potentially English records have an English LSOA code.
- An identified incident repeated exactly in the source is deduplicated. Records without an incident ID, notably ASB, are not deduplicated merely because their anonymised fields match.
- When a force-year fails, its whole inferred LAD/LSOA footprint is blank. Region and England values remain available over the smaller metric-specific covered population; they may therefore cover a different footprint in adjacent years.

Current unavailable force footprints are Avon and Somerset (2016–2019 and 2025), Staffordshire (2018), Lancashire, Thames Valley and Suffolk (2019), Greater Manchester (2019–2025), and Gloucestershire (2020–2022). Exact LAD counts are:

| Year | Blank LAD crime rows | Main cause |
|---:|---:|---|
| 2014 | 0 | — |
| 2015 | 0 | — |
| 2016 | 5 | Avon and Somerset |
| 2017 | 5 | Avon and Somerset |
| 2018 | 14 | Avon and Somerset; Staffordshire |
| 2019 | 47 | Avon and Somerset; Lancashire; Thames Valley; Suffolk; Greater Manchester |
| 2020 | 16 | Gloucestershire; Greater Manchester |
| 2021 | 16 | Gloucestershire; Greater Manchester |
| 2022 | 16 | Gloucestershire; Greater Manchester |
| 2023 | 10 | Greater Manchester |
| 2024 | 10 | Greater Manchester |
| 2025 | 15 | Avon and Somerset; Greater Manchester |

These blanks supersede earlier guidance that singled out Devon & Cornwall and City of London in 2022; the revision-aware source refresh changed which force-years meet the explicit tests. Do not copy an old missingness mask into a new analysis.

### Population and geographic conversion

LSOA 2011 source data is converted to LSOA 2021 before publication. Split-LSOA weights are now calculated from the **same year's LSOA 2021 population** that is published in `pop`; previously, a later population frame could split an earlier year's count. Rates and trends can therefore change in every year.

The LSOA-level source is available through mid-2024. ADI explicitly carries that estimate forward for 2025 and aggregates the same LSOA base to LAD, Region and England, rather than mixing in newer upper-geography estimates. Population fetching now verifies the year actually returned: an allowed one-year carry-forward is explicit, while a stale, mislabelled, or more-than-one-year substitute raises `PopulationVintageError` instead of silently entering the release.

Six complex many-to-many boundary-change LSOAs remain excluded. The release contains 33,749 of England's 33,755 LSOA 2021 areas, so `pop` is the ONS population summed over included LSOAs rather than necessarily the complete official total for an affected LAD.

### Why counts and denominators behave differently by domain

Every ordinary metric is a three-column group:

```text
<count>        metric count or modelled count
<count>_pop    population covered by that count
<count>_rate   <count> / <count>_pop
```

Employment and crime values are source counts. Introducing the target-year population cannot change how many claimants or incidents were counted, so their counts are retained and their rates are recomputed against the new denominator.

Health `*_afflicted` values are different: they are modelled as a QOF-weighted prevalence rate multiplied by ONS resident population. The prevalence rate is the estimated health quantity. When the population base changes, ADI therefore holds the rate fixed and re-derives `*_afflicted`. Keeping the old modelled count would invent a change in prevalence with no new health measurement. A revised health count can consequently reflect a population revision even when the estimated prevalence is unchanged, and it is not comparable to a raw QOF register count.

At higher geographies, a smaller `<count>_pop` means some LSOAs had no usable value. Sum counts and their matching coverage populations separately, then divide. Never replace a blank with zero or divide a partially covered count by full `pop`.

### Health: coverage, assumptions and restored history

- QOF practice weights now renormalise over practices with a usable disease register and positive list size. A practice missing from a publication is no longer treated as having zero prevalence.
- Disease estimates below 80% disease-specific QOF registration coverage are withheld. The threshold is applied before short interior gaps are interpolated.
- `qof_coverage` reports the overall share of GP registrations at practices included in that year's QOF publication with a usable list. Disease-specific coverage can be lower.
- `registration_coverage` reports total GP registrations divided by ONS residents. It can exceed 1 because they are different administrative measures and is reported rather than thresholded.
- Two representativeness assumptions are unavoidable: a practice's overall QOF prevalence is applied uniformly to its patients in every LSOA it serves, and GP registrations attributed to an LSOA are assumed to represent all residents there. The coverage columns reveal how much evidence is represented but cannot verify either assumption.
- Leading and trailing gaps are left blank; only one- or two-year interior gaps bracketed by observations are interpolated.
- A disease register larger than its practice list is arithmetically impossible and is rejected. Estimated prevalence outside `[0, 1]` is likewise rejected to missing, never clamped.
- Eight implausible LSOA epilepsy values in 2016 and seven heart-failure values in 2021 are rejected at publication. Depression in output year 2024 and osteoporosis in 2015 have known one-year source-basis anomalies and are replaced from adjacent LSOA rates only where both anchors exist.
- `CVDPP` is published for output years 2014–2020 (QOF 2013-14 through 2019-20) and blank from 2021. Its England series has a sharp 2014→2015 break, and Dartford's 2019 value remains a known local anomaly; do not treat the seven-year window as automatically homogeneous.
- The one-year `SMOK` and `THY` source groups remain excluded. Together with restored `CVDPP`, the download and site contain 22 health metrics.

Health output year `2021` means QOF 2020-21 (April 2020 to March 2021). Employment and crime year `2021` mean calendar year 2021. A join on the numeric label therefore does not align identical periods.

### Download bundles and site delivery

Four archives are published: `adi-england.zip`, `adi-region.zip`, `adi-lad.zip`, and `adi-lsoa.zip`. Each contains long-by-year employment, crime and health CSVs, a data dictionary, a geography file, and a README. Tables are keyed by `code`, `name`, and `year`, with 12 rows per area: 12 England rows, 108 Region rows, 3,552 LAD rows, or 404,988 LSOA rows.

The crime CSV now includes the derived `recorded_count` triple as well as all 13 constituent crime categories and the separate ASB series. The health CSV includes 22 metrics plus `registration_coverage` and `qof_coverage`. Counts retain sufficient decimal precision to reproduce the published eight-decimal rates.

Bundle metadata reports compressed on-disk sizes in decimal `KB`/`MB` and extracted sizes in binary `KiB`/`MiB`, so the number and unit agree. Known routes—the home, Explorer, Area, Compare, Trends, ADI-vs-IMD, Download and About pages—are prerendered as real route HTML. Crawlers and visitors without JavaScript therefore receive page content rather than only the application shell.

See [METHODOLOGY.md](METHODOLOGY.md) and each archive's data dictionary for full definitions.

## Intentional blank coverage

| Domain / metric | Years | Blank coverage | Interpretation |
|---|---:|---|---|
| All 14 crime component series and the recorded-crime aggregate | 2014–2025 | LAD counts by year: 0/0/5/5/14/47/16/16/16/10/10/15 | Failed force-years are withheld over their full footprints; Region/England use covered populations. |
| All 21 canonical health conditions plus `CVDPP` | 2014 | 64 LSOAs | No usable leading observation; endpoint extrapolation has been removed. |
| All 21 canonical health conditions | 2024 | Braintree 005C (1 LSOA) | No usable source estimate in that year. |
| All 21 canonical health conditions | 2025 | Braintree 005C and Isles of Scilly 001A (2 LSOAs) | No usable trailing observation; Isles of Scilly consequently has a wholly blank LAD health row. |
| `NDH` | 2014–2020 | All areas | The QOF group was not yet collected; blank does not mean zero prevalence. |
| `NDH` | 2021 | 16 LSOAs | No usable estimate in the first collected year. |
| `CVDPP` | 2020 | 21 LSOAs | No usable estimate in the last collected output year. |
| `CVDPP` | 2021–2025 | All areas | Register withdrawn; blank does not mean zero prevalence. |
| `EP` | 2016 | 8 LSOAs | Implausible one-year spikes rejected at publication. |
| `HF` | 2021 | 7 LSOAs | Implausible one-year spikes rejected at publication. |
| `DEP` | 2024 (QOF 2023-24) | 2 LSOAs: Braintree 005C and Isles of Scilly 001A | Source-basis anomaly replaced only where both adjacent anchors exist. |
| `OST` | 2015 (QOF 2014-15) | 64 LSOAs | Source-basis anomaly replaced only where both adjacent anchors exist. |
| `SMOK`, `THY` | Release-wide | Columns removed from public data | One-year source groups, not zero-prevalence conditions. |

## Trend-direction restatement

### Method

The audit compared the 4,440 rate values in the 370 area–metric series common to both releases (10 England/Region geographies × 37 metrics × 12 years). `CVDPP` is documented separately because it was not present on the `b152edf` public surface. The baseline was reconstructed with `b152edf` aggregation and publication corrections. The current side uses the reprocessed store outputs plus the current publication-stage health corrections; its headline crime total is the corrected 13-category recorded-crime measure, while `b152edf` used the mixed 14-series headline.

A reversal means two finite adjacent-year differences have strictly opposite signs. A transition involving a blank or exact zero difference is not counted. This is a release-impact inventory, not a claim of statistical significance.

There are **194 reversed adjacent-year comparisons across 145 distinct area–metric series**:

| Geography/domain | Reversed comparisons | Distinct series |
|---|---:|---:|
| England — Claimant Count | 0 | 0 |
| Regions — Claimant Count | 2 | 2 |
| England — crime | 12 | 8 |
| Regions — crime | 90 | 59 |
| England — health | 6 | 5 |
| Regions — health | 84 | 71 |
| **Total** | **194** | **145** |

Of the 194 comparisons, 123 have an absolute old or current movement of at least 0.1 incidents per 1,000 for crime or 0.01 percentage points for employment/health. There are 14 reversals at the 2020→2021 boundary and 7 at 2024→2025. The 2025 cases are not caused by a new LSOA population estimate: 2025 deliberately repeats the mid-2024 base.

The largest changed directions are concentrated in the redefined crime headline:

| Geography | Metric and interval | `b152edf` movement | Current movement |
|---|---|---:|---:|
| North West | Crime headline, 2019→2020 | +25.30125 per 1,000 | -6.26004 per 1,000 |
| South East | Crime headline, 2019→2020 | +1.49129 per 1,000 | -10.05968 per 1,000 |
| London | Crime headline, 2019→2020 | +6.43422 per 1,000 | -8.51975 per 1,000 |
| England | Crime headline, 2019→2020 | +3.46526 per 1,000 | -7.54536 per 1,000 |
| North West | Crime headline, 2017→2018 | -0.64719 per 1,000 | +8.30472 per 1,000 |
| North East | Crime headline, 2020→2021 | -7.53268 per 1,000 | +0.66907 per 1,000 |
| East Midlands | Crime headline, 2021→2022 | -1.10716 per 1,000 | +5.69328 per 1,000 |
| North West | Crime headline, 2021→2022 | -3.38690 per 1,000 | +5.31667 per 1,000 |

Those headline differences combine a corrected definition, refreshed source archives, BTP exclusion and force-coverage rejection. Do not interpret them as the effect of any single processing change.

## What analysts should rerun

1. **Replace earlier extracts rather than appending 2025.** Corrections affect the complete history.
2. **Rebuild every crime headline.** Use `recorded_count`/`recorded_count_rate` for recorded crime and analyse ASB separately. Do not compare a former 14-series “total” directly with the new 13-category series.
3. **Rebuild crime time comparisons and area rankings with coverage checks.** Force exclusions change both values and which resident population is represented. Do not impute blank force footprints as zero.
4. **Update denominator code.** Use each `<count>_pop`; sum count and coverage population separately before division. Do not average local rates.
5. **Rerun every historical trend, rank, threshold, regression and chart.** There are 194 changed England/Region adjacent-year directions, and local results can change even where an aggregate direction does not.
6. **Treat health counts as modelled resident estimates.** A population revision can change `*_afflicted` while prevalence remains fixed. Do not reconcile these values as if they were raw QOF register counts.
7. **Use the new coverage indicators.** Inspect `registration_coverage` and `qof_coverage`, especially for border, transient, or low-registration areas. Neither tests whether a practice's prevalence is uniform across its served LSOAs or whether represented registrations resemble all residents.
8. **Restore or remove health metrics deliberately.** `CVDPP` is available only for 2014–2020 and has known comparability concerns; `SMOK` and `THY` remain absent.
9. **Align periods explicitly.** Health uses QOF financial years labelled by ending year; employment and crime use calendar years.
10. **Refresh parsers and metadata.** Account for the `recorded_count` triple, 22 health metrics, two health coverage columns, dictionaries/geography files, and intentional blanks.

## Validation and residual issues

The extended whole-series validator was rerun against the current `store/outputs/default`:

```text
uv run python scripts/validate_outputs.py
SUMMARY: 24 BLOCKER, 104 WARN, 1 INFO
```

These are raw-pipeline findings, before publication-stage health corrections:

| Raw-store blocker class | Findings | Publication status |
|---|---:|---|
| Depression 2023-24 and osteoporosis 2014-15 source-basis anomalies | 18 | Known; corrected from flanking LSOA observations at publication. |
| Hinckley and Bosworth epilepsy spike | 1 | Known; removed by publication-stage LSOA spike rejection. |
| London anti-social behaviour in 2020 | 1 | Known COVID-period recorded-ASB event; retained as source data for review. |
| Dartford `CVDPP` reversal | 1 | Known and still published within the restored historical window. |
| Dacorum/Hertsmere/Dorset palliative-care and East Staffordshire/Rutland obesity reversals | 3 grouped findings covering 5 LADs | Known and still published; unresolved source-plausibility concerns. |

No new blocker class was found. This is not an unconditional quality guarantee: the Dartford `CVDPP` value and the five LAD health anomalies remain known concerns. The validator found no rate/count/coverage-population identity failure, incoherent partial triple, area-set loss, additivity failure or split-family inconsistency. A separate extremes review continues to flag the documented Forest of Dean 010C Claimant Count spike; no new release-blocking pattern was identified.

## Complete reversal table

Positive values mean an increase and negative values a decrease. Crime changes are incidents per 1,000 people in the metric's covered population; employment and health changes are percentage points. Health intervals use QOF financial-year labels. The values are movements within each release, not the difference between releases in a single year.

#### Claimant Count (2)

| Geography | Metric | Interval | `b152edf` change | Current change | Unit |
|---|---|---:|---:|---:|---|
| North East | `Claimant Count` | 2023→2024 | +0.02276 | -0.00978 | percentage points |
| North West | `Claimant Count` | 2020→2021 | +0.00124 | -0.02079 | percentage points |

#### Crime (102)

| Geography | Metric | Interval | `b152edf` change | Current change | Unit |
|---|---|---:|---:|---:|---|
| England | `Anti-social behaviour` | 2023→2024 | +0.00399 | -0.17698 | incidents per 1,000 |
| England | `Bicycle theft` | 2015→2016 | -0.04314 | +0.03738 | incidents per 1,000 |
| England | `Burglary` | 2022→2023 | +0.02052 | -0.04975 | incidents per 1,000 |
| England | `Other crime` | 2018→2019 | -0.02170 | +0.01981 | incidents per 1,000 |
| England | `Other crime` | 2022→2023 | +0.02550 | -0.00412 | incidents per 1,000 |
| England | `Other theft` | 2022→2023 | +0.05284 | -0.08126 | incidents per 1,000 |
| England | `Robbery` | 2023→2024 | +0.00082 | -0.00961 | incidents per 1,000 |
| England | `Theft from the person` | 2015→2016 | -0.00548 | +0.09819 | incidents per 1,000 |
| England | `Theft from the person` | 2017→2018 | -0.00461 | +0.00554 | incidents per 1,000 |
| England | `Recorded-crime headline` | 2018→2019 | -3.96556 | +0.20259 | incidents per 1,000 |
| England | `Recorded-crime headline` | 2019→2020 | +3.46526 | -7.54536 | incidents per 1,000 |
| England | `Recorded-crime headline` | 2020→2021 | -2.49851 | +3.64904 | incidents per 1,000 |
| North East | `Burglary` | 2023→2024 | +0.05601 | -0.01364 | incidents per 1,000 |
| North East | `Other crime` | 2021→2022 | +0.01382 | -0.02295 | incidents per 1,000 |
| North East | `Public order` | 2021→2022 | +0.10007 | -0.07803 | incidents per 1,000 |
| North East | `Shoplifting` | 2020→2021 | +0.02464 | -0.00349 | incidents per 1,000 |
| North East | `Shoplifting` | 2024→2025 | -0.00485 | +0.00290 | incidents per 1,000 |
| North East | `Recorded-crime headline` | 2020→2021 | -7.53268 | +0.66907 | incidents per 1,000 |
| North West | `Bicycle theft` | 2015→2016 | -0.02205 | +0.00533 | incidents per 1,000 |
| North West | `Bicycle theft` | 2024→2025 | -0.00952 | +0.00571 | incidents per 1,000 |
| North West | `Criminal damage and arson` | 2019→2020 | +0.88874 | -0.81107 | incidents per 1,000 |
| North West | `Drugs` | 2019→2020 | +1.39664 | -0.56009 | incidents per 1,000 |
| North West | `Possession of weapons` | 2019→2020 | +0.00001 | -0.01544 | incidents per 1,000 |
| North West | `Public order` | 2019→2020 | +0.67854 | -1.60326 | incidents per 1,000 |
| North West | `Vehicle crime` | 2022→2023 | +0.02899 | -0.03124 | incidents per 1,000 |
| North West | `Recorded-crime headline` | 2017→2018 | -0.64719 | +8.30472 | incidents per 1,000 |
| North West | `Recorded-crime headline` | 2019→2020 | +25.30125 | -6.26004 | incidents per 1,000 |
| North West | `Recorded-crime headline` | 2020→2021 | -3.46723 | +5.72564 | incidents per 1,000 |
| North West | `Recorded-crime headline` | 2021→2022 | -3.38691 | +5.31667 | incidents per 1,000 |
| Yorkshire and The Humber | `Anti-social behaviour` | 2015→2016 | -0.08429 | +0.05606 | incidents per 1,000 |
| Yorkshire and The Humber | `Possession of weapons` | 2023→2024 | +0.01140 | -0.00035 | incidents per 1,000 |
| Yorkshire and The Humber | `Recorded-crime headline` | 2018→2019 | -2.54338 | +1.53469 | incidents per 1,000 |
| East Midlands | `Anti-social behaviour` | 2023→2024 | +0.03330 | -0.15445 | incidents per 1,000 |
| East Midlands | `Recorded-crime headline` | 2019→2020 | +0.66015 | -6.05161 | incidents per 1,000 |
| East Midlands | `Recorded-crime headline` | 2020→2021 | -2.02936 | +3.09207 | incidents per 1,000 |
| East Midlands | `Recorded-crime headline` | 2021→2022 | -1.10716 | +5.69328 | incidents per 1,000 |
| West Midlands | `Anti-social behaviour` | 2023→2024 | +0.01124 | -0.12817 | incidents per 1,000 |
| West Midlands | `Bicycle theft` | 2015→2016 | -0.03598 | +0.01143 | incidents per 1,000 |
| West Midlands | `Other crime` | 2017→2018 | +0.00251 | -0.04382 | incidents per 1,000 |
| West Midlands | `Other theft` | 2015→2016 | -0.05754 | +0.02116 | incidents per 1,000 |
| West Midlands | `Possession of weapons` | 2022→2023 | +0.00939 | -0.01483 | incidents per 1,000 |
| West Midlands | `Robbery` | 2018→2019 | +0.10527 | -0.11796 | incidents per 1,000 |
| West Midlands | `Shoplifting` | 2017→2018 | -0.29378 | +0.23264 | incidents per 1,000 |
| West Midlands | `Recorded-crime headline` | 2019→2020 | +4.37526 | -0.86457 | incidents per 1,000 |
| East of England | `Bicycle theft` | 2015→2016 | -0.11274 | +0.04080 | incidents per 1,000 |
| East of England | `Bicycle theft` | 2021→2022 | +0.01373 | -0.04425 | incidents per 1,000 |
| East of England | `Drugs` | 2016→2017 | +0.00249 | -0.01011 | incidents per 1,000 |
| East of England | `Other theft` | 2015→2016 | -0.07410 | +0.00382 | incidents per 1,000 |
| East of England | `Theft from the person` | 2014→2015 | -0.00570 | +0.00065 | incidents per 1,000 |
| East of England | `Theft from the person` | 2023→2024 | +0.00351 | -0.00517 | incidents per 1,000 |
| East of England | `Recorded-crime headline` | 2018→2019 | -0.58693 | +2.77989 | incidents per 1,000 |
| East of England | `Recorded-crime headline` | 2021→2022 | -0.60995 | +2.43047 | incidents per 1,000 |
| East of England | `Recorded-crime headline` | 2024→2025 | -0.07457 | +0.72191 | incidents per 1,000 |
| London | `Criminal damage and arson` | 2015→2016 | -0.02503 | +0.09284 | incidents per 1,000 |
| London | `Other crime` | 2016→2017 | +0.02192 | -0.00037 | incidents per 1,000 |
| London | `Other crime` | 2020→2021 | -0.01122 | +0.00131 | incidents per 1,000 |
| London | `Possession of weapons` | 2022→2023 | +0.01166 | -0.00319 | incidents per 1,000 |
| London | `Theft from the person` | 2015→2016 | -0.30699 | +0.10446 | incidents per 1,000 |
| London | `Violence and sexual offences` | 2018→2019 | +0.01458 | -1.17858 | incidents per 1,000 |
| London | `Violence and sexual offences` | 2019→2020 | -0.49818 | +1.53271 | incidents per 1,000 |
| London | `Recorded-crime headline` | 2014→2015 | -1.90175 | +2.27345 | incidents per 1,000 |
| London | `Recorded-crime headline` | 2019→2020 | +6.43421 | -8.51975 | incidents per 1,000 |
| South East | `Anti-social behaviour` | 2023→2024 | +0.08202 | -0.04514 | incidents per 1,000 |
| South East | `Bicycle theft` | 2015→2016 | -0.03367 | +0.13169 | incidents per 1,000 |
| South East | `Burglary` | 2018→2019 | -0.09807 | +0.22639 | incidents per 1,000 |
| South East | `Criminal damage and arson` | 2018→2019 | -0.08691 | +0.50615 | incidents per 1,000 |
| South East | `Other crime` | 2019→2020 | +0.05279 | -0.11176 | incidents per 1,000 |
| South East | `Public order` | 2018→2019 | -0.24510 | +0.88110 | incidents per 1,000 |
| South East | `Public order` | 2019→2020 | +0.61840 | -0.45632 | incidents per 1,000 |
| South East | `Robbery` | 2023→2024 | +0.00022 | -0.00938 | incidents per 1,000 |
| South East | `Shoplifting` | 2018→2019 | -0.05318 | +0.27790 | incidents per 1,000 |
| South East | `Theft from the person` | 2018→2019 | +0.04357 | -0.08367 | incidents per 1,000 |
| South East | `Violence and sexual offences` | 2019→2020 | +0.99035 | -1.68275 | incidents per 1,000 |
| South East | `Recorded-crime headline` | 2017→2018 | -2.89254 | +3.63373 | incidents per 1,000 |
| South East | `Recorded-crime headline` | 2019→2020 | +1.49129 | -10.05968 | incidents per 1,000 |
| South East | `Recorded-crime headline` | 2021→2022 | -1.31373 | +3.03322 | incidents per 1,000 |
| South West | `Anti-social behaviour` | 2015→2016 | -2.03405 | +0.55773 | incidents per 1,000 |
| South West | `Bicycle theft` | 2017→2018 | +0.01908 | -0.00296 | incidents per 1,000 |
| South West | `Bicycle theft` | 2019→2020 | -0.15106 | +0.06913 | incidents per 1,000 |
| South West | `Criminal damage and arson` | 2020→2021 | +0.02279 | -0.11644 | incidents per 1,000 |
| South West | `Drugs` | 2015→2016 | -0.18518 | +0.01630 | incidents per 1,000 |
| South West | `Drugs` | 2016→2017 | +0.00855 | -0.02135 | incidents per 1,000 |
| South West | `Drugs` | 2019→2020 | +0.20504 | -0.00715 | incidents per 1,000 |
| South West | `Other crime` | 2017→2018 | -0.01153 | +0.01957 | incidents per 1,000 |
| South West | `Other crime` | 2018→2019 | +0.00833 | -0.01061 | incidents per 1,000 |
| South West | `Other crime` | 2024→2025 | +0.02668 | -0.06211 | incidents per 1,000 |
| South West | `Public order` | 2015→2016 | +1.43441 | -0.18618 | incidents per 1,000 |
| South West | `Public order` | 2021→2022 | +0.43063 | -0.09704 | incidents per 1,000 |
| South West | `Robbery` | 2015→2016 | +0.04289 | -0.04463 | incidents per 1,000 |
| South West | `Robbery` | 2019→2020 | -0.03692 | +0.10726 | incidents per 1,000 |
| South West | `Robbery` | 2024→2025 | +0.07386 | -0.17921 | incidents per 1,000 |
| South West | `Shoplifting` | 2015→2016 | +0.01933 | -0.60588 | incidents per 1,000 |
| South West | `Theft from the person` | 2018→2019 | +0.02216 | -0.01189 | incidents per 1,000 |
| South West | `Vehicle crime` | 2015→2016 | +0.21712 | -0.32873 | incidents per 1,000 |
| South West | `Vehicle crime` | 2022→2023 | +0.12016 | -0.06400 | incidents per 1,000 |
| South West | `Violence and sexual offences` | 2019→2020 | -0.01012 | +0.93061 | incidents per 1,000 |
| South West | `Violence and sexual offences` | 2024→2025 | +0.66547 | -2.20405 | incidents per 1,000 |
| South West | `Recorded-crime headline` | 2014→2015 | -0.98960 | +1.88592 | incidents per 1,000 |
| South West | `Recorded-crime headline` | 2015→2016 | +2.33303 | -0.66962 | incidents per 1,000 |
| South West | `Recorded-crime headline` | 2017→2018 | -1.64364 | +1.92330 | incidents per 1,000 |
| South West | `Recorded-crime headline` | 2020→2021 | -1.90400 | +1.01881 | incidents per 1,000 |
| South West | `Recorded-crime headline` | 2021→2022 | -3.40175 | +2.39562 | incidents per 1,000 |

#### Health (90)

| Geography | Metric | Interval | `b152edf` change | Current change | Unit |
|---|---|---:|---:|---:|---|
| England | `AF` | 2019-20→2020-21 | -0.00320 | +0.00076 | percentage points |
| England | `CHD` | 2018-19→2019-20 | +0.01756 | -0.00887 | percentage points |
| England | `CKD` | 2015-16→2016-17 | -0.01209 | +0.01831 | percentage points |
| England | `EP` | 2015-16→2016-17 | -0.00588 | +0.00514 | percentage points |
| England | `EP` | 2016-17→2017-18 | -0.00054 | +0.00007 | percentage points |
| England | `HYP` | 2015-16→2016-17 | -0.01724 | +0.09916 | percentage points |
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
| West Midlands | `HYP` | 2015-16→2016-17 | -0.82819 | +0.06940 | percentage points |
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
| South East | `OB` | 2015-16→2016-17 | -0.01162 | +0.01515 | percentage points |
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
