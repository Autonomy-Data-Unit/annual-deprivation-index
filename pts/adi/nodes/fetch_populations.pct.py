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
import asyncio

# %%
#|export
year_start = ctx.vars["year_start"]
year_end = ctx.vars["year_end"]
lsoa_vintage = ctx.vars["lsoa_vintage"]

pop_dir_2021 = const.population_data_path / "lsoa_2021"
pop_dir_2011 = const.population_data_path / "lsoa_2011"

tasks = []

# Always download LSOA 2021 populations (NM_2014_1, covers 2011-2024)
print(f"fetch_populations: LSOA 2021, years {year_start}-{year_end}")
tasks.append(download_populations(
    pop_dir_2021, year_start, year_end,
    geography_type="TYPE151", print=print,
))

# Also download LSOA 2011 populations (NM_2010_1, covers 2011-2020).
# Needed for claimant count and crime processing since those data
# sources only report LSOA 2011 codes.
# Always include 2020 as a fallback for years beyond 2020.
lsoa2011_start = min(year_start, 2020)
lsoa2011_end = min(year_end, 2020)
print(f"fetch_populations: LSOA 2011, years {lsoa2011_start}-{lsoa2011_end}")
tasks.append(download_populations(
    pop_dir_2011, lsoa2011_start, lsoa2011_end,
    geography_type="TYPE298", print=print,
))

await asyncio.gather(*tasks)
print("fetch_populations: done")
True  #|func_return_line
