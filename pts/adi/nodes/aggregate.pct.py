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
#
# Every output file carries TWO populations, and they answer different questions:
#
# * `pop` -- the ONS mid-year estimate for the whole area. One meaning in every
#   domain, level and year, so the three domains agree on how many people live
#   somewhere, and the figure reconciles to Nomis NM_2014_1.
# * `{col}_pop` -- the population behind `{col}` specifically, and the denominator
#   `{col}_rate` divides by. Equal to `pop` where the whole area was measured,
#   smaller where it was not (Greater Manchester's street crime from 2019, a QOF
#   disease group whose practices were not published), NaN where nothing was.
#
# `{col}_rate == {col} / {col}_pop` holds exactly at every level, and
# `{col}_pop / pop` is the share of the area the number rests on.

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

from adi.utils.geo import (
    COVERED_POP_SUFFIX,
    build_crosswalk,
    apply_crosswalk,
    aggregate_to_geography,
    covered_population,
    load_lsoa21_population,
)

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
# The crosswalk's split weights and the published denominator are two halves of
# one division, so they must come from the SAME population year. Every output
# year therefore gets its own crosswalk, weighted by that year's LSOA 2021
# estimate, and both halves read one cached frame per year via
# `_population_for`. Weighting every year from a single file (it used to be the
# latest, population_2025.csv) while denominating per year scaled split LSOAs'
# published rates by up to 1.68x in 2014 -- see the note in `build_crosswalk`.
pop_dir_2021 = const.population_data_path / "lsoa_2021"

_populations = {}
_crosswalks = {}


def _population_for(pop_year):
    """LSOA 2021 population for `pop_year`, loaded once and shared."""
    if pop_year not in _populations:
        _populations[pop_year] = load_lsoa21_population(pop_dir_2021, pop_year)
    return _populations[pop_year]


def _crosswalk_for(pop_year):
    """Crosswalk weighted by the same population that will be the denominator."""
    if pop_year not in _crosswalks:
        cw = build_crosswalk(
            const.crosswalk_path / "lsoa11_to_lsoa21.csv",
            _population_for(pop_year),
        )
        if not _crosswalks:  # composition is year-independent; log it once
            print(f"  crosswalk: {(cw['CHGIND'] == 'U').sum()} unchanged, "
                  f"{(cw['CHGIND'] == 'S').sum()} split rows, "
                  f"{(cw['CHGIND'] == 'M').sum()} merge rows; "
                  f"weights rebuilt per publication year")
        _crosswalks[pop_year] = cw
    return _crosswalks[pop_year]

# %% [markdown]
# ## Load geographic lookup tables

# %%
#|export
lsoa_to_lad = pd.read_csv(const.geo_lookups_path / "lsoa21_to_lad25.csv")
lad_to_rgn = pd.read_csv(const.geo_lookups_path / "lad25_to_rgn25.csv")

# One LSOA -> geography lookup per published level, so LSOA, LAD, Region and
# England all go through `aggregate_to_geography` and cannot drift apart. England
# used to sum the LSOA frame directly while LAD and Region inner-joined a lookup,
# so an LSOA missing from `lsoa21_to_lad25` would have silently made England
# larger than the sum of its LADs; `_check_lsoa_coverage` now refuses that
# outright instead.
lsoa_to_rgn = (
    lsoa_to_lad[["LSOA21CD", "LAD25CD"]].drop_duplicates()
    .merge(lad_to_rgn[["LAD25CD", "RGN25CD", "RGN25NM"]].drop_duplicates(), on="LAD25CD")
    [["LSOA21CD", "RGN25CD", "RGN25NM"]]
)
lsoa_to_eng = (
    lsoa_to_lad[["LSOA21CD"]].drop_duplicates()
    .assign(area_code="E92000001", area_name="England")
)


def _check_lsoa_coverage(stem, lsoa21_df):
    """Every published LSOA must roll up, or the levels stop reconciling."""
    for name, lookup in (("LAD", lsoa_to_lad), ("region", lsoa_to_rgn), ("England", lsoa_to_eng)):
        orphans = sorted(set(lsoa21_df["LSOA21CD"]) - set(lookup["LSOA21CD"]))
        if orphans:
            raise ValueError(
                f"{stem}: {len(orphans)} LSOA 2021 areas have no {name} in the geographic "
                f"lookups (e.g. {orphans[:5]}). Refusing to publish a national total that "
                f"disagrees with the sum of its parts."
            )

# %% [markdown]
# ## Process each domain and year

# %%
#|export
def _pop_year_from_stem(stem):
    """Calendar year whose population estimate is the denominator for `stem`.

    Claimant and crime files are calendar years ("crime_2021" -> 2021). Health
    files are QOF years, named by the April-to-March window they cover
    ("health_2020_21" -> 2021); the ADI labels a QOF year by the year it ENDS,
    so that is the population year too.
    """
    m = re.search(r"_(\d{4})_(\d{2})$", stem)
    if m:
        start_year, end_suffix = int(m.group(1)), int(m.group(2))
        return start_year + 1 if end_suffix < 50 else start_year
    m = re.search(r"_(\d{4})$", stem)
    if not m:
        raise ValueError(f"Cannot determine a population year from filename stem {stem!r}")
    return int(m.group(1))


def _reset_denominator(df, count_cols, pop_col, pop_year, derived_counts):
    """Swap the crosswalked denominator for the real LSOA 2021 estimate.

    `apply_crosswalk` carries the LSOA 2011 population through the crosswalk,
    but that series (Nomis NM_2010_1) ends at 2020, so every year from 2021 on
    would otherwise be published against a frozen mid-2020 denominator. The
    real per-year LSOA 2021 estimate (NM_2014_1) is the correct denominator and
    is what METHODOLOGY.md has always claimed is used.

    Two kinds of domain, handled differently:

    * Claimant and crime counts are GENUINE counts -- a claimant is a claimant
      whatever the population is. The counts are untouched; only the rate
      denominator moves.
    * The health count is DERIVED: afflicted = prevalence_rate * population,
      where the QOF-weighted prevalence RATE is the measured quantity and the
      count is a presentational scaling of it. Swapping the denominator without
      rescaling would silently corrupt the prevalence estimate, so the rate is
      held fixed and the count re-derived against the new population.

    The denominator comes from `_population_for(pop_year)` -- the same cached
    frame that weighted this file's crosswalk. Do not load it independently
    here: numerator and denominator drifting apart is #6.
    """
    df = df.reset_index(drop=True).copy()
    if derived_counts:
        denom = df[pop_col].replace(0, np.nan)
        for col in count_cols:
            df[f"_rate_{col}"] = df[col] / denom

    pop21 = _population_for(pop_year)
    df = df.drop(columns=[pop_col]).merge(pop21, on="LSOA21CD", how="left")

    n_missing = int(df[pop_col].isna().sum())
    if n_missing:
        raise ValueError(
            f"{n_missing} LSOA 2021 areas have no {pop_year} population estimate. "
            f"Refusing to publish rates against a partial denominator."
        )

    if derived_counts:
        for col in count_cols:
            df[col] = df[f"_rate_{col}"] * df[pop_col]
        df = df.drop(columns=[f"_rate_{col}" for col in count_cols])
    return df


def _process_domain(domain_name, domain_dir, count_cols_fn, pop_col, year_pattern,
                    derived_counts=False):
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

        # Which year's population this file is published against. It picks BOTH
        # the crosswalk's split weights and the denominator, which is the point:
        # the two cancel for a split LSOA only when they are the same year.
        pop_year = _pop_year_from_stem(stem)

        # Apply crosswalk (LSOA 2011 -> LSOA 2021)
        lsoa21_df = apply_crosswalk(df, _crosswalk_for(pop_year), count_cols, pop_col)

        # Publish against the real LSOA 2021 mid-year estimate for this year,
        # not the crosswalked (and, from 2021, frozen) 2011-vintage population.
        lsoa21_df = _reset_denominator(
            lsoa21_df, count_cols, pop_col, pop_year, derived_counts,
        )

        _check_lsoa_coverage(stem, lsoa21_df)

        # --- LSOA level ---
        lsoa_dir = output_dir / "lsoa" / domain_name
        lsoa_dir.mkdir(parents=True, exist_ok=True)

        # Add LSOA names, then the covered population and the rate it denominates.
        # An LSOA is measured or it is not, so `{col}_pop` here is `pop` or NaN --
        # carried anyway so that one expression, `{col} / {col}_pop`, reproduces
        # the rate at every level rather than only above LSOA.
        lsoa_names = lsoa_to_lad[["LSOA21CD", "LSOA21NM"]].drop_duplicates()
        lsoa_out = lsoa_names.merge(lsoa21_df, on="LSOA21CD", how="right")
        lsoa_out = pd.concat(
            [lsoa_out, covered_population(lsoa_out, count_cols, pop_col)], axis=1,
        )
        for col in count_cols:
            denom = lsoa_out[f"{col}{COVERED_POP_SUFFIX}"].replace(0, np.nan)
            lsoa_out[f"{col}_rate"] = lsoa_out[col] / denom
        lsoa_out.to_csv(lsoa_dir / f"{stem}.csv", index=False)

        # --- LAD, Region and England ---
        # All three are the same operation over a different lookup, so they share
        # one code path and cannot disagree about what they summed.
        levels = {}
        for level, lookup, code_col, name_col in (
            ("lad", lsoa_to_lad, "LAD25CD", "LAD25NM"),
            ("region", lsoa_to_rgn, "RGN25CD", "RGN25NM"),
            ("england", lsoa_to_eng, "area_code", "area_name"),
        ):
            level_dir = output_dir / level / domain_name
            level_dir.mkdir(parents=True, exist_ok=True)
            level_df = aggregate_to_geography(
                lsoa21_df, lookup, "LSOA21CD", code_col, name_col,
                count_cols, pop_col,
            )
            level_df.to_csv(level_dir / f"{stem}.csv", index=False)
            levels[level] = level_df

        print(f"  {domain_name}/{stem}: LSOA={len(lsoa_out)}, LAD={len(levels['lad'])}, "
              f"Region={len(levels['region'])}, pop_year={pop_year}")

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
    derived_counts=True,
)

# %%
#|export
print(f"aggregate: done, output at {const.rel(output_dir)}")
True  #|func_return_line
