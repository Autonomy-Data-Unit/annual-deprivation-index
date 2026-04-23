# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_data
#
# Download and cache all raw data sources to `store/inputs/`. Uses async I/O
# for parallel downloads. Idempotent: skips files already present.
#
# Data fetched:
# - Claimant count data from Nomis REST API
# - Crime archives from data.police.uk
# - QOF prevalence data from NHS Digital (scraped)
# - GP catchment area geodata from NHS Digital (scraped)
# - LSOA population estimates from Nomis REST API
# - LSOA boundary GeoJSON from ONS ArcGIS REST API
# - Geographic lookup tables from ONS ArcGIS REST API
# - LSOA crosswalk data (OA-level lookups and populations) from ONS ArcGIS REST API

# %%
#|default_exp fetch_data
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print):
    """Download and cache all raw data sources."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_data', run_name=run_name)
show_node_vars('fetch_data', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
lsoa_vintage = ctx.vars["lsoa_vintage"]

print(f"fetch_data: years {year_start}-{year_end}, target vintage LSOA {lsoa_vintage}")

# TODO: Implement data fetching
# - Nomis API for claimant counts and populations
# - data.police.uk archive downloads for crime
# - NHS Digital scraping for QOF and GP catchment areas
# - ONS ArcGIS API for boundaries, lookups, and crosswalk data

print("fetch_data: done")
