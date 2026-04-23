# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_claimant_counts
#
# Download Universal Credit claimant count data from the Nomis REST API.
# Saves one CSV per year to `store/inputs/claimant_counts/claimant_counts_{year}.csv`,
# containing all 12 monthly counts for that year.
# Idempotent: skips years where the file already exists.

# %%
#|default_exp fetch_claimant_counts
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print) -> bool:
    """Download Universal Credit claimant count data from Nomis."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_claimant_counts', run_name=run_name)
show_node_vars('fetch_claimant_counts', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
from adi.utils.nomis import download_claimant_counts

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]

# Claimant count data starts at 2013.
# Historical data is only available at LSOA 2011 (TYPE298).
# The crosswalk in the aggregate node handles conversion to LSOA 2021.
effective_start = max(year_start, 2013)

print(f"fetch_claimant_counts: years {effective_start}-{year_end}, LSOA 2011 (TYPE298)")
await download_claimant_counts(
    const.claimant_data_path,
    effective_start,
    year_end,
    geography_type="TYPE298",
    print=print,
)
print("fetch_claimant_counts: done")
True  #|func_return_line
