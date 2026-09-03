"""Nomis REST API client for claimant counts and population estimates.

No authentication required. 25,000 row limit per CSV request;
must paginate via RecordLimit and RecordOffset parameters.
"""

import asyncio
import io
import shutil
from pathlib import Path

import httpx
import pandas as pd

NOMIS_API_BASE = "https://www.nomisweb.co.uk/api/v01/dataset"
PAGE_SIZE = 25_000

#: Population dataset behind each LSOA geography vintage.
POPULATION_DATASETS = {"TYPE151": "NM_2014_1", "TYPE298": "NM_2010_1"}

#: How many years past the end of a population series we are willing to publish
#: against that series' last estimate. ONS releases LSOA mid-year estimates about
#: 14 months in arrears, so the newest ADI year is routinely one year ahead of the
#: newest population estimate and holding the denominator for that one year is the
#: honest choice. Two years is not a publication lag, it is a stale index, and the
#: run should stop and wait for ONS rather than quietly compound the error.
MAX_POPULATION_VINTAGE_LAG = 1

#: The age-restricted denominators QOF measures prevalence against, as
#: `PATIENT_LIST_TYPE` label -> lowest qualifying age. Asthma 6+, rheumatoid
#: arthritis 16+, diabetes 17+, chronic kidney disease / depression / epilepsy /
#: non-diabetic hyperglycaemia / obesity 18+, osteoporosis 50+.
#:
#: The ADI divides every condition by the all-ages practice list, so its
#: osteoporosis rate is 0.450% against NHS England's published 1.198%. The level
#: error is not the worst of it: deprived neighbourhoods are child-heavy, so an
#: all-ages denominator deflates their rate more than an affluent area's, and the
#: index's own health-deprivation gradient comes out attenuated (#42).
#:
#: `MAKE|<label>|<codes>` has Nomis sum single years of age server-side, so each
#: band is an exact total of published cells rather than an approximation --
#: verified as integer identities, e.g. 16+ composed this way equals Nomis's own
#: published "Aged 16+" code 202 exactly.
QOF_AGE_BANDS = {"06OV": 6, "16OV": 16, "17OV": 17, "18OV": 18, "50OV": 50}

#: Nomis `c_age` code for a single year of age: 101 is age 0, so age `a` is
#: `101 + a`. 191 is the open-ended top code, "Aged 90+".
AGE_CODE_BASE = 101
AGE_CODE_90_PLUS = 191

#: Label Nomis gives the all-ages total (`c_age=200`), which every band file
#: carries alongside the bands so it can be reconciled against the plain
#: population file.
ALL_AGES_LABEL = "All Ages"


class PopulationBandError(RuntimeError):
    """A population band file is not the shape an age denominator has to be.

    The bands are nested by construction -- everyone aged 18+ is also aged 17+ --
    so any violation means the `MAKE` expression did not mean what it was supposed
    to, and a denominator built from it would be wrong in a way no downstream
    check could attribute.
    """


class PopulationVintageError(RuntimeError):
    """A population file does not hold the year it is named for.

    Nomis does not reject a `date` outside a dataset's range: asked for 2025 it
    answers 200 OK with the 2024 estimate, and the rows carry `DATE_NAME=2024`
    while the caller believes it received 2025. Writing that response to
    `population_2025.csv` produces a file whose name and contents disagree, and
    every consumer downstream reads only GEOGRAPHY_CODE and OBS_VALUE, so nothing
    notices. That is the failure this exception exists to make loud.
    """


def _population_dataset(geography_type: str) -> str:
    """Nomis dataset id for an LSOA geography vintage."""
    if geography_type not in POPULATION_DATASETS:
        raise ValueError(
            f"No population dataset known for geography {geography_type!r}. "
            f"Known: {sorted(POPULATION_DATASETS)}."
        )
    return POPULATION_DATASETS[geography_type]


def band_c_age() -> str:
    """The `c_age` query that returns the all-ages total and every QOF band.

    One request, six series: `200` for the all-ages total plus a `MAKE` per band
    summing the single-year codes from its lowest qualifying age to the 90+ top
    code. Composed from `QOF_AGE_BANDS` rather than written out, so a band added
    there cannot arrive with a hand-typed code range that is off by one.
    """
    parts = ["200"]
    for label, min_age in sorted(QOF_AGE_BANDS.items(), key=lambda kv: kv[1]):
        parts.append(f"MAKE|{label}|{AGE_CODE_BASE + min_age}...{AGE_CODE_90_PLUS}")
    return ",".join(parts)


#: The six series every band file must carry, widest first. Nesting is checked
#: along this order: each band is a subset of the one before it, so the counts
#: must not increase.
BAND_SERIES = [ALL_AGES_LABEL] + sorted(QOF_AGE_BANDS, key=QOF_AGE_BANDS.get)


def population_bands_filename(year: int, geography_type: str) -> str:
    """File name for one year of banded population.

    Named for the dataset and geography as well as the year, because both LSOA
    vintages live in one directory: the LSOA 2011 bands weight the crosswalk's
    merge rows and the LSOA 2021 bands are the published denominator, and the two
    are not interchangeable.
    """
    return f"{_population_dataset(geography_type)}_{geography_type}_{year}.csv"


def validate_population_bands(df: pd.DataFrame, source: str) -> dict:
    """Check a banded population frame is usable as a denominator, or raise.

    Three things have to hold, and all three are free to check:

    * every geography carries all six series -- a missing band would otherwise
      become a missing denominator for one condition in one place;
    * no count is negative;
    * the bands nest. All Ages >= 6+ >= 16+ >= 17+ >= 18+ >= 50+ is true of the
      populations by definition, so a violation means the `MAKE` expression
      returned something other than the age range asked for.

    Returns a summary (row and geography counts, per-band minimum and total) for
    the caller to log; the minima matter because a band population of a handful of
    people makes a modelled count meaningless even where the rate is sound.
    """
    missing_cols = [c for c in ("GEOGRAPHY_CODE", "DATE_NAME", "C_AGE_NAME", "OBS_VALUE")
                    if c not in df.columns]
    if missing_cols:
        raise PopulationBandError(f"{source}: missing column(s) {missing_cols}.")

    unexpected = sorted(set(df["C_AGE_NAME"].unique()) - set(BAND_SERIES))
    if unexpected:
        raise PopulationBandError(
            f"{source}: unexpected age series {unexpected}. Expected exactly {BAND_SERIES}."
        )

    wide = df.pivot(index="GEOGRAPHY_CODE", columns="C_AGE_NAME", values="OBS_VALUE")
    absent = [s for s in BAND_SERIES if s not in wide.columns]
    if absent:
        raise PopulationBandError(f"{source}: no rows for age series {absent}.")
    wide = wide[BAND_SERIES]

    gaps = int(wide.isna().to_numpy().sum())
    if gaps:
        incomplete = wide.index[wide.isna().any(axis=1)][:5].tolist()
        raise PopulationBandError(
            f"{source}: {gaps} missing band value(s) across "
            f"{int(wide.isna().any(axis=1).sum())} geographies (e.g. {incomplete}). "
            f"Every geography must carry all {len(BAND_SERIES)} series."
        )

    negative = int((wide < 0).to_numpy().sum())
    if negative:
        raise PopulationBandError(f"{source}: {negative} negative population value(s).")

    for wider, narrower in zip(BAND_SERIES, BAND_SERIES[1:]):
        bad = wide.index[wide[wider] < wide[narrower]]
        if len(bad):
            example = bad[0]
            raise PopulationBandError(
                f"{source}: {len(bad)} geographies where {wider} < {narrower}, which "
                f"cannot be true of nested age bands (e.g. {example}: "
                f"{wider}={wide.at[example, wider]}, {narrower}={wide.at[example, narrower]}). "
                f"The MAKE expression did not return the age range it was asked for."
            )

    # A band CAN legitimately be zero -- two student-heavy LSOAs had no residents
    # aged 50+ at all in 2021 -- so this is reported, not rejected. It is reported
    # because a zero denominator makes that condition's rate undefined for that
    # area, and the consumer needs to meet that as a stated fact rather than as an
    # inf appearing in an output file.
    zero_bands = [(code, s) for s in BAND_SERIES
                  for code in wide.index[wide[s] == 0]]

    return {
        "rows": len(df),
        "geographies": len(wide),
        "totals": {s: int(wide[s].sum()) for s in BAND_SERIES},
        "minima": {s: int(wide[s].min()) for s in BAND_SERIES},
        "zero_bands": zero_bands,
    }


def _report_band_summary(summary: dict, label: str, print=print) -> None:
    """Say what a band file holds, and flag any zero denominator in it."""
    tightest = min(QOF_AGE_BANDS, key=lambda b: summary["minima"][b])
    print(f"  {label}: {summary['geographies']} geographies x {len(BAND_SERIES)} series; "
          f"smallest band population {summary['minima'][tightest]} ({tightest})")
    if summary["zero_bands"]:
        shown = ", ".join(f"{code} {band}" for code, band in summary["zero_bands"][:5])
        print(f"  {label}: WARNING -- {len(summary['zero_bands'])} area(s) have a zero "
              f"band population ({shown}). Any rate against that band is undefined there.")


def _years_in(df: pd.DataFrame) -> list[int]:
    """The reference years a Nomis population response actually carries."""
    if "DATE_NAME" not in df.columns:
        raise PopulationVintageError(
            "Nomis population response has no DATE_NAME column, so the year it "
            "describes cannot be checked. Refusing to save it."
        )
    return sorted({int(v) for v in df["DATE_NAME"].unique()})


async def latest_population_year(
    geography_type: str = "TYPE151",
    print=print,
) -> int:
    """Last reference year the Nomis population series actually holds.

    Read from the dataset's own time dimension rather than hardcoded, because the
    two series end in different places and both move: NM_2014_1 (LSOA 2021) runs
    to 2024 and NM_2010_1 (LSOA 2011) stops at 2020. Asking removes a constant
    that would otherwise have to be edited every time ONS publishes.
    """
    dataset_id = _population_dataset(geography_type)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{NOMIS_API_BASE}/{dataset_id}.overview.json")
        resp.raise_for_status()
        payload = resp.json()

    dimensions = payload["overview"]["dimensions"]["dimension"]
    if isinstance(dimensions, dict):  # Nomis unwraps single-element lists
        dimensions = [dimensions]
    time_dims = [d for d in dimensions if d.get("concept") == "time"]
    if not time_dims:
        raise PopulationVintageError(
            f"{dataset_id} overview has no time dimension, so the end of the "
            f"series cannot be established."
        )
    codes = time_dims[0]["codes"]["code"]
    if isinstance(codes, dict):
        codes = [codes]
    return max(int(c["name"]) for c in codes)


async def fetch_nomis_csv(
    dataset_id: str,
    params: dict[str, str],
    print=print,
) -> pd.DataFrame:
    """Paginated Nomis REST API CSV query.

    Args:
        dataset_id: Nomis dataset ID (e.g. "NM_162_1").
        params: Query parameters (geography, date, gender, etc.).
        print: Print function for progress.

    Returns:
        DataFrame with all paginated results concatenated.
    """
    url = f"{NOMIS_API_BASE}/{dataset_id}.data.csv"
    all_frames = []
    offset = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            page_params = {**params, "RecordLimit": str(PAGE_SIZE), "RecordOffset": str(offset)}
            resp = await client.get(url, params=page_params)
            resp.raise_for_status()

            df = pd.read_csv(io.StringIO(resp.text))
            if df.empty:
                break

            all_frames.append(df)
            if len(df) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            print(f"  paginating: {offset} rows fetched so far...")

    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


async def fetch_claimant_counts_for_date(
    date: str,
    geography_type: str = "TYPE151",
    print=print,
) -> pd.DataFrame:
    """Fetch claimant counts for a specific month at LSOA level.

    Args:
        date: Month in YYYY-MM format (e.g. "2024-01").
        geography_type: "TYPE151" for LSOA 2021, "TYPE298" for 2011.

    Returns:
        DataFrame with columns: GEOGRAPHY_CODE, GEOGRAPHY_NAME, DATE_NAME, OBS_VALUE.
    """
    params = {
        "geography": geography_type,
        "date": date,
        "gender": "0",
        "age": "0",
        "measure": "1",
        "measures": "20100",
        "select": "GEOGRAPHY_CODE,GEOGRAPHY_NAME,DATE_NAME,OBS_VALUE",
    }
    return await fetch_nomis_csv("NM_162_1", params, print=print)


async def fetch_population_for_year(
    year: int,
    geography_type: str = "TYPE151",
    c_age: str = "200",
    print=print,
) -> pd.DataFrame:
    """Fetch mid-year LSOA population estimates for a specific year.

    Args:
        year: Calendar year (e.g. 2024).
        geography_type: "TYPE151" for LSOA 2021, "TYPE298" for LSOA 2011.
        c_age: Age group code. "200" = all ages, "202" = 16+.

    Returns:
        DataFrame with columns: GEOGRAPHY_CODE, GEOGRAPHY_NAME, DATE_NAME, OBS_VALUE.
    """
    dataset_id = _population_dataset(geography_type)
    params = {
        "geography": geography_type,
        "date": str(year),
        "gender": "0",
        "c_age": c_age,
        "measures": "20100",
        "select": "GEOGRAPHY_CODE,GEOGRAPHY_NAME,DATE_NAME,OBS_VALUE",
    }
    return await fetch_nomis_csv(dataset_id, params, print=print)


async def _fetch_and_save_population(
    year: int,
    out_path: Path,
    geography_type: str,
    print=print,
) -> None:
    """Fetch and save one year of population data, or refuse to.

    The response must carry the year that was asked for. Nomis answers an
    out-of-range `date` with its newest estimate instead of an error, so this is
    the only place the substitution can be caught before it becomes a file whose
    name lies about its contents.
    """
    print(f"  population {year}: fetching from Nomis...")
    df = await fetch_population_for_year(year, geography_type, print=print)
    if df.empty:
        raise PopulationVintageError(
            f"Nomis returned no {geography_type} population rows for {year}. "
            f"Not writing {out_path.name}: an absent file is recoverable, an "
            f"empty one is a silent hole in every rate for that year."
        )

    observed = _years_in(df)
    if observed != [year]:
        raise PopulationVintageError(
            f"Asked Nomis for the {year} {geography_type} population and it "
            f"returned {observed}. Refusing to save that as {out_path.name}, "
            f"which would publish {observed} data under a {year} label."
        )

    df.to_csv(out_path, index=False)
    print(f"  population {year}: {len(df)} LSOAs saved")


def _check_saved_vintage(out_path: Path, expected_year: int, print=print) -> None:
    """A file already on disk must hold the year the policy says it should.

    Skipping an existing file is what let a wrong-year download survive every
    later run of this node, so the skip now costs one read of one column.
    """
    observed = _years_in(pd.read_csv(out_path, usecols=["DATE_NAME"]))
    if observed != [expected_year]:
        raise PopulationVintageError(
            f"{out_path.name} holds {observed} where {expected_year} was expected. "
            f"Delete it and re-run this node; do not publish rates against it."
        )


async def fetch_population_bands_for_year(
    year: int,
    geography_type: str = "TYPE151",
    print=print,
) -> pd.DataFrame:
    """Fetch one year of LSOA population split into the QOF age bands.

    Same datasets, geography and year semantics as `fetch_population_for_year`;
    only `c_age` differs. `GEOGRAPHY_NAME` is not selected -- six rows per LSOA
    would repeat it six times for no gain, and the code is the join key.

    Returns:
        DataFrame with columns: GEOGRAPHY_CODE, DATE_NAME, C_AGE_NAME, OBS_VALUE,
        six rows per geography.
    """
    dataset_id = _population_dataset(geography_type)
    params = {
        "geography": geography_type,
        "date": str(year),
        "gender": "0",
        "c_age": band_c_age(),
        "measures": "20100",
        "select": "GEOGRAPHY_CODE,DATE_NAME,C_AGE_NAME,OBS_VALUE",
    }
    return await fetch_nomis_csv(dataset_id, params, print=print)


async def _fetch_and_save_population_bands(
    year: int,
    out_path: Path,
    geography_type: str,
    print=print,
) -> None:
    """Fetch and save one year of banded population, or refuse to.

    The vintage guard is the same one the all-ages fetch uses, because the failure
    modes are the same: NM_2014_1 asked for 2025 answers 200 OK with 2024 rows,
    NM_2010_1 asked for 2021 answers 200 OK with an empty body. On top of that the
    band structure is checked before anything is written.
    """
    print(f"  population bands {year}: fetching {len(BAND_SERIES)} series from Nomis...")
    df = await fetch_population_bands_for_year(year, geography_type, print=print)
    if df.empty:
        raise PopulationVintageError(
            f"Nomis returned no {geography_type} banded population rows for {year}. "
            f"Not writing {out_path.name}: an absent file is recoverable, an "
            f"empty one is a silent hole in every age-restricted rate for that year."
        )

    observed = _years_in(df)
    if observed != [year]:
        raise PopulationVintageError(
            f"Asked Nomis for the {year} {geography_type} banded population and it "
            f"returned {observed}. Refusing to save that as {out_path.name}, "
            f"which would publish {observed} data under a {year} label."
        )

    summary = validate_population_bands(df, out_path.name)
    df.to_csv(out_path, index=False)
    _report_band_summary(summary, f"population bands {year}", print=print)


def _check_saved_bands(out_path: Path, expected_year: int, print=print) -> None:
    """Re-check a band file already on disk: right year, and still nested.

    Full structural validation, not just the vintage, and on every run rather than
    only on download. It costs about a sixth of a second per file and it is the
    only thing standing between a hand-placed or half-written cache file and a
    silently wrong denominator for one condition.
    """
    df = pd.read_csv(out_path)
    observed = _years_in(df)
    if observed != [expected_year]:
        raise PopulationVintageError(
            f"{out_path.name} holds {observed} where {expected_year} was expected. "
            f"Delete it and re-run this node; do not publish rates against it."
        )
    _report_band_summary(validate_population_bands(df, out_path.name),
                         f"population bands {expected_year}", print=print)


async def _download_population_series(
    output_dir: Path,
    year_start: int,
    year_end: int,
    geography_type: str,
    beyond_series: str,
    label: str,
    filename,
    fetch_and_save,
    check_existing,
    print=print,
) -> None:
    """Download one per-year population series, whatever its shape.

    The all-ages population and the age-banded population differ only in the query
    and the file name; the policy for years the series does not reach is identical,
    because the API behaves identically. It lives here once rather than in each
    caller, so the two cannot drift apart -- silent divergence between two copies
    of this policy is how the wrong-year 2025 file survived in the first place.

    Args:
        output_dir: Directory to write per-year files into.
        year_start: First year to request (inclusive).
        year_end: Last year to request (inclusive).
        geography_type: "TYPE151" for LSOA 2021, "TYPE298" for LSOA 2011.
        beyond_series: Policy for years past the end of the series -- see
            `download_populations`.
        label: What to call these files in progress output.
        filename: `year -> file name` within `output_dir`.
        fetch_and_save: `(year, out_path, geography_type, print)` coroutine that
            fetches one year and writes it, or raises rather than write.
        check_existing: `(out_path, expected_year, print)` validator for a file
            already on disk.
        print: Progress printer.
    """
    if beyond_series not in ("fail", "substitute", "skip"):
        raise ValueError(
            f"beyond_series must be 'fail', 'substitute' or 'skip', not {beyond_series!r}."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_id = _population_dataset(geography_type)
    latest = await latest_population_year(geography_type, print=print)
    print(f"  {dataset_id} ({geography_type}) publishes to {latest}")

    tasks = []
    substitutions = []
    for year in range(year_start, year_end + 1):
        out_path = output_dir / filename(year)
        # Which year this file is supposed to hold: itself, or -- where the
        # series has not reached it and substitution is allowed -- the last year
        # that was published.
        held_year = year if year <= latest else latest

        if year > latest:
            if beyond_series == "skip":
                print(f"  {label} {year}: past the end of {dataset_id}, not fetched")
                continue
            if beyond_series == "fail":
                raise PopulationVintageError(
                    f"{dataset_id} publishes to {latest}, so there is no {year} "
                    f"population estimate to download. Nomis would answer this "
                    f"request with {latest} data; refusing to accept it."
                )
            lag = year - latest
            if lag > MAX_POPULATION_VINTAGE_LAG:
                raise PopulationVintageError(
                    f"{year} is {lag} years past the end of {dataset_id} ({latest}). "
                    f"At most {MAX_POPULATION_VINTAGE_LAG} year may be published "
                    f"against the previous estimate; beyond that the denominator is "
                    f"too stale to stand behind. Wait for ONS or lower year_end."
                )

        if out_path.exists():
            check_existing(out_path, held_year, print=print)
            print(f"  {label} {year}: already exists ({held_year} estimate), skipping")
            continue

        if year <= latest:
            tasks.append(fetch_and_save(year, out_path, geography_type, print=print))
        else:
            substitutions.append((year, latest, out_path))

    if tasks:
        await asyncio.gather(*tasks)

    # After the downloads: a substitution may be copying a year fetched above.
    for year, source_year, out_path in substitutions:
        source = output_dir / filename(source_year)
        if not source.exists():
            raise PopulationVintageError(
                f"Cannot stand {year} on the {source_year} estimate: "
                f"{source.name} was not downloaded."
            )
        shutil.copyfile(source, out_path)
        print(f"  {label} {year}: NOT PUBLISHED by {dataset_id} (ends {source_year}); "
              f"copied the {source_year} estimate, rows keep DATE_NAME={source_year}")


async def download_populations(
    output_dir: Path,
    year_start: int,
    year_end: int,
    geography_type: str = "TYPE151",
    beyond_series: str = "fail",
    print=print,
) -> None:
    """Download all-ages population estimates for a range of years, in parallel.

    Saves one CSV per year to output_dir/population_{year}.csv. A year already on
    disk is not re-downloaded, but its vintage is re-checked.

    `beyond_series` decides what happens to a requested year the Nomis series does
    not reach yet. There is deliberately no option that lets one pass silently:

    * `"fail"` -- raise. The default, because a missing population year is a real
      problem and the caller should have to say otherwise.
    * `"substitute"` -- copy the last published year forward, up to
      `MAX_POPULATION_VINTAGE_LAG` years, and say so. The copy keeps its original
      `DATE_NAME`, so the file still states which year it holds. This is the ADI's
      standing policy for the LSOA 2021 series, whose newest estimate is always
      about a year behind the newest claimant and crime data.
    * `"skip"` -- do not fetch and do not invent. For the LSOA 2011 series, which
      ends in 2020: the domain processors handle later years explicitly, and
      materialising copies here would silently pre-empt that.

    Args:
        output_dir: Directory to write population_{year}.csv into.
        year_start: First year to request (inclusive).
        year_end: Last year to request (inclusive).
        geography_type: "TYPE151" for LSOA 2021, "TYPE298" for LSOA 2011.
        beyond_series: Policy for years past the end of the series, as above.
        print: Progress printer.
    """
    await _download_population_series(
        output_dir, year_start, year_end, geography_type, beyond_series,
        label="population",
        filename=lambda y: f"population_{y}.csv",
        fetch_and_save=_fetch_and_save_population,
        check_existing=_check_saved_vintage,
        print=print,
    )


async def download_population_bands(
    output_dir: Path,
    year_start: int,
    year_end: int,
    geography_type: str = "TYPE151",
    beyond_series: str = "fail",
    print=print,
) -> None:
    """Download QOF-banded population estimates for a range of years, in parallel.

    Saves one CSV per year to output_dir/{dataset}_{geography}_{year}.csv, each
    holding the all-ages total and the five QOF age bands. Both LSOA vintages
    share the directory; the file name says which is which.

    Same years, same datasets and the same `beyond_series` policy as
    `download_populations` -- these are the same two Nomis series with one query
    parameter changed, so the coverage is identical and no new year gap opens. A
    year already on disk is not re-downloaded, but it is re-validated: right year,
    all six series present, and the bands still nested.
    """
    await _download_population_series(
        output_dir, year_start, year_end, geography_type, beyond_series,
        label="population bands",
        filename=lambda y: population_bands_filename(y, geography_type),
        fetch_and_save=_fetch_and_save_population_bands,
        check_existing=_check_saved_bands,
        print=print,
    )


async def _fetch_and_save_claimant_counts(
    year: int,
    out_path: Path,
    geography_type: str,
    print=print,
) -> None:
    """Fetch and save claimant count data for a single year (all 12 months)."""
    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    date_str = ",".join(months)

    print(f"  claimant counts {year}: fetching 12 months from Nomis...")
    params = {
        "geography": geography_type,
        "date": date_str,
        "gender": "0",
        "age": "0",
        "measure": "1",
        "measures": "20100",
        "select": "GEOGRAPHY_CODE,GEOGRAPHY_NAME,DATE_NAME,OBS_VALUE",
    }
    df = await fetch_nomis_csv("NM_162_1", params, print=print)
    if df.empty:
        print(f"  claimant counts {year}: no data available")
        return
    df.to_csv(out_path, index=False)
    n_lsoas = df["GEOGRAPHY_CODE"].nunique()
    n_months = df["DATE_NAME"].nunique()
    print(f"  claimant counts {year}: {n_lsoas} LSOAs x {n_months} months saved")


async def download_claimant_counts(
    output_dir: Path,
    year_start: int,
    year_end: int,
    geography_type: str = "TYPE151",
    print=print,
) -> None:
    """Download monthly claimant counts for a range of years, in parallel.

    Saves one CSV per year to output_dir/claimant_counts_{year}.csv,
    containing all months for that year.
    Skips years where the file already exists.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for year in range(year_start, year_end + 1):
        out_path = output_dir / f"claimant_counts_{year}.csv"
        if out_path.exists():
            print(f"  claimant counts {year}: already exists, skipping")
            continue
        tasks.append(_fetch_and_save_claimant_counts(year, out_path, geography_type, print=print))

    if tasks:
        await asyncio.gather(*tasks)
