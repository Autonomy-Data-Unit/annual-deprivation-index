# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Validation: Crosswalk Conservation
#
# The aggregate node converts domain outputs from LSOA 2011 to LSOA 2021
# using a population-weighted crosswalk. This notebook verifies:
#
# 1. **Count conservation:** total counts before crosswalk (LSOA 2011)
#    ≈ total counts after (LSOA 2021). Small differences are expected from
#    excluded complex-change (X) LSOAs.
# 2. **Population conservation:** same check for population totals.
# 3. **Unchanged LSOA identity:** for the ~33,647 unchanged (U) LSOAs,
#    values should be identical before and after.
# 4. **Split LSOA weights:** for split (S) LSOAs, disaggregated counts
#    should sum back to the original LSOA 2011 count.

# %%
from pathlib import Path

import numpy as np
import pandas as pd

repo_root = Path.cwd()
if repo_root.name in ("validation", "nbs", "pts"):
    repo_root = repo_root.parent
while not (repo_root / "config").exists() and repo_root != repo_root.parent:
    repo_root = repo_root.parent

pipeline_dir = repo_root / "store" / "pipeline" / "default"
output_dir = repo_root / "store" / "outputs" / "default" / "lsoa"
crosswalk_path = repo_root / "store" / "inputs" / "crosswalk" / "lsoa11_to_lsoa21.csv"

xwalk = pd.read_csv(crosswalk_path)

print("Crosswalk change indicator counts:")
print(xwalk["CHGIND"].value_counts().to_string())
print(f"\nTotal LSOA 2011: {xwalk['LSOA11CD'].nunique()}")
print(f"Total LSOA 2021: {xwalk['LSOA21CD'].nunique()}")

# %% [markdown]
# ## 1. Claimant counts — crosswalk conservation

# %%
def compare_pre_post_crosswalk(domain: str, pipeline_file: str, output_file: str,
                                count_cols_11: list[str], count_cols_21: list[str]):
    """Compare totals before and after crosswalk."""
    pre = pd.read_csv(pipeline_dir / domain / pipeline_file)
    post = pd.read_csv(output_dir / domain / output_file)

    # Identify excluded LSOAs (complex change X)
    x_lsoas = set(xwalk[xwalk["CHGIND"] == "X"]["LSOA11CD"])
    pre_excl = pre[~pre["LSOA11CD"].isin(x_lsoas)]

    results = []
    for col_11, col_21 in zip(count_cols_11, count_cols_21):
        pre_total = pre[col_11].sum()
        pre_excl_total = pre_excl[col_11].sum()
        post_total = post[col_21].sum()
        diff_pct = (post_total - pre_excl_total) / pre_excl_total * 100 if pre_excl_total != 0 else 0
        results.append({
            "column": col_11,
            "pre_crosswalk (all)": pre_total,
            "pre_crosswalk (excl X)": pre_excl_total,
            "post_crosswalk": post_total,
            "diff_pct": diff_pct,
            "excluded_X_count": pre_total - pre_excl_total,
        })

    # Population
    pre_pop = pre["pop"].sum()
    pre_excl_pop = pre_excl["pop"].sum()
    post_pop = post["pop"].sum()
    pop_diff = (post_pop - pre_excl_pop) / pre_excl_pop * 100 if pre_excl_pop != 0 else 0
    results.append({
        "column": "pop",
        "pre_crosswalk (all)": pre_pop,
        "pre_crosswalk (excl X)": pre_excl_pop,
        "post_crosswalk": post_pop,
        "diff_pct": pop_diff,
        "excluded_X_count": pre_pop - pre_excl_pop,
    })

    df = pd.DataFrame(results)
    print(f"\nPre/post crosswalk comparison:")
    print(df.to_string(index=False))
    return df


year = 2024
print(f"=== Claimant counts {year} ===")
compare_pre_post_crosswalk(
    "claimant_counts", f"claimant_counts_{year}.csv", f"claimant_counts_{year}.csv",
    ["claimant_count"], ["claimant_count"],
)

# %% [markdown]
# ## 2. Crime — crosswalk conservation

# %%
pre_crime = pd.read_csv(pipeline_dir / "crime" / f"crime_{year}.csv")
crime_count_cols = [c for c in pre_crime.columns
                    if c not in ("LSOA11CD", "LSOA11NM", "pop") and "_rate" not in c]
print(f"=== Crime {year} ===")
compare_pre_post_crosswalk(
    "crime", f"crime_{year}.csv", f"crime_{year}.csv",
    crime_count_cols, crime_count_cols,
)

# %% [markdown]
# ## 3. Health — crosswalk conservation

# %%
pre_health = pd.read_csv(pipeline_dir / "health" / "health_2023_24.csv")
health_count_cols_11 = [c for c in pre_health.columns if c.endswith("_afflicted")]
print("=== Health 2023-24 ===")
compare_pre_post_crosswalk(
    "health", "health_2023_24.csv", "health_2023_24.csv",
    health_count_cols_11, health_count_cols_11,
)

# %% [markdown]
# ## 4. Unchanged (U) LSOAs — exact match
#
# For LSOAs that didn't change between 2011 and 2021 (CHGIND == "U"),
# the values should be identical before and after the crosswalk.

# %%
u_lsoas = xwalk[xwalk["CHGIND"] == "U"][["LSOA11CD", "LSOA21CD"]]


def check_unchanged_identity(domain: str, pipeline_file: str, output_file: str,
                              col_11: str, col_21: str):
    """For unchanged LSOAs, pre-crosswalk value should equal post-crosswalk value."""
    pre = pd.read_csv(pipeline_dir / domain / pipeline_file)
    post = pd.read_csv(output_dir / domain / output_file)

    merged = (
        u_lsoas
        .merge(pre[["LSOA11CD", col_11]].rename(columns={col_11: "val_pre"}),
               on="LSOA11CD", how="inner")
        .merge(post[["LSOA21CD", col_21]].rename(columns={col_21: "val_post"}),
               on="LSOA21CD", how="inner")
    )
    diffs = (merged["val_pre"] - merged["val_post"]).abs()
    max_diff = diffs.max()
    n_mismatches = (diffs > 1e-10).sum()
    return {
        "column": col_11,
        "n_unchanged": len(merged),
        "n_mismatches": n_mismatches,
        "max_abs_diff": max_diff,
        "pass": n_mismatches == 0,
    }


results = []

# Claimant
results.append(check_unchanged_identity(
    "claimant_counts", f"claimant_counts_{year}.csv", f"claimant_counts_{year}.csv",
    "claimant_count", "claimant_count",
))
results.append(check_unchanged_identity(
    "claimant_counts", f"claimant_counts_{year}.csv", f"claimant_counts_{year}.csv",
    "pop", "pop",
))

# Crime — total crime
pre_crime = pd.read_csv(pipeline_dir / "crime" / f"crime_{year}.csv")
post_crime = pd.read_csv(output_dir / "crime" / f"crime_{year}.csv")
pre_crime["total_crime"] = pre_crime[crime_count_cols].sum(axis=1)
post_crime_count_cols = [c for c in post_crime.columns
                         if c not in ("LSOA21CD", "LSOA21NM", "pop") and "_rate" not in c]
post_crime["total_crime"] = post_crime[post_crime_count_cols].sum(axis=1)

merged_crime = (
    u_lsoas
    .merge(pre_crime[["LSOA11CD", "total_crime"]], on="LSOA11CD", how="inner")
    .merge(post_crime[["LSOA21CD", "total_crime"]], on="LSOA21CD", how="inner",
           suffixes=("_pre", "_post"))
)
diffs = (merged_crime["total_crime_pre"] - merged_crime["total_crime_post"]).abs()
results.append({
    "column": "total_crime",
    "n_unchanged": len(merged_crime),
    "n_mismatches": (diffs > 1e-10).sum(),
    "max_abs_diff": diffs.max(),
    "pass": (diffs > 1e-10).sum() == 0,
})

# Health — spot check a few diseases
for disease in ["DM", "CHD", "DEP", "COPD"]:
    col = f"{disease}_afflicted"
    if col in pre_health.columns:
        results.append(check_unchanged_identity(
            "health", "health_2023_24.csv", "health_2023_24.csv",
            col, col,
        ))

results_df = pd.DataFrame(results)
all_pass = results_df["pass"].all()
print(f"\nUnchanged LSOA identity check: {'ALL PASSED' if all_pass else 'FAILURES DETECTED'}")
print(results_df.to_string(index=False))

# %% [markdown]
# ## 5. Split (S) LSOA weight check
#
# For split LSOAs (one LSOA 2011 → multiple LSOA 2021), the sum of
# disaggregated counts across the daughter LSOAs should approximately
# equal the original parent count.

# %%
s_lsoas = xwalk[xwalk["CHGIND"] == "S"]
split_parents = s_lsoas["LSOA11CD"].unique()
print(f"Split LSOAs: {len(split_parents)} parents → {len(s_lsoas)} daughters")

# Check claimant counts
pre_cc = pd.read_csv(pipeline_dir / "claimant_counts" / f"claimant_counts_{year}.csv")
post_cc = pd.read_csv(output_dir / "claimant_counts" / f"claimant_counts_{year}.csv")

parent_totals = pre_cc[pre_cc["LSOA11CD"].isin(split_parents)].set_index("LSOA11CD")["claimant_count"]

daughter_totals = (
    s_lsoas[["LSOA11CD", "LSOA21CD"]]
    .merge(post_cc[["LSOA21CD", "claimant_count"]], on="LSOA21CD", how="left")
    .groupby("LSOA11CD")["claimant_count"]
    .sum()
)

# Compare
comparison = pd.DataFrame({
    "parent_count": parent_totals,
    "daughter_sum": daughter_totals,
}).dropna()
comparison["diff"] = (comparison["parent_count"] - comparison["daughter_sum"]).abs()
comparison["pct_diff"] = comparison["diff"] / comparison["parent_count"].replace(0, np.nan) * 100

print(f"\nSplit LSOA claimant count conservation ({len(comparison)} parents):")
print(f"  Max absolute diff: {comparison['diff'].max():.6f}")
print(f"  Mean absolute diff: {comparison['diff'].mean():.6f}")
print(f"  Max % diff: {comparison['pct_diff'].max():.4f}%")
print(f"  Parents with diff > 1%: {(comparison['pct_diff'] > 1).sum()}")

# %% [markdown]
# ## 6. Full time-series crosswalk conservation
#
# Run the total conservation check across all years.

# %%
ts_results = []

for f in sorted((pipeline_dir / "claimant_counts").glob("claimant_counts_*.csv")):
    year_str = f.stem.split("_")[-1]
    pre = pd.read_csv(f)
    out_path = output_dir / "claimant_counts" / f.name
    if not out_path.exists():
        continue
    post = pd.read_csv(out_path)
    x_lsoas = set(xwalk[xwalk["CHGIND"] == "X"]["LSOA11CD"])
    pre_excl = pre[~pre["LSOA11CD"].isin(x_lsoas)]
    pre_sum = pre_excl["claimant_count"].sum()
    post_sum = post["claimant_count"].sum()
    ts_results.append({
        "domain": "claimant",
        "year": year_str,
        "pre_sum": pre_sum,
        "post_sum": post_sum,
        "diff_pct": (post_sum - pre_sum) / pre_sum * 100 if pre_sum != 0 else 0,
    })

for f in sorted((pipeline_dir / "crime").glob("crime_*.csv")):
    year_str = f.stem.split("_")[-1]
    pre = pd.read_csv(f)
    out_path = output_dir / "crime" / f.name
    if not out_path.exists():
        continue
    post = pd.read_csv(out_path)
    x_lsoas = set(xwalk[xwalk["CHGIND"] == "X"]["LSOA11CD"])
    pre_excl = pre[~pre["LSOA11CD"].isin(x_lsoas)]
    crime_cols = [c for c in pre.columns
                  if c not in ("LSOA11CD", "LSOA11NM", "pop") and "_rate" not in c]
    pre_sum = pre_excl[crime_cols].sum().sum()
    post_crime_cols = [c for c in post.columns
                       if c not in ("LSOA21CD", "LSOA21NM", "pop") and "_rate" not in c]
    post_sum = post[post_crime_cols].sum().sum()
    ts_results.append({
        "domain": "crime",
        "year": year_str,
        "pre_sum": pre_sum,
        "post_sum": post_sum,
        "diff_pct": (post_sum - pre_sum) / pre_sum * 100 if pre_sum != 0 else 0,
    })

ts_df = pd.DataFrame(ts_results)
print("Crosswalk conservation across all years (% diff, excl. X LSOAs):")
print(ts_df.to_string(index=False))
