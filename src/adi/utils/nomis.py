"""Nomis REST API client for claimant counts and population estimates.

No authentication required (anonymous guest). 25,000 cell limit per request;
queries must paginate via RecordLimit and RecordOffset parameters.

Key datasets:
- NM_162_1: Claimant count by sex and age (supports LSOA 2021 via TYPE151)
- NM_2010_1: Population estimates, small area, 2011-based (LSOA 2011, TYPE298)
- NM_2014_1: Population estimates, small area, 2021-based (LSOA 2021, TYPE151)
"""

import pandas as pd

NOMIS_API_BASE = "https://www.nomisweb.co.uk/api/v01/dataset"


async def fetch_nomis_data(
    dataset_id: str,
    geography_type: str,
    select: str,
    **params: str,
) -> pd.DataFrame:
    """Generic paginated Nomis REST API query.

    Args:
        dataset_id: Nomis dataset ID (e.g. "NM_162_1").
        geography_type: Geography type code (e.g. "TYPE151" for LSOA 2021).
        select: Comma-separated column names to return.
        **params: Additional query parameters (e.g. date, gender, age, measure).

    Returns:
        DataFrame with all paginated results concatenated.
    """
    raise NotImplementedError


async def fetch_claimant_counts(year: int, lsoa_type: str = "TYPE151") -> pd.DataFrame:
    """Fetch Universal Credit claimant counts for a given year at LSOA level.

    Args:
        year: Calendar year.
        lsoa_type: Nomis geography type ("TYPE151" for LSOA 2021, "TYPE298" for 2011).

    Returns:
        DataFrame with columns: geography_code, geography_name, date_name, obs_value.
    """
    raise NotImplementedError


async def fetch_lsoa_populations(
    dataset_id: str = "NM_2014_1",
    geography_type: str = "TYPE151",
) -> pd.DataFrame:
    """Fetch mid-year LSOA population estimates.

    Args:
        dataset_id: "NM_2014_1" for 2021-based, "NM_2010_1" for 2011-based.
        geography_type: "TYPE151" for LSOA 2021, "TYPE298" for LSOA 2011.

    Returns:
        DataFrame with per-LSOA population estimates.
    """
    raise NotImplementedError
