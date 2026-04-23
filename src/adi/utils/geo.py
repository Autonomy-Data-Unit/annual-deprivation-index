"""Spatial utilities for LSOA-GP intersection and LSOA vintage crosswalk."""

import numpy as np
import pandas as pd
import geopandas as gpd


def compute_spherical_area(polygon, radius: float = 6_378_137.0) -> float:
    """Compute area of a geographic polygon using spherical geometry.

    Uses Green's Theorem on a sphere. Handles MultiPolygon and
    polygons with interior rings (holes).

    Args:
        polygon: A shapely Polygon or MultiPolygon in lat/lon coordinates.
        radius: Earth radius in metres.

    Returns:
        Area in square metres.
    """
    raise NotImplementedError


def compute_intersection_weights(
    lsoa_gdf: gpd.GeoDataFrame,
    gp_gdf: gpd.GeoDataFrame,
    max_gps: int = 2000,
) -> np.ndarray:
    """Compute LSOA-GP spatial intersection weights.

    For each LSOA, finds the nearest GP catchment areas by centroid
    distance (Mercator projection), computes geometric intersection areas,
    and returns a sparse weights array.

    Args:
        lsoa_gdf: LSOA boundary geometries.
        gp_gdf: GP catchment area geometries.
        max_gps: Maximum number of GP catchment areas to consider per LSOA.

    Returns:
        Numpy array of intersection weights, cacheable as .npy.
    """
    raise NotImplementedError


def fill_missing_lsoas_from_neighbours(
    gdf: gpd.GeoDataFrame,
    value_cols: list[str],
) -> gpd.GeoDataFrame:
    """Fill LSOAs with no GP overlap using spatial neighbour averaging.

    Iteratively assigns the average prevalence of spatially adjacent
    LSOAs until all LSOAs have values.

    Args:
        gdf: GeoDataFrame with LSOA geometries and value columns.
        value_cols: Column names to fill.

    Returns:
        GeoDataFrame with filled values.
    """
    raise NotImplementedError


def build_crosswalk(
    oa11_to_oa21: pd.DataFrame,
    oa11_to_lsoa11: pd.DataFrame,
    oa21_to_lsoa21: pd.DataFrame,
    oa_populations: pd.DataFrame,
) -> pd.DataFrame:
    """Build OA-level population-weighted crosswalk between LSOA vintages.

    Traces LSOA11 -> constituent OA11s -> corresponding OA21s -> containing
    LSOA21s, weighting by OA population.

    Args:
        oa11_to_oa21: OA 2011 to OA 2021 exact-fit lookup.
        oa11_to_lsoa11: OA 2011 to LSOA 2011 membership lookup.
        oa21_to_lsoa21: OA 2021 to LSOA 2021 membership lookup.
        oa_populations: OA-level population estimates.

    Returns:
        DataFrame with columns [source_lsoa, target_lsoa, weight].
        Weights sum to 1.0 per source LSOA.
    """
    raise NotImplementedError


def apply_crosswalk(
    df: pd.DataFrame,
    crosswalk: pd.DataFrame,
    count_cols: list[str],
    pop_col: str,
    lsoa_col: str,
) -> pd.DataFrame:
    """Apply crosswalk to convert data between LSOA vintages.

    Disaggregates absolute counts using population weights, then
    reaggregates to target LSOAs. Rates are recomputed from
    disaggregated numerators and denominators.

    Args:
        df: Source data with LSOA codes and count columns.
        crosswalk: Crosswalk table from build_crosswalk().
        count_cols: Column names containing absolute counts to disaggregate.
        pop_col: Column name for population (also disaggregated).
        lsoa_col: Column name for LSOA codes.

    Returns:
        DataFrame with target LSOA codes and converted values.
    """
    raise NotImplementedError
