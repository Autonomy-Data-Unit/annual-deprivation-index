"""QOF data parsing across year formats.

Reads the QOF schema config (config/qof_schemas.toml) and uses it to
normalise raw QOF prevalence data from different years into a consistent
wide-format schema: practice_code, list_pop, {disease_col_1}, {disease_col_2}, ...
"""

import tomllib
from pathlib import Path

import pandas as pd


def load_qof_schemas(schemas_path: Path) -> dict:
    """Load QOF column mapping config from TOML file.

    Args:
        schemas_path: Path to config/qof_schemas.toml.

    Returns:
        Dict with year keys mapping to schema definitions.
    """
    with open(schemas_path, "rb") as f:
        return tomllib.load(f)["years"]


def normalise_qof(raw_path: Path, year_key: str, schema: dict) -> pd.DataFrame:
    """Parse and normalise a raw QOF prevalence file into standardised wide format.

    Reads the raw file using the column mapping from the schema config,
    pivots from long format (one row per practice-per-disease) to wide
    format (one row per practice, columns = disease group codes).

    Args:
        raw_path: Path to the raw prevalence CSV/Excel file.
        year_key: Year key in the schema config (e.g. "2013_14").
        schema: Schema dict for this year (from load_qof_schemas()).

    Returns:
        DataFrame with columns: practice_code, list_pop, and one column
        per disease group code containing the register count.
    """
    raise NotImplementedError
