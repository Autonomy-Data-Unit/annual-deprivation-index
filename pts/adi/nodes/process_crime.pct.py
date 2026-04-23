# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.process_crime
#
# Process raw street crime data into per-LSOA annual rates.
#
# For each year:
# 1. Concatenate all monthly per-force CSVs
# 2. Remove non-England entries (Welsh LSOAs)
# 3. Aggregate counts by LSOA and crime type
# 4. Compute per-capita rates
# 5. Save per-year CSV (with both counts and population for crosswalk compatibility)
#
# Output is in **source LSOA vintage** (currently LSOA 2011 from police.uk).

# %%
#|default_exp process_crime
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, data_ready: dict) -> bool:
    """Process raw street crime data into per-LSOA annual rates."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('process_crime', run_name=run_name)
show_node_vars('process_crime', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
run_name = ctx.vars["run_name"]

output_dir = const.pipeline_store_path / run_name / "crime"
output_dir.mkdir(parents=True, exist_ok=True)

print(f"process_crime: years {year_start}-{year_end}")

# TODO: Implement crime data processing

print(f"process_crime: done, output at {const.rel(output_dir)}")
True  #|func_return_line
