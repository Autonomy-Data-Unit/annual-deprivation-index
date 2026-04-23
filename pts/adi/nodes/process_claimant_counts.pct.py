# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.process_claimant_counts
#
# Process raw claimant count data into per-LSOA annual rates.
#
# For each year:
# 1. Load monthly claimant counts (LSOA 2011 from Nomis)
# 2. Filter out Welsh LSOAs
# 3. Average monthly counts to get annual mean
# 4. Merge with LSOA 2011 population data
# 5. Compute claimant_rate = claimant_count / population
# 6. Save per-year CSV with counts and population (for crosswalk compatibility)
#
# Output is in **LSOA 2011** vintage (the only geography available for
# historical claimant count data on Nomis).

# %%
#|default_exp process_claimant_counts
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, data_ready: dict) -> bool:
    """Process raw claimant count data into per-LSOA annual rates."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('process_claimant_counts', run_name=run_name)
show_node_vars('process_claimant_counts', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import pandas as pd

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
run_name = ctx.vars["run_name"]

# Claimant count data starts at 2013
effective_start = max(year_start, 2013)

output_dir = const.pipeline_store_path / run_name / "claimant_counts"
output_dir.mkdir(parents=True, exist_ok=True)

pop_dir = const.population_data_path / "lsoa_2011"

print(f"process_claimant_counts: years {effective_start}-{year_end}")

# %% [markdown]
# ## Load LSOA 2011 population
#
# NM_2010_1 covers 2011-2020. For years > 2020, fall back to 2020 data.

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

# %% [markdown]
# ## Process each year

# %%
#|export
for year in range(effective_start, year_end + 1):
    out_path = output_dir / f"claimant_counts_{year}.csv"
    if out_path.exists():
        print(f"  {year}: already processed, skipping")
        continue

    # Load monthly claimant counts
    claimant_path = const.claimant_data_path / f"claimant_counts_{year}.csv"
    if not claimant_path.exists():
        print(f"  {year}: no claimant count data, skipping")
        continue

    df = pd.read_csv(claimant_path)

    # Filter out Welsh LSOAs (codes starting with 'W')
    df = df[~df["GEOGRAPHY_CODE"].str.startswith("W")].copy()

    # Average monthly counts to annual.
    # OBS_VALUE may have NaN for suppressed small counts — these are
    # treated as 0 (Nomis suppresses counts below 5).
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce").fillna(0)

    annual = (
        df.groupby(["GEOGRAPHY_CODE", "GEOGRAPHY_NAME"])["OBS_VALUE"]
        .mean()
        .reset_index()
        .rename(columns={
            "GEOGRAPHY_CODE": "LSOA11CD",
            "GEOGRAPHY_NAME": "LSOA11NM",
            "OBS_VALUE": "claimant_count",
        })
    )

    # Merge with population
    pop = _load_population(year)
    result = annual.merge(pop, on="LSOA11CD", how="inner")

    # Compute rate
    result["claimant_rate"] = result["claimant_count"] / result["pop"]

    result.to_csv(out_path, index=False)
    print(f"  {year}: {len(result)} LSOAs, mean rate={result['claimant_rate'].mean():.4f}")

print(f"process_claimant_counts: done, output at {const.rel(output_dir)}")
True  #|func_return_line
