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
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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
HEALTH = [
    ("AF", "Atrial fibrillation"), ("AST", "Asthma"), ("CAN", "Cancer"),
    ("CHD", "Coronary heart disease"), ("CKD", "Chronic kidney disease"),
    ("COPD", "COPD"), ("DEM", "Dementia"), ("DEP", "Depression"),
    ("DM", "Diabetes"), ("EP", "Epilepsy"), ("HF", "Heart failure"),
    ("HYP", "Hypertension"), ("LD", "Learning disability"),
    ("MH", "Severe mental illness"), ("NDH", "Non-diabetic hyperglycaemia"),
    ("OB", "Obesity"), ("OST", "Osteoporosis"),
    ("PAD", "Peripheral arterial disease"), ("PC", "Palliative care"),
    ("RA", "Rheumatoid arthritis"), ("STIA", "Stroke / TIA"),
    ("CVDPP", "CVD primary prevention"), ("SMOK", "Smoking"),
    ("THY", "Hypothyroidism"),
]

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
    expected_downloads = {Path(f"adi-{level}.zip") for level in LEVELS}
    if set(staged_downloads) != expected_downloads:
        raise RuntimeError(
            "Staged download set is incomplete; "
            f"missing={sorted(map(str, expected_downloads - set(staged_downloads)))}, "
            f"extra={sorted(map(str, set(staged_downloads) - expected_downloads))}"
        )
    for level in LEVELS:
        zip_path = DOWNLOADS / f"adi-{level}.zip"
        member = f"adi-{level}/adi-{level}-health.csv"
        with zipfile.ZipFile(zip_path) as archive, archive.open(member) as health_csv:
            header = health_csv.readline().decode("utf-8")
        leaked = sorted(code for code in DROP_HEALTH if f"{code}_" in header)
        if leaked:
            raise RuntimeError(f"Dropped health metrics leaked into {member}: {leaked}")


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


def _reaggregate_health_metric(disease: str, year: int) -> None:
    """Rebuild one corrected health metric at every higher level from LSOAs."""
    count_col = f"{disease}_afflicted"
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
                f"Cannot propagate {disease} {year}: LSOAs have no {level} mapping: {missing[:5]}"
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
                f"Cannot propagate {disease} {year} to {level}: corrected and stored code sets differ"
            )
        aligned = grouped.reindex(target.index)
        target[count_col] = aligned[count_col]
        target[covered_col] = aligned[covered_col]
        target[rate_col] = target[count_col] / target[covered_col].replace(0, np.nan)


# (1) Drop QOF indicators with no usable prevalence series (sparse/empty: present in
#     only one year or all-zero). Leaves the canonical 21 conditions.
DROP_HEALTH = {"CVDPP", "SMOK", "THY"}
_before = len(HEALTH)
HEALTH = [(c, l) for (c, l) in HEALTH if c not in DROP_HEALTH]
print(f"  health: dropped {sorted(DROP_HEALTH)} -> {len(HEALTH)} conditions (was {_before})")


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
    count_col = f"{disease}_afflicted"
    affected_years = []
    rejected = 0
    for year in YEARS[1:-1]:
        cur = data["lsoa"]["health"][year]
        left = data["lsoa"]["health"][year - 1]
        right = data["lsoa"]["health"][year + 1]
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
            cur.loc[bad, [count_col, covered_col, rate_col]] = np.nan
            affected_years.append(year)
            rejected += n_bad
            print(f"  health: rejected {n_bad} implausible {disease} LSOA values in {year}")
    for year in affected_years:
        _reaggregate_health_metric(disease, year)
    print(f"  health: {disease} sanity guard rejected {rejected} values in total")


# (3) Single-year source anomalies: a disease whose register switched basis for one
#     publication (DEP 2023-24 reported new-diagnosis incidence rather than cumulative
#     prevalence; OST 2014-15 dip-and-reverse). Discard the affected LSOA observation
#     first, then interpolate from flanking years. The modelled count covers the current
#     year's whole LSOA population. Rebuild all higher levels from those corrected LSOAs
#     rather than independently interpolating each geography.
HEALTH_FIX = [("DEP", 2024), ("OST", 2015)]
for disease, year in HEALTH_FIX:
    count_col = f"{disease}_afflicted"
    cur = data["lsoa"]["health"][year]
    left = data["lsoa"]["health"][year - 1]
    right = data["lsoa"]["health"][year + 1]
    covered_col, rate_col = _required_metric_columns(cur, count_col)

    left_rate = left[rate_col].reindex(cur.index)
    right_rate = right[rate_col].reindex(cur.index)
    interpolated_rate = (left_rate + right_rate) / 2.0
    valid = interpolated_rate.notna() & cur["pop"].notna()

    # The whole source-year metric is known to be on the wrong basis, so values without
    # two valid anchors stay missing rather than leaking the bad source observation through.
    cur[[count_col, covered_col, rate_col]] = np.nan
    cur.loc[valid, rate_col] = interpolated_rate.loc[valid]
    cur.loc[valid, covered_col] = cur.loc[valid, "pop"]
    cur.loc[valid, count_col] = (
        cur.loc[valid, rate_col] * cur.loc[valid, covered_col]
    )
    _reaggregate_health_metric(disease, year)
    print(
        f"  health: {disease} {year} interpolated {int(valid.sum())} LSOAs once; "
        "rebuilt LAD/Region/England from them"
    )


# Crime coverage is not corrected here. The pipeline now rejects incomplete force-years
# before annual aggregation and every crime count carries its own `<count>_pop` coverage
# denominator. The former median-rate heuristic and Region/England recomputation were both
# redundant and dangerous: on a wholly missing year, pandas' default sum could turn all-NaN
# counts into zero. The site now publishes the upstream NaNs and denominators unchanged.

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

CONTENTS
  adi-{level}-employment.csv   Universal Credit claimant counts (Nomis NM_162_1)
  adi-{level}-crime.csv        Police-recorded street crime (data.police.uk)
  adi-{level}-health.csv       GP disease prevalence, QOF (NHS Digital), 21 conditions

Each file is long by year: one row per area per year, with a `year` column.
Areas are 2021 LSOA boundaries, rolled up to 2025 local authority and region
boundaries.

POPULATION AND COVERAGE
  `pop` is the ONS mid-year population estimate for ALL AGES (Nomis NM_2014_1,
  2021 LSOA vintage) for that year. It is not an adult-only or working-age base.
  Every count column has a matching `<count>_pop`: the population actually covered
  by that metric. Every `_rate` is count / `<count>_pop`, not count / `pop`.
  At LSOA level `<count>_pop` equals `pop` when measured and is blank when not; at
  higher levels it can be smaller than `pop` where some child areas were not measured.
  2025 uses the 2024 estimate, because the ONS series stops at 2024.

YEARS
  Employment and crime years are CALENDAR years.
  Health years are QOF years, which run April to March and are labelled here by
  the year they END. Health `2021` therefore covers April 2020 to March 2021.
  Comparing the three domains for one labelled year compares slightly different
  periods.

KNOWN GAPS — these are empty cells, never zeros
  The pipeline rejects a force-year unless all 12 monthly police files are present
  and non-empty. British Transport Police gaps make crime unavailable everywhere in
  2016 and 2025. Greater Manchester is unavailable from 2019 onward; Devon &
  Cornwall is additionally unavailable in 2022. Higher-level counts and rates use
  each metric's explicit `<count>_pop` reporting denominator.

  Health figures for the year labelled 2021 (QOF 2020-21) under-record across
  all conditions because routine GP activity collapsed during the pandemic.
  We recommend not using that year for trend analysis.

  Smoking, hypothyroidism and CVD primary prevention are NOT included. NHS
  Digital stopped publishing them as QOF prevalence groups (smoking and
  hypothyroidism after 2013-14, CVD primary prevention after 2019-20), so no
  later figures exist at any geography.

LICENCE
  Open Government Licence v3.0. Boundaries (c) ONS / Crown copyright.

Generated {generated}. Methodology: https://adi.apps.autonomy.work/about
"""

_LEVEL_LABELS = {"england": "England", "region": "Regions",
                 "lad": "Local authorities", "lsoa": "Neighbourhoods (LSOA)"}
_DOMAIN_FILES = {"employment": "employment", "crime": "crime", "health": "health"}

DOWNLOADS.mkdir(parents=True, exist_ok=True)
_generated = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
_bundle_index = []

for lv in LEVELS:
    members = {}
    for dom in _DOMAIN_FILES:
        frames = []
        for yr in sorted(data[lv][dom]):
            df = data[lv][dom][yr].copy()
            df.insert(0, "year", yr)
            frames.append(df.reset_index())
        if not frames:
            continue
        tidy = pd.concat(frames, ignore_index=True)
        # code, name, year first; drop the dropped-QOF columns entirely rather
        # than shipping empty ones.
        if dom == "health":
            drop_cols = [c for c in tidy.columns
                         if any(c.startswith(f"{code}_") for code in DROP_HEALTH)]
            tidy = tidy.drop(columns=drop_cols)
        lead = [c for c in ("code", "name", "year") if c in tidy.columns]
        tidy = tidy[lead + [c for c in tidy.columns if c not in lead]]
        tidy = tidy.sort_values(["code", "year"], kind="stable")

        # Format per column kind rather than with a global float_format, which
        # renders population as 5.43612e+07. `pop` and every metric-specific
        # `<count>_pop` are whole people; rates need precision; counts can be
        # fractional (claimant counts are 12-month means, health counts are modelled).
        pop_cols = [c for c in tidy.columns if c == "pop" or c.endswith(COUNT_POP_SUFFIX)]
        for c in pop_cols:
            tidy[c] = tidy[c].round().astype("Int64")
        for c in tidy.columns:
            if c in ("code", "name", "year") or c in pop_cols:
                continue
            tidy[c] = tidy[c].round(8 if c.endswith("_rate") else 3)
        members[f"adi-{lv}-{dom}.csv"] = tidy.to_csv(index=False)

    if not members:
        continue
    members["README.txt"] = DL_README.format(
        level=lv, level_label=_LEVEL_LABELS[lv], generated=_generated)

    zip_path = DOWNLOADS / f"adi-{lv}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, payload in members.items():
            z.writestr(f"adi-{lv}/{name}", payload)
    size = zip_path.stat().st_size
    _bundle_index.append({
        "level": lv,
        "label": _LEVEL_LABELS[lv],
        "file": f"downloads/{zip_path.name}",
        "bytes": size,
        "size": (f"{size/1_048_576:.1f} MB" if size >= 1_048_576 else f"{size/1024:.0f} KB"),
    })
    print(f"  {lv}: {zip_path.name} ({_bundle_index[-1]['size']})")

# Download index: written here because it carries the per-level area counts,
# which are only canonical once codes_by_level exists.
for _entry in _bundle_index:
    _entry["areas"] = len(codes_by_level[_entry["level"]])
write_json(WEB / "downloads.json", {"years": [YEARS[0], YEARS[-1]],
                                    "generated": _generated,
                                    "bundles": _bundle_index}, indent=1)
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
def _crime_total(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return total crime count and its shared coverage population.

    Crime types currently share one force-coverage mask. Refuse to invent a total if
    that invariant changes: counts measured over different populations cannot be summed
    into a meaningful rate without an explicit total-crime denominator policy.
    """
    count_cols = [name for name, _ in CRIME_TYPES]
    required = count_cols + [f"{name}{COUNT_POP_SUFFIX}" for name in count_cols]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Crime total is missing required columns: {missing}")

    covered = df[[f"{name}{COUNT_POP_SUFFIX}" for name in count_cols]]
    first = covered.iloc[:, 0]
    same = covered.eq(first, axis=0) | (covered.isna() & first.isna().to_numpy()[:, None])
    if not bool(same.all().all()):
        raise ValueError(
            "Crime-type coverage populations differ; cannot derive an all-crime rate"
        )
    return df[count_cols].sum(axis=1, min_count=1), first


def _crime_total_from_row(row: dict) -> tuple[float, float]:
    """Row-dict equivalent of `_crime_total`, used by compact area profiles."""
    counts = [row[name] for name, _ in CRIME_TYPES]
    covered = [row[f"{name}{COUNT_POP_SUFFIX}"] for name, _ in CRIME_TYPES]
    first = covered[0]
    if any(
        not ((pd.isna(value) and pd.isna(first)) or value == first)
        for value in covered[1:]
    ):
        raise ValueError("Crime-type coverage populations differ in an area record")
    total = sum(float(value) for value in counts if not pd.isna(value))
    return (total if any(not pd.isna(value) for value in counts) else np.nan), first


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
                total, covered_pop = _crime_total(df)
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
    emp = [{"key": "claimant_rate", "label": "Universal Credit claimant rate", "fmt": "pct"}]
    cri = [{"key": "total", "label": "All street crime", "fmt": "rate1k"}]
    cri += [{"key": slug, "label": name, "fmt": "rate1k"} for name, slug in CRIME_TYPES]
    hea = [{"key": code, "label": label, "fmt": "pct"} for code, label in HEALTH]
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
    "years": YEARS,
    "levels": LEVELS,
    "level_labels": {"england": "England", "region": "Region", "lad": "Local authority", "lsoa": "Neighbourhood (LSOA)"},
    "domains": {
        "employment": {"label": "Employment", "metrics": METRICS["employment"],
                       "source": "Universal Credit claimant counts (Nomis)"},
        "crime": {"label": "Crime", "metrics": METRICS["crime"],
                  "source": "Police-recorded street crime (data.police.uk)"},
        # `note` is surfaced in the Explorer beneath the source line. The QOF
        # year offset is not cosmetic: comparing health against employment or
        # crime for the same labelled year compares different periods, and the
        # 2020-21 recording collapse makes the year labelled 2021 unusable for
        # trends. Both are easy to walk into without being told.
        "health": {"label": "Health", "metrics": METRICS["health"],
                   "source": "GP disease prevalence, QOF (NHS Digital)",
                   "note": "QOF years run April\u2013March and are labelled by the year they end, "
                           "so health \u201c2021\u201d covers April 2020\u2013March 2021 "
                           "(employment and crime are calendar years). Pandemic disruption to GP "
                           "recording makes that year under-record across all conditions."},
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
    # Crime likewise carries a denominator for the total and each type.
    cri = {
        "total_count": [], "total_pop": [], "total_rate": [], "pop": [],
        "types": {slug: {"count": [], "pop": [], "rate": []} for _, slug in CRIME_TYPES},
    }
    for yr in YEARS:
        r = DD[lv]["crime"].get(yr, {}).get(code)
        if r is not None:
            area_pop = r["pop"]
            cri["pop"].append(int(area_pop) if not pd.isna(area_pop) else None)
            total, total_pop = _crime_total_from_row(r)
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
            for code_, _ in HEALTH
        },
    }
    for yr in YEARS:
        r = DD[lv]["health"].get(yr, {}).get(code)
        if r is not None:
            hea["pop"].append(int(r["pop"]) if not pd.isna(r["pop"]) else None)
            for code_, _ in HEALTH:
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
            for code_, _ in HEALTH:
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
    crime_total, crime_pop = _crime_total(cr)
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
