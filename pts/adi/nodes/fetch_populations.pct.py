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
from adi.utils.nomis import download_populations, latest_population_year

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

# LSOA 2021 populations (NM_2014_1) are the published denominator for every rate.
#
# The series is always about a year behind the claimant and crime data, because
# ONS releases LSOA mid-year estimates roughly 14 months in arrears: today it ends
# at 2024 while the ADI publishes 2025. `beyond_series="substitute"` is the ADI's
# standing answer -- carry the last published estimate forward for that one year,
# say so in the log, and leave the rows' DATE_NAME stating the year they really
# hold. It refuses a second year of it.
#
# What it is NOT is a silent fallback. Nomis answers an out-of-range `date` with
# its newest estimate and HTTP 200, so before this the node asked for 2025, was
# handed 2024, and wrote it to population_2025.csv with nothing anywhere
# recording the substitution (#16).
print(f"fetch_populations: LSOA 2021, years {year_start}-{year_end}")
tasks.append(download_populations(
    pop_dir_2021, year_start, year_end,
    geography_type="TYPE151", beyond_series="substitute", print=print,
))

# LSOA 2011 populations (NM_2010_1) are needed by the domain processors, whose
# sources only report LSOA 2011 codes. This series ended in 2020 and will not be
# extended, so later years are skipped rather than substituted: process_* handles
# them explicitly, and copying 2020 forward here would silently pre-empt that.
# `year_start` is clamped down so the last published year is always on disk for
# them to fall back to, whatever range this run asks for.
lsoa2011_latest = await latest_population_year("TYPE298", print=print)
lsoa2011_start = min(year_start, lsoa2011_latest)
print(f"fetch_populations: LSOA 2011, years {lsoa2011_start}-{year_end} "
      f"(series ends {lsoa2011_latest})")
tasks.append(download_populations(
    pop_dir_2011, lsoa2011_start, year_end,
    geography_type="TYPE298", beyond_series="skip", print=print,
))

await asyncio.gather(*tasks)
print("fetch_populations: done")
True  #|func_return_line
