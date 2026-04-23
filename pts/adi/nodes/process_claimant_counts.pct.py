# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.process_claimant_counts
#
# Process raw claimant count data into per-LSOA annual rates.
#
# For each year:
# 1. Parse LSOA codes, remove Welsh LSOAs
# 2. Average monthly counts to annual
# 3. Merge with population data to compute claimant_rate = claimant_count / pop
# 4. Save per-year CSV (with both counts and population for crosswalk compatibility)
#
# Output is in **source LSOA vintage** (whatever the Nomis data reports).

# %%
#|default_exp process_claimant_counts
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, data_ready: dict) -> bool:
    """Process raw claimant count data into per-LSOA annual rates."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('process_claimant_counts', run_name=run_name)
show_node_vars('process_claimant_counts', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
run_name = ctx.vars["run_name"]

output_dir = const.pipeline_store_path / run_name / "claimant_counts"
output_dir.mkdir(parents=True, exist_ok=True)

print(f"process_claimant_counts: years {year_start}-{year_end}")

# TODO: Implement claimant count processing

print(f"process_claimant_counts: done, output at {const.rel(output_dir)}")
True  #|func_return_line
