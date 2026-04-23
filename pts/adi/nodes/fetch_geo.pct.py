# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_geo
#
# Download LSOA boundaries, geographic lookup tables, and crosswalk data
# from the ONS Open Geography Portal (ArcGIS REST API).
#
# Downloads:
# - LSOA boundary geometries (Generalised Clipped)
# - LSOA-to-LAD lookup table
# - LAD-to-Region lookup table
# - LSOA 2011-to-2021 exact-fit crosswalk
# - OA 2011-to-2021 exact-fit crosswalk
# - OA-to-LSOA 2021 lookup
#
# Idempotent: skips files that already exist.

# %%
#|default_exp fetch_geo
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print) -> bool:
    """Download LSOA boundaries, lookups, and crosswalk data from ONS."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_geo', run_name=run_name)
show_node_vars('fetch_geo', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
from adi.utils.ons import download_geo_data

# %%
#|export
lsoa_vintage = ctx.vars["lsoa_vintage"]

print(f"fetch_geo: downloading geographic data for LSOA {lsoa_vintage}...")
await download_geo_data(const.inputs_path, lsoa_vintage, print=print)
print("fetch_geo: done")
True  #|func_return_line
