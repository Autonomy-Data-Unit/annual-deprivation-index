#!/usr/bin/env python
"""
ADI output data-quality validator (national + regional level).

Validates the final pipeline outputs under
``store/outputs/{run}/{england,region}/{claimant_counts,crime,health}/*.csv``
across all years, for every (domain, metric, geography), and emits a report of
flagged anomalies. Exits non-zero if any BLOCKER-severity finding is present.

Scope rationale
---------------
We deliberately validate ONLY the national (England, 1 area) and regional
(9 areas) aggregates. These are tiny (~10 areas x ~40 metrics x ~12 years) and
any LSOA/LAD-level data issue of meaningful size surfaces in the aggregates
anyway (a 10x undercount of England depression cannot hide once summed).

Usage
-----
    uv run --with pandas --with numpy python scripts/validate_outputs.py
    uv run --with pandas --with numpy python scripts/validate_outputs.py --run default
    uv run --with pandas --with numpy python scripts/validate_outputs.py --json

Checks and thresholds (all documented inline; tune in the CONSTANTS block)
--------------------------------------------------------------------------
1. REVERSAL anomaly (the DEP 2023-24 signature). For an interior year y with
   neighbours y-1, y+1, let nmean = (prev+next)/2. We flag when the point is
   far from the neighbour mean AND the two neighbours agree with each other
   (i.e. the value dips/spikes then *reverses* back to baseline next year):
       dev   = |v - nmean| / nmean              # how far the point sits
       spread= |prev - next| / nmean            # how much neighbours disagree
       BLOCKER  if dev > REVERSAL_DEV (0.50) and spread < REVERSAL_SPREAD (0.35)
       WARN     if dev > REVERSAL_DEV but spread >= REVERSAL_SPREAD
   The WARN bucket is where a genuine level-shift shock lands: COVID employment
   2020 jumps from 0.0167 (2019) to 0.0336 (2020) and *stays* at 0.0346 (2021),
   so its neighbours disagree (spread ~0.67) and it is NEVER a BLOCKER.
   The DEP 2023-24 dip (0.107 -> 0.0119 -> 0.116) has dev~0.89, spread~0.08 and
   IS a blocker. Skipped when nmean < EPS (an all-zero metric has no baseline).

2. STRUCTURAL break (level shift). A consecutive ratio > STEP_RATIO (3x) that
   *persists* into the following year (does not reverse) is reported as WARN
   (suggestive of an indicator/schema change, e.g. DEP 2019-20 -> 2020-21).

3. RANGE / BOUNDS.
   - prevalence & claimant rates must be in [0, 1]            -> BLOCKER
   - crime per-capita rates must be >= 0                      -> BLOCKER
   - crime per-capita rates must be < CRIME_RATE_CEILING (2.0)-> WARN
   - any NaN where a value is expected                        -> BLOCKER
   - negative count or population, or population == 0         -> BLOCKER

4. INTERNAL consistency.
   - rate ~= count / pop within CONSISTENCY_TOL (1%)          -> WARN
   - England absolute count ~= sum over the 9 regions
     within AGG_TOL (2%)                                      -> WARN
   - population year-on-year change > POP_JUMP (20%)          -> WARN

5. COVERAGE.
   - no gaps in the per-domain year sequence                 -> BLOCKER
   - full metric/column set present
     (24 health conditions, 14 crime types)                  -> BLOCKER

6. INFO. A metric that is exactly zero across every year is reported as INFO
   (e.g. CVDPP / SMOK / THY are never populated in the current outputs).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# CONSTANTS / THRESHOLDS  (edit here to tune)                                  #
# --------------------------------------------------------------------------- #
EPS = 1e-9

REVERSAL_DEV = 0.50       # point must deviate >50% from neighbour mean
REVERSAL_SPREAD = 0.35    # neighbours must agree within 35% to count as reversal
STEP_RATIO = 3.0          # consecutive >3x change = candidate structural break

CRIME_RATE_CEILING = 2.0  # per-capita crime rate sanity ceiling
CONSISTENCY_TOL = 0.01    # rate vs count/pop relative tolerance
AGG_TOL = 0.02            # England vs sum-of-regions relative tolerance
POP_JUMP = 0.20           # tolerated year-on-year population change

# 24 health condition codes expected in every health file.
HEALTH_CONDITIONS = [
    "AF", "AST", "CAN", "CHD", "CKD", "COPD", "DEM", "DEP", "DM", "EP", "HF",
    "HYP", "LD", "MH", "NDH", "OB", "OST", "PAD", "PC", "RA", "STIA", "CVDPP",
    "SMOK", "THY",
]
# 14 crime types expected in every crime file.
CRIME_TYPES = [
    "Anti-social behaviour", "Bicycle theft", "Burglary",
    "Criminal damage and arson", "Drugs", "Other crime", "Other theft",
    "Possession of weapons", "Public order", "Robbery", "Shoplifting",
    "Theft from the person", "Vehicle crime", "Violence and sexual offences",
]

GEOGRAPHIES = ["england", "region"]
DOMAINS = ["claimant_counts", "crime", "health"]

SEVERITY_ORDER = {"BLOCKER": 0, "WARN": 1, "INFO": 2}


# --------------------------------------------------------------------------- #
# Loading helpers                                                             #
# --------------------------------------------------------------------------- #
def parse_year(domain: str, path: Path) -> tuple[int, str]:
    """Return (sort_year, label) for a domain file."""
    stem = path.stem  # e.g. claimant_counts_2014 or health_2013_14
    if domain == "health":
        # health_2013_14 -> sort by 2013, label '2013-14'
        _, y0, y1 = stem.rsplit("_", 2)
        return int(y0), f"{y0}-{y1}"
    year = stem.rsplit("_", 1)[1]
    return int(year), year


def load_domain(base: Path, geo: str, domain: str) -> dict[str, pd.DataFrame]:
    """Load all year files for a (geo, domain). Returns {label: df} keyed by
    sort order; each df is indexed by area code with a 'name' column. The first
    CSV column is the area code, the second the area name (names differ per
    level: area_code/RGN25CD etc.)."""
    d = base / geo / domain
    files = sorted(d.glob(f"{domain}_*.csv"))
    out: dict[str, pd.DataFrame] = {}
    order: list[tuple[int, str]] = []
    for f in files:
        sort_year, label = parse_year(domain, f)
        df = pd.read_csv(f)
        code_col, name_col = df.columns[0], df.columns[1]
        df = df.rename(columns={code_col: "code", name_col: "name"})
        df = df.set_index("code")
        out[label] = df
        order.append((sort_year, label))
    out["__order__"] = [lbl for _, lbl in sorted(order)]  # type: ignore
    out["__years__"] = sorted(order)  # type: ignore
    return out


# --------------------------------------------------------------------------- #
# Report accumulation                                                          #
# --------------------------------------------------------------------------- #
class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, domain, metric, geography, year, value, neighbours, reason,
            severity):
        self.rows.append({
            "domain": domain,
            "metric": metric,
            "geography": geography,
            "year": year,
            "value": value,
            "neighbours": neighbours,
            "reason": reason,
            "severity": severity,
        })

    def has_blocker(self) -> bool:
        return any(r["severity"] == "BLOCKER" for r in self.rows)

    def sorted_rows(self) -> list[dict]:
        return sorted(
            self.rows,
            key=lambda r: (SEVERITY_ORDER[r["severity"]], r["domain"],
                           r["geography"], r["metric"], str(r["year"])),
        )


# --------------------------------------------------------------------------- #
# Metric definitions per domain                                                #
# --------------------------------------------------------------------------- #
def metric_specs(domain: str):
    """Yield (metric_name, rate_col, count_col) tuples. count_col may be None
    for derived metrics (handled specially)."""
    if domain == "claimant_counts":
        yield ("claimant_count_rate", "claimant_count_rate", "claimant_count")
    elif domain == "crime":
        for t in CRIME_TYPES:
            yield (f"{t}_rate", f"{t}_rate", t)
        yield ("total_crime_rate", None, None)  # derived
    elif domain == "health":
        for c in HEALTH_CONDITIONS:
            yield (f"{c}_afflicted_rate", f"{c}_afflicted_rate",
                   f"{c}_afflicted")


def is_rate_in_unit_interval(domain: str) -> bool:
    """Domains whose rate metric must lie in [0,1]."""
    return domain in ("claimant_counts", "health")


# --------------------------------------------------------------------------- #
# Series extraction                                                            #
# --------------------------------------------------------------------------- #
def build_series(data, code, rate_col, count_col, domain):
    """Return ordered lists (labels, rate_vals, count_vals, pop_vals) for one
    area/metric. For derived total_crime_rate, rate_col/count_col are None and
    we compute totals from the 14 type columns."""
    labels = data["__order__"]
    rates, counts, pops = [], [], []
    for lbl in labels:
        df = data[lbl]
        if code not in df.index:
            rates.append(np.nan); counts.append(np.nan); pops.append(np.nan)
            continue
        row = df.loc[code]
        pop = float(row["pop"]) if "pop" in df.columns else np.nan
        pops.append(pop)
        if rate_col is None:  # derived total crime
            cnt = float(sum(row[t] for t in CRIME_TYPES if t in df.columns))
            counts.append(cnt)
            rates.append(cnt / pop if pop and pop > 0 else np.nan)
        else:
            rates.append(float(row[rate_col]) if rate_col in df.columns
                         else np.nan)
            counts.append(float(row[count_col]) if count_col in df.columns
                          else np.nan)
    return labels, rates, counts, pops


# --------------------------------------------------------------------------- #
# Checks                                                                       #
# --------------------------------------------------------------------------- #
def check_coverage(report, geo, domain, data):
    years = data["__years__"]
    # year-sequence gaps
    yints = [y for y, _ in years]
    for prev, nxt in zip(yints, yints[1:]):
        if nxt - prev != 1:
            for missing in range(prev + 1, nxt):
                report.add(domain, "(coverage)", geo, missing, None,
                           f"between {prev} and {nxt}",
                           f"missing year in {domain} sequence", "BLOCKER")
    # metric/column completeness (check most recent file)
    if not years:
        report.add(domain, "(coverage)", geo, None, None, None,
                   f"no files found for {domain}", "BLOCKER")
        return
    last_lbl = data["__order__"][-1]
    cols = set(data[last_lbl].columns)
    if domain == "health":
        for c in HEALTH_CONDITIONS:
            if f"{c}_afflicted_rate" not in cols:
                report.add(domain, f"{c}_afflicted_rate", geo, last_lbl, None,
                           None, "missing expected health condition column",
                           "BLOCKER")
    elif domain == "crime":
        for t in CRIME_TYPES:
            if f"{t}_rate" not in cols:
                report.add(domain, f"{t}_rate", geo, last_lbl, None, None,
                           "missing expected crime type column", "BLOCKER")


def check_series(report, geo, domain, area_name, metric, labels,
                 rates, counts, pops):
    arr = np.array(rates, dtype=float)

    # ---- all-zero metric (INFO) ----
    finite = arr[np.isfinite(arr)]
    if finite.size and np.allclose(finite, 0.0):
        report.add(domain, metric, geo, "all", 0.0, None,
                   "metric is exactly zero across all years", "INFO")
        # still run bounds/NaN below but skip reversal/structural (no baseline)
        all_zero = True
    else:
        all_zero = False

    for i, (lbl, v) in enumerate(zip(labels, arr)):
        # ---- NaN where expected ----
        if not np.isfinite(v):
            report.add(domain, metric, geo, lbl, v, None,
                       "value is NaN/missing where a value is expected",
                       "BLOCKER")
            continue
        # ---- bounds ----
        if is_rate_in_unit_interval(domain):
            if v < 0 or v > 1:
                report.add(domain, metric, geo, lbl, v, "[0,1]",
                           "rate outside [0,1]", "BLOCKER")
        else:  # crime
            if v < 0:
                report.add(domain, metric, geo, lbl, v, ">=0",
                           "negative per-capita crime rate", "BLOCKER")
            elif v > CRIME_RATE_CEILING:
                report.add(domain, metric, geo, lbl, v,
                           f"< {CRIME_RATE_CEILING}",
                           "crime rate above sane ceiling", "WARN")

    if all_zero:
        return

    # ---- zero-transition (added/removed indicator, or data absent emitted as
    # exactly 0). Reported separately so the reversal/structural checks below
    # can require non-zero windows and stay free of zero-boundary noise. ----
    has_zero = np.any(np.isfinite(arr) & (np.abs(arr) <= EPS))
    has_nonzero = np.any(np.isfinite(arr) & (np.abs(arr) > EPS))
    if has_zero and has_nonzero:
        for i in range(1, len(arr)):
            prev, v = arr[i - 1], arr[i]
            if not (np.isfinite(prev) and np.isfinite(v)):
                continue
            if abs(prev) > EPS and abs(v) <= EPS:
                report.add(domain, metric, geo, labels[i], v,
                           f"prev={prev:.4g}",
                           "metric drops to exactly 0 (indicator removed or "
                           "data absent emitted as 0)", "WARN")
            elif abs(prev) <= EPS and abs(v) > EPS:
                report.add(domain, metric, geo, labels[i], v,
                           f"prev={prev:.4g}",
                           "metric becomes non-zero from 0 (indicator added)",
                           "WARN")

    # ---- structural break (persistent level shift, non-zero window) ----
    structural_years: set[str] = set()
    for i in range(1, len(arr) - 1):
        prev, v, nxt = arr[i - 1], arr[i], arr[i + 1]
        if not (np.isfinite(prev) and np.isfinite(v) and np.isfinite(nxt)):
            continue
        if prev <= EPS or v <= EPS:
            continue
        ratio = v / prev
        if ratio > STEP_RATIO or ratio < 1.0 / STEP_RATIO:
            # persists if next stays near the new level (does not revert)
            if 1.0 / STEP_RATIO < (nxt / v) < STEP_RATIO:
                structural_years.add(labels[i])
                report.add(domain, metric, geo, labels[i], v,
                           f"prev={prev:.4g}, next={nxt:.4g}",
                           f"structural level shift ({ratio:.1f}x vs prior "
                           f"year, persists) — possible indicator/schema change",
                           "WARN")

    # ---- reversal (interior years, non-zero window only) ----
    for i in range(1, len(arr) - 1):
        prev, v, nxt = arr[i - 1], arr[i], arr[i + 1]
        if not (np.isfinite(prev) and np.isfinite(v) and np.isfinite(nxt)):
            continue
        if prev <= EPS or v <= EPS or nxt <= EPS:
            continue  # zero-boundary handled by the zero-transition check
        nmean = (prev + nxt) / 2.0
        dev = abs(v - nmean) / abs(nmean)
        spread = abs(prev - nxt) / abs(nmean)
        if dev > REVERSAL_DEV:
            ctx = f"prev={prev:.4g}, next={nxt:.4g}, nmean={nmean:.4g}"
            if spread < REVERSAL_SPREAD:
                report.add(domain, metric, geo, labels[i], v, ctx,
                           f"reversing anomaly: {dev*100:.0f}% off neighbour "
                           f"mean, neighbours agree (spread {spread*100:.0f}%)",
                           "BLOCKER")
            elif labels[i] not in structural_years:
                report.add(domain, metric, geo, labels[i], v, ctx,
                           f"large deviation ({dev*100:.0f}%) but neighbours "
                           f"disagree (spread {spread*100:.0f}%) — possible "
                           f"legitimate shock, review", "WARN")

    # ---- internal consistency: rate ~= count/pop ----
    for lbl, r, c, p in zip(labels, rates, counts, pops):
        if not (np.isfinite(r) and np.isfinite(c) and np.isfinite(p)):
            continue
        if p <= 0:
            report.add(domain, metric, geo, lbl, p, None,
                       "population is zero/negative", "BLOCKER")
            continue
        implied = c / p
        denom = max(abs(r), EPS)
        if abs(implied - r) / denom > CONSISTENCY_TOL:
            report.add(domain, metric, geo, lbl, r,
                       f"count/pop={implied:.4g}",
                       f"rate != count/pop (off {abs(implied-r)/denom*100:.1f}%)",
                       "WARN")


def check_population(report, geo, domain, area_name, labels, pops):
    arr = np.array(pops, dtype=float)
    for i, (lbl, p) in enumerate(zip(labels, arr)):
        if not np.isfinite(p):
            continue
        if p <= 0:
            report.add(domain, "pop", geo, lbl, p, None,
                       "population zero/negative", "BLOCKER")
    for i in range(1, len(arr)):
        prev, p = arr[i - 1], arr[i]
        if not (np.isfinite(prev) and np.isfinite(p)) or prev <= 0:
            continue
        if abs(p - prev) / prev > POP_JUMP:
            report.add(domain, "pop", geo, labels[i], p,
                       f"prev={prev:.0f}",
                       f"population jumped {abs(p-prev)/prev*100:.0f}% "
                       f"year-on-year", "WARN")


def check_england_vs_regions(report, base, run, domain):
    """England absolute counts/pop ~= sum over regions."""
    eng = load_domain(base, "england", domain)
    reg = load_domain(base, "region", domain)
    eng_code = eng["__order__"] and next(iter(eng[eng["__order__"][0]].index))
    for lbl in eng["__order__"]:
        if lbl not in reg:
            continue
        edf, rdf = eng[lbl], reg[lbl]
        ecode = next(iter(edf.index))
        # which count columns to compare
        if domain == "claimant_counts":
            cols = ["claimant_count", "pop"]
        elif domain == "crime":
            cols = CRIME_TYPES + ["pop"]
        else:
            cols = [f"{c}_afflicted" for c in HEALTH_CONDITIONS] + ["pop"]
        for col in cols:
            if col not in edf.columns or col not in rdf.columns:
                continue
            e_val = float(edf.loc[ecode, col])
            r_sum = float(rdf[col].sum())
            if abs(e_val) < EPS and abs(r_sum) < EPS:
                continue
            denom = max(abs(e_val), EPS)
            if abs(e_val - r_sum) / denom > AGG_TOL:
                report.add(domain, col, "england-vs-regions", lbl, e_val,
                           f"sum(regions)={r_sum:.4g}",
                           f"England count != sum of regions "
                           f"(off {abs(e_val-r_sum)/denom*100:.1f}%)", "WARN")


# --------------------------------------------------------------------------- #
# Reporting                                                                    #
# --------------------------------------------------------------------------- #
def fmt_value(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def print_report(report: Report) -> None:
    rows = report.sorted_rows()
    counts = {"BLOCKER": 0, "WARN": 0, "INFO": 0}
    for r in rows:
        counts[r["severity"]] += 1

    print("=" * 100)
    print("ADI OUTPUT VALIDATION REPORT")
    print("=" * 100)
    if not rows:
        print("No findings. All checks passed.")
        return

    header = ["SEVERITY", "DOMAIN", "METRIC", "GEOGRAPHY", "YEAR", "VALUE",
              "NEIGHBOURS", "REASON"]
    widths = [9, 16, 24, 18, 9, 12, 34, 60]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
    print(line)
    print("-" * len(line))
    for r in rows:
        cells = [
            r["severity"], r["domain"], str(r["metric"]), r["geography"],
            str(r["year"]), fmt_value(r["value"]),
            fmt_value(r["neighbours"]), r["reason"],
        ]
        print("  ".join(str(c)[:w].ljust(w) for c, w in zip(cells, widths)))
    print("-" * len(line))
    print(f"SUMMARY: {counts['BLOCKER']} BLOCKER, {counts['WARN']} WARN, "
          f"{counts['INFO']} INFO")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="default", help="run name under store/outputs/")
    ap.add_argument("--outputs-root", default=None,
                    help="override store/outputs root (default: repo store/outputs)")
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    root = Path(args.outputs_root) if args.outputs_root else repo_root / "store" / "outputs"
    base = root / args.run

    if not base.exists():
        print(f"ERROR: outputs not found at {base}", file=sys.stderr)
        return 2

    report = Report()

    for geo in GEOGRAPHIES:
        for domain in DOMAINS:
            ddir = base / geo / domain
            if not ddir.exists():
                report.add(domain, "(coverage)", geo, None, None, None,
                           f"domain directory missing: {ddir}", "BLOCKER")
                continue
            data = load_domain(base, geo, domain)
            check_coverage(report, geo, domain, data)
            if not data["__order__"]:
                continue
            # iterate areas present in latest file
            last = data["__order__"][-1]
            codes = list(data[last].index)
            names = {c: data[last].loc[c, "name"] for c in codes}
            for code in codes:
                gname = f"{geo}:{names[code]}"
                # population series check (once per area)
                pop_labels = data["__order__"]
                pop_vals = []
                for lbl in pop_labels:
                    df = data[lbl]
                    pop_vals.append(float(df.loc[code, "pop"])
                                    if code in df.index and "pop" in df.columns
                                    else np.nan)
                check_population(report, gname, domain, names[code],
                                 pop_labels, pop_vals)
                for metric, rate_col, count_col in metric_specs(domain):
                    labels, rates, counts, pops = build_series(
                        data, code, rate_col, count_col, domain)
                    check_series(report, gname, domain, names[code], metric,
                                 labels, rates, counts, pops)

    # England vs sum-of-regions (per domain)
    for domain in DOMAINS:
        if (base / "england" / domain).exists() and (base / "region" / domain).exists():
            check_england_vs_regions(report, base, args.run, domain)

    if args.json:
        out = {
            "run": args.run,
            "findings": report.sorted_rows(),
            "has_blocker": report.has_blocker(),
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print_report(report)

    return 1 if report.has_blocker() else 0


if __name__ == "__main__":
    sys.exit(main())
