# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.fetch_populations
#
# Download LSOA mid-year population estimates from the Nomis REST API.
# Saves one CSV per year to `store/inputs/population/population_{year}.csv`.
# Idempotent: skips years where the file already exists.

# %%
#|default_exp fetch_populations
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print) -> bool:
    """Download LSOA mid-year population estimates from Nomis."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('fetch_populations', run_name=run_name)
show_node_vars('fetch_populations', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
from adi.utils.nomis import download_populations

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
lsoa_vintage = ctx.vars["lsoa_vintage"]

geography_type = "TYPE151" if lsoa_vintage == "2021" else "TYPE298"

print(f"fetch_populations: years {year_start}-{year_end}, LSOA {lsoa_vintage} ({geography_type})")
await download_populations(
    const.population_data_path,
    year_start,
    year_end,
    geography_type=geography_type,
    print=print,
)
print("fetch_populations: done")
True  #|func_return_line
