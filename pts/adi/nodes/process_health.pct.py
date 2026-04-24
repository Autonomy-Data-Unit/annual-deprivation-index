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
# 3. For each LSOA, compute the weighted prevalence across all GP practices
#    that serve patients from that LSOA
# 4. Save per-year CSV with prevalence rates and afflicted counts
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
from scipy import stats

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

    # Clean numeric columns
    for col in [register_col, list_pop_col]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").replace("-", "0").replace("Insufficient indicator data", "0"),
                errors="coerce",
            ).fillna(0)

    # Filter by list_type if needed (Era 4: multiple PATIENT_LIST_TYPE per practice)
    list_type_filter = schema.get("list_type_filter")
    if list_type_filter and "PATIENT_LIST_TYPE" in df.columns:
        # Get list_pop from TOTAL rows only
        pop_df = df[df["PATIENT_LIST_TYPE"] == list_type_filter][[practice_col, list_pop_col]].drop_duplicates(subset=practice_col)
    else:
        pop_df = df[[practice_col, list_pop_col]].drop_duplicates(subset=practice_col)

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
    pivot = df.pivot_table(
        index=practice_col, columns=disease_col, values=register_col,
        aggfunc="max", fill_value=0,
    ).reset_index()
    pivot.columns.name = None

    # Merge list_pop
    result = pop_df.rename(columns={practice_col: "practice_code", list_pop_col: "list_pop"}).merge(
        pivot.rename(columns={practice_col: "practice_code"}),
        on="practice_code", how="inner",
    )

    return result

# %% [markdown]
# ## Prevalence estimation
#
# For each LSOA, compute weighted prevalence across all GPs that serve patients
# from that LSOA. Weight = fraction of GP's patients from this LSOA.

# %%
#|export
def _estimate_lsoa_prevalence(qof: pd.DataFrame, gp_lsoa: pd.DataFrame) -> pd.DataFrame:
    """Estimate LSOA-level prevalence from QOF + GP-LSOA registration data.

    For each LSOA i and GP practice k:
        weight_ik = patients_from_LSOA_i_at_GP_k / total_patients_from_LSOA_i
        LSOA_i_prevalence = sum_k(weight_ik * GP_k_register / GP_k_list_pop)

    Weights sum to 1.0 per LSOA, so the result is a proper weighted average
    of practice-level prevalence rates.
    """
    disease_cols = [c for c in qof.columns if c not in ("practice_code", "list_pop")]

    # Compute total patients per LSOA (for normalising weights)
    lsoa_totals = gp_lsoa.groupby("lsoa_code")["patients"].sum().rename("lsoa_total_patients")

    # Join GP-LSOA with QOF data
    merged = gp_lsoa.merge(qof, on="practice_code", how="inner")
    merged = merged.merge(lsoa_totals, on="lsoa_code", how="inner")

    # Weight = fraction of this LSOA's patients at this GP (sums to 1.0 per LSOA)
    merged["weight"] = merged["patients"] / merged["lsoa_total_patients"]

    # Compute practice-level prevalence rates for all diseases at once
    list_pop_safe = merged["list_pop"].replace(0, np.nan)
    for disease in disease_cols:
        merged[f"_wprev_{disease}"] = merged["weight"] * (merged[disease] / list_pop_safe)

    # Aggregate to LSOA level in a single groupby
    wprev_cols = [f"_wprev_{d}" for d in disease_cols]
    lsoa_agg = merged.groupby("lsoa_code")[wprev_cols].sum()

    # Build result DataFrame
    result = pd.DataFrame(index=lsoa_agg.index)
    for disease in disease_cols:
        result[f"{disease}_prevalence_rate"] = lsoa_agg[f"_wprev_{disease}"]
    result.index.name = "LSOA11CD"
    result = result.reset_index().rename(columns={"lsoa_code": "LSOA11CD"})

    return result

# %% [markdown]
# ## Process each QOF year

# %%
#|export
def _load_population(year: int) -> pd.DataFrame:
    """Load LSOA 2011 population for a given year, falling back to 2020."""
    for try_year in [year, 2020]:
        path = pop_dir / f"population_{try_year}.csv"
        if path.exists():
            df = pd.read_csv(path)
            df = df.rename(columns={"GEOGRAPHY_CODE": "LSOA11CD", "OBS_VALUE": "pop"})
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
    result = _estimate_lsoa_prevalence(qof, gp_lsoa)

    # Merge with population data and compute afflicted counts
    pop = _load_population(qof_end)
    result = result.merge(pop, on="LSOA11CD", how="inner")

    # Compute afflicted counts from prevalence * ONS population
    disease_cols_cur = [c for c in result.columns if c.endswith("_prevalence_rate")]
    for rate_col in disease_cols_cur:
        afflicted_col = rate_col.replace("_prevalence_rate", "_afflicted")
        result[afflicted_col] = result[rate_col] * result["pop"]

    result.to_csv(out_path, index=False)
    disease_cols = [c for c in result.columns if c.endswith("_prevalence_rate")]
    print(f"  QOF {year_key}: {len(result)} LSOAs, {len(disease_cols)} disease subdomains")
    processed_years.append(year_key)

# %% [markdown]
# ## Temporal interpolation
#
# Fill missing health subdomains across years. Some disease groups are not
# tracked in all years. For gaps of <= 2 consecutive missing values, interpolate.

# %%
#|export
def _interpolate_series(values: list) -> list:
    """Interpolate missing values (NaN) in a time series.

    - Interior gaps (max 2 consecutive): linear interpolation
    - Leading gaps: extrapolate from first valid segment via linear regression
    - Trailing gaps: extrapolate from last valid segment via linear regression
    - Gaps > 2 consecutive: leave as NaN
    """
    arr = np.array(values, dtype=float)
    n = len(arr)
    if n == 0 or not np.any(np.isnan(arr)):
        return values

    # Find runs of NaN
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
        if gap_len > 2:
            continue  # Too long to interpolate

        if start == 0:
            # Leading gap: extrapolate backward from next valid segment
            valid_after = result[end:end + max(2, gap_len + 1)]
            valid_after = valid_after[~np.isnan(valid_after)]
            if len(valid_after) >= 2:
                x = np.arange(len(valid_after))
                slope, intercept, _, _, _ = stats.linregress(x, valid_after)
                for k in range(gap_len):
                    result[start + k] = slope * (k - gap_len) + intercept
        elif end == n:
            # Trailing gap: extrapolate forward from previous valid segment
            valid_before = result[max(0, start - max(2, gap_len + 1)):start]
            valid_before = valid_before[~np.isnan(valid_before)]
            if len(valid_before) >= 2:
                x = np.arange(len(valid_before))
                slope, intercept, _, _, _ = stats.linregress(x, valid_before)
                for k in range(gap_len):
                    result[start + k] = slope * (len(valid_before) + k) + intercept
        else:
            # Interior gap: linear interpolation
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

    # Save interpolated data
    for yk in sorted_years:
        out_path = output_dir / f"health_{yk}.csv"
        all_health[yk].reset_index().to_csv(out_path, index=False)

    print(f"  interpolated {n_interpolated} values across {len(sorted_years)} years")

print(f"process_health: done, output at {const.rel(output_dir)}")
True  #|func_return_line
