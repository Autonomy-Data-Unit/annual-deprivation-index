# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.process_health
#
# Process QOF + GP catchment data into per-LSOA health prevalence estimates.
#
# Steps:
# 1. Parse QOF data using schema config (config/qof_schemas.toml)
# 2. Clean GP catchment areas (remove outlier polygons)
# 3. Compute LSOA-GP spatial intersections (cache as .npy)
# 4. Estimate LSOA-level health prevalence via area-weighted allocation
# 5. Fill LSOAs with no GP overlap from spatial neighbours
# 6. Interpolate missing temporal data
# 7. Save per-year CSV (with both counts and population for crosswalk compatibility)
#
# Output is in **source LSOA vintage** (whichever boundary shapefile was used).

# %%
#|default_exp process_health
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, data_ready: dict) -> bool:
    """Process QOF + GP catchment data into per-LSOA health prevalence estimates."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('process_health', run_name=run_name)
show_node_vars('process_health', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
run_name = ctx.vars["run_name"]
lsoa_vintage = ctx.vars["lsoa_vintage"]

output_dir = const.pipeline_store_path / run_name / "health"
output_dir.mkdir(parents=True, exist_ok=True)

print(f"process_health: years {year_start}-{year_end}, LSOA vintage {lsoa_vintage}")

# TODO: Implement health domain processing
# This is the most complex node. Key components:
# - QOF schema normalisation (adi.utils.qof)
# - GP catchment area cleaning and spatial intersection (adi.utils.geo)
# - Prevalence estimation via area-weighted allocation
# - Spatial neighbour fill for LSOAs with no GP overlap
# - Temporal interpolation for missing years/subdomains

print(f"process_health: done, output at {const.rel(output_dir)}")
True  #|func_return_line
