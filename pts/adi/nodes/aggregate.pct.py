# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.aggregate
#
# Apply LSOA vintage crosswalk and aggregate domain outputs to higher geographies.
#
# Steps:
# 1. Build LSOA 2011 → LSOA 2021 crosswalk (population-weighted for splits)
# 2. Load domain outputs (claimant counts, crime, health) from pipeline store
# 3. Convert all domains from LSOA 2011 to LSOA 2021 via crosswalk
# 4. Aggregate to four geography levels: LSOA, LAD, Region, England
# 5. Save final outputs to store/outputs/{run_name}/

# %%
#|default_exp aggregate
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, domains_ready: dict) -> bool:
    """Apply LSOA crosswalk and aggregate to LAD/Region/England."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('aggregate', run_name=run_name)
show_node_vars('aggregate', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import re
from pathlib import Path

import numpy as np
import pandas as pd

from adi.utils.geo import build_crosswalk, apply_crosswalk, aggregate_to_geography

# %%
#|export
run_name = ctx.vars["run_name"]
lsoa_vintage = ctx.vars["lsoa_vintage"]
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]

pipeline_dir = const.pipeline_store_path / run_name
output_dir = const.outputs_path / run_name
output_dir.mkdir(parents=True, exist_ok=True)

print(f"aggregate: years {year_start}-{year_end}, target vintage LSOA {lsoa_vintage}")

# %% [markdown]
# ## Build crosswalk

# %%
#|export
# Find the latest LSOA 2021 population file for crosswalk weighting
pop_dir_2021 = const.population_data_path / "lsoa_2021"
pop_files = sorted(pop_dir_2021.glob("population_*.csv"))
lsoa21_pop_path = pop_files[-1]  # latest year

print(f"  building crosswalk using {lsoa21_pop_path.name} for population weights...")
crosswalk = build_crosswalk(
    const.crosswalk_path / "lsoa11_to_lsoa21.csv",
    lsoa21_pop_path,
)
n_unchanged = (crosswalk["CHGIND"] == "U").sum()
n_split = (crosswalk["CHGIND"] == "S").sum()
n_merged = (crosswalk["CHGIND"] == "M").sum()
print(f"  crosswalk: {n_unchanged} unchanged, {n_split} split rows, {n_merged} merge rows")

# %% [markdown]
# ## Load geographic lookup tables

# %%
#|export
lsoa_to_lad = pd.read_csv(const.geo_lookups_path / "lsoa21_to_lad25.csv")
lad_to_rgn = pd.read_csv(const.geo_lookups_path / "lad25_to_rgn25.csv")

# %% [markdown]
# ## Process each domain and year

# %%
#|export
def _process_domain(domain_name, domain_dir, count_cols_fn, pop_col, year_pattern):
    """Process a single domain: crosswalk + aggregate to all geography levels."""
    files = sorted(domain_dir.glob(year_pattern))
    if not files:
        print(f"  {domain_name}: no files found in {domain_dir}")
        return

    for file_path in files:
        df = pd.read_csv(file_path)
        stem = file_path.stem  # e.g. "claimant_counts_2022"

        # Identify count columns (not rates, not identifiers)
        count_cols = count_cols_fn(df)

        # Apply crosswalk (LSOA 2011 -> LSOA 2021)
        lsoa21_df = apply_crosswalk(df, crosswalk, count_cols, pop_col)

        # --- LSOA level ---
        lsoa_dir = output_dir / "lsoa" / domain_name
        lsoa_dir.mkdir(parents=True, exist_ok=True)

        # Add LSOA names and recompute rates
        lsoa_names = lsoa_to_lad[["LSOA21CD", "LSOA21NM"]].drop_duplicates()
        lsoa_out = lsoa_names.merge(lsoa21_df, on="LSOA21CD", how="right")
        for col in count_cols:
            lsoa_out[f"{col}_rate"] = lsoa_out[col] / lsoa_out[pop_col].replace(0, np.nan)
        lsoa_out.to_csv(lsoa_dir / f"{stem}.csv", index=False)

        # --- LAD level ---
        lad_dir = output_dir / "lad" / domain_name
        lad_dir.mkdir(parents=True, exist_ok=True)
        lad_df = aggregate_to_geography(
            lsoa21_df, lsoa_to_lad, "LSOA21CD", "LAD25CD", "LAD25NM",
            count_cols, pop_col,
        )
        lad_df.to_csv(lad_dir / f"{stem}.csv", index=False)

        # --- Region level ---
        rgn_dir = output_dir / "region" / domain_name
        rgn_dir.mkdir(parents=True, exist_ok=True)
        # Need to go via LAD: merge LSOA->LAD, then LAD->Region
        lsoa_with_lad = lsoa21_df.merge(
            lsoa_to_lad[["LSOA21CD", "LAD25CD"]].drop_duplicates(),
            on="LSOA21CD", how="inner",
        )
        lsoa_with_rgn = lsoa_with_lad.merge(
            lad_to_rgn[["LAD25CD", "RGN25CD", "RGN25NM"]].drop_duplicates(),
            on="LAD25CD", how="inner",
        )
        rgn_df = lsoa_with_rgn.groupby(["RGN25CD", "RGN25NM"])[count_cols + [pop_col]].sum().reset_index()
        for col in count_cols:
            rgn_df[f"{col}_rate"] = rgn_df[col] / rgn_df[pop_col].replace(0, np.nan)
        rgn_df.to_csv(rgn_dir / f"{stem}.csv", index=False)

        # --- England level ---
        eng_dir = output_dir / "england" / domain_name
        eng_dir.mkdir(parents=True, exist_ok=True)
        eng_row = lsoa21_df[count_cols + [pop_col]].sum().to_frame().T
        eng_row.insert(0, "area_code", "E92000001")
        eng_row.insert(1, "area_name", "England")
        for col in count_cols:
            eng_row[f"{col}_rate"] = eng_row[col] / eng_row[pop_col].replace(0, np.nan)
        eng_row.to_csv(eng_dir / f"{stem}.csv", index=False)

        print(f"  {domain_name}/{stem}: LSOA={len(lsoa_out)}, LAD={len(lad_df)}, Region={len(rgn_df)}")

# %% [markdown]
# ## Claimant counts

# %%
#|export
_process_domain(
    "claimant_counts",
    pipeline_dir / "claimant_counts",
    lambda df: ["claimant_count"],
    "pop",
    "claimant_counts_*.csv",
)

# %% [markdown]
# ## Crime

# %%
#|export
_process_domain(
    "crime",
    pipeline_dir / "crime",
    lambda df: [c for c in df.columns if c not in ("LSOA11CD", "LSOA11NM", "pop") and "_rate" not in c],
    "pop",
    "crime_*.csv",
)

# %% [markdown]
# ## Health

# %%
#|export
_process_domain(
    "health",
    pipeline_dir / "health",
    lambda df: [c for c in df.columns if c.endswith("_afflicted")],
    "pop",
    "health_*.csv",
)

# %%
#|export
print(f"aggregate: done, output at {const.rel(output_dir)}")
True  #|func_return_line
