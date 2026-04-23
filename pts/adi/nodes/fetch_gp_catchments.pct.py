# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_gp_catchments
#
# Download GP catchment area data from NHS Digital.
#
# Scrapes the "Patients Registered at a GP Practice" publication pages
# to find LSOA-level patient registration data. Downloads the ZIP files
# containing per-practice LSOA breakdowns.
#
# Idempotent: skips files that already exist.

# %%
#|default_exp fetch_gp_catchments
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print) -> bool:
    """Download GP catchment area data from NHS Digital."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_gp_catchments', run_name=run_name)
show_node_vars('fetch_gp_catchments', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import zipfile

from adi.utils.scrape import scrape_gp_catchment_urls, scrape_download_urls, download_file

# %%
#|export
gp_dir = const.gp_catchments_path
gp_dir.mkdir(parents=True, exist_ok=True)

# We need GP catchment data to map QOF practice-level data to LSOAs.
# Download the latest available LSOA-level patient registration data.
print("fetch_gp_catchments: scraping publication listing page...")
month_urls = scrape_gp_catchment_urls()
print(f"  found {len(month_urls)} GP patient publications")

# Get the latest publication
if not month_urls:
    print("  WARNING: no GP patient publications found")
else:
    latest_slug = sorted(month_urls.keys())[-1]
    latest_url = month_urls[latest_slug]

    extract_marker = gp_dir / f".extracted_{latest_slug}"
    if extract_marker.exists():
        print(f"  GP data ({latest_slug}): already downloaded, skipping")
    else:
        print(f"  GP data ({latest_slug}): scraping download links...")
        downloads = scrape_download_urls(latest_url)

        # Find the LSOA-level ZIP (contains "lsoa" in filename/text)
        lsoa_zips = [d for d in downloads if d["is_zip"] and "lsoa" in d["text"].lower()]
        if not lsoa_zips:
            lsoa_zips = [d for d in downloads if d["is_zip"] and "lsoa" in d["url"].lower()]

        if not lsoa_zips:
            print(f"  WARNING: no LSOA-level ZIP found for {latest_slug}")
            # Download all ZIPs as fallback
            lsoa_zips = [d for d in downloads if d["is_zip"]]

        for dl in lsoa_zips:
            filename = dl["url"].split("/")[-1]
            zip_path = gp_dir / filename
            print(f"  downloading {filename}...")
            await download_file(dl["url"], zip_path, print=print)

            # Extract
            print(f"  extracting {filename}...")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(gp_dir)
            zip_path.unlink()

        extract_marker.touch()
        print(f"  GP data ({latest_slug}): done")

print("fetch_gp_catchments: done")
True  #|func_return_line
