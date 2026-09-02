"""LSOA vintage crosswalk and geographic aggregation utilities."""

from pathlib import Path

import numpy as np
import pandas as pd


def build_crosswalk(
    lsoa_xwalk_path: Path,
    lsoa21_pop: pd.DataFrame,
) -> pd.DataFrame:
    """Build a crosswalk table mapping LSOA 2011 to LSOA 2021 with weights.

    Uses the LSOA exact-fit lookup (with change indicators) and LSOA 2021
    population data for weighting splits.

    For unchanged (U): weight = 1.0
    For merged (M): weight = 1.0 (multiple LSOA11 -> one LSOA21, values summed)
    For split (S): weight = LSOA21_pop / sum(LSOA21_pop for this LSOA11)
    For complex (X): excluded

    `lsoa21_pop` MUST be the population of the year the output will be published
    against -- pass the very frame that becomes the denominator, as returned by
    `load_lsoa21_population`. A split's weight and its denominator are two halves
    of one division: weight_i = P_i / sum_j P_j, and the denominator is P_i, so
    the published rate is count / sum_j P_j -- the parent's rate, identically for
    every child, which is the only rate the crosswalk can justify. Take the two
    from different years and that cancellation breaks: the child's rate is then
    scaled by share_weighting_year / share_publication_year, which ran from 0.485
    to 1.678 in 2014 while the weights came from a single 2025 file (#6).

    This takes a DataFrame rather than a path precisely so that the caller cannot
    hand the weights one population year and the denominator another.

    Args:
        lsoa_xwalk_path: ONS LSOA11 -> LSOA21 exact-fit lookup, with CHGIND.
        lsoa21_pop: LSOA 2021 populations for the publication year, columns
            LSOA21CD and pop, from `load_lsoa21_population`.

    Returns:
        DataFrame with columns: LSOA11CD, LSOA21CD, weight, CHGIND
    """
    xwalk = pd.read_csv(lsoa_xwalk_path)
    pop = lsoa21_pop.rename(columns={"pop": "lsoa21_pop"})[["LSOA21CD", "lsoa21_pop"]]

    # Filter out complex changes
    xwalk = xwalk[xwalk["CHGIND"] != "X"].copy()

    # Merge with LSOA 2021 populations
    xwalk = xwalk.merge(pop, on="LSOA21CD", how="left")
    xwalk["lsoa21_pop"] = xwalk["lsoa21_pop"].fillna(0)

    # Compute weights
    # For U and M: each row gets weight 1.0 (one LSOA11 -> one LSOA21, or
    # multiple LSOA11 -> one LSOA21 where each contributes fully)
    # For S: distribute by LSOA21 population proportion
    weights = []
    for chgind, group in xwalk.groupby("CHGIND"):
        if chgind in ("U", "M"):
            group = group.copy()
            group["weight"] = 1.0
            weights.append(group)
        elif chgind == "S":
            # For each LSOA11, compute weight as LSOA21_pop / total_pop_of_splits
            group = group.copy()
            total_pop = group.groupby("LSOA11CD")["lsoa21_pop"].transform("sum")
            group["weight"] = np.where(total_pop > 0, group["lsoa21_pop"] / total_pop, 0)
            weights.append(group)

    result = pd.concat(weights, ignore_index=True)
    return result[["LSOA11CD", "LSOA21CD", "weight", "CHGIND"]]


def apply_crosswalk(
    df: pd.DataFrame,
    crosswalk: pd.DataFrame,
    count_cols: list[str],
    pop_col: str,
    lsoa_col: str = "LSOA11CD",
) -> pd.DataFrame:
    """Apply crosswalk to convert LSOA 2011 data to LSOA 2021.

    Disaggregates absolute counts using population weights, then
    reaggregates to LSOA 2021. Rates are recomputed from the
    disaggregated numerators and denominators.

    Args:
        df: Source data with LSOA 2011 codes.
        crosswalk: Crosswalk table from build_crosswalk().
        count_cols: Column names containing absolute counts to disaggregate.
        pop_col: Column name for population (also disaggregated).
        lsoa_col: Column name for LSOA codes in df.

    Returns:
        DataFrame with LSOA 2021 codes and converted values.
    """
    # Merge source data with crosswalk
    merged = df.merge(crosswalk, left_on=lsoa_col, right_on="LSOA11CD", how="inner")

    # Disaggregate: multiply counts and population by weight
    cols_to_weight = count_cols + [pop_col]
    for col in cols_to_weight:
        merged[col] = merged[col] * merged["weight"]

    # Reaggregate by LSOA21CD.
    #
    # min_count=1 is load-bearing: pandas' default sum() returns 0 for an
    # all-NaN group, which would turn "this quantity was never collected" into
    # the assertion "we measured it and it was nil". QOF stopped publishing
    # several disease groups (SMOK after 2013-14, THY after 2013-14, CVDPP
    # after 2019-20), and those arrive here as all-NaN columns. They must stay
    # NaN all the way to the published outputs.
    result = merged.groupby("LSOA21CD")[cols_to_weight].sum(min_count=1).reset_index()

    return result


def aggregate_to_geography(
    df: pd.DataFrame,
    lookup: pd.DataFrame,
    lsoa_col: str,
    geo_code_col: str,
    geo_name_col: str,
    count_cols: list[str],
    pop_col: str,
) -> pd.DataFrame:
    """Aggregate LSOA-level data to a higher geography level.

    Sums absolute counts and populations, then recomputes rates.

    Args:
        df: LSOA-level data.
        lookup: Lookup table mapping LSOAs to target geography.
        lsoa_col: LSOA code column in df.
        geo_code_col: Target geography code column in lookup.
        geo_name_col: Target geography name column in lookup.
        count_cols: Columns with absolute counts.
        pop_col: Population column.

    Returns:
        Aggregated DataFrame with geo code, name, counts, population, and rates.
    """
    # Merge with lookup
    merged = df.merge(
        lookup[[lsoa_col, geo_code_col, geo_name_col]].drop_duplicates(),
        on=lsoa_col, how="inner",
    )

    # Sum counts and population by geography.
    # min_count=1 so an all-NaN group stays NaN rather than becoming 0 -- see
    # the note in apply_crosswalk.
    agg_cols = count_cols + [pop_col]
    result = (
        merged.groupby([geo_code_col, geo_name_col])[agg_cols]
        .sum(min_count=1)
        .reset_index()
    )

    # Recompute rates
    for col in count_cols:
        rate_col = f"{col}_rate" if not col.endswith("_rate") else col
        if rate_col != col:
            result[rate_col] = result[col] / result[pop_col].replace(0, np.nan)

    return result


def load_lsoa21_population(pop_dir: Path, year: int) -> pd.DataFrame:
    """Load the ONS mid-year LSOA 2021 population estimate for `year`.

    This is the denominator for the published outputs. It is deliberately the
    real per-year estimate for the target vintage, NOT the LSOA 2011 population
    carried through the crosswalk: the 2011-vintage series (Nomis NM_2010_1)
    ends at 2020, so using it freezes the denominator from 2021 onward and
    silently understates population growth in every later year.

    Raises FileNotFoundError if the year is missing. There is deliberately no
    fallback to a neighbouring year -- a silently substituted denominator is
    exactly the failure this function exists to remove.
    """
    path = pop_dir / f"population_{year}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No LSOA 2021 population file for {year} at {path}. "
            f"Run the fetch_populations node for that year."
        )
    pop = pd.read_csv(path)
    pop = pop.rename(columns={"GEOGRAPHY_CODE": "LSOA21CD", "OBS_VALUE": "pop"})
    return pop[["LSOA21CD", "pop"]]
