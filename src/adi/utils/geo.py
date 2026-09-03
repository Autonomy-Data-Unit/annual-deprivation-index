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
    count_pops: dict[str, str] | None = None,
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

    `count_pops` extends this from "a different coverage subset of one population"
    to "a genuinely different population". QOF measures nine of its registers
    against an age-restricted list -- osteoporosis against 50+, depression against
    18+ -- so those counts have a different DENOMINATOR, not merely a different
    mask over the same one. A count named there takes its population from the
    column it names instead of `pop_col`, and everything downstream is unchanged:
    the same masking, the same summation, the same `{col}_rate == {col} /
    {col}_pop` identity at every level. Counts absent from the mapping keep
    `pop_col`, so the existing metrics are untouched.

    Args:
        df: Rows carrying the count columns, `pop_col`, and any population column
            named in `count_pops`.
        count_cols: Count columns to derive a denominator for.
        pop_col: The area's full population column, and the default denominator.
        count_pops: Optional `{count_col: population_col}` for counts measured
            against a population other than `pop_col`.

    Returns:
        DataFrame aligned to `df.index`, one `{col}{COVERED_POP_SUFFIX}` column
        per entry in `count_cols`.
    """
    count_pops = count_pops or {}
    clashes = [c for c in count_cols if f"{c}{COVERED_POP_SUFFIX}" in df.columns]
    if clashes:
        raise ValueError(
            f"Covered-population columns would overwrite existing ones: {clashes}. "
            f"Rename the count column or the {COVERED_POP_SUFFIX!r} suffix."
        )
    unknown = {c: p for c, p in count_pops.items()
               if c in count_cols and p not in df.columns}
    if unknown:
        raise ValueError(
            f"These counts name a population column that is not present: {unknown}. "
            f"A count cannot be published against a denominator we do not have."
        )
    return pd.DataFrame(
        {f"{c}{COVERED_POP_SUFFIX}": df[count_pops.get(c, pop_col)].where(df[c].notna())
         for c in count_cols},
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
    extra_pop_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Apply crosswalk to convert LSOA 2011 data to LSOA 2021.

    Disaggregates absolute counts using population weights, then
    reaggregates to LSOA 2021. Rates are recomputed from the
    disaggregated numerators and denominators.

    `extra_pop_cols` are further absolute head counts to carry across -- the
    age-band resident populations an age-restricted metric is measured against.
    They are disaggregated and reaggregated exactly like a count, because that is
    what they are; they are listed separately only because they are denominators
    rather than metrics, so nothing downstream should give them a rate.

    Carrying them matters most for a MERGE, where two LSOA 2011 areas become one
    LSOA 2021 area and the merged rate is `sum(count) / sum(denominator)`. Weight
    that by the all-ages population instead of the band population and the merged
    rate is wrong by the difference in the two areas' age structure: measured on
    2016-17 osteoporosis that reaches 57% on one merged area, against a median of
    0.4%. For unchanged and split areas both scale by the same weight and cancel,
    so it is merges alone that need this -- but they need it badly.

    Args:
        df: Source data with LSOA 2011 codes.
        crosswalk: Crosswalk table from build_crosswalk().
        count_cols: Column names containing absolute counts to disaggregate.
        pop_col: Column name for population (also disaggregated).
        lsoa_col: Column name for LSOA codes in df.
        extra_pop_cols: Further absolute population columns to carry across.

    Returns:
        DataFrame with LSOA 2021 codes and converted values.
    """
    # Merge source data with crosswalk
    merged = df.merge(crosswalk, left_on=lsoa_col, right_on="LSOA11CD", how="inner")

    # Disaggregate: multiply counts and population by weight
    cols_to_weight = count_cols + [pop_col] + list(extra_pop_cols or [])
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
    count_pops: dict[str, str] | None = None,
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
    #
    # This is also what makes an age-restricted metric aggregate correctly. Its
    # `{col}_pop` is the eligible population, not the resident one, so summing the
    # pair and dividing weights each LSOA by the population that metric is actually
    # measured against. Weighting osteoporosis by resident population instead would
    # be wrong at every level above LSOA while LSOA itself looked fine.
    covered = covered_population(merged, count_cols, pop_col, count_pops)
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


#: Prefix for an age-band resident population column carried through aggregation.
#: `pop` alone stays the all-ages estimate; `pop_50OV` is the 50-and-over one.
BAND_POP_PREFIX = "pop_"


def band_pop_col(band: str) -> str:
    """Column name for an age band's resident population."""
    return f"{BAND_POP_PREFIX}{band}"


def _load_age_bands(path: Path, bands: list[str], code_col: str) -> pd.DataFrame:
    """Pivot one Nomis age-band file to one column per band.

    The file is long -- one row per (LSOA, band) -- and carries `All Ages` beside
    the bands so it can be reconciled against the plain population file.
    """
    raw = pd.read_csv(path, usecols=["GEOGRAPHY_CODE", "C_AGE_NAME", "OBS_VALUE"])
    wide = raw.pivot_table(index="GEOGRAPHY_CODE", columns="C_AGE_NAME",
                           values="OBS_VALUE", aggfunc="max")
    wide.columns.name = None
    missing = [b for b in bands if b not in wide.columns]
    if missing:
        raise ValueError(
            f"{path.name} has no {missing} series (it carries {sorted(wide.columns)}). "
            f"An age-restricted metric cannot be published without the population "
            f"its register is measured against."
        )
    out = wide[bands].rename(columns={b: band_pop_col(b) for b in bands})
    out.index.name = code_col
    return out.reset_index()


def load_lsoa21_age_bands(band_dir: Path, year: int, bands: list[str]) -> pd.DataFrame:
    """LSOA 2021 resident population for each requested age band, for `year`.

    The published denominator for an age-restricted metric, and the exact analogue
    of `load_lsoa21_population` for one. No fallback to a neighbouring year, for
    the same reason: a silently substituted denominator is the failure this exists
    to remove.

    A band population of zero is left as zero here and rejected to NaN where the
    rate is formed, not clamped. Two LSOAs have a 50+ population of exactly 0 in
    2021 -- E01033276 and E01034950, both purpose-built student accommodation --
    and osteoporosis there is unmeasurable, not nil.
    """
    path = band_dir / f"NM_2014_1_TYPE151_{year}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No LSOA 2021 age-band population file for {year} at {path}. "
            f"Run the fetch_populations node for that year."
        )
    return _load_age_bands(path, bands, "LSOA21CD")


def load_lsoa11_age_bands(band_dir: Path, year: int, bands: list[str],
                          fallback_year: int) -> tuple[pd.DataFrame, int]:
    """LSOA 2011 resident population per age band, falling back to `fallback_year`.

    Used only to carry a metric's own denominator across the crosswalk, so that a
    merged LSOA 2021 area combines its parents' rates weighted by the population
    each rate is measured against rather than by residents of every age.

    The 2011-vintage series (Nomis NM_2010_1) ends in 2020, so later years have no
    2011-vintage band population and there is nothing to substitute but the last
    one. That is survivable here precisely because this denominator does not reach
    the outputs: it is divided back out immediately after the crosswalk, so for
    unchanged and split areas it cancels exactly, and only the weighting of a merge
    is affected. `fallback_year` is a required argument rather than a default so
    the substitution is a decision at the call site, never a silent one.

    Returns `(frame, year_used)` so the caller can say which it got.
    """
    path = band_dir / f"NM_2010_1_TYPE298_{year}.csv"
    used = year
    if not path.exists():
        path, used = band_dir / f"NM_2010_1_TYPE298_{fallback_year}.csv", fallback_year
        if not path.exists():
            raise FileNotFoundError(
                f"No LSOA 2011 age-band population file for {year} or {fallback_year} "
                f"in {band_dir}. Run the fetch_populations node."
            )
    return _load_age_bands(path, bands, "LSOA11CD"), used
