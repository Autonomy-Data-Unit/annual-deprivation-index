"""LSOA vintage crosswalk and geographic aggregation utilities."""

from pathlib import Path

import numpy as np
import pandas as pd

#: Suffix for the "population standing behind this count" column that accompanies
#: every count column in the published outputs. See `covered_population`.
COVERED_POP_SUFFIX = "_pop"


def covered_population(
    df: pd.DataFrame,
    count_cols: list[str],
    pop_col: str,
) -> pd.DataFrame:
    """Per row and per count column, the population that count actually covers.

    A count is NaN where the area was not measured -- Greater Manchester's street
    crime from 2019, a QOF disease group whose practices were not published, a
    crime year where BTP never reported. Population is never NaN, so summing the
    two independently produces a rate whose numerator covers less ground than its
    denominator, and the published rate is understated by exactly the share of the
    population that was never measured. England's 2019 burglary rate was computed
    over 56.2m residents from a count that excluded Greater Manchester's 1,673
    LSOAs; Camden's 2014 diabetes rate divided 220,568 people's registers by
    221,095 people.

    So every count column gets its own denominator: this area's population where
    this count exists, NaN where it does not. Summed alongside the count, that
    gives `{col}{COVERED_POP_SUFFIX}`, and `{col}_rate == {col} / {col}_pop`
    holds exactly at every geography level.

    `pop` keeps one meaning throughout: the ONS mid-year estimate for the whole
    area, whatever was or was not measured in it. Dividing `{col}_pop` by `pop`
    is how a reader sees the coverage.

    Args:
        df: Rows carrying the count columns and `pop_col`.
        count_cols: Count columns to derive a denominator for.
        pop_col: The area's full population column.

    Returns:
        DataFrame aligned to `df.index`, one `{col}{COVERED_POP_SUFFIX}` column
        per entry in `count_cols`.
    """
    clashes = [c for c in count_cols if f"{c}{COVERED_POP_SUFFIX}" in df.columns]
    if clashes:
        raise ValueError(
            f"Covered-population columns would overwrite existing ones: {clashes}. "
            f"Rename the count column or the {COVERED_POP_SUFFIX!r} suffix."
        )
    return pd.DataFrame(
        {f"{c}{COVERED_POP_SUFFIX}": df[pop_col].where(df[c].notna()) for c in count_cols},
        index=df.index,
    )


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

    # Merge with LSOA 2021 populations.
    #
    # A missing population used to become 0 here, which gives the LSOA weight 0
    # and publishes it with zero claimants, zero crime and zero disease -- a gap
    # in the population fetch presented as a measurement. Reject instead: there
    # is no defensible weight for an area whose population we do not have.
    xwalk = xwalk.merge(pop, on="LSOA21CD", how="left")
    missing = sorted(xwalk.loc[xwalk["lsoa21_pop"].isna(), "LSOA21CD"].unique())
    if missing:
        raise ValueError(
            f"{len(missing)} LSOA 2021 area(s) in the crosswalk have no population "
            f"estimate (e.g. {missing[:5]}). Refusing to weight them as zero, which "
            f"would publish them as measured zeroes. Re-run the fetch_populations "
            f"node for this year."
        )

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
            # For each LSOA11, compute weight as LSOA21_pop / total_pop_of_splits.
            # A family with no population at all has no defensible split, so it
            # is rejected rather than given weight 0 -- which would silently
            # delete the parent's counts instead of failing.
            group = group.copy()
            total_pop = group.groupby("LSOA11CD")["lsoa21_pop"].transform("sum")
            empty = sorted(group.loc[total_pop <= 0, "LSOA11CD"].unique())
            if empty:
                raise ValueError(
                    f"{len(empty)} split LSOA 2011 area(s) have zero total LSOA 2021 "
                    f"population (e.g. {empty[:5]}), so their counts cannot be divided "
                    f"between the children. Refusing to assign weight 0, which would "
                    f"drop the parent's counts from the outputs entirely."
                )
            group["weight"] = group["lsoa21_pop"] / total_pop
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
    # min_count=1 covers exactly one case, and it is worth being precise about
    # which. pandas' default sum() returns 0 for an ALL-NaN group, turning "this
    # quantity was never collected" into "we measured it and it was nil". QOF
    # stopped publishing several disease groups (SMOK and THY after 2013-14,
    # CVDPP after 2019-20) and they arrive here as all-NaN columns; min_count=1
    # keeps them NaN all the way to the published outputs.
    #
    # It does NOT rescue a PARTLY-NaN group. That still sums its measured members
    # and returns a total that looks complete. What makes the partial case safe
    # is not this argument but `covered_population`: the count and the population
    # it is divided by carry the same NaN mask, so the published rate is over the
    # measured subset either way, and `{col}_pop / pop` is how a reader sees how
    # much of the area it rests on. Do not read min_count=1 as more than it is.
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

    Two populations come out of this, and they answer different questions:

    * `pop_col` is the area's full ONS mid-year population -- every LSOA in it,
      measured or not. It means the same thing in every domain, level and year,
      so the three domains agree on how many people live somewhere.
    * `{col}{COVERED_POP_SUFFIX}` is the population behind `col` specifically,
      and is what `{col}_rate` divides by. It equals `pop_col` wherever the whole
      area was measured, and is smaller where it was not.

    Aggregating a count over reporting areas and dividing it by everybody is what
    made England's 2019 crime rates read ~5% low; see `covered_population`.

    Args:
        df: LSOA-level data.
        lookup: Lookup table mapping LSOAs to target geography.
        lsoa_col: LSOA code column in df.
        geo_code_col: Target geography code column in lookup.
        geo_name_col: Target geography name column in lookup.
        count_cols: Columns with absolute counts.
        pop_col: Population column.

    Returns:
        Aggregated DataFrame with geo code, name, counts, population, per-count
        covered populations, and rates.
    """
    # Merge with lookup
    merged = df.merge(
        lookup[[lsoa_col, geo_code_col, geo_name_col]].drop_duplicates(),
        on=lsoa_col, how="inner",
    )

    # Sum counts, population and per-count covered population by geography.
    #
    # min_count=1 keeps an all-NaN group NaN instead of 0 -- "nothing here was
    # measured" rather than "nothing here was found". It does nothing for a
    # partly-measured group; see the fuller note in apply_crosswalk. What handles
    # that case is the pairing below: a count and its covered population share
    # one NaN mask by construction, so they are summed over the same areas and
    # the rate is right whether the group was fully measured, partly measured, or
    # not at all.
    covered = covered_population(merged, count_cols, pop_col)
    agg_cols = count_cols + [pop_col] + list(covered.columns)
    result = (
        pd.concat([merged[[geo_code_col, geo_name_col] + count_cols + [pop_col]], covered], axis=1)
        .groupby([geo_code_col, geo_name_col])[agg_cols]
        .sum(min_count=1)
        .reset_index()
    )

    # Recompute rates against the population each count actually covers.
    for col in count_cols:
        rate_col = f"{col}_rate" if not col.endswith("_rate") else col
        if rate_col != col:
            denom = result[f"{col}{COVERED_POP_SUFFIX}"].replace(0, np.nan)
            result[rate_col] = result[col] / denom

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
