#!/usr/bin/env python3
"""Build compact web data for the ADI site from store/outputs/default + IMD inputs.

Outputs under site/static/data/:
  manifest.json                         levels, domains, metrics (+ label/fmt/scale breaks), years
  codes/{level}.json                    {codes:[...sorted], names:[...]}  (index-aligned)
  hierarchy.json                        england/regions/lad/lsoa parent+child maps
  map/{level}/{domain}/{metric}.json    {years:[...], values:[[per-area per codes order] per year]}
  area/{england,region,lad}.json        full per-area records (all domains, all years)
  area/lsoa/{ladcode}.json              LSOA records sharded by parent LAD
  dashboard.json                        headline stats + england series + extremes
  imd.json                              ADI-vs-IMD analysis (ported from nbs/analysis)

Run:  uv run --with pandas --with numpy --with scipy python site/scripts/build_data.py
"""
from __future__ import annotations

import atexit
import json
import math
import os
import shutil
import stat
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# Deliberately hand-set for each materially new dataset publication. Deriving this
# from the build clock would make a later rebuild look like a new data release, while
# silently collapsing multiple same-day revisions onto the same identifier.
DATASET_RELEASE = "2026-09-03"


def _validate_dataset_release(value: str) -> None:
    """Require an explicit canonical ISO date before reading or publishing data."""
    if not isinstance(value, str) or not value:
        raise RuntimeError(
            "Set DATASET_RELEASE explicitly to the dataset publication date (YYYY-MM-DD)"
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(
            "DATASET_RELEASE must be an explicit date in YYYY-MM-DD format"
        ) from exc
    if parsed.isoformat() != value:
        raise RuntimeError(
            "DATASET_RELEASE must use canonical zero-padded YYYY-MM-DD format"
        )


_validate_dataset_release(DATASET_RELEASE)

ROOT = Path(__file__).resolve().parents[2]
OUT_DEF = ROOT / "store" / "outputs" / "default"
IMD_DIR = ROOT / "store" / "inputs" / "imd"
XWALK = ROOT / "store" / "inputs" / "crosswalk" / "lsoa11_to_lsoa21.csv"
LU_LAD = ROOT / "store" / "inputs" / "geo_lookups" / "lsoa21_to_lad25.csv"
LU_RGN = ROOT / "store" / "inputs" / "geo_lookups" / "lad25_to_rgn25.csv"
STATIC = ROOT / "site" / "static"
LIVE_WEB = STATIC / "data"
LIVE_DOWNLOADS = STATIC / "downloads"

# Build outside the publicly served static tree. A data-loading or generation failure
# therefore leaves the last complete build in place. The staging directory stays under
# site/ so promotion can use same-filesystem atomic file replacements.
_STAGING_PARENT = STATIC.parent
_STAGING = Path(tempfile.mkdtemp(prefix=".build-data-", dir=_STAGING_PARENT))
WEB = _STAGING / "data"
DOWNLOADS = _STAGING / "downloads"


def _remove_staging() -> None:
    """Remove only the uniquely-created staging directory, never a live output path."""
    if _STAGING.parent != _STAGING_PARENT or not _STAGING.name.startswith(".build-data-"):
        raise RuntimeError(f"Refusing to remove unsafe staging path: {_STAGING}")
    shutil.rmtree(_STAGING, ignore_errors=True)


atexit.register(_remove_staging)

YEARS = list(range(2014, 2026))  # 2014..2025
LEVELS = ["england", "region", "lad", "lsoa"]


def _bundle_filename(level: str) -> str:
    return f"adi-{level}-{DATASET_RELEASE}.zip"


CRIME_TYPES = [
    ("Anti-social behaviour", "anti_social"),
    ("Bicycle theft", "bicycle_theft"),
    ("Burglary", "burglary"),
    ("Criminal damage and arson", "criminal_damage"),
    ("Drugs", "drugs"),
    ("Other crime", "other_crime"),
    ("Other theft", "other_theft"),
    ("Possession of weapons", "weapons"),
    ("Public order", "public_order"),
    ("Robbery", "robbery"),
    ("Shoplifting", "shoplifting"),
    ("Theft from the person", "theft_person"),
    ("Vehicle crime", "vehicle"),
    ("Violence and sexual offences", "violence"),
]
ANTI_SOCIAL_COLUMN = "Anti-social behaviour"
ANTI_SOCIAL_KEY = "anti_social"
RECORDED_CRIME_TYPES = [
    crime_type for crime_type in CRIME_TYPES if crime_type[1] != ANTI_SOCIAL_KEY
]
if (
    (ANTI_SOCIAL_COLUMN, ANTI_SOCIAL_KEY) not in CRIME_TYPES
    or len(RECORDED_CRIME_TYPES) != 13
    or len(CRIME_TYPES) != 14
):
    raise RuntimeError("Expected 13 recorded-crime categories plus one separate ASB series")

RECORDED_COUNT_COLUMN = "recorded_count"
RECORDED_CRIME_LABEL = "Police-recorded street crime (excludes ASB)"

HEALTH = [
    ("AF", "Atrial fibrillation"), ("AST", "Asthma"), ("CAN", "Cancer"),
    ("CHD", "Coronary heart disease"), ("CKD", "Chronic kidney disease"),
    ("COPD", "Chronic obstructive pulmonary disease"),
    ("DEM", "Dementia"), ("DEP", "Depression"),
    ("DM", "Diabetes"), ("EP", "Epilepsy"), ("HF", "Heart failure"),
    ("HYP", "Hypertension"), ("LD", "Learning disability"),
    ("MH", "Severe mental illness"), ("NDH", "Non-diabetic hyperglycaemia"),
    ("OB", "Obesity"), ("OST", "Osteoporosis"),
    ("PAD", "Peripheral arterial disease"), ("PC", "Palliative care"),
    ("RA", "Rheumatoid arthritis"),
    ("STIA", "Stroke or transient ischaemic attack"),
    ("CVDPP", "CVD primary prevention (withdrawn after 2019-20)"),
    ("SMOK", "Smoking"),
    ("THY", "Hypothyroidism"),
]

# QOF publishes these registers against an eligible-age practice list as well as the
# all-ages list used by the existing ADI metric. The second representation is deliberately
# additive: existing `{CODE}_afflicted` outputs retain their definition and values, while
# `{CODE}_qof_afflicted` uses the corresponding resident eligible-age population. These
# are age-restricted rates, not age-standardised rates.
QOF_ELIGIBLE_HEALTH = {
    "AST": {
        "first_year": 2021,
        "eligible_population": "residents aged 6 and over",
    },
    "CKD": {
        "first_year": 2015,
        "eligible_population": "residents aged 18 and over",
    },
    "DEP": {
        "first_year": 2015,
        "eligible_population": "residents aged 18 and over",
    },
    "DM": {
        "first_year": 2015,
        "eligible_population": "residents aged 17 and over",
    },
    "EP": {
        "first_year": 2015,
        "eligible_population": "residents aged 18 and over",
    },
    "NDH": {
        "first_year": 2021,
        "eligible_population": "residents aged 18 and over",
    },
    "OB": {
        "first_year": 2015,
        "eligible_population": (
            "residents aged 16 and over in output year 2015, then residents aged "
            "18 and over from 2016"
        ),
    },
    "OST": {
        "first_year": 2015,
        "eligible_population": "residents aged 50 and over",
    },
    "RA": {
        "first_year": 2015,
        "eligible_population": "residents aged 16 and over",
    },
}
if set(QOF_ELIGIBLE_HEALTH) - {code for code, _ in HEALTH}:
    raise RuntimeError("QOF eligible-population metadata names an unknown health condition")

# ---------------------------------------------------------------- helpers

def rnd(x, n=6):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


def rnd_count(x, n=1):
    """Round a display count compactly without turning a measurement into zero.

    Counts normally retain the existing fixed decimal precision. A non-zero value below
    half that precision keeps six significant digits instead, avoiding a contradictory
    zero count beside a positive rate while adding bytes only for exceptional tiny values.
    """
    rounded = rnd(x, n)
    if rounded is None:
        return None
    value = float(x)
    if value != 0 and rounded == 0:
        return float(f"{value:.6g}")
    return rounded


def read_level(level: str, domain: str, year: int) -> pd.DataFrame | None:
    """Read one CSV; normalise first two cols to code,name. Returns None if missing."""
    d = OUT_DEF / level / domain
    if domain == "health":
        # health_{y}_{y+1}.csv ; map to ending calendar year (start+1)
        cands = sorted(d.glob("health_*.csv"))
        path = None
        for f in cands:
            parts = f.stem.split("_")  # health, YYYY, YY
            try:
                start = int(parts[1])
            except (IndexError, ValueError):
                continue
            if start + 1 == year:
                path = f
                break
        if path is None:
            return None
    else:
        path = d / f"{domain}_{year}.csv"
        if not path.exists():
            return None
    df = pd.read_csv(path)
    cols = list(df.columns)
    df = df.rename(columns={cols[0]: "code", cols[1]: "name"})
    return df


def write_json(path: Path, obj, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), allow_nan=False, indent=indent)


def _decimal_size(size: int) -> str:
    """Human-readable on-disk size using the decimal units named in the result."""
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size / 1_000:.0f} KB"
    return f"{size} bytes"


def _binary_size(size: int) -> str:
    """Human-readable extracted size using explicitly binary IEC units."""
    if size >= 1_048_576:
        return f"{size / 1_048_576:.1f} MiB"
    if size >= 1_024:
        return f"{size / 1_024:.1f} KiB"
    return f"{size} bytes"


_ROOT_DATA_OUTPUTS = {
    "dashboard.json", "downloads.json", "hierarchy.json", "imd.json", "manifest.json",
}


def _owns_data_output(relative: Path) -> bool:
    """Whether build_data.py owns an existing path and may remove it as obsolete."""
    parts = relative.parts
    if len(parts) == 1:
        return parts[0] in _ROOT_DATA_OUTPUTS
    if len(parts) == 2 and parts[0] == "codes":
        return relative.suffix == ".json"
    # The complete map/<level>/<domain>/<metric>.json namespace belongs to this
    # builder. Do not restrict this to today's levels or domains: retired ones
    # must be recognised as obsolete on the next build too.
    if len(parts) == 4 and parts[0] == "map":
        return relative.suffix == ".json"
    if len(parts) == 2 and parts[0] == "area" and parts[1] in {
        "england.json", "region.json", "lad.json",
    }:
        return True
    if len(parts) == 3 and parts[:2] == ("area", "lsoa"):
        return relative.suffix == ".json"
    return False


def _owns_download_output(relative: Path) -> bool:
    """Download ZIPs use a dedicated builder-owned filename namespace."""
    return len(relative.parts) == 1 and relative.name.startswith("adi-") and relative.suffix == ".zip"


def _files_below(root: Path) -> dict[Path, Path]:
    if not root.exists():
        return {}
    return {path.relative_to(root): path for path in root.rglob("*") if path.is_file()}


def _validate_staged_outputs() -> None:
    """Reject an incomplete or internally inconsistent staging tree before publication."""
    staged_data = _files_below(WEB)
    unexpected = sorted(str(path) for path in staged_data if not _owns_data_output(path))
    if unexpected:
        raise RuntimeError(f"Builder created paths outside its owned data namespaces: {unexpected}")

    required = _ROOT_DATA_OUTPUTS | {f"codes/{level}.json" for level in LEVELS}
    required |= {f"area/{level}.json" for level in ("england", "region", "lad")}
    missing = sorted(path for path in required if Path(path) not in staged_data)
    if missing:
        raise RuntimeError(f"Staged data build is incomplete; missing: {missing}")

    with (WEB / "manifest.json").open() as f:
        staged_manifest = json.load(f)
    if staged_manifest.get("release") != DATASET_RELEASE:
        raise RuntimeError(
            "Staged manifest has the wrong dataset release: "
            f"{staged_manifest.get('release')!r}"
        )
    expected_maps = {
        Path("map") / level / domain / f"{metric['key']}.json"
        for level in staged_manifest["levels"]
        for domain, domain_spec in staged_manifest["domains"].items()
        for metric in domain_spec["metrics"]
    }
    actual_maps = {path for path in staged_data if path.parts[0] == "map"}
    if actual_maps != expected_maps:
        raise RuntimeError(
            "Staged map files do not match manifest metrics; "
            f"missing={sorted(map(str, expected_maps - actual_maps))}, "
            f"extra={sorted(map(str, actual_maps - expected_maps))}"
        )

    staged_downloads = _files_below(DOWNLOADS)
    expected_downloads = {Path(_bundle_filename(level)) for level in LEVELS}
    if set(staged_downloads) != expected_downloads:
        raise RuntimeError(
            "Staged download set is incomplete; "
            f"missing={sorted(map(str, expected_downloads - set(staged_downloads)))}, "
            f"extra={sorted(map(str, set(staged_downloads) - expected_downloads))}"
        )
    with (WEB / "downloads.json").open() as f:
        download_index = json.load(f)
    if download_index.get("release") != DATASET_RELEASE:
        raise RuntimeError(
            "Staged download index has the wrong dataset release: "
            f"{download_index.get('release')!r}"
        )
    download_metadata = {entry["level"]: entry for entry in download_index["bundles"]}
    if set(download_metadata) != set(LEVELS):
        raise RuntimeError(
            "Download metadata does not cover every level; "
            f"found={sorted(download_metadata)}, expected={sorted(LEVELS)}"
        )
    for level in LEVELS:
        zip_path = DOWNLOADS / _bundle_filename(level)
        prefix = f"adi-{level}/"
        expected_members = {
            f"{prefix}README.txt",
            f"{prefix}adi-{level}-data-dictionary.csv",
            f"{prefix}adi-{level}-geography.csv",
            *(f"{prefix}adi-{level}-{domain}.csv" for domain in _DOMAIN_FILES),
        }
        with zipfile.ZipFile(zip_path) as archive:
            actual_members = set(archive.namelist())
            if actual_members != expected_members:
                raise RuntimeError(
                    f"Unexpected members in {zip_path.name}; "
                    f"missing={sorted(expected_members - actual_members)}, "
                    f"extra={sorted(actual_members - expected_members)}"
                )

            for member_info in archive.infolist():
                unix_mode = member_info.external_attr >> 16
                if not stat.S_ISREG(unix_mode) or stat.S_IMODE(unix_mode) != 0o644:
                    raise RuntimeError(
                        f"{zip_path.name}:{member_info.filename} has Unix mode "
                        f"{stat.filemode(unix_mode)}, expected -rw-r--r--"
                    )

            extracted_bytes = sum(info.file_size for info in archive.infolist())
            metadata = download_metadata[level]
            expected_metadata = {
                "label": _LEVEL_LABELS[level],
                "file": f"downloads/{zip_path.name}",
                "bytes": zip_path.stat().st_size,
                "size": _decimal_size(zip_path.stat().st_size),
                "extracted_bytes": extracted_bytes,
                "extracted_size": _binary_size(extracted_bytes),
                "areas": len(codes_by_level[level]),
            }
            mismatched_metadata = {
                key: {"actual": metadata.get(key), "expected": value}
                for key, value in expected_metadata.items()
                if metadata.get(key) != value
            }
            if mismatched_metadata:
                raise RuntimeError(
                    f"Download metadata is stale for {zip_path.name}: {mismatched_metadata}"
                )

            expected_areas = len(codes_by_level[level])
            readme = archive.read(f"{prefix}README.txt").decode("utf-8")
            expected_rows = expected_areas * len(YEARS)
            if (
                f"Dataset release: {DATASET_RELEASE}" not in readme
                or f"{expected_rows:,} data" not in readme
                or f"{expected_areas:,} unique areas x {len(YEARS)} years" not in readme
            ):
                raise RuntimeError(
                    f"README release or row claims are stale in {zip_path.name}"
                )

            geography_member = f"{prefix}adi-{level}-geography.csv"
            with archive.open(geography_member) as geography_csv:
                geography = pd.read_csv(geography_csv)
            geography_columns = {
                "code", "name", "geography_level", "lad_code", "lad_name",
                "region_code", "region_name",
            }
            if (
                len(geography) != expected_areas
                or set(geography["code"]) != set(codes_by_level[level])
                or set(geography.columns) != geography_columns
            ):
                raise RuntimeError(f"Geography dictionary is incomplete in {zip_path.name}")
            required_parents = {
                "lsoa": ["lad_code", "lad_name", "region_code", "region_name"],
                "lad": ["lad_code", "lad_name", "region_code", "region_name"],
                "region": ["region_code", "region_name"],
                "england": [],
            }[level]
            if required_parents and geography[required_parents].isna().any().any():
                raise RuntimeError(
                    f"Current parent geography is missing in {geography_member}"
                )

            dictionary_member = f"{prefix}adi-{level}-data-dictionary.csv"
            with archive.open(dictionary_member) as dictionary_csv:
                dictionary = pd.read_csv(dictionary_csv)
            expected_metrics = 2 + len(CRIME_TYPES) + len(HEALTH) + len(QOF_HEALTH)
            expected_dictionary_rows = expected_metrics + len(HEALTH_QUALITY_COLUMNS)
            if (
                len(dictionary) != expected_dictionary_rows
                or dictionary["metric"].nunique() != expected_dictionary_rows
                or (dictionary["column_role"] == "metric").sum() != expected_metrics
            ):
                raise RuntimeError(f"Metric dictionary is incomplete in {zip_path.name}")
            dictionary_releases = (
                set(dictionary["release"].dropna().astype(str))
                if "release" in dictionary
                else set()
            )
            if (
                dictionary_releases != {DATASET_RELEASE}
                or dictionary["release"].isna().any()
            ):
                raise RuntimeError(
                    f"Dataset release is missing or inconsistent in {dictionary_member}: "
                    f"found={sorted(dictionary_releases)}"
                )

            quality_dictionary = dictionary[
                dictionary["column_role"] == "quality_indicator"
            ]
            if (
                set(quality_dictionary["indicator_column"])
                != set(HEALTH_QUALITY_COLUMNS)
                or quality_dictionary["indicator_definition"].isna().any()
            ):
                raise RuntimeError(
                    f"Health quality indicators are not defined in {dictionary_member}"
                )

            for domain in _DOMAIN_FILES:
                member = f"{prefix}adi-{level}-{domain}.csv"
                rows = 0
                rows_by_year: dict[int, int] = {}
                codes_by_year = {year: set() for year in YEARS}
                with archive.open(member) as source:
                    for chunk in pd.read_csv(source, chunksize=50_000):
                        rows += len(chunk)
                        if rows == len(chunk):
                            rate_columns = [c for c in chunk if c.endswith("_rate")]
                            count_columns = [c.removesuffix("_rate") for c in rate_columns]
                            domain_dictionary = dictionary[
                                (dictionary["domain"] == domain)
                                & (dictionary["column_role"] == "metric")
                            ]
                            if (
                                set(domain_dictionary["count_column"]) != set(count_columns)
                                or set(domain_dictionary["coverage_population_column"])
                                != {f"{column}{COUNT_POP_SUFFIX}" for column in count_columns}
                                or set(domain_dictionary["rate_column"]) != set(rate_columns)
                            ):
                                raise RuntimeError(
                                    f"Metric dictionary columns do not match {member}"
                                )
                            if domain == "health":
                                missing_quality = set(HEALTH_QUALITY_COLUMNS) - set(chunk.columns)
                                if missing_quality:
                                    raise RuntimeError(
                                        f"Health quality columns missing from {member}: "
                                        f"{sorted(missing_quality)}"
                                    )
                        for year, year_rows in chunk.groupby("year"):
                            year = int(year)
                            if year not in codes_by_year:
                                raise RuntimeError(f"Unexpected year {year} in {member}")
                            chunk_codes = set(year_rows["code"])
                            duplicates = codes_by_year[year] & chunk_codes
                            duplicates |= set(
                                year_rows.loc[year_rows["code"].duplicated(), "code"]
                            )
                            if duplicates:
                                raise RuntimeError(
                                    f"Duplicate area-year keys in {member}: "
                                    f"{sorted(duplicates)[:5]}"
                                )
                            codes_by_year[year].update(chunk_codes)
                            rows_by_year[year] = rows_by_year.get(year, 0) + len(year_rows)

                        rate_columns = [c for c in chunk if c.endswith("_rate")]
                        for rate_col in rate_columns:
                            count_col = rate_col.removesuffix("_rate")
                            covered_col = f"{count_col}{COUNT_POP_SUFFIX}"
                            triple = chunk[[count_col, covered_col, rate_col]]
                            present = triple.notna()
                            partial = present.any(axis=1) & ~present.all(axis=1)
                            if partial.any():
                                sample = chunk.loc[partial, ["code", "year", *triple.columns]].head()
                                raise RuntimeError(
                                    f"Partially blank metric triple in {member}:\n{sample}"
                                )
                            valid = present.all(axis=1)
                            reproduced = (
                                chunk.loc[valid, count_col]
                                / chunk.loc[valid, covered_col]
                            ).round(8)
                            mismatched = ~reproduced.eq(chunk.loc[valid, rate_col])
                            if mismatched.any():
                                bad_index = mismatched[mismatched].index[:5]
                                sample = chunk.loc[
                                    bad_index, ["code", "year", count_col, covered_col, rate_col]
                                ]
                                raise RuntimeError(
                                    f"Published rates do not reproduce in {member}:\n{sample}"
                                )

                        if domain == "crime":
                            recorded_columns = [name for name, _ in RECORDED_CRIME_TYPES]
                            expected_recorded = chunk[recorded_columns].sum(
                                axis=1, min_count=1
                            )
                            actual_recorded = chunk[RECORDED_COUNT_COLUMN]
                            inconsistent_blanks = expected_recorded.isna() != actual_recorded.isna()
                            present = expected_recorded.notna() & actual_recorded.notna()
                            # Each of the 13 category counts and the aggregate starts at
                            # three-decimal publication precision, so their independently
                            # rounded representations can differ by at most 0.007.
                            mismatched = present & ~np.isclose(
                                expected_recorded,
                                actual_recorded,
                                rtol=0,
                                atol=0.008,
                            )
                            expected_pop = chunk[
                                f"{RECORDED_CRIME_TYPES[0][0]}{COUNT_POP_SUFFIX}"
                            ]
                            actual_pop = chunk[
                                f"{RECORDED_COUNT_COLUMN}{COUNT_POP_SUFFIX}"
                            ]
                            pop_mismatch = ~(
                                actual_pop.eq(expected_pop)
                                | (actual_pop.isna() & expected_pop.isna())
                            )
                            bad = inconsistent_blanks | mismatched | pop_mismatch
                            if bad.any():
                                sample = chunk.loc[
                                    bad,
                                    [
                                        "code", "year", RECORDED_COUNT_COLUMN,
                                        ANTI_SOCIAL_COLUMN, *recorded_columns,
                                    ],
                                ].head()
                                raise RuntimeError(
                                    "Recorded-crime aggregate is not the 13-category "
                                    f"non-ASB sum in {member}:\n{sample}"
                                )

                        if domain == "health":
                            registration = chunk["registration_coverage"].dropna()
                            qof = chunk["qof_coverage"].dropna()
                            if (registration < 0).any() or ((qof < 0) | (qof > 1)).any():
                                raise RuntimeError(
                                    f"Health coverage indicator outside its valid range in {member}"
                                )

                expected_by_year = {year: expected_areas for year in YEARS}
                expected_codes = set(codes_by_level[level])
                wrong_code_sets = {
                    year: {
                        "missing": sorted(expected_codes - codes)[:5],
                        "extra": sorted(codes - expected_codes)[:5],
                    }
                    for year, codes in codes_by_year.items()
                    if codes != expected_codes
                }
                if (
                    rows != expected_rows
                    or rows_by_year != expected_by_year
                    or wrong_code_sets
                ):
                    raise RuntimeError(
                        f"Incomplete area-year grid in {member}: rows={rows}, "
                        f"expected={expected_rows}, rows_by_year={rows_by_year}, "
                        f"code_set_errors={wrong_code_sets}"
                    )

            health_member = f"{prefix}adi-{level}-health.csv"
            with archive.open(health_member) as health_csv:
                header = health_csv.readline().decode("utf-8")
            leaked = sorted(code for code in DROP_HEALTH if f"{code}_" in header)
            if leaked:
                raise RuntimeError(f"Dropped health metrics leaked into {health_member}: {leaked}")
            leaked_support = sorted(
                column for column in HEALTH_SUPPORT_COLUMNS if column in header.split(",")
            )
            if leaked_support:
                raise RuntimeError(
                    f"Internal health coverage counts leaked into {health_member}: {leaked_support}"
                )


def _promote_files(staged_root: Path, live_root: Path, owns) -> list[Path]:
    """Atomically replace current files, then remove obsolete builder-owned files.

    Stale removal happens only after every staged file has been promoted. Unknown files are
    neither replaced nor removed. If promotion itself fails, old files remain for every
    target not yet replaced, so the live directory is never emptied first.
    """
    if live_root not in (LIVE_WEB, LIVE_DOWNLOADS):
        raise RuntimeError(f"Refusing to publish outside the configured live roots: {live_root}")
    staged = _files_below(staged_root)
    existing = {path: source for path, source in _files_below(live_root).items() if owns(path)}
    invalid = sorted(str(path) for path in staged if not owns(path))
    if invalid:
        raise RuntimeError(f"Refusing to promote unowned output paths: {invalid}")

    for relative, source in sorted(staged.items()):
        target = live_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)

    obsolete = sorted(set(existing) - set(staged))
    for relative in obsolete:
        (live_root / relative).unlink()

    return obsolete


def publish_staged_outputs() -> tuple[list[Path], list[Path]]:
    _validate_staged_outputs()
    removed_data = _promote_files(WEB, LIVE_WEB, _owns_data_output)
    removed_downloads = _promote_files(DOWNLOADS, LIVE_DOWNLOADS, _owns_download_output)
    return removed_data, removed_downloads


# ---------------------------------------------------------------- load everything into nested dict
# data[level][domain][year] -> DataFrame indexed by code

print("Loading CSVs...")
data: dict = {lv: {"employment": {}, "crime": {}, "health": {}} for lv in LEVELS}
for lv in LEVELS:
    for yr in YEARS:
        cc = read_level(lv, "claimant_counts", yr)
        if cc is not None:
            data[lv]["employment"][yr] = cc.set_index("code")
        cr = read_level(lv, "crime", yr)
        if cr is not None:
            data[lv]["crime"][yr] = cr.set_index("code")
        he = read_level(lv, "health", yr)
        if he is not None:
            data[lv]["health"][yr] = he.set_index("code")

# ---------------------------------------------------------------- data-quality corrections
# Documented, transparent corrections for known source-data defects. Store outputs stay
# frozen as the audit trail; corrections happen at the publishing boundary and are logged.
print("Applying data-quality corrections...")

COUNT_POP_SUFFIX = "_pop"
HEALTH_QUALITY_COLUMNS = ("registration_coverage", "qof_coverage")
HEALTH_SUPPORT_COUNTS = ("gp_registrations", "qof_covered_registrations")
HEALTH_SUPPORT_COLUMNS = tuple(
    column
    for count_col in HEALTH_SUPPORT_COUNTS
    for column in (count_col, f"{count_col}{COUNT_POP_SUFFIX}", f"{count_col}_rate")
)


# Geography used to propagate every LSOA correction upward. Correcting each stored level
# independently breaks the defining invariant that England == sum(regions) == sum(LADs) ==
# sum(LSOAs), so corrected higher levels are always rebuilt from corrected LSOAs.
lu_lad0 = pd.read_csv(LU_LAD)[["LSOA21CD", "LAD25CD"]].drop_duplicates()
lu_rgn0 = pd.read_csv(LU_RGN)[["LAD25CD", "RGN25CD"]].drop_duplicates()
_lsoa_geo = lu_lad0.merge(lu_rgn0, on="LAD25CD", how="inner").set_index("LSOA21CD")


def _required_metric_columns(df: pd.DataFrame, count_col: str) -> tuple[str, str]:
    """Return this count's population/rate columns, failing on schema drift."""
    covered_col = f"{count_col}{COUNT_POP_SUFFIX}"
    rate_col = f"{count_col}_rate"
    missing = [c for c in (count_col, covered_col, rate_col) if c not in df.columns]
    if missing:
        raise ValueError(f"Metric {count_col!r} is missing required columns {missing}")
    return covered_col, rate_col


def _reaggregate_health_metric(count_col: str, year: int) -> None:
    """Rebuild one corrected health count/population/rate triple from LSOAs."""
    source = data["lsoa"]["health"][year]
    covered_col, rate_col = _required_metric_columns(source, count_col)
    source_codes = source.index.to_series()

    targets = {
        "lad": source_codes.map(_lsoa_geo["LAD25CD"]),
        "region": source_codes.map(_lsoa_geo["RGN25CD"]),
        "england": pd.Series("E92000001", index=source.index),
    }
    for level, target_codes in targets.items():
        if target_codes.isna().any():
            missing = source.index[target_codes.isna()].tolist()
            raise ValueError(
                f"Cannot propagate {count_col} {year}: "
                f"LSOAs have no {level} mapping: {missing[:5]}"
            )
        grouped = (
            source[[count_col, covered_col]]
            .assign(_target=target_codes.to_numpy())
            .groupby("_target")[[count_col, covered_col]]
            .sum(min_count=1)
        )
        target = data[level]["health"][year]
        if set(grouped.index) != set(target.index):
            raise ValueError(
                f"Cannot propagate {count_col} {year} to {level}: "
                "corrected and stored code sets differ"
            )
        aligned = grouped.reindex(target.index)
        target[count_col] = aligned[count_col]
        target[covered_col] = aligned[covered_col]
        target[rate_col] = target[count_col] / target[covered_col].replace(0, np.nan)


def _health_count_variants(disease: str) -> list[str]:
    """Count columns that must receive the same publication-stage correction."""
    columns = [f"{disease}_afflicted"]
    if disease in QOF_ELIGIBLE_HEALTH:
        columns.append(f"{disease}_qof_afflicted")
    return columns


# (1) Drop QOF indicators represented in only one source year. CVD primary
#     prevention remains publishable for its seven-year source window and is left blank
#     after NHS Digital withdrew the register, matching the treatment of later-starting NDH.
DROP_HEALTH = {"SMOK", "THY"}
_before = len(HEALTH)
HEALTH = [(c, l) for (c, l) in HEALTH if c not in DROP_HEALTH]
print(f"  health: dropped {sorted(DROP_HEALTH)} -> {len(HEALTH)} conditions (was {_before})")

QOF_HEALTH = [
    (f"{code}_qof", f"{label} — QOF eligible-age rate (not age-standardised)")
    for code, label in HEALTH
    if code in QOF_ELIGIBLE_HEALTH
]
PUBLISHED_HEALTH_METRICS = [*HEALTH, *QOF_HEALTH]


# (2) Reject implausible LSOA health spikes; never clamp them to the boundary,
#     because a clamped prevalence is a fabricated observation. The finest published
#     geography is the right place for this guard: reject there once, then rebuild every
#     aggregate from the surviving LSOAs. A 5% all-age prevalence can be real in an
#     unusually old/institutional neighbourhood, so the absolute bound alone is not enough;
#     the value must also exceed the mean of both adjacent years by at least 3x. This
#     distinguishes the two known one-year extra-digit register errors from persistent high
#     values. The current inputs reject 8 EP LSOAs in 2016 and 7 HF LSOAs in 2021.
HEALTH_SPIKE_BOUNDS = {
    "EP": {"max_rate": 0.05, "max_neighbour_factor": 3.0},
    "HF": {"max_rate": 0.05, "max_neighbour_factor": 3.0},
}
for disease, bound in HEALTH_SPIKE_BOUNDS.items():
    count_columns = _health_count_variants(disease)
    affected_years = []
    rejected = 0
    for year in YEARS[1:-1]:
        cur = data["lsoa"]["health"][year]
        left = data["lsoa"]["health"][year - 1]
        right = data["lsoa"]["health"][year + 1]
        count_col = f"{disease}_afflicted"
        covered_col, rate_col = _required_metric_columns(cur, count_col)
        neighbour_mean = (
            left[rate_col].reindex(cur.index) + right[rate_col].reindex(cur.index)
        ) / 2.0
        bad = (
            (cur[rate_col] > bound["max_rate"])
            & (cur[rate_col] > bound["max_neighbour_factor"] * neighbour_mean)
        )
        n_bad = int(bad.sum())
        if n_bad:
            for variant in count_columns:
                variant_pop, variant_rate = _required_metric_columns(cur, variant)
                cur.loc[bad, [variant, variant_pop, variant_rate]] = np.nan
            affected_years.append(year)
            rejected += n_bad
            print(f"  health: rejected {n_bad} implausible {disease} LSOA values in {year}")
    for year in affected_years:
        for count_col in count_columns:
            _reaggregate_health_metric(count_col, year)
    print(f"  health: {disease} sanity guard rejected {rejected} values in total")


# (3) Single-year source anomalies: a disease whose register switched basis for one
#     publication (DEP 2023-24 reported new-diagnosis incidence rather than cumulative
#     prevalence; OST 2014-15 dip-and-reverse). Discard the affected LSOA observation
#     first, then interpolate from flanking years. Re-derive the all-ages and eligible-age
#     counts against their respective current-year populations, then rebuild higher levels
#     from those corrected LSOAs rather than interpolating each geography independently.
HEALTH_FIX = [("DEP", 2024), ("OST", 2015)]
for disease, year in HEALTH_FIX:
    cur = data["lsoa"]["health"][year]
    left = data["lsoa"]["health"][year - 1]
    right = data["lsoa"]["health"][year + 1]
    count_columns = _health_count_variants(disease)

    # Preflight both representations before mutating either. A schema that lacks the
    # eligible-population triple must fail rather than applying the known-year correction
    # only to the all-ages series and publishing two silently inconsistent views.
    triples = {}
    for count_col in count_columns:
        covered_col, rate_col = _required_metric_columns(cur, count_col)
        _required_metric_columns(left, count_col)
        _required_metric_columns(right, count_col)
        triples[count_col] = (covered_col, rate_col)

    all_age_count = f"{disease}_afflicted"
    all_age_rate_col = triples[all_age_count][1]
    source_rates = {
        count_col: cur[rate_col].copy()
        for count_col, (_, rate_col) in triples.items()
    }
    all_age_interpolated = (
        left[all_age_rate_col].reindex(cur.index)
        + right[all_age_rate_col].reindex(cur.index)
    ) / 2.0

    interpolated = {}
    for count_col, (covered_col, rate_col) in triples.items():
        if count_col == all_age_count:
            corrected_rate = all_age_interpolated
        elif left[rate_col].notna().any() and right[rate_col].notna().any():
            corrected_rate = (
                left[rate_col].reindex(cur.index) + right[rate_col].reindex(cur.index)
            ) / 2.0
        elif disease == "OST" and year == 2015:
            # OST 2015 is the first eligible-population release, so it has no 2014
            # eligible-rate anchor. Its source numerator has the same known anomaly as
            # the all-ages view; rescale the contemporaneous eligible rate by the exact
            # all-ages correction factor while retaining the valid 2015 50+ denominator.
            correction_factor = all_age_interpolated / source_rates[
                all_age_count
            ].replace(0, np.nan)
            corrected_rate = source_rates[count_col] * correction_factor
        else:
            raise ValueError(
                f"Cannot correct {count_col} {year}: eligible-rate anchors are unavailable"
            )
        # Preserve the original all-ages correction exactly. The second metric instead
        # retains its own current-year eligible-age denominator.
        denominator = (
            cur["pop"].copy()
            if count_col == all_age_count
            else cur[covered_col].copy()
        )
        valid = corrected_rate.notna() & denominator.notna() & denominator.gt(0)

        # The whole source-year metric is known to be on the wrong basis, so values without
        # every input required by its correction stay missing rather than leaking it through.
        cur[[count_col, covered_col, rate_col]] = np.nan
        cur.loc[valid, rate_col] = corrected_rate.loc[valid]
        cur.loc[valid, covered_col] = denominator.loc[valid]
        cur.loc[valid, count_col] = corrected_rate.loc[valid] * denominator.loc[valid]
        _reaggregate_health_metric(count_col, year)
        interpolated[count_col] = int(valid.sum())

    print(
        f"  health: {disease} {year} interpolated paired all-age/eligible-population "
        f"metrics ({interpolated}); rebuilt LAD/Region/England from them"
    )


# Crime coverage is not corrected here. The pipeline now rejects incomplete force-years
# before annual aggregation and every crime count carries its own `<count>_pop` coverage
# denominator. The former median-rate heuristic and Region/England recomputation were both
# redundant and dangerous: on a wholly missing year, pandas' default sum could turn all-NaN
# counts into zero. The site now publishes the upstream NaNs and denominators unchanged.


def _recorded_crime_total(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return the 13-category recorded-crime count and shared coverage population.

    Anti-social behaviour is a separately governed incident series, not part of the main
    police-recorded crime collection, so it must never enter this aggregate. The recorded
    categories currently share one force-coverage mask; reject schema drift rather than
    summing counts measured over different populations.
    """
    count_cols = [name for name, _ in RECORDED_CRIME_TYPES]
    required = count_cols + [f"{name}{COUNT_POP_SUFFIX}" for name in count_cols]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Recorded-crime total is missing required columns: {missing}")

    covered = df[[f"{name}{COUNT_POP_SUFFIX}" for name in count_cols]]
    first = covered.iloc[:, 0]
    same = covered.eq(first, axis=0) | (covered.isna() & first.isna().to_numpy()[:, None])
    if not bool(same.all().all()):
        raise ValueError(
            "Recorded-crime category coverage populations differ; cannot derive a rate"
        )
    return df[count_cols].sum(axis=1, min_count=1), first


def _recorded_crime_total_from_row(row: dict) -> tuple[float, float]:
    """Row-dict equivalent of `_recorded_crime_total` for compact area profiles."""
    counts = [row[name] for name, _ in RECORDED_CRIME_TYPES]
    covered = [row[f"{name}{COUNT_POP_SUFFIX}"] for name, _ in RECORDED_CRIME_TYPES]
    first = covered[0]
    if any(
        not ((pd.isna(value) and pd.isna(first)) or value == first)
        for value in covered[1:]
    ):
        raise ValueError("Recorded-crime category populations differ in an area record")
    total = sum(float(value) for value in counts if not pd.isna(value))
    return (total if any(not pd.isna(value) for value in counts) else np.nan), first

# canonical code/name per level (sorted by code), from the latest employment year
codes_by_level: dict[str, list[str]] = {}
names_by_level: dict[str, dict[str, str]] = {}
for lv in LEVELS:
    # union of codes across employment years; names from any year
    all_codes = set()
    names = {}
    for yr, df in data[lv]["employment"].items():
        all_codes.update(df.index)
        for c, n in df["name"].items():
            names[c] = n
    codes_by_level[lv] = sorted(all_codes)
    names_by_level[lv] = names

for lv in LEVELS:
    print(f"  {lv}: {len(codes_by_level[lv])} areas")

# ---------------------------------------------------------------- download bundle
# Published CSVs are built here rather than copied from store/outputs so the explicit
# health corrections above are reflected identically in downloads and site JSON.
print("Building download bundle...")

DL_README = """Annual Deprivation Index (ADI) — {level_label}
Autonomy Data Unit, Autonomy Institute
https://adi.apps.autonomy.work
Dataset release: {release}

CONTENTS
  adi-{level}-employment.csv       Claimant Count, Nomis NM_162_1
  adi-{level}-crime.csv            Recorded street crime plus separate ASB incidents
  adi-{level}-health.csv           Modelled QOF prevalence and two coverage indicators
  adi-{level}-data-dictionary.csv  Metric/indicator definitions, units, sources and availability
  adi-{level}-geography.csv        Current LAD and region codes/names for each area

SHAPE AND GEOGRAPHY
  Each domain CSV is UTF-8, long by year, and contains exactly {row_count:,} data
  rows: {area_count:,} unique areas x 12 years (2014-2025). `code`, `name` and
  `year` identify a row. Missing values are empty fields; numeric zero is a
  published value, not the missing-value marker (and may reflect source rounding).

  LSOAs use 2021 boundaries and are rolled up to 2025 local authority district
  (LAD) and region boundaries. This release contains 33,749 of England's 33,755
  2021 LSOAs; six complex 2011-to-2021 boundary-change LSOAs are excluded. The
  geography CSV supplies the current parent codes and names needed to select a
  council or region. Higher-level `pop` values sum the 33,749 included LSOAs.

POPULATION, COUNTS AND RATES
  `pop` is the ONS mid-year population estimate for all ages (Nomis NM_2014_1,
  2021 LSOA vintage) for that area and year. It is not an adult or working-age
  denominator. The 2025 value repeats 2024 because the source series ends in 2024.

  Each deprivation metric is a three-column group:
    `<count>`       the metric count or modelled count
    `<count>_pop`   the population covered by that count
    `<count>_rate`  round(`<count>` / `<count>_pop`, 8)

  Use the metric-specific `<count>_pop`, not `pop`, to reproduce a nonblank rate.
  Counts may be fractional and retain the decimal precision needed to reproduce
  the published eight-decimal rate. At LSOA level, a measured metric's coverage
  population normally equals `pop`; all three metric fields are blank when it is
  unavailable. At higher levels, coverage population can be below `pop` because
  it sums only LSOAs with that metric available.

COUNT SEMANTICS
  Employment `claimant_count` is the mean of 12 monthly Claimant Count values in
  the calendar year. Claimant Count combines Jobseeker's Allowance with the
  relevant Universal Credit component: UC claimants not in employment early in
  the series, then those in the `Searching for Work` conditionality regime from
  April 2015. The same person can appear in both components. Nomis independently
  rounds each monthly observation to the nearest five before download, so the
  annual mean can be slightly above or below the unrounded value, with the
  largest relative effects in low-count areas. It is neither a unique-person
  count nor a sum of monthly values.

  Crime counts are annual street incidents assigned or apportioned to LSOAs.
  `recorded_count` sums the 13 police-recorded crime categories and excludes
  `Anti-social behaviour`. ASB remains available as its own incident series: it is
  governed by the National Standard for Incident Recording rather than the main
  police-recorded crime collection and must not be added to `recorded_count` when
  describing recorded crime. British Transport Police incidents are excluded.
  These measures are not survey estimates of all crime.

  Health `_afflicted` values are modelled estimates, not observed resident counts.
  They combine published GP-practice QOF prevalence with LSOA GP-registration
  patterns, then multiply the estimated prevalence rate by the ONS resident
  population; fractional people are therefore expected. They will not reconcile
  to NHS England's raw QOF register totals because GP practice lists and resident
  populations are different measures. Use `_rate` for area comparisons and
  `_afflicted` for roll-ups within these ADI files. Source gaps of at most two
  consecutive years are filled only when they are interior gaps bounded by an
  observation on each side. Leading and trailing gaps remain blank. The CSV has
  no per-cell flag distinguishing those interpolated estimates.

HEALTH COVERAGE INDICATORS
  `registration_coverage` is the area's GP registrations divided by its ONS
  resident population. It can exceed 1 because registrations and residents are
  different administrative measures. It is reported for interpretation; low
  values are not used to suppress estimates.

  `qof_coverage` is the share of those GP registrations at practices included in
  that year's QOF publication with a usable list size. It lies between 0 and 1.
  It is an overall practice-publication measure; coverage for a specific disease
  can be lower, and a disease estimate is withheld below 80% disease-specific
  coverage. The internal registration counts used to calculate these indicators
  are not additional deprivation metrics and are not included in the CSV.

  Missing LSOA indicator rows (years not listed have zero):
{health_coverage_gaps}

YEARS
  Employment and crime use calendar years. Health uses QOF financial years and is
  labelled by the ending year: health `2021` means QOF 2020-21 (April 2020 to
  March 2021). A shared year label therefore does not mean identical periods.

AVAILABILITY AND ADJUSTMENTS
  A territorial police force-year is accepted only when all 12 monthly files are
  present and non-empty and at least 90% of records that could belong to England
  carry an English LSOA code. A rejected force-year leaves its resident LADs and
  LSOAs blank. Exact rows with every crime metric blank are:
{crime_gap_table}
  Region and England rows remain available on their reduced metric-specific
  coverage populations.

  Source values that cannot be bracketed by two observations remain blank. LSOAs
  with every published health metric blank are:
{health_gap_table}
  Non-diabetic hyperglycaemia (NDH) was not a published QOF register before
  QOF 2020-21, so every output row is intentionally blank through 2020 rather
  than missing through data loss. It begins in output year 2021, when
  {ndh_2021_missing:,} LSOA rows remain blank. Eight LSOA epilepsy (EP) values
  in 2016 and seven LSOA heart-failure (HF) values in 2021 were rejected as
  implausible one-year spikes; aggregate coverage excludes them.

  Depression (DEP) in 2024 is interpolated from adjacent LSOA rates where both
  exist; {dep_2024_missing:,} LSOAs without both anchors remain blank.
  Osteoporosis (OST) in 2015 is likewise interpolated where both anchors exist;
  {ost_2015_missing:,} LSOAs without both anchors remain blank. Both corrected
  metrics are reaggregated from LSOAs.

  NHS Digital warns that QOF 2020-21 implementation changes may make indicator
  values inaccurate and comparisons with earlier years unreliable. Obesity was
  particularly affected, and asthma and COPD register definitions changed. This
  is a comparability warning, not evidence that every condition moved downward.
  See https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data/2020-21

  CVD primary prevention (CVDPP) is published for output years 2014-2020 (QOF
  2013-14 through 2019-20) and is blank from 2021 after the register was
  withdrawn. There is a sharp England-level break between output years 2014 and
  2015, so comparisons across that boundary should be treated cautiously.
  Dartford's output-year 2019 rate (0.00624) also reverses sharply against 2018
  (0.00303) and 2020 (0.00412); it is retained but has not been source-validated.
  Smoking (SMOK) and hypothyroidism (THY) are excluded because each is available
  in only the first source year. Exact availability is in the data dictionary.

LICENCE
  Open Government Licence v3.0. Boundaries (c) ONS / Crown copyright.

Generated {generated}. Methodology: https://adi.apps.autonomy.work/about
"""

_LEVEL_LABELS = {"england": "England", "region": "Regions",
                 "lad": "Local authorities", "lsoa": "Neighbourhoods (LSOA)"}
_DOMAIN_FILES = {"employment": "employment", "crime": "crime", "health": "health"}


def _missing_counts(level: str, domain: str, column: str) -> dict[int, int]:
    counts = {}
    for year in YEARS:
        frame = data[level][domain].get(year)
        if frame is None or column not in frame.columns:
            raise ValueError(f"Cannot describe availability: no {level}/{domain}/{year}:{column}")
        counts[year] = int(frame[column].isna().sum())
    return counts


def _nonzero_missing_summary(
    level: str,
    domain: str,
    column: str,
    first_year: int = YEARS[0],
    last_year: int = YEARS[-1],
) -> str:
    missing = _missing_counts(level, domain, column)
    nonzero = [
        f"{year}: {count:,}"
        for year, count in missing.items()
        if first_year <= year <= last_year and count
    ]
    return "; ".join(nonzero) if nonzero else "none"


def _crime_missing_counts(level: str) -> dict[int, int]:
    """Count rows whose entire crime vector is blank, rejecting mixed masks."""
    counts = {}
    for year in YEARS:
        frame = data[level]["crime"].get(year)
        if frame is None:
            raise ValueError(f"Cannot describe crime availability: no {level}/crime/{year}")
        rate_columns = [column for column in frame if column.endswith("_rate")]
        if len(rate_columns) != len(CRIME_TYPES):
            raise ValueError(
                f"Expected {len(CRIME_TYPES)} crime rates in {level}/{year}; "
                f"found {len(rate_columns)}"
            )
        blank = frame[rate_columns].isna()
        partially_blank = blank.any(axis=1) & ~blank.all(axis=1)
        if partially_blank.any():
            raise ValueError(
                f"Crime metrics have different availability masks in {level}/{year}: "
                f"{frame.index[partially_blank].tolist()[:5]}"
            )
        counts[year] = int(blank.all(axis=1).sum())
    return counts


def _crime_gap_table() -> str:
    lad = _crime_missing_counts("lad")
    lsoa = _crime_missing_counts("lsoa")
    lines = ["    year   missing LAD rows   missing LSOA rows"]
    lines.extend(f"    {year}   {lad[year]:>16,}   {lsoa[year]:>17,}" for year in YEARS)
    return "\n".join(lines)


def _health_gap_table() -> str:
    rate_columns = [f"{code}_afflicted_rate" for code, _ in HEALTH]
    lines = [f"    year   LSOAs with all {len(HEALTH)} metric rates blank"]
    for year in YEARS:
        frame = data["lsoa"]["health"].get(year)
        missing = [column for column in rate_columns if column not in frame.columns]
        if missing:
            raise ValueError(f"Cannot describe health availability in {year}: {missing}")
        lines.append(f"    {year}   {int(frame[rate_columns].isna().all(axis=1).sum()):>36,}")
    return "\n".join(lines)


def _health_coverage_gap_summary() -> str:
    return "\n".join(
        f"    {column}: {_nonzero_missing_summary('lsoa', 'health', column)}"
        for column in HEALTH_QUALITY_COLUMNS
    )


def _metric_count_columns(columns) -> list[str]:
    """Return count columns in source order and reject an unpaired metric schema."""
    columns = list(columns)
    count_columns = [
        column for column in columns
        if f"{column}{COUNT_POP_SUFFIX}" in columns and f"{column}_rate" in columns
    ]
    metric_columns = {
        column
        for count_col in count_columns
        for column in (count_col, f"{count_col}{COUNT_POP_SUFFIX}", f"{count_col}_rate")
    }
    schema_columns = {
        column for column in columns
        if column.endswith("_rate") or column.endswith(COUNT_POP_SUFFIX)
    }
    if schema_columns - metric_columns:
        raise ValueError(f"Unpaired metric columns: {sorted(schema_columns - metric_columns)}")
    return count_columns


def _validate_health_quality_columns(tidy: pd.DataFrame, member: str) -> None:
    """Verify the two public coverage ratios against their internal source counts."""
    formulas = {
        "registration_coverage": ("gp_registrations", "gp_registrations_pop"),
        "qof_coverage": ("qof_covered_registrations", "gp_registrations"),
    }
    required = set(HEALTH_QUALITY_COLUMNS) | {
        column for pair in formulas.values() for column in pair
    }
    missing = required - set(tidy.columns)
    if missing:
        raise ValueError(f"Cannot verify health coverage in {member}; missing {sorted(missing)}")

    for quality_col, (numerator, denominator) in formulas.items():
        expected = tidy[numerator] / tidy[denominator].replace(0, np.nan)
        actual = tidy[quality_col]
        inconsistent_blanks = expected.isna() != actual.isna()
        present = expected.notna() & actual.notna()
        mismatched = present & ~np.isclose(expected, actual, rtol=0, atol=5e-15)
        bad = inconsistent_blanks | mismatched
        if bad.any():
            sample = tidy.loc[
                bad, ["code", "year", numerator, denominator, quality_col]
            ].head()
            raise ValueError(
                f"{member}:{quality_col} does not reproduce from its source counts:\n{sample}"
            )

    registration = tidy["registration_coverage"].dropna()
    qof = tidy["qof_coverage"].dropna()
    if (registration < 0).any() or ((qof < 0) | (qof > 1)).any():
        raise ValueError(f"Health coverage indicator outside its valid range in {member}")


def _validate_qof_health_metrics(tidy: pd.DataFrame, member: str) -> None:
    """Require every eligible-population triple and preserve pre-collection blanks."""
    if "year" not in tidy:
        raise ValueError(f"Cannot verify eligible-population health years in {member}")
    for code, metadata in QOF_ELIGIBLE_HEALTH.items():
        count_col = f"{code}_qof_afflicted"
        covered_col, rate_col = _required_metric_columns(tidy, count_col)
        triple = [count_col, covered_col, rate_col]
        before_collection = tidy["year"] < metadata["first_year"]
        leaked = tidy.loc[before_collection, triple].notna().any(axis=1)
        if leaked.any():
            sample = tidy.loc[leaked[leaked].index, ["code", "year", *triple]].head()
            raise ValueError(
                f"{member}:{code} eligible-population values precede QOF collection:\n{sample}"
            )
        if not tidy.loc[~before_collection, rate_col].notna().any():
            raise ValueError(
                f"{member}:{code} eligible-population rate is blank in every collected year"
            )
        observed = tidy.loc[tidy[rate_col].notna(), triple]
        if (
            not np.isfinite(observed).all().all()
            or (observed < 0).any().any()
            or (observed[rate_col] > 1).any()
        ):
            raise ValueError(
                f"{member}:{code} eligible-population triple is outside its valid range"
            )


def _serialise_download_table(
    tidy: pd.DataFrame,
    member: str,
    indicator_columns: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, int]:
    """Format a CSV while preserving exact rate reproducibility at eight decimals."""
    tidy = tidy.copy()
    pop_cols = [c for c in tidy if c == "pop" or c.endswith(COUNT_POP_SUFFIX)]
    for column in pop_cols:
        observed = tidy[column].dropna()
        non_integer = ~np.isclose(observed, observed.round(), rtol=0, atol=1e-9)
        if non_integer.any():
            raise ValueError(
                f"{member}:{column} contains non-whole coverage populations: "
                f"{observed[non_integer].head().tolist()}"
            )
        tidy[column] = tidy[column].round().astype("Int64")

    max_decimals = 3
    for count_col in _metric_count_columns(tidy.columns):
        covered_col = f"{count_col}{COUNT_POP_SUFFIX}"
        rate_col = f"{count_col}_rate"
        triple = tidy[[count_col, covered_col, rate_col]]
        present = triple.notna()
        partial = present.any(axis=1) & ~present.all(axis=1)
        if partial.any():
            sample = tidy.loc[partial, ["code", "year", *triple.columns]].head()
            raise ValueError(f"Partially blank metric triple in {member}:\n{sample}")

        valid = present.all(axis=1)
        if (tidy.loc[valid, covered_col] <= 0).any():
            raise ValueError(f"{member}:{covered_col} contains a non-positive denominator")

        source_count = tidy[count_col].copy()
        formula_rate = source_count / tidy[covered_col]
        drift = valid.copy()
        drift.loc[valid] = ~np.isclose(
            formula_rate.loc[valid], tidy.loc[valid, rate_col], rtol=0, atol=5e-15
        )
        if drift.any():
            sample = tidy.loc[
                drift, ["code", "year", count_col, covered_col, rate_col]
            ].head()
            raise ValueError(
                f"Upstream rate is not count / coverage population in {member}:{count_col}:\n"
                f"{sample}"
            )
        # Calculate the displayed rate from the formula, rather than independently
        # rounding a binary-float source value that can sit either side of an exact tie.
        published_rate = formula_rate.round(8)
        published_count = source_count.round(3)
        reproduced = (published_count / tidy[covered_col]).round(8)
        pending = valid & ~reproduced.eq(published_rate)

        for decimals in range(4, 12):
            pending_index = pending[pending].index
            if pending_index.empty:
                break
            candidate = source_count.loc[pending_index].round(decimals)
            matches = (
                (candidate / tidy.loc[pending_index, covered_col]).round(8)
                .eq(published_rate.loc[pending_index])
            )
            matched_index = matches[matches].index
            if not matched_index.empty:
                published_count.loc[matched_index] = candidate.loc[matched_index]
                pending.loc[matched_index] = False
                max_decimals = max(max_decimals, decimals)

        if pending.any():
            sample = tidy.loc[
                pending, ["code", "year", count_col, covered_col, rate_col]
            ].head()
            raise ValueError(
                f"Could not serialise {member}:{count_col} reproducibly at <=11 decimals:\n"
                f"{sample}"
            )

        tidy[count_col] = published_count
        tidy[rate_col] = published_rate

    for column in indicator_columns:
        values = tidy[column].dropna()
        if not np.isfinite(values).all():
            raise ValueError(f"{member}:{column} contains a non-finite value")
        tidy[column] = tidy[column].round(8)

    return tidy, max_decimals


def _data_dictionary(level: str) -> pd.DataFrame:
    common = {
        "release": DATASET_RELEASE,
        "geography_level": level,
        "column_role": "metric",
        "coverage_population_definition": (
            "All-age population covered by this metric count; use this column as the rate denominator"
        ),
        "indicator_column": "",
        "indicator_unit": "",
        "indicator_definition": "",
    }
    rows = [{
        **common,
        "domain": "employment",
        "metric": "claimant_count",
        "label": "Claimant Count",
        "count_column": "claimant_count",
        "count_unit": "mean monthly claimants (may be fractional)",
        "count_definition": (
            "Mean of 12 monthly Claimant Count values: JSA plus the relevant UC component "
            "(not in employment early in the series; Searching for Work from April 2015)"
        ),
        "coverage_population_column": "claimant_count_pop",
        "rate_column": "claimant_count_rate",
        "rate_unit": "mean monthly claimants per resident, rounded to 8 decimal places",
        "first_year": 2014,
        "last_year": 2025,
        "source": "Nomis NM_162_1",
        "availability_and_adjustments": (
            "Calendar years; no metric-specific gaps. Nomis rounds monthly observations "
            "to the nearest 5, so rounding can move an annual mean up or down; "
            "JSA/UC double counting is possible"
        ),
    }]
    rows.append({
        **common,
        "domain": "crime",
        "metric": "recorded_crime",
        "label": RECORDED_CRIME_LABEL,
        "count_column": RECORDED_COUNT_COLUMN,
        "count_unit": "police-recorded street crimes (may be fractional after apportionment)",
        "count_definition": (
            "Sum of the 13 police-recorded crime categories in this file; excludes the "
            "separately governed Anti-social behaviour incident series"
        ),
        "coverage_population_column": f"{RECORDED_COUNT_COLUMN}{COUNT_POP_SUFFIX}",
        "rate_column": f"{RECORDED_COUNT_COLUMN}_rate",
        "rate_unit": "annual recorded crimes per resident, rounded to 8 decimal places",
        "first_year": 2014,
        "last_year": 2025,
        "source": "data.police.uk",
        "availability_and_adjustments": (
            "Calendar years; a force-year is withheld unless all 12 monthly files are "
            "non-empty and at least 90% of potentially English records have an English "
            f"LSOA code. Missing {level} rows by year (years not listed have zero): "
            f"{_nonzero_missing_summary(level, 'crime', f'{RECORDED_CRIME_TYPES[0][0]}_rate')}"
        ),
    })
    for label, key in CRIME_TYPES:
        count_col = label
        is_asb = key == ANTI_SOCIAL_KEY
        rows.append({
            **common,
            "domain": "crime",
            "metric": key,
            "label": "Anti-social behaviour incidents (separate series)" if is_asb else label,
            "count_column": count_col,
            "count_unit": (
                "anti-social behaviour incidents (may be fractional after apportionment)"
                if is_asb
                else "police-recorded street crimes (may be fractional after apportionment)"
            ),
            "count_definition": (
                "Separately governed incident series recorded under the National Standard for "
                "Incident Recording; not part of the main police-recorded crime collection and "
                "excluded from recorded_count; British Transport Police excluded"
                if is_asb
                else "Annual police-recorded crimes assigned or apportioned to LSOAs; "
                     "British Transport Police excluded"
            ),
            "coverage_population_column": f"{count_col}{COUNT_POP_SUFFIX}",
            "rate_column": f"{count_col}_rate",
            "rate_unit": "annual incidents per resident, rounded to 8 decimal places",
            "first_year": 2014,
            "last_year": 2025,
            "source": "data.police.uk",
            "availability_and_adjustments": (
                (
                    "Separate ASB incident series; excluded from the recorded-crime aggregate. "
                    if is_asb else ""
                )
                + "Calendar years; a force-year is withheld unless all 12 monthly files are "
                "non-empty and at least 90% of potentially English records have an English "
                f"LSOA code. Missing {level} rows by year (years not listed have zero): "
                f"{_nonzero_missing_summary(level, 'crime', f'{count_col}_rate')}"
            ),
        })
    for code, label in HEALTH:
        count_col = f"{code}_afflicted"
        notes = [
            "QOF financial year labelled by ending year",
            "endpoint source gaps remain blank rather than being extrapolated",
        ]
        if code == "NDH":
            notes.append(
                "not collected/published as a QOF register before QOF 2020-21, so output "
                "years 2014-2020 are intentionally blank rather than lost"
            )
            notes.append(
                f"missing {level} rows by year from 2021 (years not listed have zero): "
                f"{_nonzero_missing_summary(level, 'health', f'{count_col}_rate', 2021)}"
            )
        if code == "CVDPP":
            notes.append(
                "published for output years 2014-2020 (QOF 2013-14 through 2019-20); "
                "blank from 2021 after the register was withdrawn"
            )
            notes.append(
                "sharp England-level break between output years 2014 and 2015; treat "
                "comparisons across that boundary cautiously"
            )
            notes.append(
                "Dartford output year 2019 is 0.00624 versus 0.00303 in 2018 and 0.00412 "
                "in 2020; retained but not source-validated"
            )
            notes.append(
                f"missing {level} rows within 2014-2020 (years not listed have zero): "
                f"{_nonzero_missing_summary(level, 'health', f'{count_col}_rate', 2014, 2020)}"
            )
        if code == "EP":
            notes.append("8 implausible LSOA values rejected in 2016")
        if code == "HF":
            notes.append("7 implausible LSOA values rejected in 2021")
        if code == "DEP":
            notes.append("2024 rates interpolated only where both adjacent-year anchors exist")
        if code == "OST":
            notes.append(
                "2015 rates interpolated only where both adjacent-year anchors exist"
            )
        rows.append({
            **common,
            "domain": "health",
            "metric": code,
            "label": label,
            "count_column": count_col,
            "count_unit": "modelled people (fractional)",
            "count_definition": (
                "Modelled prevalence rate from GP-practice QOF registers/list sizes and LSOA "
                "registration patterns, multiplied by ONS resident population; not an "
                "observed patient count and not directly comparable with raw QOF register "
                "totals; short interior source gaps may be interpolated, while endpoint "
                "gaps remain blank"
            ),
            "coverage_population_column": f"{count_col}{COUNT_POP_SUFFIX}",
            "rate_column": f"{count_col}_rate",
            "rate_unit": (
                "modelled people per resident (prevalence rate, 0 to 1), "
                "rounded to 8 decimal places"
            ),
            "first_year": 2021 if code == "NDH" else 2014,
            "last_year": 2020 if code == "CVDPP" else 2025,
            "source": "NHS Digital / NHS England QOF",
            "availability_and_adjustments": "; ".join(notes),
        })
    health_labels = dict(HEALTH)
    qof_labels = dict(QOF_HEALTH)
    health_fixes = dict(HEALTH_FIX)
    for code, metadata in QOF_ELIGIBLE_HEALTH.items():
        label = health_labels[code]
        count_col = f"{code}_qof_afflicted"
        first_year = metadata["first_year"]
        notes = [
            "QOF financial year labelled by ending year",
            f"intentionally blank before output year {first_year} because QOF did not "
            "publish a distinct eligible-age denominator for this condition",
            f"eligible population: {metadata['eligible_population']}",
            "alternative denominator for the same condition as the all-ages metric; do not "
            "sum or average the two representations",
            f"missing {level} rows from {first_year} (years not listed have zero): "
            f"{_nonzero_missing_summary(level, 'health', f'{count_col}_rate', first_year)}",
        ]
        if code == "EP":
            notes.append(
                "the same 8 implausible LSOA observations as the all-ages metric are "
                "rejected in 2016"
            )
        if code in health_fixes:
            if code == "OST":
                notes.append(
                    "output year 2015 is rescaled by the same per-LSOA correction factor "
                    "as the all-ages rate because this first eligible-population year has "
                    "no earlier eligible-rate anchor; the 2015 50+ denominator is retained, "
                    "then the metric is reaggregated"
                )
            else:
                notes.append(
                    f"output year {health_fixes[code]} is interpolated from adjacent LSOA "
                    "eligible-population rates only where both anchors exist, in parallel "
                    "with the all-ages correction, then reaggregated"
                )
        rows.append({
            **common,
            "domain": "health",
            "metric": f"{code}_qof",
            "label": qof_labels[f"{code}_qof"],
            "count_column": count_col,
            "count_unit": "modelled eligible-age people (fractional)",
            "count_definition": (
                f"Alternative representation of the same {label} estimate as "
                f"{code}_afflicted: the practice-weighted QOF register/list rate is "
                "multiplied by the corresponding resident eligible-age population. Do not "
                f"add to or average with {code}_afflicted"
            ),
            "coverage_population_column": f"{count_col}{COUNT_POP_SUFFIX}",
            "coverage_population_definition": (
                f"{metadata['eligible_population'].capitalize()} covered by this estimate; "
                "this restricts the denominator to eligible ages but does not adjust for "
                "differences in age structure"
            ),
            "rate_column": f"{count_col}_rate",
            "rate_unit": (
                "modelled share of the eligible resident population, rounded to 8 decimal "
                "places; age-restricted, not age-standardised"
            ),
            "first_year": first_year,
            "last_year": 2025,
            "source": "NHS Digital / NHS England QOF; ONS age-band population",
            "availability_and_adjustments": "; ".join(notes),
        })
    rows.extend([
        {
            **common,
            "domain": "health",
            "metric": "registration_coverage",
            "label": "GP registration coverage",
            "column_role": "quality_indicator",
            "count_column": "",
            "count_unit": "",
            "count_definition": "",
            "coverage_population_column": "",
            "coverage_population_definition": "",
            "rate_column": "",
            "rate_unit": "",
            "indicator_column": "registration_coverage",
            "indicator_unit": "GP registrations per ONS resident; ratio may exceed 1",
            "indicator_definition": (
                "Estimated GP registrations associated with area residents divided by ONS "
                "all-age resident population. Registrations and residents are different "
                "administrative measures, so values can exceed 1. Reported for interpretation; "
                "low values do not suppress disease estimates"
            ),
            "first_year": 2014,
            "last_year": 2025,
            "source": "NHS England GP registrations; ONS mid-year population",
            "availability_and_adjustments": (
                f"Missing {level} rows by year (years not listed have zero): "
                f"{_nonzero_missing_summary(level, 'health', 'registration_coverage')}"
            ),
        },
        {
            **common,
            "domain": "health",
            "metric": "qof_coverage",
            "label": "QOF publication coverage",
            "column_role": "quality_indicator",
            "count_column": "",
            "count_unit": "",
            "count_definition": "",
            "coverage_population_column": "",
            "coverage_population_definition": "",
            "rate_column": "",
            "rate_unit": "",
            "indicator_column": "qof_coverage",
            "indicator_unit": "share of GP registrations (0 to 1)",
            "indicator_definition": (
                "GP registrations at practices included in that year's QOF publication with "
                "a usable list size, divided by all GP registrations associated with the area. "
                "This is overall publication coverage; disease-specific coverage can be lower, "
                "and disease estimates are withheld below 80% disease-specific coverage"
            ),
            "first_year": 2014,
            "last_year": 2025,
            "source": "NHS Digital / NHS England QOF; NHS England GP registrations",
            "availability_and_adjustments": (
                f"Missing {level} rows by year (years not listed have zero): "
                f"{_nonzero_missing_summary(level, 'health', 'qof_coverage')}"
            ),
        },
    ])
    columns = [
        "release", "domain", "metric", "label", "geography_level", "column_role",
        "count_column", "count_unit", "count_definition",
        "coverage_population_column", "coverage_population_definition",
        "rate_column", "rate_unit", "indicator_column", "indicator_unit",
        "indicator_definition", "first_year", "last_year", "source",
        "availability_and_adjustments",
    ]
    return pd.DataFrame(rows)[columns]


def _geography_dictionary(level: str) -> pd.DataFrame:
    rows = []
    for code in codes_by_level[level]:
        lad_code = ""
        region_code = ""
        if level == "lsoa":
            if code not in _lsoa_geo.index:
                raise ValueError(f"No current parent geography for LSOA {code}")
            lad_code = _lsoa_geo.at[code, "LAD25CD"]
            region_code = _lsoa_geo.at[code, "RGN25CD"]
        elif level == "lad":
            lad_code = code
            matches = lu_rgn0.loc[lu_rgn0["LAD25CD"] == code, "RGN25CD"]
            if len(matches) != 1:
                raise ValueError(f"Expected one current region for LAD {code}; found {len(matches)}")
            region_code = matches.iloc[0]
        elif level == "region":
            region_code = code

        if lad_code and lad_code not in names_by_level["lad"]:
            raise ValueError(f"No published LAD name for {lad_code}")
        if region_code and region_code not in names_by_level["region"]:
            raise ValueError(f"No published region name for {region_code}")
        rows.append({
            "code": code,
            "name": names_by_level[level][code],
            "geography_level": level,
            "lad_code": lad_code,
            "lad_name": names_by_level["lad"].get(lad_code, ""),
            "region_code": region_code,
            "region_name": names_by_level["region"].get(region_code, ""),
        })
    return pd.DataFrame(rows)


def _write_public_zip_member(archive: zipfile.ZipFile, name: str, payload: str) -> None:
    """Write a regular, world-readable text member instead of ZipFile's 0600 default."""
    info = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(
        info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
    )


DOWNLOADS.mkdir(parents=True, exist_ok=True)
_generated = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
_bundle_index = []

for lv in LEVELS:
    members = {}
    bundle_max_decimals = 3
    for dom in _DOMAIN_FILES:
        frames = []
        for yr in sorted(data[lv][dom]):
            df = data[lv][dom][yr].copy()
            df.insert(0, "year", yr)
            frames.append(df.reset_index())
        if not frames:
            continue
        tidy = pd.concat(frames, ignore_index=True)
        member_name = f"adi-{lv}-{dom}.csv"
        if dom == "crime":
            aggregate_columns = {
                RECORDED_COUNT_COLUMN,
                f"{RECORDED_COUNT_COLUMN}{COUNT_POP_SUFFIX}",
                f"{RECORDED_COUNT_COLUMN}_rate",
            }
            overlap = aggregate_columns & set(tidy.columns)
            if overlap:
                raise ValueError(
                    f"Cannot derive {member_name} recorded-crime aggregate; "
                    f"columns already exist: {sorted(overlap)}"
                )
            recorded_count, recorded_pop = _recorded_crime_total(tidy)
            tidy[RECORDED_COUNT_COLUMN] = recorded_count
            tidy[f"{RECORDED_COUNT_COLUMN}{COUNT_POP_SUFFIX}"] = recorded_pop
            tidy[f"{RECORDED_COUNT_COLUMN}_rate"] = (
                recorded_count / recorded_pop.replace(0, np.nan)
            )
        # code, name, year first; drop the dropped-QOF columns entirely rather
        # than shipping empty ones.
        indicator_columns: tuple[str, ...] = ()
        if dom == "health":
            drop_cols = [c for c in tidy.columns
                         if any(c.startswith(f"{code}_") for code in DROP_HEALTH)]
            tidy = tidy.drop(columns=drop_cols)
            _validate_health_quality_columns(tidy, member_name)
            _validate_qof_health_metrics(tidy, member_name)
            tidy = tidy.drop(columns=list(HEALTH_SUPPORT_COLUMNS))
            indicator_columns = HEALTH_QUALITY_COLUMNS
        lead = [c for c in ("code", "name", "year", "pop") if c in tidy.columns]
        count_cols = _metric_count_columns(tidy.columns)
        if dom == "crime":
            count_cols = [RECORDED_COUNT_COLUMN] + [
                column for column in count_cols if column != RECORDED_COUNT_COLUMN
            ]
        metric_cols = [
            column for count_col in count_cols
            for column in (count_col, f"{count_col}{COUNT_POP_SUFFIX}", f"{count_col}_rate")
        ]
        ordered = lead + list(indicator_columns) + metric_cols
        leftovers = [c for c in tidy.columns if c not in ordered]
        if leftovers:
            raise ValueError(f"Unclassified columns in adi-{lv}-{dom}.csv: {leftovers}")
        tidy = tidy[ordered]
        tidy = tidy.sort_values(["code", "year"], kind="stable")
        tidy, max_decimals = _serialise_download_table(
            tidy, member_name, indicator_columns
        )
        bundle_max_decimals = max(bundle_max_decimals, max_decimals)
        members[member_name] = tidy.to_csv(index=False)

    if not members:
        continue
    members["README.txt"] = DL_README.format(
        level=lv, level_label=_LEVEL_LABELS[lv], release=DATASET_RELEASE,
        generated=_generated,
        area_count=len(codes_by_level[lv]), row_count=len(codes_by_level[lv]) * len(YEARS),
        health_coverage_gaps=_health_coverage_gap_summary(),
        crime_gap_table=_crime_gap_table(), health_gap_table=_health_gap_table(),
        ndh_2021_missing=_missing_counts("lsoa", "health", "NDH_afflicted_rate")[2021],
        dep_2024_missing=_missing_counts("lsoa", "health", "DEP_afflicted_rate")[2024],
        ost_2015_missing=_missing_counts("lsoa", "health", "OST_afflicted_rate")[2015],
    )
    members[f"adi-{lv}-data-dictionary.csv"] = _data_dictionary(lv).to_csv(index=False)
    members[f"adi-{lv}-geography.csv"] = _geography_dictionary(lv).to_csv(index=False)

    zip_path = DOWNLOADS / _bundle_filename(lv)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, payload in members.items():
            _write_public_zip_member(z, f"adi-{lv}/{name}", payload)
    size = zip_path.stat().st_size
    with zipfile.ZipFile(zip_path) as z:
        extracted_size = sum(info.file_size for info in z.infolist())
    _bundle_index.append({
        "level": lv,
        "label": _LEVEL_LABELS[lv],
        "file": f"downloads/{zip_path.name}",
        "bytes": size,
        "size": _decimal_size(size),
        "extracted_bytes": extracted_size,
        "extracted_size": _binary_size(extracted_size),
    })
    print(
        f"  {lv}: {zip_path.name} ({_bundle_index[-1]['size']}; "
        f"{_bundle_index[-1]['extracted_size']} extracted; "
        f"counts use at most {bundle_max_decimals} decimals)"
    )

# Download index: written here because it carries the per-level area counts,
# which are only canonical once codes_by_level exists.
for _entry in _bundle_index:
    _entry["areas"] = len(codes_by_level[_entry["level"]])
write_json(
    WEB / "downloads.json",
    {
        "release": DATASET_RELEASE,
        "years": [YEARS[0], YEARS[-1]],
        "generated": _generated,
        "bundles": _bundle_index,
    },
    indent=1,
)
print(f"  download index: {len(_bundle_index)} bundles")

# ---------------------------------------------------------------- hierarchy
print("Building hierarchy...")
lu_lad = pd.read_csv(LU_LAD)[["LSOA21CD", "LAD25CD"]]
lsoa_lad = dict(zip(lu_lad["LSOA21CD"], lu_lad["LAD25CD"]))
lu_rgn = pd.read_csv(LU_RGN)[["LAD25CD", "RGN25CD", "RGN25NM"]].drop_duplicates("LAD25CD")
lad_rgn = dict(zip(lu_rgn["LAD25CD"], lu_rgn["RGN25CD"]))

# restrict to areas present in data
lsoa_set = set(codes_by_level["lsoa"])
lad_set = set(codes_by_level["lad"])
rgn_set = set(codes_by_level["region"])
lsoa_lad = {k: v for k, v in lsoa_lad.items() if k in lsoa_set and v in lad_set}
lad_rgn = {k: v for k, v in lad_rgn.items() if k in lad_set and v in rgn_set}

lad_lsoas: dict[str, list[str]] = {}
for ls, ld in lsoa_lad.items():
    lad_lsoas.setdefault(ld, []).append(ls)
for ld in lad_lsoas:
    lad_lsoas[ld].sort()

region_lads: dict[str, list[str]] = {}
for ld, rg in lad_rgn.items():
    region_lads.setdefault(rg, []).append(ld)
for rg in region_lads:
    region_lads[rg].sort()

hierarchy = {
    "england": {"code": "E92000001", "name": "England"},
    "regions": [{"code": c, "name": names_by_level["region"][c]} for c in codes_by_level["region"]],
    "region_lads": region_lads,
    "lad_region": lad_rgn,
    "lad_lsoas": lad_lsoas,
    "lsoa_lad": lsoa_lad,
    "lad_names": names_by_level["lad"],
    "region_names": names_by_level["region"],
}
write_json(WEB / "hierarchy.json", hierarchy)

# ---------------------------------------------------------------- codes files
for lv in LEVELS:
    codes = codes_by_level[lv]
    write_json(WEB / "codes" / f"{lv}.json",
               {"codes": codes, "names": [names_by_level[lv].get(c, c) for c in codes]})

# ---------------------------------------------------------------- per-(level) metric value series helpers
def metric_series_for_level(lv, domain, metric_key):
    """Return dict year -> pd.Series(code->value) for a metric at a level."""
    out = {}
    for yr in YEARS:
        df = data[lv][domain].get(yr)
        if df is None:
            continue
        if domain == "employment":
            s = df["claimant_count_rate"]
        elif domain == "crime":
            if metric_key == "total":
                total, covered_pop = _recorded_crime_total(df)
                s = total / covered_pop.replace(0, np.nan)
            else:
                name = next(t[0] for t in CRIME_TYPES if t[1] == metric_key)
                col = f"{name}_rate"
                s = df[col] if col in df.columns else None
        else:  # health
            col = f"{metric_key}_afflicted_rate"
            s = df[col] if col in df.columns else None
        if s is not None:
            out[yr] = s
    return out


# metric definitions
def domain_metrics():
    emp = [{"key": "claimant_rate", "label": "Claimant Count rate", "fmt": "pct"}]
    cri = [{
        "key": "total",
        "label": RECORDED_CRIME_LABEL,
        "fmt": "rate1k",
        "definition": "Sum of 13 police-recorded crime categories; anti-social behaviour excluded",
    }]
    cri += [
        {
            "key": slug,
            "label": (
                "Anti-social behaviour incidents (separate series)"
                if slug == ANTI_SOCIAL_KEY else name
            ),
            "fmt": "rate1k",
        }
        for name, slug in CRIME_TYPES
    ]
    hea = []
    for code, label in HEALTH:
        metric = {"key": code, "label": label, "fmt": "pct"}
        if code == "CVDPP":
            metric["definition"] = (
                "Published for output years 2014-2020 and blank after withdrawal; "
                "2014-2015 has a sharp national level break, and Dartford 2019 remains "
                "an unvalidated local reversal"
            )
        hea.append(metric)
    for metric_key, label in QOF_HEALTH:
        code = metric_key.removesuffix("_qof")
        metadata = QOF_ELIGIBLE_HEALTH[code]
        hea.append({
            "key": metric_key,
            "label": label,
            "fmt": "pct",
            "definition": (
                f"Age-restricted share of {metadata['eligible_population']}; an alternative "
                f"denominator for the same {dict(HEALTH)[code]} estimate, not an additional "
                "condition and not age-standardised. Do not sum or average it with the "
                "all-ages metric."
            ),
        })
    return {"employment": emp, "crime": cri, "health": hea}


METRICS = domain_metrics()

# ---------------------------------------------------------------- color scale breaks (from LSOA pooled)
print("Computing scale breaks + writing map value files...")
NCLASS = 7

def compute_breaks(pooled: np.ndarray):
    pooled = pooled[~np.isnan(pooled)]
    pooled = pooled[pooled >= 0]
    if pooled.size == 0:
        return {"breaks": [0], "min": 0, "max": 0}
    qs = np.quantile(pooled, [i / NCLASS for i in range(1, NCLASS)])
    breaks = sorted({rnd(q, 7) for q in qs})
    return {"breaks": breaks, "min": rnd(float(pooled.min()), 7), "max": rnd(float(pooled.max()), 7)}


def metric_key_for(domain, m):
    return m["key"] if domain != "employment" else "claimant_rate"


scale_by_metric: dict[str, dict] = {}
for domain, mlist in METRICS.items():
    for m in mlist:
        mk = metric_key_for(domain, m)
        # pooled LSOA values for breaks
        series = metric_series_for_level("lsoa", domain, mk)
        pooled = np.concatenate([s.to_numpy(dtype=float) for s in series.values()]) if series else np.array([])
        scale_by_metric[f"{domain}/{mk}"] = compute_breaks(pooled)

        # write per-level value files
        for lv in LEVELS:
            codes = codes_by_level[lv]
            lvseries = metric_series_for_level(lv, domain, mk)
            years_present = [y for y in YEARS if y in lvseries]
            values = []
            for y in years_present:
                s = lvseries[y].reindex(codes)
                values.append([rnd(v, 7) for v in s.to_numpy(dtype=float)])
            write_json(WEB / "map" / lv / domain / f"{mk}.json",
                       {"years": years_present, "values": values})

# attach scale into metric defs
for domain, mlist in METRICS.items():
    for m in mlist:
        mk = metric_key_for(domain, m)
        m["scale"] = scale_by_metric[f"{domain}/{mk}"]

# ---------------------------------------------------------------- manifest
manifest = {
    "release": DATASET_RELEASE,
    "years": YEARS,
    "levels": LEVELS,
    "level_labels": {"england": "England", "region": "Region", "lad": "Local authority", "lsoa": "Neighbourhood (LSOA)"},
    "domains": {
        "employment": {"label": "Employment", "metrics": METRICS["employment"],
                       "source": "Claimant Count (Nomis NM_162_1)"},
        "crime": {
            "label": "Crime",
            "metrics": METRICS["crime"],
            "source": "Street-level crime and ASB incidents (data.police.uk)",
            "note": "The headline total and crime rankings sum 13 police-recorded "
                    "crime categories. Anti-social behaviour is a separately governed "
                    "incident series and is excluded from that total; select it separately.",
        },
        # `note` is surfaced in the Explorer beneath the source line. The QOF
        # year offset is not cosmetic: comparing health against employment or
        # crime for the same labelled year compares different periods. NHS Digital
        # also warns that QOF 2020-21 implementation and definition changes affect
        # comparisons, especially for obesity, asthma and COPD.
        "health": {"label": "Health", "metrics": METRICS["health"],
                   "source": "GP disease prevalence, QOF (NHS Digital)",
                   "note": "QOF years run April–March and are labelled by the year they end, "
                           "so health ‘2021’ covers April 2020–March 2021 "
                           "(employment and crime are calendar years). CVD primary prevention "
                           "is available only for output years 2014–2020 and is blank after its "
                           "withdrawal; its sharp 2014–2015 level break limits comparison. NHS "
                           "Digital warns that QOF 2020–21 implementation and definition changes "
                           "affect comparisons, especially for obesity, asthma and COPD."},
    },
    "counts": {lv: len(codes_by_level[lv]) for lv in LEVELS},
}
write_json(WEB / "manifest.json", manifest)

# ---------------------------------------------------------------- area profiles
print("Building area profiles...", flush=True)
# Fast O(1) row lookups: per (level, domain, year) a {code: {col: val}} dict.
DD: dict = {lv: {"employment": {}, "crime": {}, "health": {}} for lv in LEVELS}
for lv in LEVELS:
    for dom in ("employment", "crime", "health"):
        for yr, df in data[lv][dom].items():
            DD[lv][dom][yr] = df.to_dict("index")

def build_record(lv, code):
    rec = {"code": code, "name": names_by_level[lv].get(code, code), "level": lv}
    # Employment keeps the full area population and the claimant count's coverage
    # population separately. They currently agree, but using the explicit denominator makes
    # schema drift visible instead of silently changing a rate's meaning.
    emp = {"count": [], "pop": [], "count_pop": [], "rate": []}
    for yr in YEARS:
        r = DD[lv]["employment"].get(yr, {}).get(code)
        if r is not None:
            emp["count"].append(rnd_count(r["claimant_count"], 1))
            emp["pop"].append(int(r["pop"]) if not pd.isna(r["pop"]) else None)
            covered = r["claimant_count_pop"]
            emp["count_pop"].append(int(covered) if not pd.isna(covered) else None)
            emp["rate"].append(rnd(r["claimant_count_rate"], 7))
        else:
            emp["count"].append(None); emp["pop"].append(None)
            emp["count_pop"].append(None); emp["rate"].append(None)
    rec["employment"] = emp
    # The compatibility `total_*` fields are the recorded-crime aggregate: 13 crime
    # categories with the separately governed anti-social-behaviour series excluded.
    # Each category and the aggregate carry their own coverage denominator.
    cri = {
        "total_count": [], "total_pop": [], "total_rate": [], "pop": [],
        "types": {slug: {"count": [], "pop": [], "rate": []} for _, slug in CRIME_TYPES},
    }
    for yr in YEARS:
        r = DD[lv]["crime"].get(yr, {}).get(code)
        if r is not None:
            area_pop = r["pop"]
            cri["pop"].append(int(area_pop) if not pd.isna(area_pop) else None)
            total, total_pop = _recorded_crime_total_from_row(r)
            for name, slug in CRIME_TYPES:
                count = r[name]
                covered = r[f"{name}{COUNT_POP_SUFFIX}"]
                rate = r[f"{name}_rate"]
                cri["types"][slug]["count"].append(rnd_count(count, 1))
                cri["types"][slug]["pop"].append(
                    int(covered) if not pd.isna(covered) else None
                )
                cri["types"][slug]["rate"].append(rnd(rate, 8))
            if not pd.isna(total):
                cri["total_count"].append(rnd_count(total, 1))
                cri["total_pop"].append(int(total_pop))
                cri["total_rate"].append(rnd(total / total_pop, 8))
            else:
                cri["total_count"].append(None); cri["total_pop"].append(None)
                cri["total_rate"].append(None)
        else:
            cri["pop"].append(None); cri["total_count"].append(None)
            cri["total_pop"].append(None); cri["total_rate"].append(None)
            for _, slug in CRIME_TYPES:
                cri["types"][slug]["count"].append(None)
                cri["types"][slug]["pop"].append(None)
                cri["types"][slug]["rate"].append(None)
    rec["crime"] = cri
    # Health
    hea = {
        "pop": [],
        "diseases": {
            code_: {"rate": [], "afflicted": [], "afflicted_pop": []}
            for code_, _ in PUBLISHED_HEALTH_METRICS
        },
    }
    for yr in YEARS:
        r = DD[lv]["health"].get(yr, {}).get(code)
        if r is not None:
            hea["pop"].append(int(r["pop"]) if not pd.isna(r["pop"]) else None)
            for code_, _ in PUBLISHED_HEALTH_METRICS:
                rate_col = f"{code_}_afflicted_rate"
                count_col = f"{code_}_afflicted"
                covered_col = f"{count_col}{COUNT_POP_SUFFIX}"
                hea["diseases"][code_]["rate"].append(rnd(r[rate_col], 7))
                hea["diseases"][code_]["afflicted"].append(rnd_count(r[count_col], 1))
                covered = r[covered_col]
                hea["diseases"][code_]["afflicted_pop"].append(
                    int(covered) if not pd.isna(covered) else None
                )
        else:
            hea["pop"].append(None)
            for code_, _ in PUBLISHED_HEALTH_METRICS:
                hea["diseases"][code_]["rate"].append(None)
                hea["diseases"][code_]["afflicted"].append(None)
                hea["diseases"][code_]["afflicted_pop"].append(None)
    rec["health"] = hea
    # parents
    if lv == "lsoa":
        ld = lsoa_lad.get(code)
        rg = lad_rgn.get(ld) if ld else None
        rec["parents"] = {"lad": {"code": ld, "name": names_by_level["lad"].get(ld)} if ld else None,
                          "region": {"code": rg, "name": names_by_level["region"].get(rg)} if rg else None}
    elif lv == "lad":
        rg = lad_rgn.get(code)
        rec["parents"] = {"region": {"code": rg, "name": names_by_level["region"].get(rg)} if rg else None}
    return rec

# england, region, lad: single files
for lv in ["england", "region", "lad"]:
    areas = {c: build_record(lv, c) for c in codes_by_level[lv]}
    write_json(WEB / "area" / f"{lv}.json", {"areas": areas})
    print(f"  wrote area/{lv}.json ({len(areas)})", flush=True)

# lsoa: shard by parent lad, streaming (write + free per shard)
orphan = {}
nshards = 0
for ld in sorted(lad_lsoas):
    areas = {c: build_record("lsoa", c) for c in lad_lsoas[ld]}
    write_json(WEB / "area" / "lsoa" / f"{ld}.json", {"areas": areas})
    nshards += 1
# any LSOAs without a parent LAD
missing = [c for c in codes_by_level["lsoa"] if c not in lsoa_lad]
if missing:
    orphan = {c: build_record("lsoa", c) for c in missing}
    write_json(WEB / "area" / "lsoa" / "_orphan.json", {"areas": orphan})
print(f"  wrote {nshards} LSOA shards ({len(missing)} orphan LSOAs)", flush=True)

# ---------------------------------------------------------------- dashboard
print("Building dashboard...")
def england_series(domain, mk):
    s = metric_series_for_level("england", domain, mk)
    return {"years": [y for y in YEARS if y in s],
            "values": [rnd(float(s[y].iloc[0]), 7) for y in YEARS if y in s]}

emp_eng = england_series("employment", "claimant_rate")
crime_eng = england_series("crime", "total")
crime_eng["label"] = RECORDED_CRIME_LABEL
crime_eng["includes_asb"] = False
dep_eng = england_series("health", "DEP")

# COVID by LAD 2019->2020
lad19 = data["lad"]["employment"][2019]
lad20 = data["lad"]["employment"][2020]
covid = lad19[["name", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "r19"}).join(
    lad20["claimant_count_rate"].rename("r20"), how="inner")
covid["change"] = covid["r20"] - covid["r19"]
covid["pct"] = covid["change"] / covid["r19"] * 100
covid_top = covid.sort_values("change", ascending=False).head(20)

# extremes for the latest available year, most-deprived LADs by claimant rate
LATEST = YEARS[-1]
lad24 = data["lad"]["employment"][LATEST]
most_dep = lad24.sort_values("claimant_count_rate", ascending=False).head(15)
least_dep = lad24.sort_values("claimant_count_rate", ascending=True).head(15)

dashboard = {
    "latest_year": LATEST,
    "england": {"claimant_rate": emp_eng, "total_crime_rate": crime_eng, "depression_rate": dep_eng},
    "headline": {
        "claimant_rate_latest": rnd(
            float(lad24["claimant_count"].sum() / lad24["claimant_count_pop"].sum()), 6
        ),
        "covid": {
            "y2019": rnd(
                float(lad19["claimant_count"].sum() / lad19["claimant_count_pop"].sum()), 6
            ),
            "y2020": rnd(
                float(lad20["claimant_count"].sum() / lad20["claimant_count_pop"].sum()), 6
            ),
        },
        "n_lsoa": len(codes_by_level["lsoa"]),
        "n_lad": len(codes_by_level["lad"]),
    },
    "covid_top_lads": [
        {"code": c, "name": r["name"], "r19": rnd(r["r19"], 5), "r20": rnd(r["r20"], 5),
         "change": rnd(r["change"], 5), "pct": rnd(r["pct"], 1)}
        for c, r in covid_top.iterrows()
    ],
    "covid_all_increase": bool((covid["change"] > 0).all()),
    "covid_n_lads": int(len(covid)),
    "most_deprived_lads": [
        {"code": c, "name": r["name"], "rate": rnd(r["claimant_count_rate"], 5)} for c, r in most_dep.iterrows()],
    "least_deprived_lads": [
        {"code": c, "name": r["name"], "rate": rnd(r["claimant_count_rate"], 5)} for c, r in least_dep.iterrows()],
}
write_json(WEB / "dashboard.json", dashboard)

# ---------------------------------------------------------------- IMD analysis (ported from nbs/analysis)
print("Building ADI-vs-IMD analysis...")

def load_imd(edition):
    df = pd.read_csv(IMD_DIR / f"imd_{edition}.csv")
    lsoa_col = [c for c in df.columns if c.startswith("LSOA code")][0]
    return df.rename(columns={
        lsoa_col: "lsoa_code",
        "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank",
        "Employment Rank (where 1 is most deprived)": "imd_emp_rank",
        "Crime Rank (where 1 is most deprived)": "imd_crime_rank",
        "Health Deprivation and Disability Rank (where 1 is most deprived)": "imd_health_rank",
    })

xw = pd.read_csv(XWALK)
xw_u = xw[xw["CHGIND"] == "U"][["LSOA11CD", "LSOA21CD"]]

def adi_lsoa_year(year):
    cc = data["lsoa"]["employment"][year].reset_index()[["code", "claimant_count_rate"]].rename(
        columns={"code": "LSOA21CD"})
    cr = data["lsoa"]["crime"][year].reset_index()
    crime_total, crime_pop = _recorded_crime_total(cr)
    cr["adi_crime_rate"] = crime_total / crime_pop.replace(0, np.nan)
    cr = cr[["code", "adi_crime_rate"]].rename(columns={"code": "LSOA21CD"})
    m = cc.merge(cr, on="LSOA21CD", how="inner").rename(columns={"claimant_count_rate": "adi_claimant_rate"})
    he = data["lsoa"]["health"].get(year)
    if he is not None and "DEP_afflicted_rate" in he.columns:
        h = he.reset_index()[["code", "DEP_afflicted_rate"]].rename(
            columns={"code": "LSOA21CD", "DEP_afflicted_rate": "adi_dep_rate"})
        m = m.merge(h, on="LSOA21CD", how="left")
    return m

def spearman(x, y):
    """Return a finite correlation, or None when a metric has no usable data."""
    v = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(v) < 2:
        return None
    statistic = float(stats.spearmanr(v["x"], v["y"]).statistic)
    return statistic if math.isfinite(statistic) else None


def correlations_for(adi, imd, via_xwalk):
    if via_xwalk:
        imd = imd.merge(xw_u, left_on="lsoa_code", right_on="LSOA11CD", how="inner")
        m = adi.merge(imd, on="LSOA21CD", how="inner")
    else:
        m = adi.merge(imd, left_on="LSOA21CD", right_on="lsoa_code", how="inner")
    m["adi_claimant_rank"] = m["adi_claimant_rate"].rank(ascending=False)
    m["adi_crime_rank"] = m["adi_crime_rate"].rank(ascending=False)
    res = {
        "n": int(len(m)),
        "employment": rnd(spearman(m["adi_claimant_rank"], m["imd_emp_rank"]), 3),
        "crime": rnd(spearman(m["adi_crime_rank"], m["imd_crime_rank"]), 3),
        "overall_claimant": rnd(spearman(m["adi_claimant_rank"], m["imd_rank"]), 3),
    }
    if "adi_dep_rate" in m.columns and m["adi_dep_rate"].notna().any():
        m["adi_dep_rank"] = m["adi_dep_rate"].rank(ascending=False)
        res["health"] = rnd(spearman(m["adi_dep_rank"], m["imd_health_rank"]), 3)
    return res, m

imd25, imd19, imd15 = load_imd("2025"), load_imd("2019"), load_imd("2015")
corr15, _ = correlations_for(adi_lsoa_year(2015), imd15, True)
corr19, _ = correlations_for(adi_lsoa_year(2019), imd19, True)
corr25, m25 = correlations_for(adi_lsoa_year(YEARS[-1]), imd25, False)

# scatter sample for 2025 (claimant vs imd employment; crime vs imd crime; dep vs imd health)
samp = m25.sample(min(4000, len(m25)), random_state=42)
scatter = {
    "employment": [[rnd(a, 1), rnd(b, 1)] for a, b in zip(samp["adi_claimant_rank"], samp["imd_emp_rank"]) if pd.notna(a) and pd.notna(b)],
    "crime": [[rnd(a, 1), rnd(b, 1)] for a, b in zip(samp["adi_crime_rank"], samp["imd_crime_rank"]) if pd.notna(a) and pd.notna(b)],
}
if "adi_dep_rank" in m25.columns:
    scatter["health"] = [[rnd(a, 1), rnd(b, 1)] for a, b in zip(samp["adi_dep_rank"], samp["imd_health_rank"]) if pd.notna(a) and pd.notna(b)]
n_lsoa_scatter = int(len(m25))

# ---- LAD + LSOA "relative-improves-but-absolute-worsens" contradictions ----
# Computed for BOTH consecutive IMD pairs: 2015->2019 and the latest 2019->2025.
imd15r = imd15.rename(columns={"lsoa_code": "LSOA11CD", "imd_rank": "imd_rank_15"})
imd19r = pd.read_csv(IMD_DIR / "imd_2019.csv").rename(columns={
    "LSOA code (2011)": "LSOA11CD",
    "Local Authority District name (2019)": "lad_name",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_19"})
imd25r = pd.read_csv(IMD_DIR / "imd_2025.csv").rename(columns={
    "LSOA code (2021)": "LSOA21CD",
    "Local Authority District name (2024)": "lad_name",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_25"})

# map LAD name -> LAD25 code (for linking to area pages)
lad_code_by_name = {r["name"]: c for c, r in data["lad"]["employment"][YEARS[-1]].iterrows()}

def _lad_contradictions(merged, rank_e, rank_l, cc_e_yr, cc_l_yr):
    g = merged.groupby("lad_name").agg(re=(rank_e, "mean"), rl=(rank_l, "mean")).reset_index()
    g["imd_rank_change"] = g["rl"].rank() - g["re"].rank()
    cce = data["lad"]["employment"][cc_e_yr].reset_index()[["name", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_e"})
    ccl = data["lad"]["employment"][cc_l_yr].reset_index()[["name", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_l"})
    g = g.merge(cce, left_on="lad_name", right_on="name", how="inner").merge(ccl, on="name", how="inner")
    g["cc_change"] = g["cc_l"] - g["cc_e"]
    g["contradiction"] = (g["imd_rank_change"] > 0) & (g["cc_change"] > 0)
    n = int(g["contradiction"].sum())
    return n, len(g), [
        {"code": lad_code_by_name.get(r["lad_name"]), "name": r["lad_name"],
         "imd_rank_change": rnd(r["imd_rank_change"], 0), "cc_change_pp": rnd(r["cc_change"] * 100, 2),
         "contradiction": bool(r["contradiction"])}
        for _, r in g.sort_values("cc_change", ascending=False).iterrows()]

def _lsoa_major(merged21, rank_e, rank_l, cc_e_yr, cc_l_yr):
    m = merged21.copy()
    m["imd_change"] = m[rank_l] - m[rank_e]
    ae = data["lsoa"]["employment"][cc_e_yr].reset_index()[["code", "claimant_count_rate"]].rename(columns={"code": "LSOA21CD", "claimant_count_rate": "cc_e"})
    al = data["lsoa"]["employment"][cc_l_yr].reset_index()[["code", "claimant_count_rate"]].rename(columns={"code": "LSOA21CD", "claimant_count_rate": "cc_l"})
    m = m.merge(ae, on="LSOA21CD").merge(al, on="LSOA21CD")
    m["cc_change"] = m["cc_l"] - m["cc_e"]
    return int(((m["imd_change"] > 500) & (m["cc_change"] > 0.01)).sum())

# LSOA-2021 rank tables per IMD edition (2015/2019 via crosswalk; 2025 native)
imd15_21 = imd15r[["LSOA11CD", "imd_rank_15"]].merge(xw_u, on="LSOA11CD")[["LSOA21CD", "imd_rank_15"]]
imd19_21 = imd19r[["LSOA11CD", "imd_rank_19", "lad_name"]].merge(xw_u, on="LSOA11CD")[["LSOA21CD", "imd_rank_19", "lad_name"]]
imd25_21 = imd25r[["LSOA21CD", "imd_rank_25", "lad_name"]]

def _period(rank_e_df, rank_e, name_join_late, rank_l_df, rank_l, cc_e_yr, cc_l_yr, on_lsoa, lad_from):
    lad_merged = on_lsoa.copy()
    n, tot, lads = _lad_contradictions(lad_merged, rank_e, rank_l, cc_e_yr, cc_l_yr)
    major = _lsoa_major(on_lsoa, rank_e, rank_l, cc_e_yr, cc_l_yr)
    return {"n_total": tot, "n_contradiction": n, "pct": round(n / tot * 100) if tot else 0,
            "lads": lads, "lsoa_major": major, "early": cc_e_yr, "late": cc_l_yr}

# 2015->2019: both LSOA11, joined directly, LAD from imd19
m1519 = imd15r[["LSOA11CD", "imd_rank_15"]].merge(imd19r[["LSOA11CD", "imd_rank_19", "lad_name"]], on="LSOA11CD")
m1519_21 = m1519.merge(xw_u, on="LSOA11CD")[["LSOA21CD", "imd_rank_15", "imd_rank_19", "lad_name"]]
c1519 = _period(None, "imd_rank_15", None, None, "imd_rank_19", 2015, 2019, m1519_21, "lad_name")
# 2019->2025: 2019 via crosswalk to LSOA21, joined to native 2025, LAD from imd25
m1925 = imd19_21[["LSOA21CD", "imd_rank_19"]].merge(imd25_21, on="LSOA21CD")
c1925 = _period(None, "imd_rank_19", None, None, "imd_rank_25", 2019, YEARS[-1], m1925, "lad_name")

contradictions = c1519  # back-compat default
contradictions_periods = {"2015_2019": c1519, "2019_2025": c1925}
n_major = c1519["lsoa_major"]

imd_out = {
    "correlations": {"2015": corr15, "2019": corr19, "2025": corr25},
    "crime_measure": {
        "label": RECORDED_CRIME_LABEL,
        "category_count": len(RECORDED_CRIME_TYPES),
        "includes_asb": False,
    },
    "annual_trend": emp_eng,
    "imd_editions": [2015, 2019, 2025],
    "covid": {"y2019": dashboard["headline"]["covid"]["y2019"],
              "y2020": dashboard["headline"]["covid"]["y2020"]},
    "scatter": scatter,
    "scatter_n": n_lsoa_scatter,
    "contradictions": contradictions,
    "contradictions_periods": contradictions_periods,
    "lsoa_major_contradictions": n_major,
}
write_json(WEB / "imd.json", imd_out)

removed_data, removed_downloads = publish_staged_outputs()
print(
    f"Published staged outputs; removed {len(removed_data)} obsolete data files "
    f"and {len(removed_downloads)} obsolete downloads"
)
for obsolete in removed_data + removed_downloads:
    print(f"  removed stale output: {obsolete}")

print("\nDONE. Summary:")
print(f"  correlations 2019: {corr19}")
print(f"  LAD contradictions 2015-19: {c1519['n_contradiction']}/{c1519['n_total']} ({c1519['pct']}%); 2019-25: {c1925['n_contradiction']}/{c1925['n_total']} ({c1925['pct']}%)")
print(f"  LSOA major contradictions: {n_major}")
print(f"  COVID national: {imd_out['covid']}")
