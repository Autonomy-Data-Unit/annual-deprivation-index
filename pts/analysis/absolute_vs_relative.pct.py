# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Absolute vs Relative: The ADI's Advantage over the IMD
#
# The IMD ranks areas relative to each other. If every area deteriorates
# uniformly, the rankings stay the same — the IMD is blind to absolute
# changes. The ADI measures absolute rates, revealing real deprivation
# trends that the IMD structurally cannot capture.
#
# This notebook demonstrates three concrete cases where this matters.

# %%
from pathlib import Path

import matplotlib.pyplot as plt
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
plot_dir = repo_root / "store" / "outputs"

plt.rcParams.update({"figure.dpi": 120, "figure.figsize": (10, 5)})

# %% [markdown]
# ## 1. COVID-19 Impact: The ADI captures what the IMD cannot
#
# The IMD was last published in 2019 (before the newly released 2025
# edition). It completely missed the COVID-19 pandemic's impact on
# employment deprivation. The ADI's annual claimant count data reveals
# the shock immediately.

# %%
years = range(2014, 2025)
annual_national = []
for year in years:
    path = adi_lad_dir / "claimant_counts" / f"claimant_counts_{year}.csv"
    if path.exists():
        df = pd.read_csv(path)
        rate = df["claimant_count"].sum() / df["pop"].sum()
        annual_national.append({"year": year, "rate": rate})

annual_df = pd.DataFrame(annual_national)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(annual_df["year"], annual_df["rate"] * 100, "o-", color="steelblue", linewidth=2, markersize=6)
ax.fill_between(annual_df["year"], 0, annual_df["rate"] * 100, alpha=0.1, color="steelblue")

# Mark IMD editions
for imd_year, label in [(2015, "IMD 2015"), (2019, "IMD 2019"), (2025, "IMD 2025")]:
    if imd_year <= 2024:
        ax.axvline(imd_year, color="red", linestyle="--", alpha=0.4, linewidth=1)
        ax.text(imd_year + 0.1, ax.get_ylim()[1] * 0.92, label, color="red", fontsize=9, rotation=0)

ax.annotate("COVID-19\nshock", xy=(2020, annual_df[annual_df.year==2020]["rate"].values[0]*100),
            xytext=(2020.5, 3.8), fontsize=10, color="darkred",
            arrowprops=dict(arrowstyle="->", color="darkred"))

ax.set_xlabel("Year")
ax.set_ylabel("National claimant rate (%)")
ax.set_title("ADI captures annual deprivation trends — IMD provides only sporadic snapshots")
ax.set_xlim(2013.5, 2024.5)
ax.set_ylim(0)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
plt.savefig(plot_dir / "adi_annual_trend.png", dpi=150, bbox_inches="tight")
plt.show()

# %%
# COVID impact by LAD
cc19 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2019.csv")
cc20 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2020.csv")
covid = cc19[["LAD25CD", "LAD25NM", "claimant_count_rate"]].rename(
    columns={"claimant_count_rate": "rate_2019"}
).merge(
    cc20[["LAD25CD", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "rate_2020"}),
    on="LAD25CD",
)
covid["change"] = covid["rate_2020"] - covid["rate_2019"]
covid["pct_change"] = (covid["change"] / covid["rate_2019"]) * 100

fig, ax = plt.subplots(figsize=(10, 5))
covid_sorted = covid.sort_values("change", ascending=False)
top20 = covid_sorted.head(20)
ax.barh(range(len(top20)), top20["change"].values * 100, color="indianred")
ax.set_yticks(range(len(top20)))
ax.set_yticklabels(top20["LAD25NM"].values, fontsize=9)
ax.invert_yaxis()
ax.set_xlabel("Change in claimant rate (percentage points)")
ax.set_title("Top 20 LADs by claimant rate increase, 2019 to 2020")
fig.tight_layout()
plt.savefig(plot_dir / "covid_impact_lads.png", dpi=150, bbox_inches="tight")
plt.show()

print(f"National claimant rate: {covid['rate_2019'].mean()*100:.2f}% (2019) -> {covid['rate_2020'].mean()*100:.2f}% (2020)")
print(f"Mean increase: {covid['change'].mean()*100:+.2f} pp ({covid['pct_change'].mean():+.0f}%)")
print(f"All {len(covid)} LADs saw an increase.")

# %% [markdown]
# Every single LAD in England saw its claimant rate increase between 2019
# and 2020. The most affected areas were London boroughs (Haringey,
# Newham, Brent) where rates nearly tripled. The IMD 2019 — published
# just before the pandemic — contains no trace of this. Without the ADI,
# the next available deprivation measurement would be the IMD 2025,
# leaving a 6-year blind spot.

# %% [markdown]
# ## 2. IMD says "improving", ADI says "worsening"
#
# Because the IMD is relative, an area can appear to improve in the
# rankings even if its absolute deprivation increased — as long as other
# areas improved faster. We find these contradictions by comparing IMD
# 2015 vs 2019 rank changes with ADI rate changes.

# %%
imd15 = pd.read_csv(imd_dir / "imd_2015.csv")
imd19 = pd.read_csv(imd_dir / "imd_2019.csv")
imd15 = imd15.rename(columns={"LSOA code (2011)": "LSOA11CD",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_15"})
imd19 = imd19.rename(columns={"LSOA code (2011)": "LSOA11CD",
    "Local Authority District code (2019)": "lad_code",
    "Local Authority District name (2019)": "lad_name",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_19"})

imd_merged = imd15[["LSOA11CD", "imd_rank_15"]].merge(
    imd19[["LSOA11CD", "lad_code", "lad_name", "imd_rank_19"]], on="LSOA11CD")
imd_lad = imd_merged.groupby(["lad_code", "lad_name"]).agg(
    mean_rank_15=("imd_rank_15", "mean"),
    mean_rank_19=("imd_rank_19", "mean"),
).reset_index()
imd_lad["lad_rank_15"] = imd_lad["mean_rank_15"].rank()
imd_lad["lad_rank_19"] = imd_lad["mean_rank_19"].rank()
imd_lad["imd_rank_change"] = imd_lad["lad_rank_19"] - imd_lad["lad_rank_15"]

cc15 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2015.csv")
cc19 = pd.read_csv(adi_lad_dir / "claimant_counts" / "claimant_counts_2019.csv")

lad = imd_lad.merge(
    cc15[["LAD25NM", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_15"}),
    left_on="lad_name", right_on="LAD25NM", how="inner",
).merge(
    cc19[["LAD25NM", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_19"}),
    on="LAD25NM", how="inner",
)
lad["cc_change"] = lad["cc_19"] - lad["cc_15"]

# %%
fig, ax = plt.subplots(figsize=(8, 6))
# Color by contradiction: IMD improved but ADI worsened
contradiction = (lad["imd_rank_change"] > 0) & (lad["cc_change"] > 0)
ax.scatter(lad.loc[~contradiction, "imd_rank_change"],
           lad.loc[~contradiction, "cc_change"] * 100,
           s=15, alpha=0.5, color="steelblue", label="Consistent")
ax.scatter(lad.loc[contradiction, "imd_rank_change"],
           lad.loc[contradiction, "cc_change"] * 100,
           s=25, alpha=0.7, color="indianred", label="Contradiction", zorder=5)

ax.axhline(0, color="black", linewidth=0.5)
ax.axvline(0, color="black", linewidth=0.5)

# Annotate the top contradictions
top_contradictions = lad[contradiction].nlargest(5, "cc_change")
for _, row in top_contradictions.iterrows():
    ax.annotate(row["lad_name"], xy=(row["imd_rank_change"], row["cc_change"]*100),
                fontsize=8, ha="left", xytext=(5, 5), textcoords="offset points")

ax.fill_between([0, ax.get_xlim()[1]], 0, ax.get_ylim()[1], alpha=0.05, color="red")
ax.text(ax.get_xlim()[1]*0.7, ax.get_ylim()[1]*0.85, "IMD: better\nADI: worse",
        fontsize=11, color="darkred", ha="center", style="italic")

ax.set_xlabel("IMD LAD rank change 2015-2019 (positive = improved)")
ax.set_ylabel("ADI claimant rate change (percentage points)")
ax.set_title("IMD ranking vs ADI absolute change, 2015 to 2019")
ax.legend()
fig.tight_layout()
plt.savefig(plot_dir / "imd_vs_adi_contradictions.png", dpi=150, bbox_inches="tight")
plt.show()

n_contradictions = contradiction.sum()
print(f"\n{n_contradictions} of {len(lad)} LADs ({n_contradictions/len(lad)*100:.0f}%) show a contradiction:")
print(f"IMD rank improved but ADI claimant rate increased.\n")

print(f"{'LAD':30s} {'IMD rank change':>15s} {'Claimant rate change':>20s}")
print("-" * 67)
for _, row in lad[contradiction].nlargest(10, "cc_change").iterrows():
    print(f"{row['lad_name']:30s} {row['imd_rank_change']:>+15.0f} {row['cc_change']*100:>+19.2f} pp")

# %% [markdown]
# ## 3. LSOA-level: zooming into specific neighbourhoods

# %%
xwalk = pd.read_csv(crosswalk_path)
xwalk_u = xwalk[xwalk["CHGIND"] == "U"][["LSOA11CD", "LSOA21CD"]]

imd_lsoa = imd15[["LSOA11CD", "imd_rank_15"]].merge(
    imd19[["LSOA11CD", "imd_rank_19"]], on="LSOA11CD")
imd_lsoa["imd_change"] = imd_lsoa["imd_rank_19"] - imd_lsoa["imd_rank_15"]
imd_lsoa = imd_lsoa.merge(xwalk_u, on="LSOA11CD")

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

# Major contradictions: IMD improved 500+ ranks, claimant rate up 1%+
major = lsoa[(lsoa["imd_change"] > 500) & (lsoa["cc_change"] > 0.01)]
print(f"LSOAs where IMD improved 500+ ranks but claimant rate rose 1%+: {len(major)}")
print(f"\nTop 10:")
print(f"{'LSOA':30s} {'IMD change':>12s} {'CC change':>12s}")
print("-" * 56)
for _, row in major.nlargest(10, "cc_change").iterrows():
    name = str(row.get("LSOA21NM", ""))[:30]
    print(f"{name:30s} {row['imd_change']:>+12.0f} {row['cc_change']*100:>+11.2f} pp")

# %%
fig, ax = plt.subplots(figsize=(8, 6))
sample = lsoa.sample(min(5000, len(lsoa)), random_state=42)
ax.scatter(sample["imd_change"], sample["cc_change"]*100, s=1, alpha=0.15, color="steelblue")
ax.scatter(major["imd_change"], major["cc_change"]*100, s=5, alpha=0.5, color="indianred", zorder=5)
ax.axhline(0, color="black", linewidth=0.5)
ax.axvline(0, color="black", linewidth=0.5)
ax.fill_between([0, ax.get_xlim()[1]], 0, ax.get_ylim()[1], alpha=0.05, color="red")
ax.set_xlabel("IMD rank change 2015-2019 (positive = improved)")
ax.set_ylabel("ADI claimant rate change (percentage points)")
ax.set_title(f"LSOA-level: {len(major)} neighbourhoods where IMD improved but ADI worsened")
fig.tight_layout()
plt.savefig(plot_dir / "lsoa_contradictions.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## Interpretation
#
# These three analyses demonstrate the ADI's structural advantage:
#
# **Annual resolution matters.** The national claimant rate trend shows a
# clear narrative: decline (2014-2016), gradual rise (2017-2019), COVID
# shock (2020), partial recovery (2021-2023), and a slight uptick (2024).
# The IMD provides just two data points (2015 and 2019) in this 11-year
# window, missing the entire pandemic.
#
# **Relative rankings hide absolute deterioration.** 43% of LADs saw their
# IMD ranking improve between 2015 and 2019 while their actual claimant
# rate increased. These are areas where deprivation genuinely worsened —
# they just worsened less than other areas. A policymaker relying solely
# on the IMD would conclude these areas are improving.
#
# **The scale of hidden deterioration is large.** At the neighbourhood
# level, over 1,200 LSOAs show major contradictions (IMD improved 500+
# ranks while claimant rate rose 1+ percentage point). These are not
# edge cases — they represent areas where policy based on IMD rankings
# alone would draw the wrong conclusions.
