"""LSOA vintage crosswalk and geographic aggregation utilities."""

from pathlib import Path

import numpy as np
import pandas as pd


def build_crosswalk(
    lsoa_xwalk_path: Path,
    lsoa21_pop_path: Path,
) -> pd.DataFrame:
    """Build a crosswalk table mapping LSOA 2011 to LSOA 2021 with weights.

    Uses the LSOA exact-fit lookup (with change indicators) and LSOA 2021
    population data for weighting splits.

    For unchanged (U): weight = 1.0
    For merged (M): weight = 1.0 (multiple LSOA11 -> one LSOA21, values summed)
    For split (S): weight = LSOA21_pop / sum(LSOA21_pop for this LSOA11)
    For complex (X): excluded

    Returns:
        DataFrame with columns: LSOA11CD, LSOA21CD, weight, CHGIND
    """
    xwalk = pd.read_csv(lsoa_xwalk_path)
    pop = pd.read_csv(lsoa21_pop_path)
    pop = pop.rename(columns={"GEOGRAPHY_CODE": "LSOA21CD", "OBS_VALUE": "lsoa21_pop"})
    pop = pop[["LSOA21CD", "lsoa21_pop"]]

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

    # Reaggregate by LSOA21CD
    result = merged.groupby("LSOA21CD")[cols_to_weight].sum().reset_index()

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

    # Sum counts and population by geography
    agg_cols = count_cols + [pop_col]
    result = merged.groupby([geo_code_col, geo_name_col])[agg_cols].sum().reset_index()

    # Recompute rates
    for col in count_cols:
        rate_col = f"{col}_rate" if not col.endswith("_rate") else col
        if rate_col != col:
            result[rate_col] = result[col] / result[pop_col].replace(0, np.nan)

    return result
