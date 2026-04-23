"""ONS Open Geography Portal ArcGIS REST API client.

No authentication required. Paginate at 2,000 records per request.

Key services:
- LSOA 2021 boundaries (BGC): Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5
- LSOA 2011 boundaries (BGC): LSOA_Dec_2011_Boundaries_Generalised_Clipped_BGC_EW_V3
- LSOA 2021 to LAD lookup: LSOA21_WD25_LAD25_EW_LU_v2
- LSOA exact-fit crosswalk: LSOA11_LSOA21_LAD22_EW_LU_v5
- OA exact-fit crosswalk: OA11_OA21_LAD22_EW_LU_Exact_fit_V3
- OA to LSOA 2021: OA_LSOA_MSOA_EW_DEC_2021_LU_v3
"""

import pandas as pd
import geopandas as gpd

ARCGIS_BASE = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"


async def fetch_arcgis_features(
    service_name: str,
    out_fields: str = "*",
    out_sr: int = 4326,
    batch_size: int = 2000,
    return_geometry: bool = False,
) -> pd.DataFrame | gpd.GeoDataFrame:
    """Generic paginated ArcGIS REST API query.

    Args:
        service_name: Name of the ArcGIS FeatureServer service.
        out_fields: Comma-separated field names, or "*" for all.
        out_sr: Output spatial reference (4326 = WGS84).
        batch_size: Records per page (max ~2000).
        return_geometry: If True, return GeoDataFrame with geometries.

    Returns:
        DataFrame or GeoDataFrame with all paginated results.
    """
    raise NotImplementedError


async def fetch_lsoa_boundaries(vintage: str = "2021") -> gpd.GeoDataFrame:
    """Fetch LSOA boundary geometries (Generalised Clipped version).

    Args:
        vintage: "2021" or "2011".

    Returns:
        GeoDataFrame with LSOA boundary polygons.
    """
    raise NotImplementedError


async def fetch_lookup_table(service_name: str) -> pd.DataFrame:
    """Fetch a geographic lookup table from ONS.

    Args:
        service_name: ArcGIS service name for the lookup table.

    Returns:
        DataFrame with lookup mappings.
    """
    raise NotImplementedError
