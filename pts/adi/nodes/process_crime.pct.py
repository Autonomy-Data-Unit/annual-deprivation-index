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
# 1. Check that every English territorial force supplied a non-empty street CSV in all 12 months
# 2. Load monthly street CSVs, excluding British Transport Police in every year
# 3. Drop rows with missing LSOA codes
# 4. Filter out Welsh LSOAs (codes starting with 'W')
# 5. Aggregate crime counts by LSOA and crime type
# 6. Merge with LSOA 2011 population data
# 7. Mark areas served by an incomplete force unavailable (NaN), never as partial totals
# 8. Compute per-capita rates and save counts, rates, and population
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
    """Validate and process raw street crime data into per-LSOA annual rates."""
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

# The resident-area measure covers the 39 English territorial forces. British
# Transport Police is excluded consistently: it is a national network force with
# no exclusive LAD footprint, so its missing months must neither erase otherwise
# complete territorial-force data nor silently change the measure between years.
# Welsh and Northern Irish files can contain occasional English geocodes, which the
# existing pipeline retains, but their reporting completeness must not decide
# whether the England series is publishable.
ENGLISH_TERRITORIAL_FORCE_SLUGS = frozenset({
    "avon-and-somerset",
    "bedfordshire",
    "cambridgeshire",
    "cheshire",
    "city-of-london",
    "cleveland",
    "cumbria",
    "derbyshire",
    "devon-and-cornwall",
    "dorset",
    "durham",
    "essex",
    "gloucestershire",
    "greater-manchester",
    "hampshire",
    "hertfordshire",
    "humberside",
    "kent",
    "lancashire",
    "leicestershire",
    "lincolnshire",
    "merseyside",
    "metropolitan",
    "norfolk",
    "north-yorkshire",
    "northamptonshire",
    "northumbria",
    "nottinghamshire",
    "south-yorkshire",
    "staffordshire",
    "suffolk",
    "surrey",
    "sussex",
    "thames-valley",
    "warwickshire",
    "west-mercia",
    "west-midlands",
    "west-yorkshire",
    "wiltshire",
})
EXCLUDED_NETWORK_FORCE_SLUGS = frozenset({"btp"})

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
def _build_lsoa11_lad_lookup() -> tuple[dict, dict]:
    """Build LSOA 2011 -> LAD 2025 and inverse lookups for coverage masking."""
    xw = pd.read_csv(const.crosswalk_path / "lsoa11_to_lsoa21.csv", dtype=str)
    lad = pd.read_csv(
        const.geo_lookups_path / "lsoa21_to_lad25.csv",
        usecols=["LSOA21CD", "LAD25CD"],
        dtype=str,
    ).drop_duplicates()
    mapped = (
        xw.loc[xw["CHGIND"] != "X", ["LSOA11CD", "LSOA21CD"]]
        .merge(lad, on="LSOA21CD", how="inner")
        [["LSOA11CD", "LAD25CD"]]
        .drop_duplicates()
    )
    ambiguous = mapped.groupby("LSOA11CD")["LAD25CD"].nunique()
    if (ambiguous > 1).any():
        raise ValueError("An LSOA 2011 code maps to more than one LAD; cannot mask a force footprint safely")

    lsoa_to_lad = dict(zip(mapped["LSOA11CD"], mapped["LAD25CD"]))
    lad_to_lsoas = {
        lad_code: set(group["LSOA11CD"])
        for lad_code, group in mapped[
            mapped["LSOA11CD"].str.startswith("E")
            & mapped["LAD25CD"].str.startswith("E")
        ].groupby("LAD25CD")
    }
    return lsoa_to_lad, lad_to_lsoas


_lsoa11_to_lad, _lad_to_lsoa11s = _build_lsoa11_lad_lookup()
print(f"  loaded LSOA11 footprints for {len(_lad_to_lsoa11s)} English LADs")

# %%
#|export
def _build_street_file_index() -> dict:
    """Index each (year, force, month) street file and reject duplicates."""
    index = {}
    for month_dir in crime_dir.glob("????-??"):
        if not month_dir.is_dir():
            continue
        year_text, month_text = month_dir.name.split("-", maxsplit=1)
        if not (year_text.isdigit() and month_text.isdigit()):
            continue
        year, month = int(year_text), int(month_text)
        prefix, suffix = f"{month_dir.name}-", "-street.csv"
        for csv_path in month_dir.glob(f"{prefix}*{suffix}"):
            force = csv_path.name[len(prefix):-len(suffix)]
            key = (year, force, month)
            if key in index:
                raise ValueError(f"Duplicate street files for {year}-{month:02d} {force}")
            index[key] = csv_path
    return index


_street_file_index = _build_street_file_index()
print(f"  indexed {len(_street_file_index)} force-month street files")

_has_records_cache = {}


def _has_data_record(path: Path) -> bool:
    """Return whether a CSV has a non-blank physical line after its header."""
    if path not in _has_records_cache:
        with path.open("rb") as f:
            f.readline()
            _has_records_cache[path] = any(line.strip() for line in f)
    return _has_records_cache[path]


def _nearest_complete_reference_year(force: str, year: int) -> int:
    """Find the closest year with 12 non-empty files, preferring the past on ties."""
    years = {y for y, f, _ in _street_file_index if f == force}
    complete = [
        candidate
        for candidate in years
        if all(
            (candidate, force, month) in _street_file_index
            and _has_data_record(_street_file_index[(candidate, force, month)])
            for month in range(1, 13)
        )
    ]
    if not complete:
        raise ValueError(
            f"No complete reference year exists for incomplete force {force!r}; "
            "refusing to publish an unknown geographic footprint"
        )
    return min(complete, key=lambda candidate: (abs(candidate - year), candidate > year, candidate))


_force_footprint_cache = {}


def _territorial_force_lads(force: str, year: int) -> tuple[set, int]:
    """Infer a territorial force's LAD footprint from its nearest complete year.

    A force must report at least one incident in half of a LAD's LSOAs in the
    reference year. Twelve months make genuine force areas approach full LSOA
    coverage, while this majority rule rejects rare cross-boundary geocodes.
    """
    reference_year = _nearest_complete_reference_year(force, year)
    cache_key = (force, reference_year)
    if cache_key not in _force_footprint_cache:
        code_frames = []
        for month in range(1, 13):
            path = _street_file_index[(reference_year, force, month)]
            code_frames.append(pd.read_csv(path, usecols=["LSOA code"], dtype=str))
        codes = pd.concat(code_frames, ignore_index=True)["LSOA code"].dropna()
        codes = codes[codes.str.startswith("E")]
        codes = codes.map(_lsoa21_to_lsoa11).fillna(codes)

        observed_by_lad = {}
        for lsoa in set(codes):
            lad = _lsoa11_to_lad.get(lsoa)
            if lad is not None:
                observed_by_lad.setdefault(lad, set()).add(lsoa)
        force_lads = {
            lad
            for lad, observed in observed_by_lad.items()
            if len(observed) / len(_lad_to_lsoa11s[lad]) >= 0.5
        }
        if not force_lads:
            raise ValueError(
                f"Could not infer any LADs for incomplete force {force!r} "
                f"from complete reference year {reference_year}"
            )
        _force_footprint_cache[cache_key] = force_lads
    return _force_footprint_cache[cache_key], reference_year

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


def _load_street_data_for_year(year: int) -> tuple[pd.DataFrame, dict, dict]:
    """Load a year and count included and excluded force-month records."""
    frames = []
    records = {force: {} for force in ENGLISH_TERRITORIAL_FORCE_SLUGS}
    excluded_records = {force: {} for force in EXCLUDED_NETWORK_FORCE_SLUGS}
    year_files = sorted(
        (key, path) for key, path in _street_file_index.items() if key[0] == year
    )
    for (_, force, month), csv_path in year_files:
        df = pd.read_csv(csv_path, usecols=["LSOA code", "LSOA name", "Crime type"])
        if force in excluded_records:
            excluded_records[force][month] = len(df)
            continue
        frames.append(df)
        if force in records:
            records[force][month] = len(df)
    if not frames:
        empty = pd.DataFrame(columns=["LSOA code", "LSOA name", "Crime type"])
        return empty, records, excluded_records
    return pd.concat(frames, ignore_index=True), records, excluded_records


def _incomplete_force_coverage(year: int, records: dict) -> list[dict]:
    """Return English force-years without 12 non-empty monthly submissions.

    Completeness is deliberately binary and source-evidenced: one non-empty
    street file for every calendar month. We do not infer missingness from a
    volume fall because real incidence/recording can change abruptly (notably
    during COVID-19), so a numeric threshold would turn measurements into gaps.
    """
    failures = []
    for force in sorted(ENGLISH_TERRITORIAL_FORCE_SLUGS):
        present = {
            month
            for month in range(1, 13)
            if (year, force, month) in _street_file_index
        }
        nonempty = {month for month, count in records[force].items() if count > 0}
        if len(nonempty) == 12:
            continue
        failures.append({
            "force": force,
            "present": present,
            "nonempty": nonempty,
            "missing": set(range(1, 13)) - present,
            "empty": present - nonempty,
            "records": sum(records[force].values()),
        })
    return failures

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
    df, force_records, excluded_force_records = _load_street_data_for_year(year)
    if df.empty:
        print(f"  {year}: no crime data found, skipping")
        continue

    for force, monthly_records in sorted(excluded_force_records.items()):
        present = {
            month for month in range(1, 13)
            if (year, force, month) in _street_file_index
        }
        nonempty = {month for month, count in monthly_records.items() if count > 0}
        print(
            f"  {year}: EXCLUDED network force {force}: "
            f"files={len(present)}/12, nonempty={len(nonempty)}/12, "
            f"records={sum(monthly_records.values()):,}"
        )

    incomplete_forces = _incomplete_force_coverage(year, force_records)
    unavailable_lsoas = set()
    for coverage in incomplete_forces:
        force = coverage["force"]
        missing = ",".join(f"{month:02d}" for month in sorted(coverage["missing"])) or "none"
        empty = ",".join(f"{month:02d}" for month in sorted(coverage["empty"])) or "none"
        print(
            f"  {year}: INCOMPLETE {force}: "
            f"files={len(coverage['present'])}/12, nonempty={len(coverage['nonempty'])}/12, "
            f"records={coverage['records']:,}, missing=[{missing}], empty=[{empty}]"
        )
        force_lads, reference_year = _territorial_force_lads(force, year)
        force_lsoas = set().union(*(_lad_to_lsoa11s[lad] for lad in force_lads))
        unavailable_lsoas.update(force_lsoas)
        print(
            f"  {year}: {force} footprint from complete {reference_year}: "
            f"{len(force_lads)} LADs / {len(force_lsoas)} LSOAs will be unavailable"
        )

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

    # Fill NaN crime counts with 0 only where every expected territorial force-year was
    # complete. A missing force-month means the annual total was not observed;
    # it is not evidence that zero incidents occurred.
    crime_type_cols = [c for c in result.columns if c not in ("LSOA11CD", "LSOA11NM", "pop")]
    for col in crime_type_cols:
        result[col] = result[col].fillna(0)

    unavailable = result["LSOA11CD"].isin(unavailable_lsoas)
    result.loc[unavailable, crime_type_cols] = np.nan

    for col in crime_type_cols:
        result[f"{col}_rate"] = result[col] / result["pop"].replace(0, np.nan)

    result.to_csv(out_path, index=False)
    available = ~unavailable
    total_crimes = result.loc[available, crime_type_cols].sum().sum()
    print(
        f"  {year}: {len(result)} LSOAs, {int(unavailable.sum())} unavailable, "
        f"{int(total_crimes)} crimes in reporting areas across {len(crime_type_cols)} types"
    )

print(f"process_crime: done, output at {const.rel(output_dir)}")
True  #|func_return_line
