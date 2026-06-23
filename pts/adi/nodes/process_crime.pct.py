# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.process_crime
#
# Process raw street crime data into per-LSOA annual crime counts and rates.
#
# For each year:
# 1. Load all monthly per-force street CSVs for that year
# 2. Drop rows with missing LSOA codes
# 3. Filter out Welsh LSOAs (codes starting with 'W')
# 4. Aggregate crime counts by LSOA and crime type
# 5. Merge with LSOA 2011 population data
# 6. Compute per-capita rates for each crime type
# 7. Save per-year CSV with counts, rates, and population
#
# Output is in **LSOA 2011** vintage (police.uk reports LSOA 2011 codes).

# %%
#|default_exp process_crime
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, data_ready: dict) -> bool:
    """Process raw street crime data into per-LSOA annual rates."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('process_crime', run_name=run_name)
show_node_vars('process_crime', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
from pathlib import Path

import numpy as np
import pandas as pd

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
run_name = ctx.vars["run_name"]

output_dir = const.pipeline_store_path / run_name / "crime"
output_dir.mkdir(parents=True, exist_ok=True)

pop_dir = const.population_data_path / "lsoa_2011"
crime_dir = const.crime_data_path

print(f"process_crime: years {year_start}-{year_end}")

# %%
#|export
def _build_lsoa21_to_lsoa11_remap() -> dict:
    """Map LSOA 2021 codes that don't exist in the LSOA 2011 universe back to their
    LSOA 2011 parent.

    From ~2024 onward data.police.uk codes incidents in split/merged areas with the
    new LSOA 2021 codes (e.g. ``E01033911``) rather than the LSOA 2011 codes. The rest
    of this node, and the downstream aggregate crosswalk, work in LSOA 2011 vintage, so
    those codes would otherwise be silently dropped by the population left-join below
    (470k incidents / 8.7% of 2025 street crime), leaving the affected LSOAs with a
    spurious zero. Mapping each new code to its LSOA 2011 parent (splits: child->parent
    1:1; merges: any one parent, re-summed identically at aggregate) recovers them.
    """
    xw = pd.read_csv(const.crosswalk_path / "lsoa11_to_lsoa21.csv", dtype=str)
    c11 = set(xw["LSOA11CD"].dropna())
    only21 = xw[~xw["LSOA21CD"].isin(c11)].drop_duplicates("LSOA21CD")
    return dict(zip(only21["LSOA21CD"], only21["LSOA11CD"]))

_lsoa21_to_lsoa11 = _build_lsoa21_to_lsoa11_remap()
print(f"  loaded {len(_lsoa21_to_lsoa11)} LSOA21->LSOA11 code remappings (recent police.uk vintage)")

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


def _load_street_data_for_year(year: int) -> pd.DataFrame:
    """Load and concatenate all street crime CSVs for a given year."""
    frames = []
    for month in range(1, 13):
        month_dir = crime_dir / f"{year}-{month:02d}"
        if not month_dir.exists():
            continue
        for csv_path in month_dir.glob("*-street.csv"):
            df = pd.read_csv(csv_path, usecols=["LSOA code", "LSOA name", "Crime type"])
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["LSOA code", "LSOA name", "Crime type"])
    return pd.concat(frames, ignore_index=True)

# %% [markdown]
# ## Process each year

# %%
#|export
for year in range(year_start, year_end + 1):
    out_path = output_dir / f"crime_{year}.csv"
    if out_path.exists():
        print(f"  {year}: already processed, skipping")
        continue

    print(f"  {year}: loading street crime data...")
    df = _load_street_data_for_year(year)
    if df.empty:
        print(f"  {year}: no crime data found, skipping")
        continue

    # Drop rows with no LSOA
    df = df.dropna(subset=["LSOA code"])

    # Normalise recent LSOA 2021 codes back to their LSOA 2011 parent so they survive
    # the LSOA 2011 population join below instead of being silently dropped.
    df["LSOA code"] = df["LSOA code"].map(_lsoa21_to_lsoa11).fillna(df["LSOA code"])

    # Filter out Welsh LSOAs
    df = df[~df["LSOA code"].str.startswith("W")]

    # Count crimes by LSOA and crime type
    counts = (
        df.groupby(["LSOA code", "Crime type"])
        .size()
        .reset_index(name="count")
    )

    # Pivot to wide format: one column per crime type
    pivot = counts.pivot_table(
        index="LSOA code", columns="Crime type", values="count", fill_value=0
    ).reset_index()
    pivot.columns.name = None
    pivot = pivot.rename(columns={"LSOA code": "LSOA11CD"})

    # Get LSOA names from crime data (take first occurrence)
    lsoa_names = (
        df[["LSOA code", "LSOA name"]]
        .drop_duplicates(subset="LSOA code")
        .rename(columns={"LSOA code": "LSOA11CD", "LSOA name": "LSOA11NM"})
    )
    pivot = pivot.merge(lsoa_names, on="LSOA11CD", how="left")

    # Merge with population — left join from population so LSOAs
    # with zero reported crimes are included with zero counts.
    pop = _load_population(year)
    pop = pop[~pop["LSOA11CD"].str.startswith("W")]
    result = pop.merge(pivot, on="LSOA11CD", how="left")

    # Fill NaN crime counts with 0 (LSOAs with no reported crimes)
    crime_type_cols = [c for c in result.columns if c not in ("LSOA11CD", "LSOA11NM", "pop")]
    for col in crime_type_cols:
        result[col] = result[col].fillna(0)
        result[f"{col}_rate"] = result[col] / result["pop"].replace(0, np.nan)

    result.to_csv(out_path, index=False)
    total_crimes = result[crime_type_cols].sum().sum()
    print(f"  {year}: {len(result)} LSOAs, {int(total_crimes)} total crimes across {len(crime_type_cols)} types")

print(f"process_crime: done, output at {const.rel(output_dir)}")
True  #|func_return_line
