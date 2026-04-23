# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_qof
#
# Download QOF (Quality and Outcomes Framework) prevalence data from NHS Digital.
#
# Scrapes publication pages to discover download URLs (pages are server-side
# rendered, no JS needed). Downloads the raw CSV ZIP for each year.
# Idempotent: skips years where the ZIP already exists.

# %%
#|default_exp fetch_qof
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print) -> bool:
    """Download QOF prevalence data from NHS Digital."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_qof', run_name=run_name)
show_node_vars('fetch_qof', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import asyncio
import re
import zipfile
from pathlib import Path

from adi.utils.scrape import scrape_qof_year_urls, find_qof_csv_zip_url, download_file

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]

qof_dir = const.qof_data_path
raw_dir = qof_dir / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)

print("fetch_qof: scraping publication listing page...")
year_urls = await scrape_qof_year_urls()
print(f"  found {len(year_urls)} QOF publications")

# Identify which QOF years we need
to_download = []
for slug, pub_url in sorted(year_urls.items()):
    year_match = re.search(r'(\d{4})-(\d{2})', slug)
    if not year_match:
        continue
    qof_start_year = int(year_match.group(1))
    qof_end_suffix = int(year_match.group(2))

    # QOF year "2019-20" covers April 2019 - March 2020
    if qof_start_year > year_end or (qof_start_year + 1) < year_start:
        continue

    year_key = f"{qof_start_year}_{qof_end_suffix:02d}"
    zip_dir = raw_dir / year_key
    extract_marker = zip_dir / ".extracted"

    if extract_marker.exists():
        print(f"  QOF {year_key}: already downloaded, skipping")
        continue

    to_download.append((year_key, slug, pub_url, zip_dir, extract_marker))


async def _download_qof_year(year_key, slug, pub_url, zip_dir, extract_marker):
    print(f"  QOF {year_key}: scraping download links from {slug}...")
    csv_zip_url = await find_qof_csv_zip_url(pub_url)
    if not csv_zip_url:
        print(f"  QOF {year_key}: WARNING - no CSV ZIP found on page")
        return

    zip_path = raw_dir / f"qof_{year_key}.zip"
    print(f"  QOF {year_key}: downloading...")
    await download_file(csv_zip_url, zip_path, print=print)

    zip_dir.mkdir(parents=True, exist_ok=True)
    print(f"  QOF {year_key}: extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(zip_dir)
    extract_marker.touch()
    zip_path.unlink()
    print(f"  QOF {year_key}: done")


if to_download:
    await asyncio.gather(*[_download_qof_year(*args) for args in to_download])

print("fetch_qof: done")
True  #|func_return_line
