# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # ADI vs IMD: Rank Correlation Analysis
#
# Compare the Annual Deprivation Index (ADI) with the Index of Multiple
# Deprivation (IMD) at the LSOA level. The ADI provides annual absolute
# rates across three domains; the IMD provides relative ranks across seven
# domains, updated every few years.
#
# We compare:
# - **IMD 2025** (LSOA 2021) vs ADI 2024 — direct join
# - **IMD 2019** (LSOA 2011) vs ADI 2019 — via crosswalk
# - **IMD 2015** (LSOA 2011) vs ADI 2015 — via crosswalk
#
# Metrics: Spearman rank correlation, Kendall's tau.

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
adi_dir = repo_root / "store" / "outputs" / "default" / "lsoa"
crosswalk_path = repo_root / "store" / "inputs" / "crosswalk" / "lsoa11_to_lsoa21.csv"

# %% [markdown]
# ## Helper functions

# %%
def load_adi_for_year(year: int) -> pd.DataFrame:
    """Load and merge all ADI domains for a given calendar year at LSOA level."""
    cc = pd.read_csv(adi_dir / "claimant_counts" / f"claimant_counts_{year}.csv")
    cr = pd.read_csv(adi_dir / "crime" / f"crime_{year}.csv")

    # Health uses QOF year — find the matching file
    health_files = sorted((adi_dir / "health").glob("health_*.csv"))
    # QOF year ending in this calendar year (e.g. 2024 -> health_2023_24.csv)
    h_file = None
    for f in health_files:
        if f.stem.endswith(f"_{year % 100:02d}"):
            h_file = f
            break
    if h_file is None:
        # Try QOF year starting in this year
        for f in health_files:
            if f"_{year}_" in f.stem or f.stem.startswith(f"health_{year}"):
                h_file = f
                break

    merged = cc[["LSOA21CD", "LSOA21NM", "claimant_count_rate", "pop"]].copy()
    merged = merged.rename(columns={"claimant_count_rate": "adi_claimant_rate"})

    # Total crime rate
    crime_count_cols = [c for c in cr.columns if c not in ("LSOA21CD", "LSOA21NM", "pop") and "_rate" not in c]
    cr["total_crime"] = cr[crime_count_cols].sum(axis=1)
    cr["adi_crime_rate"] = cr["total_crime"] / cr["pop"].replace(0, np.nan)
    merged = merged.merge(cr[["LSOA21CD", "adi_crime_rate"]], on="LSOA21CD", how="inner")

    if h_file is not None:
        h = pd.read_csv(h_file)
        # After crosswalk, health columns are {disease}_afflicted and {disease}_afflicted_rate
        health_rate_cols = [c for c in h.columns if c.endswith("_afflicted_rate")]
        h_subset = h[["LSOA21CD"] + health_rate_cols].copy()
        h_subset = h_subset.rename(columns={c: f"adi_{c}" for c in health_rate_cols})
        if "adi_DEP_afflicted_rate" in h_subset.columns:
            h_subset["adi_dep_rate"] = h_subset["adi_DEP_afflicted_rate"]
        if "adi_MH_afflicted_rate" in h_subset.columns:
            h_subset["adi_mh_rate"] = h_subset["adi_MH_afflicted_rate"]
        merged = merged.merge(h_subset, on="LSOA21CD", how="inner")

    return merged


def load_imd(edition: str) -> pd.DataFrame:
    """Load IMD data with standardised column names."""
    df = pd.read_csv(imd_dir / f"imd_{edition}.csv")
    lsoa_col = [c for c in df.columns if c.startswith("LSOA code")][0]
    df = df.rename(columns={
        lsoa_col: "lsoa_code",
        "Index of Multiple Deprivation (IMD) Score": "imd_score",
        "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank",
        "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)": "imd_decile",
        "Employment Score (rate)": "imd_employment_score",
        "Employment Rank (where 1 is most deprived)": "imd_employment_rank",
        "Crime Score": "imd_crime_score",
        "Crime Rank (where 1 is most deprived)": "imd_crime_rank",
        "Health Deprivation and Disability Score": "imd_health_score",
        "Health Deprivation and Disability Rank (where 1 is most deprived)": "imd_health_rank",
        "Income Score (rate)": "imd_income_score",
        "Income Rank (where 1 is most deprived)": "imd_income_rank",
    })
    return df


def correlate(x, y, label=""):
    """Compute and print Spearman and Kendall correlations."""
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    spearman = stats.spearmanr(valid["x"], valid["y"])
    kendall = stats.kendalltau(valid["x"], valid["y"])
    print(f"  {label:45s}  Spearman r={spearman.statistic:.4f}  Kendall tau={kendall.statistic:.4f}  (n={len(valid)})")
    return spearman.statistic

# %% [markdown]
# ## IMD 2025 vs ADI 2024
#
# Both at LSOA 2021 — direct join.

# %%
imd25 = load_imd("2025")
adi24 = load_adi_for_year(2024)
m25 = adi24.merge(imd25, left_on="LSOA21CD", right_on="lsoa_code", how="inner")
print(f"IMD 2025 vs ADI 2024: {len(m25)} matched LSOAs\n")

# Rank the ADI values (higher rate = more deprived = lower rank number)
m25["adi_claimant_rank"] = m25["adi_claimant_rate"].rank(ascending=False)
m25["adi_crime_rank"] = m25["adi_crime_rate"].rank(ascending=False)
if "adi_dep_rate" in m25.columns:
    m25["adi_dep_rank"] = m25["adi_dep_rate"].rank(ascending=False)
if "adi_mh_rate" in m25.columns:
    m25["adi_mh_rank"] = m25["adi_mh_rate"].rank(ascending=False)

print("ADI domain rank vs IMD overall rank:")
correlate(m25["adi_claimant_rank"], m25["imd_rank"], "Claimant count rank vs IMD rank")
correlate(m25["adi_crime_rank"], m25["imd_rank"], "Crime rate rank vs IMD rank")
if "adi_dep_rank" in m25.columns:
    correlate(m25["adi_dep_rank"], m25["imd_rank"], "Depression rate rank vs IMD rank")

print("\nADI domain rank vs matching IMD domain rank:")
correlate(m25["adi_claimant_rank"], m25["imd_employment_rank"], "Claimant rank vs IMD Employment rank")
correlate(m25["adi_crime_rank"], m25["imd_crime_rank"], "Crime rank vs IMD Crime rank")
if "adi_dep_rank" in m25.columns:
    correlate(m25["adi_dep_rank"], m25["imd_health_rank"], "Depression rank vs IMD Health rank")

# %% [markdown]
# ## IMD 2019 vs ADI 2019
#
# IMD 2019 uses LSOA 2011. Our ADI output is at LSOA 2021 (after crosswalk).
# Join via the LSOA 2011→2021 crosswalk (unchanged LSOAs only for clean comparison).

# %%
xwalk = pd.read_csv(crosswalk_path)
xwalk_u = xwalk[xwalk["CHGIND"] == "U"][["LSOA11CD", "LSOA21CD"]]

imd19 = load_imd("2019")
adi19 = load_adi_for_year(2019)

# Join: IMD (LSOA11) -> crosswalk -> ADI (LSOA21)
imd19_with_lsoa21 = imd19.merge(xwalk_u, left_on="lsoa_code", right_on="LSOA11CD", how="inner")
m19 = adi19.merge(imd19_with_lsoa21, on="LSOA21CD", how="inner")
print(f"\nIMD 2019 vs ADI 2019: {len(m19)} matched LSOAs (unchanged only)\n")

m19["adi_claimant_rank"] = m19["adi_claimant_rate"].rank(ascending=False)
m19["adi_crime_rank"] = m19["adi_crime_rate"].rank(ascending=False)
if "adi_dep_rate" in m19.columns:
    m19["adi_dep_rank"] = m19["adi_dep_rate"].rank(ascending=False)

print("ADI domain rank vs IMD overall rank:")
correlate(m19["adi_claimant_rank"], m19["imd_rank"], "Claimant rank vs IMD rank")
correlate(m19["adi_crime_rank"], m19["imd_rank"], "Crime rank vs IMD rank")
if "adi_dep_rank" in m19.columns:
    correlate(m19["adi_dep_rank"], m19["imd_rank"], "Depression rank vs IMD rank")

print("\nADI domain rank vs matching IMD domain rank:")
correlate(m19["adi_claimant_rank"], m19["imd_employment_rank"], "Claimant rank vs IMD Employment rank")
correlate(m19["adi_crime_rank"], m19["imd_crime_rank"], "Crime rank vs IMD Crime rank")
if "adi_dep_rank" in m19.columns:
    correlate(m19["adi_dep_rank"], m19["imd_health_rank"], "Depression rank vs IMD Health rank")

# %% [markdown]
# ## IMD 2015 vs ADI 2015

# %%
imd15 = load_imd("2015")
adi15 = load_adi_for_year(2015)

imd15_with_lsoa21 = imd15.merge(xwalk_u, left_on="lsoa_code", right_on="LSOA11CD", how="inner")
m15 = adi15.merge(imd15_with_lsoa21, on="LSOA21CD", how="inner")
print(f"\nIMD 2015 vs ADI 2015: {len(m15)} matched LSOAs (unchanged only)\n")

m15["adi_claimant_rank"] = m15["adi_claimant_rate"].rank(ascending=False)
m15["adi_crime_rank"] = m15["adi_crime_rate"].rank(ascending=False)
if "adi_dep_rate" in m15.columns:
    m15["adi_dep_rank"] = m15["adi_dep_rate"].rank(ascending=False)

print("ADI domain rank vs IMD overall rank:")
correlate(m15["adi_claimant_rank"], m15["imd_rank"], "Claimant rank vs IMD rank")
correlate(m15["adi_crime_rank"], m15["imd_rank"], "Crime rank vs IMD rank")
if "adi_dep_rank" in m15.columns:
    correlate(m15["adi_dep_rank"], m15["imd_rank"], "Depression rank vs IMD rank")

print("\nADI domain rank vs matching IMD domain rank:")
correlate(m15["adi_claimant_rank"], m15["imd_employment_rank"], "Claimant rank vs IMD Employment rank")
correlate(m15["adi_crime_rank"], m15["imd_crime_rank"], "Crime rank vs IMD Crime rank")
if "adi_dep_rank" in m15.columns:
    correlate(m15["adi_dep_rank"], m15["imd_health_rank"], "Depression rank vs IMD Health rank")

# %% [markdown]
# ## Summary table

# %%
print("\n=== Summary: Spearman rank correlations (ADI domain vs matching IMD domain) ===\n")
print(f"{'Comparison':50s} {'2015':>8s} {'2019':>8s} {'2025':>8s}")
print("-" * 76)

for label, adi_col, imd_col in [
    ("Claimant rank vs IMD Employment rank", "adi_claimant_rank", "imd_employment_rank"),
    ("Crime rank vs IMD Crime rank", "adi_crime_rank", "imd_crime_rank"),
    ("Depression rank vs IMD Health rank", "adi_dep_rank", "imd_health_rank"),
]:
    vals = []
    for m in [m15, m19, m25]:
        if adi_col in m.columns and imd_col in m.columns:
            v = pd.DataFrame({"x": m[adi_col], "y": m[imd_col]}).dropna()
            r = stats.spearmanr(v["x"], v["y"]).statistic
            vals.append(f"{r:.4f}")
        else:
            vals.append("   N/A")
    print(f"{label:50s} {vals[0]:>8s} {vals[1]:>8s} {vals[2]:>8s}")
