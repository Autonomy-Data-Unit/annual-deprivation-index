# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_crime
#
# Download street crime data archives from data.police.uk.
#
# Each archive is ~1.7 GB and contains a rolling 36-month window of data.
# For each requested calendar year, use the newest single snapshot that still
# contains all 12 months. This gives forces up to two years to correct a return,
# instead of permanently freezing every third year at its first December
# snapshot. Only street CSVs for the requested years are extracted.
#
# Idempotent: per-year source markers record which snapshot supplied the files.
# A newer eligible snapshot invalidates the old marker and replaces that year's
# month directories, so removed as well as added source files are respected.

# %%
#|default_exp fetch_crime
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print) -> bool:
    """Download street crime archives from data.police.uk."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_crime', run_name=run_name)
show_node_vars('fetch_crime', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath

import httpx

from adi.utils.scrape import crime_archive_url, download_file

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]

crime_dir = const.crime_data_path
crime_dir.mkdir(parents=True, exist_ok=True)

LATEST_ARCHIVE_URL = "https://data.police.uk/data/archive/latest.zip"
ARCHIVE_MONTHS = 36


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _select_archive(year: int, latest: tuple[int, int]) -> tuple[int, int]:
    """Newest available archive whose 36-month window contains a whole year."""
    desired = (year + 2, 12)  # latest December whose window still starts at Jan year
    selected = min(desired, latest)
    start = _month_index(*selected) - (ARCHIVE_MONTHS - 1)
    if start > _month_index(year, 1) or _month_index(*selected) < _month_index(year, 12):
        raise ValueError(
            f"Latest police archive {latest[0]}-{latest[1]:02d} does not contain "
            f"all months of requested year {year}"
        )
    return selected


async def _latest_archive() -> tuple[int, int]:
    """Resolve ``latest.zip`` to its dated archive without downloading it."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.head(LATEST_ARCHIVE_URL)
    response.raise_for_status()
    match = re.search(r"/(\d{4})-(\d{2})\.zip$", response.url.path)
    if not match:
        raise ValueError(f"Could not parse latest police archive date from {response.url}")
    return int(match.group(1)), int(match.group(2))


def _source_marker(year: int, archive_name: str) -> Path:
    return crime_dir / f".crime_year_{year}_from_{archive_name}"


def _year_is_current(year: int, archive_name: str) -> bool:
    marker = _source_marker(year, archive_name)
    months_exist = all(
        any((crime_dir / f"{year}-{month:02d}").glob("*-street.csv"))
        for month in range(1, 13)
    )
    return marker.exists() and months_exist


def _street_members(zf: zipfile.ZipFile, years: set[int]) -> list[zipfile.ZipInfo]:
    """Select safe street-CSV members for requested years only."""
    month_prefixes = {
        f"{year}-{month:02d}"
        for year in years
        for month in range(1, 13)
    }
    selected = []
    for info in zf.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe path in police archive: {info.filename!r}")
        if (
            not info.is_dir()
            and len(path.parts) == 2
            and path.parts[0] in month_prefixes
            and path.name.endswith("-street.csv")
        ):
            selected.append(info)
    return selected


def _install_years(zip_path: Path, archive_name: str, years: set[int]) -> None:
    """Replace requested month directories from one authoritative snapshot."""
    with tempfile.TemporaryDirectory(prefix=f".{archive_name}-", dir=crime_dir) as tmp:
        stage = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            members = _street_members(zf, years)
            if not members:
                raise ValueError(f"{archive_name} contains no street files for years {sorted(years)}")
            for info in members:
                zf.extract(info, stage)

        target_months = [
            f"{year}-{month:02d}"
            for year in sorted(years)
            for month in range(1, 13)
        ]
        for month_name in target_months:
            incoming = stage / month_name
            if not incoming.is_dir() or not any(incoming.glob("*-street.csv")):
                raise ValueError(f"{archive_name} has no street files for {month_name}")

        backup = stage / "_previous"
        backup.mkdir()
        replaced = []
        try:
            for month_name in target_months:
                current = crime_dir / month_name
                previous = backup / month_name
                if current.exists():
                    current.rename(previous)
                try:
                    (stage / month_name).rename(current)
                except Exception:
                    if previous.exists():
                        previous.rename(current)
                    raise
                replaced.append((current, previous))
        except Exception:
            for current, previous in reversed(replaced):
                if current.exists():
                    shutil.rmtree(current)
                if previous.exists():
                    previous.rename(current)
            raise

    for year in sorted(years):
        for old_marker in crime_dir.glob(f".crime_year_{year}_from_*"):
            old_marker.unlink()
        _source_marker(year, archive_name).touch()


latest_archive = await _latest_archive()
latest_name = f"{latest_archive[0]}-{latest_archive[1]:02d}"
archive_years = {}
for target_year in range(year_start, year_end + 1):
    source = _select_archive(target_year, latest_archive)
    archive_years.setdefault(source, set()).add(target_year)

plan = ", ".join(
    f"{year}->{source[0]}-{source[1]:02d}"
    for source, years in sorted(archive_years.items())
    for year in sorted(years)
)
print(f"fetch_crime: latest archive {latest_name}; year sources: {plan}")

for (archive_year, archive_month), target_years in sorted(archive_years.items()):
    archive_name = f"{archive_year}-{archive_month:02d}"
    pending = {
        year for year in target_years
        if not _year_is_current(year, archive_name)
    }
    if not pending:
        print(f"  {archive_name}: requested years already current, skipping")
        continue

    zip_path = crime_dir / f"{archive_name}.zip"
    url = crime_archive_url(archive_year, archive_month)
    if zip_path.exists() and not zipfile.is_zipfile(zip_path):
        print(f"  {archive_name}: removing incomplete cached ZIP")
        zip_path.unlink()
    if zip_path.exists():
        print(f"  {archive_name}: ZIP exists, refreshing years {sorted(pending)}")
    else:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            head = await client.head(url)
        head.raise_for_status()
        size_mb = int(head.headers.get("content-length", 0)) / 1024 / 1024
        print(
            f"  {archive_name}: downloading ({size_mb:.0f} MB) "
            f"to refresh years {sorted(pending)}..."
        )
        with tempfile.NamedTemporaryFile(
            prefix=f".{archive_name}-", suffix=".zip.part", dir=crime_dir, delete=False,
        ) as tmp:
            partial_zip = Path(tmp.name)
        try:
            await download_file(url, partial_zip, print=print)
            partial_zip.replace(zip_path)
        except Exception:
            partial_zip.unlink(missing_ok=True)
            raise

    print(f"  {archive_name}: installing street files for years {sorted(pending)}...")
    _install_years(zip_path, archive_name, pending)
    zip_path.unlink()
    print(f"  {archive_name}: installed years {sorted(pending)}")

print("fetch_crime: done")
True  #|func_return_line
