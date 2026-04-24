# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Validation: Aggregation Consistency
#
# Verify that geographic aggregation is internally consistent:
# - **Sum check:** LSOA counts sum to LAD, LAD to Region, Region to England
# - **Rate recomputation:** rates = count / population at every geography level
# - **Population consistency:** LSOA populations sum to LAD populations, etc.
#
# Any discrepancy here indicates a bug in the aggregation pipeline.

# %%
from pathlib import Path

import numpy as np
import pandas as pd

repo_root = Path.cwd()
if repo_root.name in ("validation", "nbs", "pts"):
    repo_root = repo_root.parent
while not (repo_root / "config").exists() and repo_root != repo_root.parent:
    repo_root = repo_root.parent

out_dir = repo_root / "store" / "outputs" / "default"

LEVELS = ["lsoa", "lad", "region", "england"]
GEO_CODE_COLS = {
    "lsoa": "LSOA21CD",
    "lad": "LAD25CD",
    "region": "RGN25CD",
    "england": "area_code",
}

# %% [markdown]
# ## 1. Claimant counts — sum consistency across levels

# %%
def load_domain(domain: str, filename: str) -> dict[str, pd.DataFrame]:
    """Load a domain file at all four geography levels."""
    dfs = {}
    for level in LEVELS:
        path = out_dir / level / domain / filename
        if path.exists():
            dfs[level] = pd.read_csv(path)
    return dfs


def check_sum_consistency(dfs: dict[str, pd.DataFrame], count_cols: list[str], label: str):
    """Check that count columns and population sum correctly across levels."""
    cols_to_check = count_cols + ["pop"]
    results = []
    for col in cols_to_check:
        lsoa_sum = dfs["lsoa"][col].sum()
        lad_sum = dfs["lad"][col].sum()
        region_sum = dfs["region"][col].sum()
        england_val = dfs["england"][col].iloc[0]
        results.append({
            "column": col,
            "LSOA sum": lsoa_sum,
            "LAD sum": lad_sum,
            "Region sum": region_sum,
            "England": england_val,
            "LSOA==LAD": np.isclose(lsoa_sum, lad_sum, rtol=1e-6),
            "LAD==Region": np.isclose(lad_sum, region_sum, rtol=1e-6),
            "Region==England": np.isclose(region_sum, england_val, rtol=1e-6),
        })
    df = pd.DataFrame(results)
    all_pass = df[["LSOA==LAD", "LAD==Region", "Region==England"]].all().all()
    print(f"\n{'='*60}")
    print(f" {label}: {'ALL PASSED' if all_pass else 'FAILURES DETECTED'}")
    print(f"{'='*60}")
    print(df.to_string(index=False))
    return df


# Test a single year first
cc_dfs = load_domain("claimant_counts", "claimant_counts_2024.csv")
check_sum_consistency(cc_dfs, ["claimant_count"], "Claimant counts 2024")

# %% [markdown]
# ## 2. Crime — sum consistency

# %%
crime_dfs = load_domain("crime", "crime_2024.csv")
crime_count_cols = [c for c in crime_dfs["lsoa"].columns
                    if c not in ("LSOA21CD", "LSOA21NM", "pop") and "_rate" not in c]
check_sum_consistency(crime_dfs, crime_count_cols, "Crime 2024")

# %% [markdown]
# ## 3. Health — sum consistency

# %%
health_dfs = load_domain("health", "health_2023_24.csv")
health_count_cols = [c for c in health_dfs["lsoa"].columns
                     if c.endswith("_afflicted")]
check_sum_consistency(health_dfs, health_count_cols, "Health 2023-24")

# %% [markdown]
# ## 4. Rate recomputation verification
#
# At every geography level, `rate = count / pop`. We recompute rates from
# counts and populations and compare against the stored rates.

# %%
def check_rate_recomputation(dfs: dict[str, pd.DataFrame], count_cols: list[str], label: str):
    """Verify that rate columns equal count / pop at every level."""
    results = []
    for level, df in dfs.items():
        for col in count_cols:
            # Find the corresponding rate column
            rate_col = f"{col}_rate" if f"{col}_rate" in df.columns else None
            if rate_col is None:
                # Health uses the count col name directly with _rate suffix
                # e.g., AF_afflicted -> AF_afflicted_rate
                continue
            stored_rate = df[rate_col]
            recomputed_rate = df[col] / df["pop"].replace(0, np.nan)
            max_diff = (stored_rate - recomputed_rate).abs().max()
            results.append({
                "level": level,
                "column": col,
                "max_abs_diff": max_diff,
                "pass": max_diff < 1e-10 or np.isnan(max_diff),
            })
    df_results = pd.DataFrame(results)
    all_pass = df_results["pass"].all()
    print(f"\n{'='*60}")
    print(f" {label} rate recomputation: {'ALL PASSED' if all_pass else 'FAILURES DETECTED'}")
    print(f"{'='*60}")
    # Only show failures or summary
    failures = df_results[~df_results["pass"]]
    if len(failures) > 0:
        print("FAILURES:")
        print(failures.to_string(index=False))
    else:
        n_checks = len(df_results)
        print(f"All {n_checks} rate checks passed (max diff < 1e-10)")
    return df_results


# Claimant counts
check_rate_recomputation(cc_dfs, ["claimant_count"], "Claimant counts 2024")

# Crime
check_rate_recomputation(crime_dfs, crime_count_cols, "Crime 2024")

# Health
check_rate_recomputation(health_dfs, health_count_cols, "Health 2023-24")

# %% [markdown]
# ## 5. Full time-series check
#
# Run sum consistency across all available years for all three domains.

# %%
summary = []

# Claimant counts
for f in sorted((out_dir / "lsoa" / "claimant_counts").glob("claimant_counts_*.csv")):
    year = f.stem.split("_")[-1]
    dfs = load_domain("claimant_counts", f.name)
    if len(dfs) == 4:
        cols = ["claimant_count", "pop"]
        for col in cols:
            lsoa_s = dfs["lsoa"][col].sum()
            eng_v = dfs["england"][col].iloc[0]
            summary.append({
                "domain": "claimant",
                "year": year,
                "column": col,
                "lsoa_sum": lsoa_s,
                "england_val": eng_v,
                "match": np.isclose(lsoa_s, eng_v, rtol=1e-6),
            })

# Crime
for f in sorted((out_dir / "lsoa" / "crime").glob("crime_*.csv")):
    year = f.stem.split("_")[-1]
    dfs = load_domain("crime", f.name)
    if len(dfs) == 4:
        lsoa_pop = dfs["lsoa"]["pop"].sum()
        eng_pop = dfs["england"]["pop"].iloc[0]
        summary.append({
            "domain": "crime",
            "year": year,
            "column": "pop",
            "lsoa_sum": lsoa_pop,
            "england_val": eng_pop,
            "match": np.isclose(lsoa_pop, eng_pop, rtol=1e-6),
        })
        crime_cols = [c for c in dfs["lsoa"].columns
                      if c not in ("LSOA21CD", "LSOA21NM", "pop") and "_rate" not in c]
        total_crime_lsoa = dfs["lsoa"][crime_cols].sum().sum()
        total_crime_eng = dfs["england"][crime_cols].iloc[0].sum()
        summary.append({
            "domain": "crime",
            "year": year,
            "column": "total_crime",
            "lsoa_sum": total_crime_lsoa,
            "england_val": total_crime_eng,
            "match": np.isclose(total_crime_lsoa, total_crime_eng, rtol=1e-6),
        })

# Health
for f in sorted((out_dir / "lsoa" / "health").glob("health_*.csv")):
    qof_year = f.stem.replace("health_", "")
    dfs = load_domain("health", f.name)
    if len(dfs) == 4:
        lsoa_pop = dfs["lsoa"]["pop"].sum()
        eng_pop = dfs["england"]["pop"].iloc[0]
        summary.append({
            "domain": "health",
            "year": qof_year,
            "column": "pop",
            "lsoa_sum": lsoa_pop,
            "england_val": eng_pop,
            "match": np.isclose(lsoa_pop, eng_pop, rtol=1e-6),
        })

summary_df = pd.DataFrame(summary)
failures = summary_df[~summary_df["match"]]
print(f"Time-series aggregation check: {len(summary_df)} checks, {len(failures)} failures")
if len(failures) > 0:
    print("\nFAILURES:")
    print(failures.to_string(index=False))
else:
    print("All checks passed.")

# %% [markdown]
# ## 6. Row count expectations
#
# Check that each geography level has the expected number of rows.

# %%
EXPECTED_ROWS = {"lad": 296, "region": 9, "england": 1}

for domain, pattern in [("claimant_counts", "claimant_counts_2024.csv"),
                         ("crime", "crime_2024.csv"),
                         ("health", "health_2023_24.csv")]:
    print(f"\n{domain}:")
    for level in LEVELS:
        path = out_dir / level / domain / pattern
        if path.exists():
            n = len(pd.read_csv(path))
            expected = EXPECTED_ROWS.get(level)
            status = ""
            if expected is not None:
                status = f" {'OK' if n == expected else f'EXPECTED {expected}'}"
            print(f"  {level}: {n} rows{status}")
