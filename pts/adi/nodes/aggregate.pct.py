# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.aggregate
#
# Apply LSOA vintage crosswalk and aggregate domain outputs to higher geographies.
#
# Steps:
# 1. Load domain outputs from store/pipeline/{run_name}/
# 2. Apply OA-level population-weighted crosswalk to convert all domains
#    to the target LSOA vintage (configured via lsoa_vintage)
# 3. Aggregate to four geography levels: LSOA, LAD, Region, England
#    - Sum absolute counts across constituent areas
#    - Recompute rates from summed counts / summed populations
# 4. Save final multi-index outputs to store/outputs/

# %%
#|default_exp aggregate
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, domains_ready: dict):
    """Apply LSOA crosswalk and aggregate to LAD/Region/England."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('aggregate', run_name=run_name)
show_node_vars('aggregate', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
run_name = ctx.vars["run_name"]
lsoa_vintage = ctx.vars["lsoa_vintage"]
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]

output_dir = const.outputs_path / run_name
output_dir.mkdir(parents=True, exist_ok=True)

print(f"aggregate: years {year_start}-{year_end}, target vintage LSOA {lsoa_vintage}")

# TODO: Implement aggregation
# - Load domain CSVs from pipeline store
# - Apply crosswalk (adi.utils.geo.apply_crosswalk)
# - Aggregate to LSOA, LAD, Region, England levels
# - Save outputs

print(f"aggregate: done, output at {const.rel(output_dir)}")
