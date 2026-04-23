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
# We download the December archive for each year needed (which covers that
# calendar year plus the two preceding years). Archives are saved as ZIPs
# to `store/inputs/crime/` and extracted in place.
#
# Idempotent: skips archives that are already downloaded.

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
import zipfile
from pathlib import Path

import httpx

from adi.utils.scrape import crime_archive_url, download_file

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]

crime_dir = const.crime_data_path
crime_dir.mkdir(parents=True, exist_ok=True)

# Each archive covers ~36 months ending at the archive date.
# To cover a calendar year Y, we need an archive from at least Y+1.
# We download December archives which cover [Y-2, Y].
# To cover year_start..year_end, we need archives for
# years (year_start+2)..(year_end+2), capped at available data.
archive_years = set()
for year in range(year_start, year_end + 1):
    # The December Y archive covers roughly Jan (Y-2) to Dec Y
    archive_years.add(year)

print(f"fetch_crime: need archives for years {sorted(archive_years)}")

for archive_year in sorted(archive_years):
    # Try December of the archive year first, fall back to earlier months
    for month in [12, 6, 1]:
        archive_name = f"{archive_year}-{month:02d}"
        zip_path = crime_dir / f"{archive_name}.zip"
        extract_marker = crime_dir / f".extracted_{archive_name}"

        if extract_marker.exists():
            print(f"  {archive_name}: already extracted, skipping")
            break

        if zip_path.exists():
            print(f"  {archive_name}: ZIP exists, extracting...")
        else:
            url = crime_archive_url(archive_year, month)
            # Check if the archive exists
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                head = await client.head(url)
            if head.status_code != 200:
                print(f"  {archive_name}: not available (HTTP {head.status_code}), trying next month...")
                continue

            size_mb = int(head.headers.get("content-length", 0)) / 1024 / 1024
            print(f"  {archive_name}: downloading ({size_mb:.0f} MB)...")
            await download_file(url, zip_path, print=print)

        # Extract
        print(f"  {archive_name}: extracting...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(crime_dir)
        extract_marker.touch()
        print(f"  {archive_name}: extracted")

        # Remove ZIP to save disk space
        zip_path.unlink()
        break

print("fetch_crime: done")
True  #|func_return_line
