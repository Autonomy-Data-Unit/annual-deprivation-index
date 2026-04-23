"""ONS Open Geography Portal ArcGIS REST API client.

No authentication required. Paginate at 2,000 records per request.
"""

import asyncio
import json
from pathlib import Path

import httpx
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape

ARCGIS_BASE = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
PAGE_SIZE = 2000

# Service names for key datasets
LSOA_BOUNDARY_SERVICES = {
    "2021": "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5",
    "2011": "LSOA_Dec_2011_Boundaries_Generalised_Clipped_BGC_EW_V3",
}
LSOA_TO_LAD_SERVICE = "LSOA21_WD25_LAD25_EW_LU_v2"
LAD_TO_RGN_SERVICE = "LAD25_RGN25_EN_LU_v2"
LSOA_CROSSWALK_SERVICE = "LSOA11_LSOA21_LAD22_EW_LU_v5"
OA_CROSSWALK_SERVICE = "OA11_OA21_LAD22_EW_LU_Exact_fit_V3"
OA_TO_LSOA21_SERVICE = "OA_LSOA_MSOA_EW_DEC_2021_LU_v3"


async def fetch_arcgis_records(
    service_name: str,
    out_fields: str = "*",
    where: str = "1=1",
    return_geometry: bool = False,
    out_sr: int = 4326,
    print=print,
) -> list[dict]:
    """Paginated ArcGIS REST API query returning raw feature records.

    Args:
        service_name: ArcGIS FeatureServer service name.
        out_fields: Comma-separated field names or "*".
        where: SQL where clause.
        return_geometry: Whether to include geometry.
        out_sr: Output spatial reference.

    Returns:
        List of feature dicts (with 'attributes' and optionally 'geometry').
    """
    url = f"{ARCGIS_BASE}/{service_name}/FeatureServer/0/query"
    all_features = []
    offset = 0

    async with httpx.AsyncClient(timeout=120) as client:
        while True:
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": str(return_geometry).lower(),
                "outSR": str(out_sr),
                "f": "json",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            exceeded = data.get("exceededTransferLimit", False)
            if not exceeded:
                break

            offset += len(features)
            print(f"  paginating {service_name}: {len(all_features)} records...")

    return all_features


async def fetch_lookup_table(
    service_name: str,
    print=print,
) -> pd.DataFrame:
    """Fetch a geographic lookup table as a DataFrame.

    Args:
        service_name: ArcGIS service name.

    Returns:
        DataFrame with lookup columns.
    """
    features = await fetch_arcgis_records(service_name, print=print)
    rows = [f["attributes"] for f in features]
    df = pd.DataFrame(rows)
    print(f"  {service_name}: {len(df)} records")
    return df


async def fetch_boundaries(
    service_name: str,
    print=print,
) -> gpd.GeoDataFrame:
    """Fetch LSOA boundary geometries as a GeoDataFrame.

    Args:
        service_name: ArcGIS service name for boundary data.

    Returns:
        GeoDataFrame with boundary polygons in WGS84.
    """
    url = f"{ARCGIS_BASE}/{service_name}/FeatureServer/0/query"
    all_features = []
    offset = 0

    async with httpx.AsyncClient(timeout=120) as client:
        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
            }
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)

            exceeded = data.get("properties", {}).get("exceededTransferLimit", False)
            if not exceeded and not data.get("exceededTransferLimit", False):
                break

            offset += len(features)
            print(f"  paginating boundaries: {len(all_features)} features...")

    geojson = {"type": "FeatureCollection", "features": all_features}
    gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")
    print(f"  {service_name}: {len(gdf)} features")
    return gdf


async def download_geo_data(
    output_dir: Path,
    lsoa_vintage: str,
    print=print,
) -> None:
    """Download all geographic reference data (boundaries, lookups, crosswalk).

    Args:
        output_dir: Base directory for geo data (store/inputs/).
        lsoa_vintage: "2021" or "2011".
    """
    boundaries_dir = output_dir / "lsoa_boundaries"
    lookups_dir = output_dir / "geo_lookups"
    crosswalk_dir = output_dir / "crosswalk"

    for d in [boundaries_dir, lookups_dir, crosswalk_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # LSOA boundaries
    boundary_path = boundaries_dir / f"lsoa_{lsoa_vintage}_bgc.geojson"
    if not boundary_path.exists():
        service = LSOA_BOUNDARY_SERVICES[lsoa_vintage]
        print(f"  fetching LSOA {lsoa_vintage} boundaries...")
        gdf = await fetch_boundaries(service, print=print)
        gdf.to_file(boundary_path, driver="GeoJSON")
        print(f"  saved {boundary_path.name}")
    else:
        print(f"  LSOA {lsoa_vintage} boundaries: already exists")

    # Download lookup tables and crosswalk data in parallel
    async def _fetch_and_save(path, service, label):
        if path.exists():
            print(f"  {label}: already exists")
            return
        print(f"  fetching {label}...")
        df = await fetch_lookup_table(service, print=print)
        df.to_csv(path, index=False)

    await asyncio.gather(
        _fetch_and_save(lookups_dir / "lsoa21_to_lad25.csv", LSOA_TO_LAD_SERVICE, "LSOA-to-LAD lookup"),
        _fetch_and_save(lookups_dir / "lad25_to_rgn25.csv", LAD_TO_RGN_SERVICE, "LAD-to-Region lookup"),
        _fetch_and_save(crosswalk_dir / "lsoa11_to_lsoa21.csv", LSOA_CROSSWALK_SERVICE, "LSOA crosswalk"),
        _fetch_and_save(crosswalk_dir / "oa11_to_oa21.csv", OA_CROSSWALK_SERVICE, "OA crosswalk"),
        _fetch_and_save(crosswalk_dir / "oa21_to_lsoa21.csv", OA_TO_LSOA21_SERVICE, "OA-to-LSOA 2021 lookup"),
    )
