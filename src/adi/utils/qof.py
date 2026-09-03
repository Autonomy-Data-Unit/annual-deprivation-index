"""QOF schema configuration utilities.

The QOF column mapping config lives in config/qof_schemas.toml and is
loaded directly by the process_health node. This module holds the QOF facts
more than one node needs.
"""

import tomllib
from pathlib import Path

import pandas as pd

from adi.utils.nomis import QOF_AGE_BANDS


def qof_age_bands(qof_schemas_path: Path, qof_raw_dir: Path,
                  year_key: str) -> dict[str, str]:
    """Which age band QOF measured each register against, for one QOF year.

    Returns `{disease_code: band_label}` — e.g. `{"OST": "50OV", "DEP": "18OV"}` —
    restricted to bands `QOF_AGE_BANDS` can supply a resident population for, and
    empty where the source has no age-restricted denominators at all.

    Two nodes need this fact and neither can infer it. `process_health` needs it to
    pick the right practice-level denominator for the RATE; `aggregate` needs it to
    pick the right LSOA-level resident population for the COUNT and for the
    aggregation weight. Getting it from two places that could disagree would mean
    dividing a register by one band and its own population by another, so it is
    read once, here, from the source's own labelling:

      * `PATIENT_LIST_TYPE` on the row, where the source has that column (2015-16 on);
      * the pinned `[years.<y>.list_types]` table, for 2014-15, which publishes
        correct per-group denominators without labelling them.

    Never inferred from the ratios at runtime, so a reissue in a different shape
    fails loudly rather than being silently re-derived.

    The mapping is not stable across years and must not be cached across them: AST
    is measured against the whole list through 2019-20 and against 6+ from 2020-21,
    OB moves from 16+ to 18+ after 2014-15, and NDH does not exist before 2020-21.

    Args:
        qof_schemas_path: config/qof_schemas.toml.
        qof_raw_dir: store/inputs/qof/raw, holding one directory per year key.
        year_key: QOF year directory name, e.g. "2022_23".

    Returns:
        `{disease_code: band_label}`, empty if this year has no age-restricted
        denominator (2013-14 published one all-ages list for every group).

    Raises:
        ValueError: the year is unknown, its prevalence file is missing, or a
            group carries more than one `PATIENT_LIST_TYPE`.
    """
    with open(qof_schemas_path, "rb") as f:
        schema = tomllib.load(f)["years"].get(year_key)
    if schema is None:
        raise ValueError(f"QOF {year_key}: no entry in {qof_schemas_path}.")

    # 2013-14 used one all-ages practice list for every group. The age-restricted
    # denominator is genuinely absent from the source, not merely unlabelled.
    if not schema.get("qof_age_denominators", True):
        return {}

    disease_col = schema["disease_code_col"]
    raw_path = qof_raw_dir / year_key / schema["file_pattern"]
    if not raw_path.exists():
        raise ValueError(
            f"QOF {year_key}: prevalence file not found at {raw_path}. The age band "
            f"each register is measured against can only be read from the source."
        )

    header = pd.read_csv(raw_path, encoding=schema.get("encoding", "utf-8"), nrows=0)
    if "PATIENT_LIST_TYPE" in header.columns:
        df = pd.read_csv(raw_path, encoding=schema.get("encoding", "utf-8"),
                         usecols=[disease_col, "PATIENT_LIST_TYPE"])
        pairs = (df.drop_duplicates()
                   .groupby(disease_col)["PATIENT_LIST_TYPE"].agg(set))
        mixed = {g: sorted(v) for g, v in pairs.items() if len(v) > 1}
        if mixed:
            raise ValueError(
                f"QOF {year_key}: these groups carry more than one PATIENT_LIST_TYPE "
                f"({mixed}); the band a register is measured against must be "
                f"unambiguous."
            )
        bands = {g: next(iter(v)) for g, v in pairs.items()}
    else:
        bands = dict(schema.get("list_types", {}))
        if not bands:
            raise ValueError(
                f"QOF {year_key}: no PATIENT_LIST_TYPE column and no [years."
                f"{year_key}.list_types] in config. Either pin the mapping or set "
                f"qof_age_denominators = false if the source genuinely has none."
            )

    # A band is only usable if a resident population exists for it: the rate is one
    # third of a metric and the other two thirds need that band's population. This
    # drops CVDPP (30_74), withdrawn from QOF after 2019-20 and dropped before
    # publication in any case.
    return {g: b for g, b in sorted(bands.items()) if b in QOF_AGE_BANDS}
