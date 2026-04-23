# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Optimal ADI Weighting: Predicting IMD Rank
#
# Find the weighted combination of ADI columns that best correlates with
# the IMD overall rank. This reveals which ADI domains capture IMD-like
# deprivation variation, and how much of IMD can be "explained" by the ADI's
# three domains.
#
# We use IMD 2025 (LSOA 2021) as the target since it's the most recent
# and uses the same LSOA vintage as our ADI output.

# %%
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

repo_root = Path.cwd()
if repo_root.name in ("analysis", "nbs", "pts"):
    repo_root = repo_root.parent
while not (repo_root / "config").exists() and repo_root != repo_root.parent:
    repo_root = repo_root.parent

imd_dir = repo_root / "store" / "inputs" / "imd"
adi_dir = repo_root / "store" / "outputs" / "default" / "lsoa"

# %% [markdown]
# ## Load data

# %%
# IMD 2025
imd = pd.read_csv(imd_dir / "imd_2025.csv")
imd = imd.rename(columns={
    "LSOA code (2021)": "LSOA21CD",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank",
    "Index of Multiple Deprivation (IMD) Score": "imd_score",
})

# ADI 2024 (matching IMD 2025)
cc = pd.read_csv(adi_dir / "claimant_counts" / "claimant_counts_2024.csv")
cr = pd.read_csv(adi_dir / "crime" / "crime_2024.csv")

# Find matching health file
health_files = sorted((adi_dir / "health").glob("health_*_24.csv")) + sorted((adi_dir / "health").glob("health_2024_*.csv"))
h = pd.read_csv(health_files[0]) if health_files else None

print(f"Claimant counts: {len(cc)} LSOAs")
print(f"Crime: {len(cr)} LSOAs")
if h is not None:
    print(f"Health: {len(h)} LSOAs")
print(f"IMD 2025: {len(imd)} LSOAs")

# %% [markdown]
# ## Build feature matrix
#
# Collect all ADI rate columns as features, IMD rank as target.

# %%
# Start with claimant rate
features = cc[["LSOA21CD", "claimant_count_rate"]].copy()
features = features.rename(columns={"claimant_count_rate": "claimant_rate"})

# Add crime rates
crime_rate_cols = [c for c in cr.columns if c.endswith("_rate")]
features = features.merge(cr[["LSOA21CD"] + crime_rate_cols], on="LSOA21CD", how="inner")

# Add health rates
if h is not None:
    health_rate_cols = [c for c in h.columns if c.endswith("_afflicted_rate")]
    features = features.merge(h[["LSOA21CD"] + health_rate_cols], on="LSOA21CD", how="inner")

# Merge with IMD
df = features.merge(imd[["LSOA21CD", "imd_rank", "imd_score"]], on="LSOA21CD", how="inner")
print(f"\nMerged dataset: {len(df)} LSOAs")

feature_cols = [c for c in df.columns if c not in ("LSOA21CD", "LSOA21NM", "imd_rank", "imd_score")]
print(f"Features: {len(feature_cols)} ADI rate columns")
for c in feature_cols:
    print(f"  {c}")

# %% [markdown]
# ## Linear regression: ADI rates → IMD rank

# %%
X = df[feature_cols].fillna(0).values
y = df["imd_rank"].values

# Standardise features for comparable coefficients
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

reg = LinearRegression()
reg.fit(X_scaled, y)
y_pred = reg.predict(X_scaled)

# Spearman correlation of predicted vs actual rank
r_spearman = stats.spearmanr(y, y_pred).statistic
r_pearson = np.corrcoef(y, y_pred)[0, 1]
r2 = reg.score(X_scaled, y)

print(f"Linear regression: {len(feature_cols)} features -> IMD rank")
print(f"  R² = {r2:.4f}")
print(f"  Pearson r = {r_pearson:.4f}")
print(f"  Spearman r = {r_spearman:.4f}")

# %% [markdown]
# ## Feature importance (standardised coefficients)
#
# Larger absolute coefficient = more influence on predicted IMD rank.
# Negative coefficient = higher rate → lower rank number (more deprived).

# %%
coef_df = pd.DataFrame({
    "feature": feature_cols,
    "coefficient": reg.coef_,
    "abs_coefficient": np.abs(reg.coef_),
}).sort_values("abs_coefficient", ascending=False)

print(f"\nTop 15 features by importance (standardised coefficients):\n")
print(f"{'Feature':45s} {'Coefficient':>12s} {'|Coef|':>8s}")
print("-" * 67)
for _, row in coef_df.head(15).iterrows():
    print(f"{row['feature']:45s} {row['coefficient']:>12.1f} {row['abs_coefficient']:>8.1f}")

# %% [markdown]
# ## Domain-level analysis
#
# How much does each ADI domain (employment, crime, health) contribute?

# %%
domain_map = {}
for c in feature_cols:
    if "claimant" in c:
        domain_map[c] = "Employment"
    elif "afflicted" in c:
        domain_map[c] = "Health"
    else:
        domain_map[c] = "Crime"

domain_importance = {}
for domain in ["Employment", "Crime", "Health"]:
    cols = [c for c, d in domain_map.items() if d == domain]
    total = sum(abs(reg.coef_[feature_cols.index(c)]) for c in cols)
    domain_importance[domain] = total

total_importance = sum(domain_importance.values())
print(f"\nDomain contribution (share of total |coefficient|):\n")
for domain, imp in sorted(domain_importance.items(), key=lambda x: -x[1]):
    n_features = sum(1 for d in domain_map.values() if d == domain)
    print(f"  {domain:15s}: {imp/total_importance*100:5.1f}%  ({n_features} features)")

# %% [markdown]
# ## Comparison: simple baselines vs full model

# %%
print(f"\n{'Model':50s} {'Spearman r':>12s}")
print("-" * 64)

# Full model
print(f"{'All ADI features (' + str(len(feature_cols)) + ')':50s} {r_spearman:>12.4f}")

# Claimant rate only
r_cc = stats.spearmanr(df["claimant_rate"].rank(ascending=False), df["imd_rank"]).statistic
print(f"{'Claimant rate only':50s} {r_cc:>12.4f}")

# Crime total rate only
total_crime_rate = df[[c for c in crime_rate_cols]].sum(axis=1)
r_cr = stats.spearmanr(total_crime_rate.rank(ascending=False), df["imd_rank"]).statistic
print(f"{'Total crime rate only':50s} {r_cr:>12.4f}")

# Claimant + crime
simple_score = df["claimant_rate"].rank(pct=True) + total_crime_rate.rank(pct=True)
r_simple = stats.spearmanr(simple_score.rank(ascending=False), df["imd_rank"]).statistic
print(f"{'Claimant + crime (equal weight)':50s} {r_simple:>12.4f}")

# Claimant + crime + depression (old ADI formula)
if "DEP_afflicted_rate" in df.columns and "MH_afflicted_rate" in df.columns:
    old_adi = df["claimant_rate"] + total_crime_rate + df["DEP_afflicted_rate"] + df["MH_afflicted_rate"]
    r_old = stats.spearmanr(old_adi.rank(ascending=False), df["imd_rank"]).statistic
    print(f"{'Old ADI formula (claimant+crime+DEP+MH)':50s} {r_old:>12.4f}")
