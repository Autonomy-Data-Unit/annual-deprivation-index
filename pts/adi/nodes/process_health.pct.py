# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.process_health
#
# Estimate LSOA-level health prevalence by joining QOF practice-level
# disease data with LSOA-level GP patient registrations.
#
# For each QOF year:
# 1. Normalise QOF prevalence data into a standard schema
# 2. Load LSOA-level GP patient registration data (which year's April edition
#    corresponds to this QOF year)
# 3. For each LSOA, compute the weighted prevalence across the GP practices
#    that serve patients from that LSOA AND that QOF published that year,
#    renormalising the weights over those practices and leaving the LSOA
#    missing where they cover too little of it (see `MIN_QOF_COVERAGE`)
# 4. Save per-year CSV with prevalence rates, afflicted counts, and two coverage
#    columns: `qof_coverage` (what share of the LSOA's registrations QOF published,
#    which IS enforced by MIN_QOF_COVERAGE) and `registration_coverage` (registrations
#    per resident, which is reported only -- see the note in _estimate_lsoa_prevalence)
#
# After all years are processed, apply temporal interpolation to fill
# missing subdomains across years.
#
# Output is in **LSOA 2011** vintage (GP registration data uses LSOA 2011).

# %%
#|default_exp process_health
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, data_ready: dict) -> bool:
    """Estimate LSOA-level health prevalence from QOF + GP registration data."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('process_health', run_name=run_name)
show_node_vars('process_health', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import re
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
run_name = ctx.vars["run_name"]

output_dir = const.pipeline_store_path / run_name / "health"
output_dir.mkdir(parents=True, exist_ok=True)

qof_raw_dir = const.qof_data_path / "raw"
gp_dir = const.gp_catchments_path
pop_dir = const.population_data_path / "lsoa_2011"

print(f"process_health: years {year_start}-{year_end}")

# %% [markdown]
# ## QOF normalisation
#
# Load the QOF schema config and normalise each year's raw prevalence data
# into a consistent format: practice_code, list_pop, {disease_columns...}

# %%
#|export
with open(const.qof_schemas_path, "rb") as f:
    qof_schemas = tomllib.load(f)["years"]


def _normalise_qof(year_key: str) -> pd.DataFrame | None:
    """Load and normalise QOF data for a given year key (e.g. '2021_22')."""
    schema = qof_schemas.get(year_key)
    if not schema:
        return None

    fmt = schema.get("format", "csv")
    if fmt == "excel":
        # Pre-2013 Excel formats not yet supported
        return None

    # Find the raw file
    year_dir = qof_raw_dir / year_key
    if not year_dir.exists():
        return None

    file_pattern = schema.get("file_pattern", "")

    # Find the prevalence file: try file_pattern first, then heuristics
    raw_path = None
    if file_pattern:
        # file_pattern may contain subdirectory (e.g. "QOF2021_v2/PREVALENCE_2021_v2.csv")
        candidate = year_dir / file_pattern
        if candidate.exists():
            raw_path = candidate

    if raw_path is None:
        # Search for prevalence files, preferring practice-level
        candidates = list(year_dir.rglob("*PREVALENCE*")) + list(year_dir.rglob("*prevalence*"))
        # Prefer practice-level files
        prac_files = [c for c in candidates if "prac" in c.name.lower()]
        candidates = prac_files or candidates
        if not candidates:
            candidates = list(year_dir.rglob("*.csv"))
        if not candidates:
            return None
        raw_path = candidates[0]
    encoding = schema.get("encoding", "utf-8")
    df = pd.read_csv(raw_path, encoding=encoding)

    practice_col = schema["practice_code_col"]
    register_col = schema["register_col"]
    list_pop_col = schema["list_pop_col"]
    disease_col = schema["disease_code_col"]

    # Clean numeric columns.
    #
    # Blanks and the "-" / "Insufficient indicator data" sentinels stay NaN. They mean
    # "QOF did not report this", which is not the same claim as "this practice has no
    # cases": coercing them to 0 puts a false zero into the weighted average and drags
    # every LSOA the practice serves down with it. There are 1,304 such blank registers
    # in 2016-17, 399 in 2018-19, 252 in 2017-18 and 64 in 2015-16, plus 21 blank list
    # sizes in 2015-16. A register genuinely recorded as "0" parses as 0 and is kept.
    for col in [register_col, list_pop_col]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "")
                       .replace("-", np.nan).replace("Insufficient indicator data", np.nan),
                errors="coerce",
            )

    # Choose the practice's list size deterministically.
    #
    # QOF reports a different list size per disease group, because 9 of the 21 registers
    # are age-restricted (AST 6+, RA 16+, DM 17+, CKD/DEP/EP/NDH/OB 18+, OST 50+). This
    # node wants the ALL-AGES list for every disease, so that `register / list_pop` scaled
    # by the LSOA's all-ages ONS population estimates the number of residents on the
    # register. (That makes the published rate a share of the whole population, NOT QOF's
    # own published prevalence for those 9 conditions -- see #42.)
    #
    # It used to take whichever row happened to come first per practice
    # (`drop_duplicates`), which lands on the all-ages list only because `AF` -- a TOTAL
    # group -- sorts first in every file NHS Digital has published so far. That is row
    # order deciding the denominator for all 21 conditions: a reissue in a different order
    # would silently move six years of the series with no error and no diff. Select it
    # explicitly instead:
    #
    #   * where the source carries PATIENT_LIST_TYPE (2015-16 onward), take the rows of
    #     the all-ages type;
    #   * where it does not (2014-15), take the largest list size the practice reports,
    #     which is the all-ages one because every other type is an age-restricted subset.
    #
    # Both rules are order-independent, and both reproduce today's values exactly.
    list_type = schema.get("list_type_filter", "TOTAL")
    if "PATIENT_LIST_TYPE" in df.columns:
        rows = df[df["PATIENT_LIST_TYPE"] == list_type]
        if rows.empty:
            raise ValueError(
                f"QOF {year_key}: no rows with PATIENT_LIST_TYPE == {list_type!r}; "
                f"cannot identify the all-ages practice list size."
            )
    else:
        rows = df
    pop_df = rows.groupby(practice_col, as_index=False)[list_pop_col].max()

    # Pivot: one row per practice, one column per disease group.
    #
    # We use aggfunc="max" to handle the 2013_14 era where "HF" (Heart Failure)
    # has two rows per practice sharing the same indicator_group code:
    #   - "Heart Failure due to LVD" (narrow subtype, e.g. register=9)
    #   - "Heart Failure" (broad category, e.g. register=48)
    # The LVD patients are a subset of the broader HF register, so summing
    # would double-count. "max" picks the broader register (48), which is
    # consistent with later years that report a single HF row.
    # For all other diseases and eras there is one row per (practice, disease),
    # so the aggfunc choice has no effect.
    #
    # No fill_value: a (practice, disease) pair QOF did not publish must stay NaN so
    # that _estimate_lsoa_prevalence drops the practice from that disease's weights.
    # fill_value=0 asserted "this practice has no cases of this disease", which is a
    # measurement nobody made.
    pivot = df.pivot_table(
        index=practice_col, columns=disease_col, values=register_col,
        aggfunc="max",
    ).reset_index()
    pivot.columns.name = None

    # Merge list_pop
    result = pop_df.rename(columns={practice_col: "practice_code", list_pop_col: "list_pop"}).merge(
        pivot.rename(columns={practice_col: "practice_code"}),
        on="practice_code", how="inner",
    )

    # A register cannot hold more people than the list it is drawn from. Where QOF says
    # it does, the pair is arithmetically impossible and is dropped to NaN -- the practice
    # then falls out of that disease's weights and the rest are renormalised, exactly as
    # for a practice QOF never published. 23 such cells exist in 2015-16, the worst a
    # register of 9 against a list size of 1 (practice J84602, an implied rate of 900%).
    # They currently carry little LSOA weight, but nothing guaranteed that, and a
    # weighted average of practice rates is bounded by the worst rate that enters it.
    #
    # This is arithmetic, not a plausibility judgement. It does NOT catch a register that
    # is merely implausible for the disease -- practice C82028's 3,636 epilepsy patients
    # on a list of 6,956 (52%) is impossible clinically but fits inside its list, so it
    # survives here. See the note on the sanity of high rates in `_estimate_lsoa_prevalence`.
    disease_cols = [c for c in result.columns if c not in ("practice_code", "list_pop")]
    over = result[disease_cols].gt(result["list_pop"], axis=0)
    n_over = int(over.to_numpy().sum())
    if n_over:
        result[disease_cols] = result[disease_cols].mask(over)
        print(f"  QOF {year_key}: rejected {n_over} practice-disease registers larger "
              f"than the practice list size")

    return result

# %% [markdown]
# ## Prevalence estimation
#
# For each LSOA, compute weighted prevalence across all GPs that serve patients
# from that LSOA. Weight = fraction of GP's patients from this LSOA.

# %%
#|export
# Minimum share of an LSOA's GP registrations that must sit at practices QOF actually
# published, for that LSOA's prevalence to be published rather than left missing.
#
# Renormalising the weights (see _estimate_lsoa_prevalence) assumes the registrations
# QOF did not publish behave like the ones it did. That assumption decays smoothly as
# coverage falls, so the floor was set by measuring the decay rather than by taste: each
# (LSOA, disease, year) estimate was compared against the same LSOA's own value in its
# full-coverage neighbouring years, and scored by how far it moved the LSOA in the
# national decile ranking -- the error that actually matters for an area index.
#
#   coverage band    median |log err|   p90 decile shift   P(shift >= 2 deciles)
#   [0.999, 1.000]        0.022                1                    2.8%   <- noise floor
#   [0.90,  0.95)         0.036                1                    5.0%
#   [0.80,  0.90)         0.048                1                    6.8%
#   [0.70,  0.80)         0.073                2                   14.0%   <- breaks here
#   [0.50,  0.60)         0.102                3                   25.8%
#   [0.00,  0.05)         0.223                6                   56.6%
#
# At and above 0.80 the estimate moves an LSOA no further through the national ranking
# than ordinary year-to-year variation moves it anyway (p90 of one decile, the same as
# at full coverage). Below 0.80 the median shift becomes a whole decile and the p90
# doubles, so the honest answer is "missing". The temporal interpolation further down
# then fills the gap from the LSOA's own neighbouring years, which is a better estimator
# than a rescaled minority of its registrations.
#
# Costs 1,296 of 394,128 LSOA-years (0.33%). Reproduce both tables with
#   _dev/2026-09-02-stress-test/health-vs-qof/fix_00_floor_analysis.py
#   _dev/2026-09-02-stress-test/health-vs-qof/fix_01_decile_shift.py
MIN_QOF_COVERAGE = 0.80


def _reject_impossible_rates(df: pd.DataFrame, rate_cols: list[str]) -> int:
    """Replace any prevalence rate that is not a possible proportion with NaN, in place.

    A prevalence rate is a share of a population: it lives in [0, 1] or it is not a
    measurement of anything. This is the last gate before the node writes, so nothing
    process_health emits can be outside that range whatever produced it.

    Rejected to NaN, never clamped. Clamping would invent a measurement -- and clamping
    to 0.0 in particular would recreate the exact defect this node was rewritten to
    remove, publishing "we could not measure this" as "we measured nil". NaN is the only
    honest representation, and the aggregate node carries a per-count covered population
    so a NaN LSOA no longer drags its LAD's rate down.
    """
    n = 0
    for col in rate_cols:
        v = pd.to_numeric(df[col], errors="coerce")
        bad = v.notna() & (~np.isfinite(v) | (v < 0) | (v > 1))
        if bad.any():
            n += int(bad.sum())
            df.loc[bad, col] = np.nan
    return n


def _estimate_lsoa_prevalence(qof: pd.DataFrame, gp_lsoa: pd.DataFrame,
                              pop_by_lsoa: pd.Series) -> pd.DataFrame:
    """Estimate LSOA-level prevalence from QOF + GP-LSOA registration data.

    For each LSOA i and disease d, over the practices k for which QOF published both a
    register for d and a usable list size ("covered" for d):

        weight_ikd  = patients_ik / sum_{k' covered for d} patients_ik'
        prevalence_id = sum_k weight_ikd * register_kd / list_pop_k
        coverage_id = sum_{k covered for d} patients_ik / sum_{all k} patients_ik

    The weights are renormalised over the COVERED practices, so they sum to 1.0 by
    construction. They are deliberately NOT divided by the LSOA's full registration
    total: QOF does not publish every practice every year -- 52 Buckinghamshire
    practices are absent from QOF 2017-18, 41 Dudley practices from 2016-17, 39
    Cornwall practices from 2018-19 -- and dividing by the full total instead leaves the
    missing practices in the denominator while dropping them from the numerator, which
    scales the whole estimate down by the missing share. That published
    Buckinghamshire's 2018 hypertension at 0.81% against a true ~12.7%, and the Isles of
    Scilly's 2025 at 0.46% against ~13%.

    Renormalising is an assumption, not a measurement: it takes the covered practices as
    representative of the uncovered ones. `coverage_id` is how much of the LSOA it rested
    on, and a disease below MIN_QOF_COVERAGE is returned NaN rather than published.

    There is deliberately no upper PLAUSIBILITY bound here, only the arithmetic one in
    `_normalise_qof` and the [0, 1] gate on the result. A weighted average cannot exceed
    the worst practice rate that enters it, so an implausibly high LSOA value means an
    implausible practice register -- and practice registers cannot be screened
    statistically: measured across 254 disease-years, the ratio of the largest practice
    rate to the national median for that disease-year has a median of 13.7 and reaches
    6,964, because tiny-list practices make the ratio meaningless. The known-bad records
    sit inside that noise (practice C82028's 52% epilepsy is 84x its national median,
    while other practices legitimately reach 1,441x). No single fence separates them, so
    a bound here would have to be a per-disease clinical ceiling -- a judgement someone
    has to defend condition by condition. That judgement already exists downstream, in
    build_data.py's HEALTH_SPIKE_BOUNDS, where a temporal reversal test is available to
    support it. Adding a second, differently-tuned copy upstream would give the project
    two sources of truth for the same question. See #66.

    Returns one row per LSOA present in `gp_lsoa`, with `{disease}_prevalence_rate`
    columns, a `qof_coverage` column and a `registration_coverage` column.
    """
    disease_cols = [c for c in qof.columns if c not in ("practice_code", "list_pop")]

    # Every registration the LSOA has, including at practices QOF did not publish.
    # This is the denominator for COVERAGE only, never for the weights.
    lsoa_totals = gp_lsoa.groupby("lsoa_code")["patients"].sum()

    merged = gp_lsoa.merge(qof, on="practice_code", how="inner")
    lsoa_code = merged["lsoa_code"]
    patients = merged["patients"].astype(float)
    list_pop = merged["list_pop"].where(merged["list_pop"] > 0)

    # Per disease, the weighted numerator and the weight actually carried. A practice
    # with no register for this disease, or no usable list size, contributes to neither,
    # so it falls out of the weights instead of entering them as a zero rate.
    parts = {}
    for disease in disease_cols:
        rate_k = merged[disease] / list_pop           # NaN if either is missing
        carried = patients.where(rate_k.notna(), 0.0)
        parts[f"_num_{disease}"] = carried * rate_k.fillna(0.0)
        parts[f"_den_{disease}"] = carried
    # Coverage over practices QOF published at all, regardless of disease -- the summary
    # reported in `qof_coverage`. Per-disease coverage can be lower where a published
    # practice did not report one disease; the floor above uses the per-disease value.
    parts["_den_any"] = patients.where(list_pop.notna(), 0.0)

    sums = pd.DataFrame(parts, index=merged.index).groupby(lsoa_code).sum()
    totals = lsoa_totals.reindex(sums.index).replace(0, np.nan)

    result = pd.DataFrame(index=sums.index)
    for disease in disease_cols:
        den = sums[f"_den_{disease}"]
        coverage = den / totals
        rate = sums[f"_num_{disease}"] / den.replace(0, np.nan)
        result[f"{disease}_prevalence_rate"] = rate.where(coverage >= MIN_QOF_COVERAGE)
    result["qof_coverage"] = sums["_den_any"] / totals
    # Registrations the LSOA has at all, per resident. Distinct from `qof_coverage`, which
    # asks what share of those registrations QOF published: an LSOA can have complete QOF
    # coverage of very few registrations. Five Forest of Dean LSOAs sit at 0.5%-9% here in
    # every year, because their residents mostly register with Welsh practices and NHS
    # Digital's registration file is England-only. Measured against the same temporal
    # control used to set MIN_QOF_COVERAGE, thin registration barely degrades the estimate
    # -- median |log error| 0.036 and p90 0.154 below 0.1, against 0.019 and 0.084 at the
    # normal ratio of ~1.05, versus 0.223 and 0.769 for thin QOF coverage -- because the
    # few residents who do register use the same practices as their neighbours. So there
    # is deliberately NO floor on this: it is reported, not enforced. See #62.
    result["registration_coverage"] = totals / pop_by_lsoa.reindex(sums.index)

    result.index.name = "LSOA11CD"
    return result.reset_index()

# %% [markdown]
# ## Process each QOF year

# %%
#|export
def _load_population(year: int) -> pd.DataFrame:
    """Load LSOA 2011 population for a given year, falling back to 2020.

    Welsh LSOAs are dropped, matching process_crime and process_claimant_counts: the
    health domain is England-only because QOF and the GP-LSOA registration file both
    are. The Nomis file carries 34,753 codes, of which 1,909 are Welsh, leaving the
    32,844 English LSOA 2011 areas that define this node's output row set.
    """
    for try_year in [year, 2020]:
        path = pop_dir / f"population_{try_year}.csv"
        if path.exists():
            df = pd.read_csv(path)
            df = df.rename(columns={"GEOGRAPHY_CODE": "LSOA11CD", "OBS_VALUE": "pop"})
            df = df[~df["LSOA11CD"].str.startswith("W")]
            return df[["LSOA11CD", "pop"]]
    raise FileNotFoundError(f"No population file found for {year} or 2020 in {pop_dir}")

# %%
#|export
# Map QOF year keys to calendar years and GP registration years
# QOF year "2021_22" covers April 2021 - March 2022 -> use April 2022 GP data
all_year_keys = sorted(qof_schemas.keys())
processed_years = []

for year_key in all_year_keys:
    schema = qof_schemas[year_key]
    if schema.get("format") == "excel":
        continue  # Skip pre-2013 Excel formats for now

    # Parse calendar years from key (e.g. "2021_22" -> start=2021, end=2022)
    m = re.match(r"(\d{4})_(\d{2})", year_key)
    if not m:
        continue
    qof_start = int(m.group(1))
    qof_end_suffix = int(m.group(2))
    qof_end = qof_start + 1 if qof_end_suffix < 50 else qof_start  # handle century

    # Check if this QOF year overlaps with our calendar year range
    if qof_start > year_end or qof_end < year_start:
        continue

    out_path = output_dir / f"health_{year_key}.csv"
    if out_path.exists():
        print(f"  QOF {year_key}: already processed, skipping")
        processed_years.append(year_key)
        continue

    # Normalise QOF data
    qof = _normalise_qof(year_key)
    if qof is None:
        print(f"  QOF {year_key}: no data available, skipping")
        continue

    # Load GP-LSOA registration data (April of the QOF end year)
    gp_lsoa_path = gp_dir / f"gp_lsoa_{qof_end}.csv"
    if not gp_lsoa_path.exists():
        # Try the start year
        gp_lsoa_path = gp_dir / f"gp_lsoa_{qof_start}.csv"
    if not gp_lsoa_path.exists():
        print(f"  QOF {year_key}: no GP-LSOA data for {qof_end} or {qof_start}, skipping")
        continue

    gp_lsoa = pd.read_csv(gp_lsoa_path)
    print(f"  QOF {year_key}: {len(qof)} practices in QOF, {gp_lsoa['practice_code'].nunique()} in GP-LSOA")

    # Estimate LSOA prevalence
    pop = _load_population(qof_end)
    result = _estimate_lsoa_prevalence(qof, gp_lsoa, pop.set_index("LSOA11CD")["pop"])

    # Merge with population and compute afflicted counts.
    #
    # Left-join FROM the population, not an inner join onto the estimate: an LSOA whose
    # every practice is missing from QOF has no prevalence but is still a real place
    # with a real population, and dropping its row shortened the year's file (33,707
    # rows in 2017-18 and 33,740 in 2018-19 against 33,749 elsewhere) and made the
    # published health `pop` contradict the employment `pop` for the same area and year
    # -- Buckinghamshire 2018 was published at 478,425 against 541,983. Such an LSOA now
    # emits an all-NaN prevalence row against its true population.
    result = pop.merge(result, on="LSOA11CD", how="left")

    # Nothing leaves this node outside [0, 1]. A weighted average of practice rates can
    # exceed 1 if QOF publishes a register larger than the practice's list size, which it
    # does (23 such practice-disease cells in 2015-16, the worst a register of 9 against
    # a list size of 1). Gate before the counts are derived, so the count agrees with the
    # rate, and before the interpolation below reads these files, so a rejected value
    # cannot anchor an interpolation.
    disease_cols_cur = [c for c in result.columns if c.endswith("_prevalence_rate")]
    n_rejected = _reject_impossible_rates(result, disease_cols_cur)

    # Compute afflicted counts from prevalence * ONS population. NaN prevalence gives a
    # NaN count, which is what "not measured here" has to look like downstream.
    for rate_col in disease_cols_cur:
        afflicted_col = rate_col.replace("_prevalence_rate", "_afflicted")
        result[afflicted_col] = result[rate_col] * result["pop"]

    result.to_csv(out_path, index=False)
    disease_cols = [c for c in result.columns if c.endswith("_prevalence_rate")]
    cov = result["qof_coverage"]
    n_thin = int((cov < MIN_QOF_COVERAGE).sum() + cov.isna().sum())
    print(f"  QOF {year_key}: {len(result)} LSOAs, {len(disease_cols)} disease subdomains, "
          f"QOF coverage mean {cov.mean():.5f} min {cov.min():.5f}, "
          f"{n_thin} LSOAs below the {MIN_QOF_COVERAGE:.0%} floor (left missing), "
          f"{n_rejected} rates rejected as outside [0,1], "
          f"registration coverage min {result['registration_coverage'].min():.4f} "
          f"({int((result['registration_coverage'] < 0.5).sum())} LSOAs below 0.5, reported not enforced)")
    processed_years.append(year_key)

# %% [markdown]
# ## Temporal interpolation
#
# Fill missing health subdomains across years. Some disease groups are not
# tracked in all years. For gaps of <= 2 consecutive missing values, interpolate.
#
# This is also what recovers the (LSOA, year) cells left missing by the
# `MIN_QOF_COVERAGE` floor. Those gaps are almost always a single year -- QOF drops a
# cohort of practices for one publication and restores them the next -- so they land in
# the interior-gap case and are filled from the LSOA's own neighbouring years. That is a
# better estimator than rescaling the minority of registrations QOF did publish, and it
# is the same treatment build_data.py already applies to the DEP 2023-24 and OST 2014-15
# basis changes.
#
# A gap at either END of the series is not filled: there is no second observation to sit
# between, and the extrapolation that used to fill them published negative prevalence.
# See `_interpolate_series` for the measurement behind that.

# %%
#|export
def _interpolate_series(values: list) -> list:
    """Fill short INTERIOR gaps in a per-LSOA time series by linear interpolation.

    - Interior gaps of at most 2 consecutive years: linear interpolation between the
      observations either side.
    - Leading and trailing gaps: left NaN.
    - Gaps longer than 2 years: left NaN.

    An interior gap is bounded by a real observation on each side, so the filled value
    cannot leave the range those two observations span. It is a guess, but a guess
    between two measurements.

    The ends used to be extrapolated by fitting a line to the nearest valid segment and
    projecting it outward. That was removed, for three reasons:

    1. It is unbounded on the open side, and it published negative prevalence rates.
       Isles of Scilly DEP ran 0.035621 (2022-23) -> 0.005425 (2023-24) -> -0.024771
       (2024-25), which reached the published LAD download bundle; 13 LSOAs had negative
       OST in 2013-14 the same way.
    2. Both failures came from a degenerate anchor. `max(2, gap_len + 1)` takes exactly
       two points for the common one-year gap, so the "regression" has zero residual
       degrees of freedom -- it is not a fit, it is the last year-on-year step, doubled.
       Where that step is a collapse rather than a trend the line runs through zero, and
       here it collapsed for a reason the node cannot see: DEP 2023-24 and OST 2014-15
       are the two QOF basis changes build_data.py corrects downstream, and the Isles of
       Scilly had 2.8% QOF coverage in 2024-25 on top.
    3. Measured, it does not work. Holding out the end value of 80,000 fully observed
       (LSOA, disease) series and predicting it, the linear extrapolator is beaten by
       simply carrying the nearest observed value forward -- on the median (trailing
       0.0376 vs 0.0353 relative error), badly on the tail (p90 0.217 vs 0.146), and it
       wins outright in only 44.5% of cases. It also goes negative in 5.0% of them.
       An extrapolator that loses to persistence has no claim to being a model.

    Persistence was considered as the replacement and rejected: it is safer and more
    accurate than the regression, but it cannot survive a degenerate anchor either. For
    Isles of Scilly DEP it would carry the anomalous 0.005425 into 2024-25 and publish
    the LAD at a twentieth of the national rate -- in range, and still wrong. When the
    only anchor available is itself suspect, the honest answer is that we do not know.

    Reproduce the hold-out table with
      _dev/2026-09-02-stress-test/health-vs-qof/fix2_01_extrap_test.py
    """
    arr = np.array(values, dtype=float)
    n = len(arr)
    if n == 0 or not np.any(np.isnan(arr)):
        return values

    is_nan = np.isnan(arr)
    result = arr.copy()

    # Identify contiguous NaN segments
    segments = []
    i = 0
    while i < n:
        if is_nan[i]:
            j = i
            while j < n and is_nan[j]:
                j += 1
            segments.append((i, j))  # [start, end) of NaN run
            i = j
        else:
            i += 1

    for start, end in segments:
        gap_len = end - start
        if gap_len > 2 or start == 0 or end == n:
            continue  # too long, or open-ended: no two observations to sit between

        v_before = result[start - 1]
        v_after = result[end]
        if not np.isnan(v_before) and not np.isnan(v_after):
            for k in range(gap_len):
                frac = (k + 1) / (gap_len + 1)
                result[start + k] = v_before + frac * (v_after - v_before)

    return result.tolist()

# %%
#|export
if len(processed_years) > 1:
    print(f"  interpolating across {len(processed_years)} years...")

    # Load all health CSVs, indexed by LSOA for fast lookup
    all_health = {}
    all_disease_cols = set()
    sorted_years = sorted(processed_years)
    for yk in sorted_years:
        path = output_dir / f"health_{yk}.csv"
        if path.exists():
            df = pd.read_csv(path).set_index("LSOA11CD")
            all_health[yk] = df
            rate_cols = [c for c in df.columns if c.endswith("_prevalence_rate")]
            all_disease_cols.update(rate_cols)

    all_disease_cols = sorted(all_disease_cols)

    # Ensure all disease columns exist in all years (fill with NaN)
    for yk in sorted_years:
        df = all_health[yk]
        for col in all_disease_cols:
            if col not in df.columns:
                df[col] = np.nan
                afflicted_col = col.replace("_prevalence_rate", "_afflicted")
                if afflicted_col not in df.columns:
                    df[afflicted_col] = np.nan

    # Vectorized interpolation: build a 3D array (years x LSOAs x diseases)
    # then interpolate along the year axis
    all_lsoas = sorted(set().union(*(df.index for df in all_health.values())))
    n_years = len(sorted_years)
    n_lsoas = len(all_lsoas)
    n_diseases = len(all_disease_cols)

    # Build matrix: shape (n_years, n_lsoas)
    n_interpolated = 0
    for col in all_disease_cols:
        # Extract time series for this disease across all years
        matrix = np.full((n_years, n_lsoas), np.nan)
        for i, yk in enumerate(sorted_years):
            df = all_health[yk]
            series = df[col].reindex(all_lsoas)
            matrix[i, :] = series.values

        # Interpolate each LSOA's time series
        for j in range(n_lsoas):
            col_vals = matrix[:, j].tolist()
            if not any(np.isnan(v) for v in col_vals):
                continue
            interp = _interpolate_series(col_vals)
            for i in range(n_years):
                if np.isnan(col_vals[i]) and not np.isnan(interp[i]):
                    n_interpolated += 1
                    matrix[i, j] = interp[i]

        # Write back interpolated values
        for i, yk in enumerate(sorted_years):
            df = all_health[yk]
            df[col] = pd.Series(matrix[i, :], index=all_lsoas).reindex(df.index)
            # Update afflicted counts
            afflicted_col = col.replace("_prevalence_rate", "_afflicted")
            if afflicted_col in df.columns and "pop" in df.columns:
                df[afflicted_col] = df[col] * df["pop"]

    # Save interpolated data, re-gating on the way out. Interior interpolation is
    # bounded by its two anchors and so cannot produce an impossible rate from possible
    # ones, but the guarantee is worth making structural rather than argued: this is the
    # node's last write.
    n_rejected_interp = 0
    for yk in sorted_years:
        df = all_health[yk]
        rate_cols = [c for c in df.columns if c.endswith("_prevalence_rate")]
        n_rejected_interp += _reject_impossible_rates(df, rate_cols)
        for rate_col in rate_cols:
            afflicted_col = rate_col.replace("_prevalence_rate", "_afflicted")
            if afflicted_col in df.columns and "pop" in df.columns:
                df[afflicted_col] = df[rate_col] * df["pop"]
        out_path = output_dir / f"health_{yk}.csv"
        df.reset_index().to_csv(out_path, index=False)

    print(f"  interpolated {n_interpolated} values across {len(sorted_years)} years; "
          f"{n_rejected_interp} rates rejected as outside [0,1] after interpolation")

print(f"process_health: done, output at {const.rel(output_dir)}")
True  #|func_return_line
