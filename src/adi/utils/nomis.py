"""Nomis REST API client for claimant counts and population estimates.

No authentication required. 25,000 row limit per CSV request;
must paginate via RecordLimit and RecordOffset parameters.
"""

import io
from pathlib import Path

import httpx
import pandas as pd

NOMIS_API_BASE = "https://www.nomisweb.co.uk/api/v01/dataset"
PAGE_SIZE = 25_000


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
    dataset_id = "NM_2014_1" if geography_type == "TYPE151" else "NM_2010_1"
    params = {
        "geography": geography_type,
        "date": str(year),
        "gender": "0",
        "c_age": c_age,
        "measures": "20100",
        "select": "GEOGRAPHY_CODE,GEOGRAPHY_NAME,DATE_NAME,OBS_VALUE",
    }
    return await fetch_nomis_csv(dataset_id, params, print=print)


async def download_populations(
    output_dir: Path,
    year_start: int,
    year_end: int,
    geography_type: str = "TYPE151",
    print=print,
) -> None:
    """Download population estimates for a range of years.

    Saves one CSV per year to output_dir/population_{year}.csv.
    Skips years where the file already exists.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for year in range(year_start, year_end + 1):
        out_path = output_dir / f"population_{year}.csv"
        if out_path.exists():
            print(f"  population {year}: already exists, skipping")
            continue

        print(f"  population {year}: fetching from Nomis...")
        df = await fetch_population_for_year(year, geography_type, print=print)
        if df.empty:
            print(f"  population {year}: no data available")
            continue

        df.to_csv(out_path, index=False)
        print(f"  population {year}: {len(df)} LSOAs saved")


async def download_claimant_counts(
    output_dir: Path,
    year_start: int,
    year_end: int,
    geography_type: str = "TYPE151",
    print=print,
) -> None:
    """Download monthly claimant counts for a range of years.

    Saves one CSV per year to output_dir/claimant_counts_{year}.csv,
    containing all months for that year.
    Skips years where the file already exists.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for year in range(year_start, year_end + 1):
        out_path = output_dir / f"claimant_counts_{year}.csv"
        if out_path.exists():
            print(f"  claimant counts {year}: already exists, skipping")
            continue

        # Fetch all 12 months for this year
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
            continue

        df.to_csv(out_path, index=False)
        n_lsoas = df["GEOGRAPHY_CODE"].nunique()
        n_months = df["DATE_NAME"].nunique()
        print(f"  claimant counts {year}: {n_lsoas} LSOAs x {n_months} months saved")
