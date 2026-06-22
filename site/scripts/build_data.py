#!/usr/bin/env python3
"""Build compact web data for the ADI site from store/outputs/default + IMD inputs.

Outputs under site/static/data/:
  manifest.json                         levels, domains, metrics (+ label/fmt/scale breaks), years
  codes/{level}.json                    {codes:[...sorted], names:[...]}  (index-aligned)
  hierarchy.json                        england/regions/lad/lsoa parent+child maps
  map/{level}/{domain}/{metric}.json    {years:[...], values:[[per-area per codes order] per year]}
  area/{england,region,lad}.json        full per-area records (all domains, all years)
  area/lsoa/{ladcode}.json              LSOA records sharded by parent LAD
  dashboard.json                        headline stats + england series + extremes
  imd.json                              ADI-vs-IMD analysis (ported from nbs/analysis)

Run:  uv run --with pandas --with numpy --with scipy python site/scripts/build_data.py
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
OUT_DEF = ROOT / "store" / "outputs" / "default"
IMD_DIR = ROOT / "store" / "inputs" / "imd"
XWALK = ROOT / "store" / "inputs" / "crosswalk" / "lsoa11_to_lsoa21.csv"
LU_LAD = ROOT / "store" / "inputs" / "geo_lookups" / "lsoa21_to_lad25.csv"
LU_RGN = ROOT / "store" / "inputs" / "geo_lookups" / "lad25_to_rgn25.csv"
WEB = ROOT / "site" / "static" / "data"

YEARS = list(range(2014, 2025))  # 2014..2024
LEVELS = ["england", "region", "lad", "lsoa"]

CRIME_TYPES = [
    ("Anti-social behaviour", "anti_social"),
    ("Bicycle theft", "bicycle_theft"),
    ("Burglary", "burglary"),
    ("Criminal damage and arson", "criminal_damage"),
    ("Drugs", "drugs"),
    ("Other crime", "other_crime"),
    ("Other theft", "other_theft"),
    ("Possession of weapons", "weapons"),
    ("Public order", "public_order"),
    ("Robbery", "robbery"),
    ("Shoplifting", "shoplifting"),
    ("Theft from the person", "theft_person"),
    ("Vehicle crime", "vehicle"),
    ("Violence and sexual offences", "violence"),
]
HEALTH = [
    ("AF", "Atrial fibrillation"), ("AST", "Asthma"), ("CAN", "Cancer"),
    ("CHD", "Coronary heart disease"), ("CKD", "Chronic kidney disease"),
    ("COPD", "COPD"), ("DEM", "Dementia"), ("DEP", "Depression"),
    ("DM", "Diabetes"), ("EP", "Epilepsy"), ("HF", "Heart failure"),
    ("HYP", "Hypertension"), ("LD", "Learning disability"),
    ("MH", "Severe mental illness"), ("NDH", "Non-diabetic hyperglycaemia"),
    ("OB", "Obesity"), ("OST", "Osteoporosis"),
    ("PAD", "Peripheral arterial disease"), ("PC", "Palliative care"),
    ("RA", "Rheumatoid arthritis"), ("STIA", "Stroke / TIA"),
    ("CVDPP", "CVD primary prevention"), ("SMOK", "Smoking"),
    ("THY", "Hypothyroidism"),
]

# ---------------------------------------------------------------- helpers

def rnd(x, n=6):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


def read_level(level: str, domain: str, year: int) -> pd.DataFrame | None:
    """Read one CSV; normalise first two cols to code,name. Returns None if missing."""
    d = OUT_DEF / level / domain
    if domain == "health":
        # health_{y}_{y+1}.csv ; map to ending calendar year (start+1)
        cands = sorted(d.glob("health_*.csv"))
        path = None
        for f in cands:
            parts = f.stem.split("_")  # health, YYYY, YY
            try:
                start = int(parts[1])
            except (IndexError, ValueError):
                continue
            if start + 1 == year:
                path = f
                break
        if path is None:
            return None
    else:
        path = d / f"{domain}_{year}.csv"
        if not path.exists():
            return None
    df = pd.read_csv(path)
    cols = list(df.columns)
    df = df.rename(columns={cols[0]: "code", cols[1]: "name"})
    return df


def write_json(path: Path, obj, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), allow_nan=False, indent=indent)


# ---------------------------------------------------------------- load everything into nested dict
# data[level][domain][year] -> DataFrame indexed by code

print("Loading CSVs...")
data: dict = {lv: {"employment": {}, "crime": {}, "health": {}} for lv in LEVELS}
for lv in LEVELS:
    for yr in YEARS:
        cc = read_level(lv, "claimant_counts", yr)
        if cc is not None:
            data[lv]["employment"][yr] = cc.set_index("code")
        cr = read_level(lv, "crime", yr)
        if cr is not None:
            data[lv]["crime"][yr] = cr.set_index("code")
        he = read_level(lv, "health", yr)
        if he is not None:
            data[lv]["health"][yr] = he.set_index("code")

# ---------------------------------------------------------------- data-quality corrections
# Documented, transparent corrections for KNOWN source-data defects (flagged by
# scripts/validate_outputs.py on the raw outputs). Each is logged. Not silent fallbacks:
# the validator still runs on the uncorrected outputs and the About page documents these.
print("Applying data-quality corrections...")

# (1) Drop QOF indicators with no usable prevalence series (sparse/empty: present in
#     only one year or all-zero). Leaves the canonical 21 conditions.
DROP_HEALTH = {"CVDPP", "SMOK", "THY"}
_before = len(HEALTH)
HEALTH = [(c, l) for (c, l) in HEALTH if c not in DROP_HEALTH]
print(f"  health: dropped {sorted(DROP_HEALTH)} -> {len(HEALTH)} conditions (was {_before})")

# (2) Single-year source anomalies: a disease whose register switched basis for one
#     publication (DEP 2023-24 reported new-diagnosis incidence ~1.5% vs cumulative
#     prevalence ~13-14%; OST 2014-15 dip-and-reverse). Null + linearly interpolate
#     from the flanking years (matches the pipeline's own ≤2-gap interpolation policy).
HEALTH_FIX = [("DEP", 2024), ("OST", 2015)]
for dis, yr in HEALTH_FIX:
    rc, ac = f"{dis}_afflicted_rate", f"{dis}_afflicted"
    n = 0
    for lv in LEVELS:
        cur = data[lv]["health"].get(yr)
        left = data[lv]["health"].get(yr - 1)
        right = data[lv]["health"].get(yr + 1)
        if right is None:  # e.g. 2024's right anchor is health_2024_25 (mapped year 2025)
            r = read_level(lv, "health", yr + 1)
            right = r.set_index("code") if r is not None else None
        if cur is None or left is None or right is None or rc not in cur.columns:
            continue
        for code in cur.index:
            if code not in left.index or code not in right.index:
                continue
            lvv, rvv = left.at[code, rc], right.at[code, rc]
            if pd.isna(lvv) or pd.isna(rvv):
                continue
            newr = (float(lvv) + float(rvv)) / 2.0
            cur.at[code, rc] = newr
            if ac in cur.columns and "pop" in cur.columns and not pd.isna(cur.at[code, "pop"]):
                cur.at[code, ac] = newr * float(cur.at[code, "pop"])
            n += 1
    print(f"  health: {dis} {yr} null+interpolated across {n} areas")

# (3) Crime: police forces with reporting gaps (notably Greater Manchester from mid-2019)
#     emit near-zero counts that are NOT real. Detect per-LAD: a year whose total crime
#     rate is < 20% of that LAD's own normal (median of non-trivial years) is a data gap.
#     Null those LAD-years (and their LSOAs); recompute Region/England crime rates from
#     REPORTING areas only so national/regional rates aren't deflated by the gap.
_crime_cnt_cols = lambda df: [t[0] for t in CRIME_TYPES if t[0] in df.columns]
def _lad_total_rate(df, code):
    if code not in df.index:
        return None
    r = df.loc[code]
    cols = _crime_cnt_cols(df)
    tot = float(sum(float(r[c]) for c in cols if not pd.isna(r[c])))
    pop = float(r["pop"]) if not pd.isna(r["pop"]) else 0.0
    return (tot / pop) if pop > 0 else None

_lad_crime = data["lad"]["crime"]
_lad_codes = set().union(*[set(df.index) for df in _lad_crime.values()]) if _lad_crime else set()
nonreporting: dict[int, set] = {}
for code in _lad_codes:
    series = {yr: _lad_total_rate(df, code) for yr, df in _lad_crime.items()}
    rates = [v for v in series.values() if v is not None]
    normal_pool = [v for v in rates if v > 0.01]
    if not normal_pool:
        continue
    normal = float(np.median(normal_pool))
    for yr, v in series.items():
        if v is not None and v < 0.2 * normal:
            nonreporting.setdefault(yr, set()).add(code)

# null nonreporting LADs + their LSOAs
lu_lad0 = pd.read_csv(LU_LAD)[["LSOA21CD", "LAD25CD"]]
_lsoa_to_lad = dict(zip(lu_lad0["LSOA21CD"], lu_lad0["LAD25CD"]))
lu_rgn0 = pd.read_csv(LU_RGN)[["LAD25CD", "RGN25CD"]].drop_duplicates("LAD25CD")
_lad_to_rgn = dict(zip(lu_rgn0["LAD25CD"], lu_rgn0["RGN25CD"]))
_n_gap = sum(len(s) for s in nonreporting.values())
for yr, codes in nonreporting.items():
    df = data["lad"]["crime"].get(yr)
    if df is not None:
        cols = [c for c in df.columns if c not in ("name", "pop")]
        for code in codes:
            if code in df.index:
                df.loc[code, cols] = np.nan
    ldf = data["lsoa"]["crime"].get(yr)
    if ldf is not None:
        cols = [c for c in ldf.columns if c not in ("name", "pop")]
        bad_lsoas = [ls for ls, ld in _lsoa_to_lad.items() if ld in codes and ls in ldf.index]
        for ls in bad_lsoas:
            ldf.loc[ls, cols] = np.nan

# recompute Region + England crime from reporting LADs only (representative rates)
for yr, codes in nonreporting.items():
    ldf = data["lad"]["crime"].get(yr)
    if ldf is None:
        continue
    reporting = [c for c in ldf.index if c not in codes]
    cnt_cols = _crime_cnt_cols(ldf)
    # England
    edf = data["england"]["crime"].get(yr)
    if edf is not None:
        ecode = edf.index[0]
        sub = ldf.loc[reporting]
        pop = float(sub["pop"].sum())
        for c in cnt_cols:
            tot = float(sub[c].sum())
            edf.at[ecode, c] = tot
            edf.at[ecode, f"{c}_rate"] = (tot / pop) if pop > 0 else np.nan
        edf.at[ecode, "pop"] = pop
    # Regions
    rdf = data["region"]["crime"].get(yr)
    if rdf is not None:
        for rcode in rdf.index:
            rep = [c for c in reporting if _lad_to_rgn.get(c) == rcode]
            if not rep:
                continue
            sub = ldf.loc[rep]
            pop = float(sub["pop"].sum())
            for c in cnt_cols:
                tot = float(sub[c].sum())
                rdf.at[rcode, c] = tot
                rdf.at[rcode, f"{c}_rate"] = (tot / pop) if pop > 0 else np.nan
            rdf.at[rcode, "pop"] = pop
print(f"  crime: nulled {_n_gap} non-reporting LAD-years (force gaps) across {len(nonreporting)} years; "
      f"Region/England crime recomputed from reporting areas")

# canonical code/name per level (sorted by code), from the latest employment year
codes_by_level: dict[str, list[str]] = {}
names_by_level: dict[str, dict[str, str]] = {}
for lv in LEVELS:
    # union of codes across employment years; names from any year
    all_codes = set()
    names = {}
    for yr, df in data[lv]["employment"].items():
        all_codes.update(df.index)
        for c, n in df["name"].items():
            names[c] = n
    codes_by_level[lv] = sorted(all_codes)
    names_by_level[lv] = names

for lv in LEVELS:
    print(f"  {lv}: {len(codes_by_level[lv])} areas")

# ---------------------------------------------------------------- hierarchy
print("Building hierarchy...")
lu_lad = pd.read_csv(LU_LAD)[["LSOA21CD", "LAD25CD"]]
lsoa_lad = dict(zip(lu_lad["LSOA21CD"], lu_lad["LAD25CD"]))
lu_rgn = pd.read_csv(LU_RGN)[["LAD25CD", "RGN25CD", "RGN25NM"]].drop_duplicates("LAD25CD")
lad_rgn = dict(zip(lu_rgn["LAD25CD"], lu_rgn["RGN25CD"]))

# restrict to areas present in data
lsoa_set = set(codes_by_level["lsoa"])
lad_set = set(codes_by_level["lad"])
rgn_set = set(codes_by_level["region"])
lsoa_lad = {k: v for k, v in lsoa_lad.items() if k in lsoa_set and v in lad_set}
lad_rgn = {k: v for k, v in lad_rgn.items() if k in lad_set and v in rgn_set}

lad_lsoas: dict[str, list[str]] = {}
for ls, ld in lsoa_lad.items():
    lad_lsoas.setdefault(ld, []).append(ls)
for ld in lad_lsoas:
    lad_lsoas[ld].sort()

region_lads: dict[str, list[str]] = {}
for ld, rg in lad_rgn.items():
    region_lads.setdefault(rg, []).append(ld)
for rg in region_lads:
    region_lads[rg].sort()

hierarchy = {
    "england": {"code": "E92000001", "name": "England"},
    "regions": [{"code": c, "name": names_by_level["region"][c]} for c in codes_by_level["region"]],
    "region_lads": region_lads,
    "lad_region": lad_rgn,
    "lad_lsoas": lad_lsoas,
    "lsoa_lad": lsoa_lad,
    "lad_names": names_by_level["lad"],
    "region_names": names_by_level["region"],
}
write_json(WEB / "hierarchy.json", hierarchy)

# ---------------------------------------------------------------- codes files
for lv in LEVELS:
    codes = codes_by_level[lv]
    write_json(WEB / "codes" / f"{lv}.json",
               {"codes": codes, "names": [names_by_level[lv].get(c, c) for c in codes]})

# ---------------------------------------------------------------- per-(level) metric value series helpers
def metric_series_for_level(lv, domain, metric_key):
    """Return dict year -> pd.Series(code->value) for a metric at a level."""
    out = {}
    for yr in YEARS:
        df = data[lv][domain].get(yr)
        if df is None:
            continue
        if domain == "employment":
            s = df["claimant_count_rate"]
        elif domain == "crime":
            if metric_key == "total":
                count_cols = [t[0] for t in CRIME_TYPES if t[0] in df.columns]
                tot = df[count_cols].sum(axis=1, min_count=1)  # all-NaN row -> NaN (no data)
                s = tot / df["pop"].replace(0, np.nan)
            else:
                name = next(t[0] for t in CRIME_TYPES if t[1] == metric_key)
                col = f"{name}_rate"
                s = df[col] if col in df.columns else None
        else:  # health
            col = f"{metric_key}_afflicted_rate"
            s = df[col] if col in df.columns else None
        if s is not None:
            out[yr] = s
    return out


# metric definitions
def domain_metrics():
    emp = [{"key": "claimant_rate", "label": "Universal Credit claimant rate", "fmt": "pct"}]
    cri = [{"key": "total", "label": "All street crime", "fmt": "rate1k"}]
    cri += [{"key": slug, "label": name, "fmt": "rate1k"} for name, slug in CRIME_TYPES]
    hea = [{"key": code, "label": label, "fmt": "pct"} for code, label in HEALTH]
    return {"employment": emp, "crime": cri, "health": hea}


METRICS = domain_metrics()

# ---------------------------------------------------------------- color scale breaks (from LSOA pooled)
print("Computing scale breaks + writing map value files...")
NCLASS = 7

def compute_breaks(pooled: np.ndarray):
    pooled = pooled[~np.isnan(pooled)]
    pooled = pooled[pooled >= 0]
    if pooled.size == 0:
        return {"breaks": [0], "min": 0, "max": 0}
    qs = np.quantile(pooled, [i / NCLASS for i in range(1, NCLASS)])
    breaks = sorted({rnd(q, 7) for q in qs})
    return {"breaks": breaks, "min": rnd(float(pooled.min()), 7), "max": rnd(float(pooled.max()), 7)}


def metric_key_for(domain, m):
    return m["key"] if domain != "employment" else "claimant_rate"


scale_by_metric: dict[str, dict] = {}
for domain, mlist in METRICS.items():
    for m in mlist:
        mk = metric_key_for(domain, m)
        # pooled LSOA values for breaks
        series = metric_series_for_level("lsoa", domain, mk)
        pooled = np.concatenate([s.to_numpy(dtype=float) for s in series.values()]) if series else np.array([])
        scale_by_metric[f"{domain}/{mk}"] = compute_breaks(pooled)

        # write per-level value files
        for lv in LEVELS:
            codes = codes_by_level[lv]
            lvseries = metric_series_for_level(lv, domain, mk)
            years_present = [y for y in YEARS if y in lvseries]
            values = []
            for y in years_present:
                s = lvseries[y].reindex(codes)
                values.append([rnd(v, 7) for v in s.to_numpy(dtype=float)])
            write_json(WEB / "map" / lv / domain / f"{mk}.json",
                       {"years": years_present, "values": values})

# attach scale into metric defs
for domain, mlist in METRICS.items():
    for m in mlist:
        mk = metric_key_for(domain, m)
        m["scale"] = scale_by_metric[f"{domain}/{mk}"]

# ---------------------------------------------------------------- manifest
manifest = {
    "years": YEARS,
    "levels": LEVELS,
    "level_labels": {"england": "England", "region": "Region", "lad": "Local authority", "lsoa": "Neighbourhood (LSOA)"},
    "domains": {
        "employment": {"label": "Employment", "metrics": METRICS["employment"],
                       "source": "Universal Credit claimant counts (Nomis)"},
        "crime": {"label": "Crime", "metrics": METRICS["crime"],
                  "source": "Police-recorded street crime (data.police.uk)"},
        "health": {"label": "Health", "metrics": METRICS["health"],
                   "source": "GP disease prevalence, QOF (NHS Digital)"},
    },
    "counts": {lv: len(codes_by_level[lv]) for lv in LEVELS},
}
write_json(WEB / "manifest.json", manifest)

# ---------------------------------------------------------------- area profiles
print("Building area profiles...", flush=True)
# Fast O(1) row lookups: per (level, domain, year) a {code: {col: val}} dict.
DD: dict = {lv: {"employment": {}, "crime": {}, "health": {}} for lv in LEVELS}
for lv in LEVELS:
    for dom in ("employment", "crime", "health"):
        for yr, df in data[lv][dom].items():
            DD[lv][dom][yr] = df.to_dict("index")

def build_record(lv, code):
    rec = {"code": code, "name": names_by_level[lv].get(code, code), "level": lv}
    # employment
    emp = {"count": [], "pop": [], "rate": []}
    for yr in YEARS:
        r = DD[lv]["employment"].get(yr, {}).get(code)
        if r is not None:
            emp["count"].append(rnd(r["claimant_count"], 1))
            emp["pop"].append(int(r["pop"]) if not pd.isna(r["pop"]) else None)
            emp["rate"].append(rnd(r["claimant_count_rate"], 7))
        else:
            emp["count"].append(None); emp["pop"].append(None); emp["rate"].append(None)
    rec["employment"] = emp
    # crime
    cri = {"total_count": [], "total_rate": [], "pop": [], "types": {slug: {"count": [], "rate": []} for _, slug in CRIME_TYPES}}
    for yr in YEARS:
        r = DD[lv]["crime"].get(yr, {}).get(code)
        if r is not None:
            pop = r["pop"]
            cri["pop"].append(int(pop) if not pd.isna(pop) else None)
            tot = 0.0
            any_cnt = False
            for name, slug in CRIME_TYPES:
                cnt = r.get(name, np.nan)
                rate = r.get(f"{name}_rate", np.nan)
                cri["types"][slug]["count"].append(rnd(cnt, 1))
                cri["types"][slug]["rate"].append(rnd(rate, 8))
                if not pd.isna(cnt):
                    tot += cnt
                    any_cnt = True
            # all-NaN crime row = data gap (e.g. force not reporting) -> no data, not 0
            if any_cnt:
                cri["total_count"].append(rnd(tot, 1))
                cri["total_rate"].append(rnd(tot / pop, 8) if pop and not pd.isna(pop) and pop > 0 else None)
            else:
                cri["total_count"].append(None)
                cri["total_rate"].append(None)
        else:
            cri["pop"].append(None); cri["total_count"].append(None); cri["total_rate"].append(None)
            for _, slug in CRIME_TYPES:
                cri["types"][slug]["count"].append(None); cri["types"][slug]["rate"].append(None)
    rec["crime"] = cri
    # health
    hea = {"pop": [], "diseases": {code_: {"rate": [], "afflicted": []} for code_, _ in HEALTH}}
    for yr in YEARS:
        r = DD[lv]["health"].get(yr, {}).get(code)
        if r is not None:
            hea["pop"].append(int(r["pop"]) if "pop" in r and not pd.isna(r["pop"]) else None)
            for code_, _ in HEALTH:
                rc = f"{code_}_afflicted_rate"; ac = f"{code_}_afflicted"
                hea["diseases"][code_]["rate"].append(rnd(r[rc], 7) if rc in r else None)
                hea["diseases"][code_]["afflicted"].append(rnd(r[ac], 1) if ac in r else None)
        else:
            hea["pop"].append(None)
            for code_, _ in HEALTH:
                hea["diseases"][code_]["rate"].append(None); hea["diseases"][code_]["afflicted"].append(None)
    rec["health"] = hea
    # parents
    if lv == "lsoa":
        ld = lsoa_lad.get(code)
        rg = lad_rgn.get(ld) if ld else None
        rec["parents"] = {"lad": {"code": ld, "name": names_by_level["lad"].get(ld)} if ld else None,
                          "region": {"code": rg, "name": names_by_level["region"].get(rg)} if rg else None}
    elif lv == "lad":
        rg = lad_rgn.get(code)
        rec["parents"] = {"region": {"code": rg, "name": names_by_level["region"].get(rg)} if rg else None}
    return rec

# england, region, lad: single files
for lv in ["england", "region", "lad"]:
    areas = {c: build_record(lv, c) for c in codes_by_level[lv]}
    write_json(WEB / "area" / f"{lv}.json", {"areas": areas})
    print(f"  wrote area/{lv}.json ({len(areas)})", flush=True)

# lsoa: shard by parent lad, streaming (write + free per shard)
orphan = {}
nshards = 0
for ld in sorted(lad_lsoas):
    areas = {c: build_record("lsoa", c) for c in lad_lsoas[ld]}
    write_json(WEB / "area" / "lsoa" / f"{ld}.json", {"areas": areas})
    nshards += 1
# any LSOAs without a parent LAD
missing = [c for c in codes_by_level["lsoa"] if c not in lsoa_lad]
if missing:
    orphan = {c: build_record("lsoa", c) for c in missing}
    write_json(WEB / "area" / "lsoa" / "_orphan.json", {"areas": orphan})
print(f"  wrote {nshards} LSOA shards ({len(missing)} orphan LSOAs)", flush=True)

# ---------------------------------------------------------------- dashboard
print("Building dashboard...")
def england_series(domain, mk):
    s = metric_series_for_level("england", domain, mk)
    return {"years": [y for y in YEARS if y in s],
            "values": [rnd(float(s[y].iloc[0]), 7) for y in YEARS if y in s]}

emp_eng = england_series("employment", "claimant_rate")
crime_eng = england_series("crime", "total")
dep_eng = england_series("health", "DEP")

# COVID by LAD 2019->2020
lad19 = data["lad"]["employment"][2019]
lad20 = data["lad"]["employment"][2020]
covid = lad19[["name", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "r19"}).join(
    lad20["claimant_count_rate"].rename("r20"), how="inner")
covid["change"] = covid["r20"] - covid["r19"]
covid["pct"] = covid["change"] / covid["r19"] * 100
covid_top = covid.sort_values("change", ascending=False).head(20)

# extremes latest year (2024) most-deprived LADs by claimant rate
lad24 = data["lad"]["employment"][2024]
most_dep = lad24.sort_values("claimant_count_rate", ascending=False).head(15)
least_dep = lad24.sort_values("claimant_count_rate", ascending=True).head(15)

dashboard = {
    "latest_year": 2024,
    "england": {"claimant_rate": emp_eng, "total_crime_rate": crime_eng, "depression_rate": dep_eng},
    "headline": {
        "claimant_rate_2024": rnd(float(lad24["claimant_count"].sum() / lad24["pop"].sum()), 6),
        "covid": {
            "y2019": rnd(float(lad19["claimant_count"].sum() / lad19["pop"].sum()), 6),
            "y2020": rnd(float(lad20["claimant_count"].sum() / lad20["pop"].sum()), 6),
        },
        "n_lsoa": len(codes_by_level["lsoa"]),
        "n_lad": len(codes_by_level["lad"]),
    },
    "covid_top_lads": [
        {"code": c, "name": r["name"], "r19": rnd(r["r19"], 5), "r20": rnd(r["r20"], 5),
         "change": rnd(r["change"], 5), "pct": rnd(r["pct"], 1)}
        for c, r in covid_top.iterrows()
    ],
    "covid_all_increase": bool((covid["change"] > 0).all()),
    "covid_n_lads": int(len(covid)),
    "most_deprived_lads": [
        {"code": c, "name": r["name"], "rate": rnd(r["claimant_count_rate"], 5)} for c, r in most_dep.iterrows()],
    "least_deprived_lads": [
        {"code": c, "name": r["name"], "rate": rnd(r["claimant_count_rate"], 5)} for c, r in least_dep.iterrows()],
}
write_json(WEB / "dashboard.json", dashboard)

# ---------------------------------------------------------------- IMD analysis (ported from nbs/analysis)
print("Building ADI-vs-IMD analysis...")

def load_imd(edition):
    df = pd.read_csv(IMD_DIR / f"imd_{edition}.csv")
    lsoa_col = [c for c in df.columns if c.startswith("LSOA code")][0]
    return df.rename(columns={
        lsoa_col: "lsoa_code",
        "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank",
        "Employment Rank (where 1 is most deprived)": "imd_emp_rank",
        "Crime Rank (where 1 is most deprived)": "imd_crime_rank",
        "Health Deprivation and Disability Rank (where 1 is most deprived)": "imd_health_rank",
    })

xw = pd.read_csv(XWALK)
xw_u = xw[xw["CHGIND"] == "U"][["LSOA11CD", "LSOA21CD"]]

def adi_lsoa_year(year):
    cc = data["lsoa"]["employment"][year].reset_index()[["code", "claimant_count_rate"]].rename(
        columns={"code": "LSOA21CD"})
    cr = data["lsoa"]["crime"][year].reset_index()
    count_cols = [t[0] for t in CRIME_TYPES if t[0] in cr.columns]
    cr["adi_crime_rate"] = cr[count_cols].sum(axis=1) / cr["pop"].replace(0, np.nan)
    cr = cr[["code", "adi_crime_rate"]].rename(columns={"code": "LSOA21CD"})
    m = cc.merge(cr, on="LSOA21CD", how="inner").rename(columns={"claimant_count_rate": "adi_claimant_rate"})
    he = data["lsoa"]["health"].get(year)
    if he is not None and "DEP_afflicted_rate" in he.columns:
        h = he.reset_index()[["code", "DEP_afflicted_rate"]].rename(
            columns={"code": "LSOA21CD", "DEP_afflicted_rate": "adi_dep_rate"})
        m = m.merge(h, on="LSOA21CD", how="left")
    return m

def spearman(x, y):
    v = pd.DataFrame({"x": x, "y": y}).dropna()
    return float(stats.spearmanr(v["x"], v["y"]).statistic)

def correlations_for(adi, imd, via_xwalk):
    if via_xwalk:
        imd = imd.merge(xw_u, left_on="lsoa_code", right_on="LSOA11CD", how="inner")
        m = adi.merge(imd, on="LSOA21CD", how="inner")
    else:
        m = adi.merge(imd, left_on="LSOA21CD", right_on="lsoa_code", how="inner")
    m["adi_claimant_rank"] = m["adi_claimant_rate"].rank(ascending=False)
    m["adi_crime_rank"] = m["adi_crime_rate"].rank(ascending=False)
    res = {
        "n": int(len(m)),
        "employment": round(spearman(m["adi_claimant_rank"], m["imd_emp_rank"]), 3),
        "crime": round(spearman(m["adi_crime_rank"], m["imd_crime_rank"]), 3),
        "overall_claimant": round(spearman(m["adi_claimant_rank"], m["imd_rank"]), 3),
    }
    if "adi_dep_rate" in m.columns and m["adi_dep_rate"].notna().any():
        m["adi_dep_rank"] = m["adi_dep_rate"].rank(ascending=False)
        res["health"] = round(spearman(m["adi_dep_rank"], m["imd_health_rank"]), 3)
    return res, m

imd25, imd19, imd15 = load_imd("2025"), load_imd("2019"), load_imd("2015")
corr15, _ = correlations_for(adi_lsoa_year(2015), imd15, True)
corr19, _ = correlations_for(adi_lsoa_year(2019), imd19, True)
corr25, m25 = correlations_for(adi_lsoa_year(2024), imd25, False)

# scatter sample for 2025 (claimant vs imd employment; crime vs imd crime; dep vs imd health)
samp = m25.sample(min(4000, len(m25)), random_state=42)
scatter = {
    "employment": [[rnd(a, 1), rnd(b, 1)] for a, b in zip(samp["adi_claimant_rank"], samp["imd_emp_rank"]) if pd.notna(a) and pd.notna(b)],
    "crime": [[rnd(a, 1), rnd(b, 1)] for a, b in zip(samp["adi_crime_rank"], samp["imd_crime_rank"]) if pd.notna(a) and pd.notna(b)],
}
if "adi_dep_rank" in m25.columns:
    scatter["health"] = [[rnd(a, 1), rnd(b, 1)] for a, b in zip(samp["adi_dep_rank"], samp["imd_health_rank"]) if pd.notna(a) and pd.notna(b)]
n_lsoa_scatter = int(len(m25))

# LAD contradictions 2015->2019 (ported)
imd15r = imd15.rename(columns={"lsoa_code": "LSOA11CD", "imd_rank": "imd_rank_15"})
imd19r = pd.read_csv(IMD_DIR / "imd_2019.csv").rename(columns={
    "LSOA code (2011)": "LSOA11CD",
    "Local Authority District code (2019)": "lad_code",
    "Local Authority District name (2019)": "lad_name",
    "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank_19"})
imd_merged = imd15r[["LSOA11CD", "imd_rank_15"]].merge(
    imd19r[["LSOA11CD", "lad_code", "lad_name", "imd_rank_19"]], on="LSOA11CD")
imd_lad = imd_merged.groupby(["lad_code", "lad_name"]).agg(
    mean_rank_15=("imd_rank_15", "mean"), mean_rank_19=("imd_rank_19", "mean")).reset_index()
imd_lad["lad_rank_15"] = imd_lad["mean_rank_15"].rank()
imd_lad["lad_rank_19"] = imd_lad["mean_rank_19"].rank()
imd_lad["imd_rank_change"] = imd_lad["lad_rank_19"] - imd_lad["lad_rank_15"]

cc15 = data["lad"]["employment"][2015].reset_index()[["name", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_15"})
cc19 = data["lad"]["employment"][2019].reset_index()[["name", "claimant_count_rate"]].rename(columns={"claimant_count_rate": "cc_19"})
ladc = imd_lad.merge(cc15, left_on="lad_name", right_on="name", how="inner").merge(cc19, on="name", how="inner")
ladc["cc_change"] = ladc["cc_19"] - ladc["cc_15"]
ladc["contradiction"] = (ladc["imd_rank_change"] > 0) & (ladc["cc_change"] > 0)
n_contra = int(ladc["contradiction"].sum())

contradictions = {
    "n_total": int(len(ladc)),
    "n_contradiction": n_contra,
    "pct": round(n_contra / len(ladc) * 100),
    "lads": [
        {"code": r["lad_code"], "name": r["lad_name"],
         "imd_rank_change": rnd(r["imd_rank_change"], 0),
         "cc_change_pp": rnd(r["cc_change"] * 100, 2),
         "contradiction": bool(r["contradiction"])}
        for _, r in ladc.sort_values("cc_change", ascending=False).iterrows()
    ],
}

# LSOA major contradictions count
imd_lsoa = imd15r[["LSOA11CD", "imd_rank_15"]].merge(
    imd19r[["LSOA11CD", "imd_rank_19"]], on="LSOA11CD")
imd_lsoa["imd_change"] = imd_lsoa["imd_rank_19"] - imd_lsoa["imd_rank_15"]
imd_lsoa = imd_lsoa.merge(xw_u, on="LSOA11CD")
a15 = data["lsoa"]["employment"][2015].reset_index()[["code", "claimant_count_rate"]].rename(columns={"code": "LSOA21CD", "claimant_count_rate": "cc_15"})
a19 = data["lsoa"]["employment"][2019].reset_index()[["code", "claimant_count_rate"]].rename(columns={"code": "LSOA21CD", "claimant_count_rate": "cc_19"})
lsoa_c = imd_lsoa.merge(a15, on="LSOA21CD").merge(a19, on="LSOA21CD")
lsoa_c["cc_change"] = lsoa_c["cc_19"] - lsoa_c["cc_15"]
n_major = int(((lsoa_c["imd_change"] > 500) & (lsoa_c["cc_change"] > 0.01)).sum())

imd_out = {
    "correlations": {"2015": corr15, "2019": corr19, "2025": corr25},
    "annual_trend": emp_eng,
    "imd_editions": [2015, 2019, 2025],
    "covid": {"y2019": dashboard["headline"]["covid"]["y2019"],
              "y2020": dashboard["headline"]["covid"]["y2020"]},
    "scatter": scatter,
    "scatter_n": n_lsoa_scatter,
    "contradictions": contradictions,
    "lsoa_major_contradictions": n_major,
}
write_json(WEB / "imd.json", imd_out)

print("\nDONE. Summary:")
print(f"  correlations 2019: {corr19}")
print(f"  LAD contradictions: {n_contra}/{len(ladc)} ({contradictions['pct']}%)")
print(f"  LSOA major contradictions: {n_major}")
print(f"  COVID national: {imd_out['covid']}")
