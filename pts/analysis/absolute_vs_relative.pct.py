# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Absolute vs Relative: The ADI's Advantage
#
# The IMD provides relative rankings — if every area gets worse uniformly,
# the rankings don't change. The ADI measures absolute rates, so it captures
# real changes in deprivation levels.
#
# This notebook finds cases where:
# 1. IMD ranking "improves" but ADI absolute values worsen
# 2. The ADI captures COVID-19 impact (2019→2020) that the IMD misses entirely
# 3. Year-on-year ADI changes reveal trends invisible to the IMD

# %%
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

repo_root = Path.cwd()
if repo_root.name in ("analysis", "nbs", "pts"):
    repo_root = repo_root.parent
while not (repo_root / "config").exists() and repo_root != repo_root.parent:
    repo_root = repo_root.parent

imd_dir = repo_root / "store" / "inputs" / "imd"
adi_lsoa_dir = repo_root / "store" / "outputs" / "default" / "lsoa"
adi_lad_dir = repo_root / "store" / "outputs" / "default" / "lad"
crosswalk_path = repo_root / "store" / "inputs" / "crosswalk" / "lsoa11_to_lsoa21.csv"

# %% [markdown]
# ## 1. IMD 2015 vs IMD 2019: Areas where ranking improved but ADI worsened
#
# At LAD level: find councils whose IMD rank improved (less deprived)
# but whose ADI claimant rate or crime rate increased.

# %%
# Load IMD at LAD level (average rank per LAD)
xwalk = pd.read_csv(crosswalk_path)
xwalk_u = xwalk[xwalk["CHGIND"] == "U"][["LSOA11CD", "LSOA21CD"]]

# IMD 2015 and 2019 at LSOA 2011
imd15 = pd.read_csv(imd_dir / "imd_2015.csv")
imd19 = pd.read_csv(imd_dir / "imd_2019.csv")

imd15 = imd15.rename(columns={
    "LSOA code (2011)": "LSOA11CD",
    "Local Authority District code (2013)": "lad_code_15",
    "Local Authority District name (2013)": "lad_name_15",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_15",
    "Index of Multiple Deprivation (IMD) Score": "imd_score_15",
})
imd19 = imd19.rename(columns={
    "LSOA code (2011)": "LSOA11CD",
    "Local Authority District code (2019)": "lad_code_19",
    "Local Authority District name (2019)": "lad_name_19",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_19",
    "Index of Multiple Deprivation (IMD) Score": "imd_score_19",
})

# Average IMD rank per LAD
imd15_lad = imd15.groupby(["lad_code_15", "lad_name_15"]).agg(
    mean_imd_rank_15=("imd_rank_15", "mean"),
    mean_imd_score_15=("imd_score_15", "mean"),
).reset_index()

imd19_lad = imd19.groupby(["lad_code_19", "lad_name_19"]).agg(
    mean_imd_rank_19=("imd_rank_19", "mean"),
    mean_imd_score_19=("imd_score_19", "mean"),
).reset_index()

# ADI at LAD level
adi_cc_15 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2015.csv")
adi_cc_19 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2019.csv")
adi_cr_15 = pd.read_csv(adi_lad_dir / "crime" / "crime_2015.csv")
adi_cr_19 = pd.read_csv(adi_lad_dir / "crime" / "crime_2019.csv")

# Merge IMD LAD data (LAD codes may differ between 2013 and 2019)
# Use IMD 2019 LAD codes as primary, join on LSOA
imd_merged = imd15[["LSOA11CD", "imd_rank_15", "imd_score_15"]].merge(
    imd19[["LSOA11CD", "lad_code_19", "lad_name_19", "imd_rank_19", "imd_score_19"]],
    on="LSOA11CD", how="inner"
)
imd_lad = imd_merged.groupby(["lad_code_19", "lad_name_19"]).agg(
    mean_rank_15=("imd_rank_15", "mean"),
    mean_rank_19=("imd_rank_19", "mean"),
    mean_score_15=("imd_score_15", "mean"),
    mean_score_19=("imd_score_19", "mean"),
).reset_index()

# Rank the LADs by their mean IMD rank (lower mean rank = more deprived)
imd_lad["lad_rank_15"] = imd_lad["mean_rank_15"].rank()
imd_lad["lad_rank_19"] = imd_lad["mean_rank_19"].rank()
imd_lad["imd_rank_change"] = imd_lad["lad_rank_19"] - imd_lad["lad_rank_15"]
# Positive = moved toward less deprived (rank improved)

# Join with ADI LAD data
# Map IMD LAD codes to ADI LAD codes (ADI uses LAD25)
# For simplicity, join on LAD name since codes change across years
lad = imd_lad.merge(
    adi_cc_15[["LAD25CD", "LAD25NM", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_rate_15"}),
    left_on="lad_name_19", right_on="LAD25NM", how="inner",
)
lad = lad.merge(
    adi_cc_19[["LAD25CD", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_rate_19"}),
    on="LAD25CD", how="inner",
)
lad["cc_change"] = lad["cc_rate_19"] - lad["cc_rate_15"]

print(f"LADs matched: {len(lad)}")

# %% [markdown]
# ### LADs where IMD ranking improved but claimant rate increased

# %%
# IMD rank improved (positive change = less deprived)
# but claimant rate went up (more claimants per capita)
contradictions = lad[(lad["imd_rank_change"] > 0) & (lad["cc_change"] > 0)].sort_values("cc_change", ascending=False)

print(f"\n=== {len(contradictions)} LADs where IMD ranking improved but claimant rate INCREASED ===\n")
print(f"{'LAD':35s} {'IMD rank Δ':>12s} {'Claimant rate Δ':>16s} {'2015 rate':>10s} {'2019 rate':>10s}")
print("-" * 85)
for _, row in contradictions.head(15).iterrows():
    print(f"{row['lad_name_19']:35s} {row['imd_rank_change']:>+12.0f} {row['cc_change']:>+16.4f} {row['cc_rate_15']:>10.4f} {row['cc_rate_19']:>10.4f}")

# %% [markdown]
# ## 2. COVID-19 Impact: ADI captures what IMD cannot
#
# The IMD was last updated in 2019 (before 2025). It completely misses the
# COVID-19 pandemic's impact on deprivation. The ADI shows dramatic changes
# in claimant counts between 2019 and 2020.

# %%
adi_cc_20 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2020.csv")

covid = adi_cc_19[["LAD25CD", "LAD25NM", "claimant_count_rate"]].rename(
    columns={"claimant_count_rate": "rate_2019"}
).merge(
    adi_cc_20[["LAD25CD", "claimant_count_rate"]].rename(
        columns={"claimant_count_rate": "rate_2020"}
    ),
    on="LAD25CD",
)
covid["change"] = covid["rate_2020"] - covid["rate_2019"]
covid["pct_change"] = (covid["change"] / covid["rate_2019"]) * 100

print(f"=== COVID-19 Impact: Claimant Rate Changes 2019 → 2020 ===\n")
print(f"National: rate went from {covid['rate_2019'].mean():.4f} to {covid['rate_2020'].mean():.4f} "
      f"({covid['pct_change'].mean():+.1f}%)\n")

print(f"{'':35s} {'2019':>8s} {'2020':>8s} {'Change':>8s} {'%':>8s}")
print("-" * 69)

print(f"\nTop 10 LADs by absolute increase:")
for _, row in covid.sort_values("change", ascending=False).head(10).iterrows():
    print(f"{row['LAD25NM']:35s} {row['rate_2019']:>8.4f} {row['rate_2020']:>8.4f} {row['change']:>+8.4f} {row['pct_change']:>+7.1f}%")

print(f"\nBottom 5 LADs (smallest increase):")
for _, row in covid.sort_values("change").head(5).iterrows():
    print(f"{row['LAD25NM']:35s} {row['rate_2019']:>8.4f} {row['rate_2020']:>8.4f} {row['change']:>+8.4f} {row['pct_change']:>+7.1f}%")

print(f"\nThe IMD provides NO information about these changes — it was frozen at 2019 rankings.")

# %% [markdown]
# ## 3. Year-on-year ADI trends: Annual resolution the IMD cannot provide
#
# Show how claimant rates evolved across 2014-2024, revealing the COVID spike
# and recovery trajectory.

# %%
years = range(2014, 2025)
annual = []
for year in years:
    path = adi_lad_dir / "claimant_counts" / f"claimant_counts_{year}.csv"
    if path.exists():
        df = pd.read_csv(path)
        national_rate = df["claimant_count"].sum() / df["pop"].sum()
        annual.append({"year": year, "national_rate": national_rate})

annual_df = pd.DataFrame(annual)
print(f"=== National Claimant Rate Trend 2014-2024 ===\n")
print(f"{'Year':>6s} {'Rate':>8s} {'Change':>10s}")
print("-" * 26)
for i, row in annual_df.iterrows():
    change = f"{row['national_rate'] - annual_df.iloc[i-1]['national_rate']:+.4f}" if i > 0 else "     -"
    print(f"{int(row['year']):>6d} {row['national_rate']:>8.4f} {change:>10s}")

print(f"\nIMD data points in this period: 2015 and 2019 (just 2 snapshots vs ADI's {len(annual_df)} annual values)")

# %% [markdown]
# ## 4. LSOA-level contradictions
#
# Find specific neighbourhoods where IMD says "improving" but ADI says "worsening".

# %%
# Compare IMD 2015 vs 2019 at LSOA level with ADI
imd_lsoa = imd15[["LSOA11CD", "imd_rank_15"]].merge(
    imd19[["LSOA11CD", "imd_rank_19"]], on="LSOA11CD"
)
imd_lsoa["imd_rank_change"] = imd_lsoa["imd_rank_19"] - imd_lsoa["imd_rank_15"]

# Map to LSOA 2021
imd_lsoa = imd_lsoa.merge(xwalk_u, on="LSOA11CD")

# ADI at LSOA level
adi_lsoa_15 = pd.read_csv(adi_lsoa_dir / "claimant_counts" / "claimant_counts_2015.csv")
adi_lsoa_19 = pd.read_csv(adi_lsoa_dir / "claimant_counts" / "claimant_counts_2019.csv")

lsoa = imd_lsoa.merge(
    adi_lsoa_15[["LSOA21CD", "LSOA21NM", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_15"}),
    on="LSOA21CD",
).merge(
    adi_lsoa_19[["LSOA21CD", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_19"}),
    on="LSOA21CD",
)
lsoa["cc_change"] = lsoa["cc_19"] - lsoa["cc_15"]

contradictions_lsoa = lsoa[(lsoa["imd_rank_change"] > 500) & (lsoa["cc_change"] > 0.01)]
print(f"\n=== LSOA-level contradictions: IMD improved by 500+ ranks, claimant rate increased by 1%+ ===")
print(f"Found: {len(contradictions_lsoa)} LSOAs\n")

print(f"{'LSOA':30s} {'IMD Δrank':>10s} {'CC Δrate':>10s} {'CC 2015':>8s} {'CC 2019':>8s}")
print("-" * 70)
for _, row in contradictions_lsoa.sort_values("cc_change", ascending=False).head(10).iterrows():
    name = str(row.get("LSOA21NM", row["LSOA21CD"]))[:30]
    print(f"{name:30s} {row['imd_rank_change']:>+10.0f} {row['cc_change']:>+10.4f} {row['cc_15']:>8.4f} {row['cc_19']:>8.4f}")

# %% [markdown]
# ## Summary
#
# The ADI provides three capabilities the IMD cannot:
#
# 1. **Absolute levels**: Detects when deprivation increases uniformly
#    (IMD rankings are unchanged even if everyone gets worse)
# 2. **Annual resolution**: 11 years of data vs IMD's sporadic updates
#    (2015, 2019, 2025 — missing the COVID period entirely)
# 3. **Real-time sensitivity**: Captures shocks like COVID-19 immediately
#    in claimant count data (the 2019→2020 spike)
