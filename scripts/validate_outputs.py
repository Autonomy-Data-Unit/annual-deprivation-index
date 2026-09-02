#!/usr/bin/env python
"""
ADI output data-quality validator (all four geography levels).

Validates the final pipeline outputs under
``store/outputs/{run}/{england,region,lad,lsoa}/{claimant_counts,crime,health}/*.csv``
across all years, for every (domain, metric, geography), and emits a report of
flagged anomalies. Exits non-zero if any BLOCKER-severity finding is present.

Scope
-----
The validator originally checked England (1 area) and Region (9) only, on the
premise that "any LSOA/LAD-level data issue of meaningful size will surface in
the aggregates anyway". That premise is false and cost this project real
blockers: Buckinghamshire's QOF 2017-18 prevalence collapsed by 94% and moved
England by 0.86%, far below any sane national threshold. A LAD is 0.2-1% of
England, so a LAD-sized defect is arithmetically incapable of surfacing in the
aggregate.

So we now check all four levels, with the work split by what each level can
usefully bear:

* **england / region / lad** (306 areas) get the full per-area time-series
  treatment: reversal, structural break, bounds, NaN, rate identity.
* **lsoa** (33,749 areas x 12 years x 3 domains) gets a vectorised pass only —
  invariants that are cheap to evaluate over whole columns (rate identity,
  bounds, NaN coherence, area-set completeness, split-family coherence). The
  per-area anomaly heuristics are deliberately NOT run at LSOA level: with
  33,749 small-count areas they would produce thousands of findings a human
  would never read. Use ``--no-lsoa`` to skip the LSOA pass entirely.

Usage
-----
    uv run --with pandas --with numpy python scripts/validate_outputs.py
    uv run --with pandas --with numpy python scripts/validate_outputs.py --run default
    uv run --with pandas --with numpy python scripts/validate_outputs.py --json
    uv run --with pandas --with numpy python scripts/validate_outputs.py --no-lsoa

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
   Runs at england/region/lad only, and only for areas above REL_POP_FLOOR:
   in a 2,000-person area a handful of bicycle thefts reverses every year.

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
   - rate == count / <metric>_pop, exactly                    -> BLOCKER
     Every count carries the population it actually covers
     (`Burglary_pop`, `DM_afflicted_pop`, ...), which is NOT the area `pop`
     wherever an area was excluded from that metric. This is exact arithmetic
     performed by the pipeline, not an estimate, so any drift beyond floating
     point is a defect rather than a rounding artefact.
   - count is NaN  <=>  <metric>_pop is NaN                   -> BLOCKER
     An area excluded from a metric must contribute to neither the numerator
     nor the denominator. A published count with no covered population (or a
     covered population with no count) is how a suppressed area silently
     re-enters a rate.
   - 0 < <metric>_pop <= pop                                  -> BLOCKER
   - population year-on-year change > POP_JUMP (20%)          -> WARN

5. ADDITIVITY LADDER (new). Sum(LSOA) == LAD, Sum(LAD) == Region,
   Sum(Region) == England, for every count column AND every population column,
   in every domain-year.
       BLOCKER  if the relative gap exceeds AGG_TOL_HARD (1e-6)
       BLOCKER  if one side is NaN and the other is not
   The pipeline computes these by summation, so they agree to ~4e-16 in
   practice; the tolerance is a floating-point allowance, not a judgement.
   Previously only England-vs-regions was compared, at a 2% tolerance, and
   only ever as a WARN — a whole region's count could vanish with exit code 0.

6. COVERAGE.
   - no gaps in the per-domain year sequence                 -> BLOCKER
   - full metric/column set present
     (24 health conditions, 14 crime types)                  -> BLOCKER
   - every domain-year carries the SAME area codes as the run's canonical set
     for that level                                          -> BLOCKER
     51 LSOA-years once vanished from the health outputs because whole practice
     cohorts were missing from a QOF year; the areas simply stopped existing in
     those files and nothing noticed.

7. QOF PUBLICATION WINDOWS. Outside a group's window a NaN is correct and is
   suppressed. Inside its window a NaN is a defect. NEW: a *finite* value
   outside the window is also a defect -> BLOCKER. Without that assertion,
   regressing `SMOK`/`THY`/`CVDPP` back to hard 0.0 — the exact defect the
   min_count work removed — passes with zero blockers.

8. RELATIVE LEVEL (new). For each area and domain, take the domain's total rate
   as a fraction of England's for the same year, then compare each year against
   that area's own median fraction. A source-coverage failure (a police force
   supplying half a year; a QOF year missing a whole practice cohort) collapses
   every metric in the domain at once, in one area, without touching the
   national figure — which is exactly what this ratio detects and what the
   year-on-year heuristics miss when the neighbouring year is NaN.
       BLOCKER  below REL_LEVEL_BLOCK (0.35), or whenever REL_LEVEL_CLUSTER
                (3) or more areas fall below the WARN line in the same
                domain-year — one authority can have a quiet year, a police
                force covering ten of them cannot
       WARN     a lone area below REL_LEVEL_WARN (0.55)
   Restricted to crime and health, and to areas above REL_POP_FLOOR — see the
   comments on those constants for why.

9. SPLIT-FAMILY COHERENCE (new, LSOA only). The 2011->2021 crosswalk carries no
   information that could distinguish two children of one split LSOA 2011, so
   every child of a split family must publish the SAME rate. They did not when
   the crosswalk was weighted with a different population year from the one it
   was published against; siblings came out up to 3.28x apart. -> BLOCKER

10. INFO. A metric that is exactly zero across every year is reported as INFO
    (e.g. CVDPP / SMOK / THY are never populated in the current outputs).

Reading the report
------------------
Checking 296 LADs instead of 10 aggregates multiplies every national defect by
the number of areas: DEP 2023-24 is one finding at England level and 295 at LAD
level. All of them are real, but a 2,000-row report is one nobody reads. So
below Region, findings that are the same defect in the same metric and year are
printed as a single row carrying the area count and a few examples. ``--verbose``
prints every area. England and Region are never collapsed — with 10 areas the
per-area detail is the point.

A NaN is not automatically a defect. When a count, its rate AND its covered
population are all absent together, the area was deliberately excluded from that
metric (a force that supplied part of a year; a source that never covered the
area) and contributes to neither the numerator nor the denominator of any total.
That is the correct representation and is passed over in silence. What IS
reported is incoherence: any one of the three present without the others.
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
CONSISTENCY_TOL = 1e-9    # rate vs count/<metric>_pop: floating-point allowance.
                          # The pipeline divides these two published numbers to
                          # get the published rate, so they must agree exactly.
AGG_TOL_HARD = 1e-6       # additivity ladder: relative gap that is a BLOCKER.
                          # Observed worst case on a healthy run is 4.4e-16.
POP_JUMP = 0.20           # tolerated year-on-year population change

# --- relative-level check ---------------------------------------------------
# Applied to CRIME and HEALTH only. Both are assembled from third-party returns
# that can fail per-area (a police force stopping mid-year; a QOF year missing a
# whole practice cohort), and both are stable enough between areas that a real
# collapse stands out: on a healthy run the worst LAD-year sits at 0.59 (crime)
# and 0.88 (health) of its own median relative level.
#
# The claimant domain is deliberately EXCLUDED. It is a single Nomis
# administrative extract with no per-area reporting body that can drop out, and
# the rollout of the Claimant Count's Universal Credit component genuinely re-ranked
# areas. Stratford-on-Avon really does sit at 0.43 of its own median in 2015.
# Including it would produce 46 findings, all true features of the series.
REL_LEVEL_DOMAINS = ("crime", "health")
REL_LEVEL_BLOCK = 0.35    # collapse: Buckinghamshire QOF 2017-18 scored 0.056
REL_LEVEL_WARN = 0.55     # partial coverage: Greater Manchester 2019 scored ~0.50
# A single authority can genuinely have a quiet year; a police force or an NHS
# region cannot. When SEVERAL areas drop below REL_LEVEL_WARN together, in the
# same domain and the same year, that is a supplier failing rather than a local
# trend -- Greater Manchester Police covers ten local authorities and all ten
# collapsed together in 2019. So a cluster is a BLOCKER even when no individual
# area is far enough down to be one on its own. On a healthy run no crime or
# health LAD-year falls below REL_LEVEL_WARN at all, so this never fires today.
REL_LEVEL_CLUSTER = 3
REL_POP_FLOOR = 20_000    # areas smaller than this are excluded from the
                          # relative-level and reversal checks. The Isles of
                          # Scilly (pop ~2,200) genuinely records zero robberies
                          # in some years; it is not a data-quality signal.

# Split-family coherence: children of one split LSOA 2011 must publish the same
# rate. Allow a little more than EPS because the rate is a ratio of two
# independently summed floats.
SPLIT_RATE_TOL = 1e-9

# --- anomaly heuristics below Region ----------------------------------------
# The reversal / structural / zero-transition heuristics were tuned on England
# and the 9 regions, where every metric is an aggregate of tens of thousands of
# events. Run unchanged over 296 LADs they produce 767 findings across 80
# metric-years, the great majority single-authority one-year bumps in
# low-volume crime types: Broadland's "theft from the person" going 5 -> 17 -> 6
# offences is a 196% reversing anomaly and is not a data defect.
#
# So below Region the heuristics require the metric to be carrying real volume.
# The floor is empirical, not statistical: every defect this validator exists to
# catch clears it with room to spare (DEP 2023-24 LAD counts run 500-3,400;
# Buckinghamshire's collapsed QOF 2017-18 diabetes count was 1,361; the
# Hinckley and Bosworth epilepsy outlier 3,931), while it removes 93% of the
# single-authority crime noise.
ANOMALY_MIN_COUNT = 300   # mean of the two neighbouring years' counts

# Below Region, a reversing anomaly is a BLOCKER for health only. Disease
# prevalence is a slow, smooth quantity -- a 50%+ dip that reverses the next
# year is always an artefact, which is exactly how DEP 2023-24 was found. Local
# crime genuinely does spike and subside (one operation, one offender, one
# retail park), so at LAD level those are WARN; the England and regional
# aggregates still block on them, unchanged.
ANOMALY_BLOCKER_DOMAINS_BELOW_REGION = ("health",)

# 24 health condition codes expected in every health file.
HEALTH_CONDITIONS = [
    "AF", "AST", "CAN", "CHD", "CKD", "COPD", "DEM", "DEP", "DM", "EP", "HF",
    "HYP", "LD", "MH", "NDH", "OB", "OST", "PAD", "PC", "RA", "STIA", "CVDPP",
    "SMOK", "THY",
]
# QOF prevalence groups that NHS Digital stopped publishing, and the last QOF
# year each appeared in. Outside its window a group is legitimately ABSENT: NaN
# there is the correct representation of "not collected" and must not be
# reported as missing data. Inside its window, a NaN is still a real defect.
#
# Before the aggregation fix these arrived as 0.0, which the validator was happy
# with -- that is precisely the bug: a hard zero asserts the disease was
# measured at nil prevalence. check_series now also rejects a FINITE value
# outside the window, so that regression cannot come back silently.
# (first, last) inclusive. Read off the raw NHS Digital prevalence files:
# smoking and hypothyroidism appear only in 2013-14; CVD primary prevention
# runs to 2019-20 and is replaced by non-diabetic hyperglycaemia in 2020-21.
QOF_GROUP_WINDOW = {
    "SMOK": ("2013-14", "2013-14"),
    "THY": ("2013-14", "2013-14"),
    "CVDPP": ("2013-14", "2019-20"),
    "NDH": ("2020-21", None),
}


def qof_group_published(condition: str, year_label: str) -> bool:
    """Was `condition` published in QOF year `year_label` (e.g. "2021-22")?

    Labels are YYYY-YY and sort lexicographically in chronological order.
    A group with no entry here is expected in every year.
    """
    window = QOF_GROUP_WINDOW.get(condition)
    if window is None:
        return True
    first, last = window
    if first is not None and year_label < first:
        return False
    return last is None or year_label <= last


def condition_of(metric: str) -> str:
    """Health condition code for a metric like "SMOK_afflicted_rate"."""
    return metric.split("_", 1)[0]


# 14 crime types expected in every crime file.
CRIME_TYPES = [
    "Anti-social behaviour", "Bicycle theft", "Burglary",
    "Criminal damage and arson", "Drugs", "Other crime", "Other theft",
    "Possession of weapons", "Public order", "Robbery", "Shoplifting",
    "Theft from the person", "Vehicle crime", "Violence and sexual offences",
]

# Levels that get the full per-area time-series treatment, coarsest first.
# LSOA is handled separately by check_lsoa_level -- see the module docstring.
GEOGRAPHIES = ["england", "region", "lad"]
# The additivity ladder, child -> parent. LSOA is included even when the LSOA
# series checks are skipped: summing one column per file is cheap.
LADDER = [("lsoa", "lad"), ("lad", "region"), ("region", "england")]
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


def load_domain(base: Path, geo: str, domain: str,
                usecols=None) -> dict[str, pd.DataFrame]:
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
        df = pd.read_csv(f, usecols=usecols)
        code_col, name_col = df.columns[0], df.columns[1]
        df = df.rename(columns={code_col: "code", name_col: "name"})
        df = df.set_index("code")
        out[label] = df
        order.append((sort_year, label))
    out["__order__"] = [lbl for _, lbl in sorted(order)]  # type: ignore
    out["__years__"] = sorted(order)  # type: ignore
    return out


def count_columns(df: pd.DataFrame, domain: str) -> list[str]:
    """Absolute-count columns for a domain, in file order."""
    if domain == "claimant_counts":
        return [c for c in ["claimant_count"] if c in df.columns]
    if domain == "crime":
        return [t for t in CRIME_TYPES if t in df.columns]
    return [f"{c}_afflicted" for c in HEALTH_CONDITIONS
            if f"{c}_afflicted" in df.columns]


def metric_pop_col(count_col: str) -> str:
    """The population a given count actually covers.

    Every count now carries its own denominator (`Burglary_pop`,
    `DM_afflicted_pop`, `claimant_count_pop`). It differs from the area `pop`
    wherever an area was excluded from that metric, and it — not `pop` — is
    what the published rate divides by.
    """
    return f"{count_col}_pop"


# --------------------------------------------------------------------------- #
# Report accumulation                                                          #
# --------------------------------------------------------------------------- #
class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, domain, metric, geography, year, value, neighbours, reason,
            severity, group=None):
        """Record a finding.

        `group` collapses findings that are the same defect seen in many areas.
        Extending the validator below Region multiplies every national defect by
        the number of areas: DEP 2023-24 is one finding at England level and 295
        at LAD level. They are all real, but a report of 2,000 rows is a report
        nobody reads, and the blocker count stops meaning anything. Findings
        sharing a group key are printed as one row carrying the area count and a
        few examples; `--verbose` prints them individually.
        """
        self.rows.append({
            "domain": domain,
            "metric": metric,
            "geography": geography,
            "year": year,
            "value": value,
            "neighbours": neighbours,
            "reason": reason,
            "severity": severity,
            "group": group,
        })

    def has_blocker(self) -> bool:
        return any(r["severity"] == "BLOCKER" for r in self.rows)

    def sorted_rows(self) -> list[dict]:
        return sorted(
            self.rows,
            key=lambda r: (SEVERITY_ORDER[r["severity"]], r["domain"],
                           r["geography"], str(r["metric"]), str(r["year"])),
        )

    def collapsed_rows(self) -> list[dict]:
        """One row per group; ungrouped findings pass through unchanged."""
        groups: dict[tuple, list[dict]] = {}
        out: list[dict] = []
        for r in self.sorted_rows():
            if r["group"] is None:
                out.append(r)
            else:
                groups.setdefault(r["group"], []).append(r)
        for key, members in groups.items():
            first = dict(members[0])
            if len(members) == 1:
                out.append(first)
                continue
            areas = [m["geography"].split(":", 1)[-1] for m in members]
            first["geography"] = f"{members[0]['geography'].split(':', 1)[0]}"
            first["n_areas"] = len(members)
            first["reason"] = (f"{len(members)} areas: {first['reason']}")
            first["neighbours"] = ("e.g. " + ", ".join(areas[:3])
                                   + (f" (+{len(areas) - 3} more)"
                                      if len(areas) > 3 else ""))
            out.append(first)
        return sorted(
            out,
            key=lambda r: (SEVERITY_ORDER[r["severity"]], r["domain"],
                           r["geography"], str(r["metric"]), str(r["year"])),
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
def build_matrices(data, domain):
    """Pre-slice a (geo, domain) into per-metric matrices.

    Returns (labels, area_pop, {metric: (rates, counts, mpops)}) where each
    value is a DataFrame indexed by area code with one column per year label.

    Doing this once per (geo, domain) rather than per (area, metric) is what
    makes the LAD level affordable: 296 areas x 40 metrics x 12 years is
    142,000 row lookups the slow way, and ~40 concatenations this way.
    """
    labels = data["__order__"]
    codes = data[labels[-1]].index

    def frame(col, derived=None):
        cols = {}
        for lbl in labels:
            df = data[lbl]
            if derived is not None:
                cols[lbl] = derived(df).reindex(codes)
            elif col in df.columns:
                cols[lbl] = df[col].reindex(codes)
            else:
                cols[lbl] = pd.Series(np.nan, index=codes)
        return pd.DataFrame(cols, index=codes)

    area_pop = frame("pop")

    out = {}
    for metric, rate_col, count_col in metric_specs(domain):
        if rate_col is None:
            # derived total crime: sum the 14 type counts, and use the coverage
            # population they share (all 14 are excluded together, so max() is
            # simply the common value, and NaN when the area is excluded).
            def _cnt(df):
                cols = [t for t in CRIME_TYPES if t in df.columns]
                return df[cols].sum(axis=1, min_count=1)

            def _pop(df):
                cols = [metric_pop_col(t) for t in CRIME_TYPES
                        if metric_pop_col(t) in df.columns]
                return df[cols].max(axis=1) if cols else pd.Series(np.nan, index=df.index)

            counts = frame(None, derived=_cnt)
            mpops = frame(None, derived=_pop)
            rates = counts / mpops.replace(0, np.nan)
        else:
            counts = frame(count_col)
            mpops = frame(metric_pop_col(count_col))
            rates = frame(rate_col)
        out[metric] = (rates, counts, mpops)
    return labels, area_pop, out


def build_series(data, code, rate_col, count_col, domain):
    """Ordered (labels, rates, counts, covered_pops) for one area and metric.

    A single-area accessor, kept as the module's simple entry point (and used by
    tests/test_validate_outputs.py). main() uses build_matrices instead: at LAD
    level this would do 142,000 row lookups where the matrix form does ~40
    concatenations.
    """
    labels = data["__order__"]
    rates, counts, pops = [], [], []
    for lbl in labels:
        df = data[lbl]
        if code not in df.index:
            rates.append(np.nan); counts.append(np.nan); pops.append(np.nan)
            continue
        row = df.loc[code]
        if rate_col is None:  # derived total crime
            types = [t for t in CRIME_TYPES if t in df.columns]
            cnt = float(pd.Series([row[t] for t in types]).sum(min_count=1))
            pcols = [metric_pop_col(t) for t in types
                     if metric_pop_col(t) in df.columns]
            pop = float(max((row[c] for c in pcols), default=np.nan))
            counts.append(cnt)
            pops.append(pop)
            rates.append(cnt / pop if pop and pop > 0 else np.nan)
        else:
            counts.append(float(row[count_col]) if count_col in df.columns
                          else np.nan)
            pcol = metric_pop_col(count_col)
            pops.append(float(row[pcol]) if pcol in df.columns else np.nan)
            rates.append(float(row[rate_col]) if rate_col in df.columns
                         else np.nan)
    return labels, rates, counts, pops


# --------------------------------------------------------------------------- #
# Checks                                                                       #
# --------------------------------------------------------------------------- #
def check_coverage(report, geo, domain, data, canonical_codes=None):
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
            if not qof_group_published(c, last_lbl):
                continue  # withdrawn from QOF by this year -- absence is correct
            if f"{c}_afflicted_rate" not in cols:
                report.add(domain, f"{c}_afflicted_rate", geo, last_lbl, None,
                           None, "missing expected health condition column",
                           "BLOCKER")
    elif domain == "crime":
        for t in CRIME_TYPES:
            if f"{t}_rate" not in cols:
                report.add(domain, f"{t}_rate", geo, last_lbl, None, None,
                           "missing expected crime type column", "BLOCKER")

    # ---- area-set completeness -------------------------------------------- #
    if canonical_codes is None:
        canonical_codes = set().union(*[set(data[lbl].index)
                                        for lbl in data["__order__"]])
    # Every domain-year must carry the same areas. 51 LSOA-years once vanished
    # from the health outputs (Buckinghamshire 2017-18, Cornwall 2018-19)
    # because whole practice cohorts were missing from a QOF year; the areas
    # simply stopped existing in those files and no check noticed. An area that
    # has no data should be a row of NaNs, not an absent row.
    for lbl in data["__order__"]:
        present = set(data[lbl].index)
        missing = canonical_codes - present
        extra = present - canonical_codes
        if missing:
            sample = ", ".join(sorted(missing)[:4])
            report.add(domain, "(coverage)", geo, lbl, len(missing),
                       f"e.g. {sample}",
                       f"{len(missing)} area(s) absent from this file but "
                       f"present elsewhere in the run", "BLOCKER")
        if extra:
            sample = ", ".join(sorted(extra)[:4])
            report.add(domain, "(coverage)", geo, lbl, len(extra),
                       f"e.g. {sample}",
                       f"{len(extra)} area(s) present here and nowhere else "
                       f"in the run", "BLOCKER")


def check_series(report, geo, domain, area_name, metric, labels, rates, counts,
                 mpops, heuristics=True, level="england"):
    """Per-area time-series checks. All four inputs are float arrays.

    With ``heuristics=False`` only the exact-arithmetic invariants run (NaN
    coherence, QOF windows, bounds, rate == count / covered population). The
    year-on-year anomaly heuristics are skipped for areas below REL_POP_FLOOR,
    where a handful of events reverses every year and every finding is noise.
    """
    arr = np.asarray(rates, dtype=float)
    cnt = np.asarray(counts, dtype=float)
    mp = np.asarray(mpops, dtype=float)

    # ---- all-zero metric (INFO) ----
    finite = arr[np.isfinite(arr)]
    if finite.size and np.allclose(finite, 0.0):
        report.add(domain, metric, geo, "all", 0.0, None,
                   "metric is exactly zero across all years", "INFO")
        all_zero = True
    else:
        all_zero = False

    for i, (lbl, v) in enumerate(zip(labels, arr)):
        in_window = (domain != "health"
                     or qof_group_published(condition_of(metric), lbl))
        # ---- NaN where expected ----
        if not np.isfinite(v):
            if not in_window:
                # Not collected by NHS Digital that year. Correctly represented
                # as missing rather than zero; not a data defect.
                continue
            if not np.isfinite(cnt[i]) and not np.isfinite(mp[i]):
                # A COHERENT EXCLUSION, not missing data: the count, the rate
                # and the covered population are all absent together, so the
                # area contributes to neither the numerator nor the denominator
                # of any total. This is how a police force that supplied part
                # of a year, or an area a source never covered, is correctly
                # represented. The incoherent cases -- exactly one of the three
                # present -- are caught below and by check_lsoa_level.
                continue
            report.add(domain, metric, geo, lbl, v,
                       f"count={cnt[i]:.6g}, {metric}_pop={mp[i]:.6g}",
                       "rate is NaN but the count and/or its covered "
                       "population is present — an excluded area must drop out "
                       "of all three", "BLOCKER",
                       group=_grp(level, domain, metric, lbl, "nan-incoherent"))
            continue
        # ---- a value OUTSIDE a QOF publication window ----
        # The converse of the suppression above, and the check that stops a
        # regression to hard zeros passing silently: NHS Digital did not
        # publish this group that year, so there is nothing a number here can
        # legitimately mean.
        if not in_window:
            report.add(domain, metric, geo, lbl, v,
                       f"window={QOF_GROUP_WINDOW[condition_of(metric)]}",
                       "value published for a QOF group NHS Digital did not "
                       "collect that year (0.0 here asserts 'measured at nil')",
                       "BLOCKER",
                       group=_grp(level, domain, metric, lbl, "qof-window"))
            continue
        # ---- bounds ----
        if is_rate_in_unit_interval(domain):
            if v < 0 or v > 1:
                report.add(domain, metric, geo, lbl, v, "[0,1]",
                           "rate outside [0,1]", "BLOCKER",
                           group=_grp(level, domain, metric, lbl, "bounds"))
        else:  # crime
            if v < 0:
                report.add(domain, metric, geo, lbl, v, ">=0",
                           "negative per-capita crime rate", "BLOCKER",
                           group=_grp(level, domain, metric, lbl, "bounds"))
            elif v > CRIME_RATE_CEILING:
                report.add(domain, metric, geo, lbl, v,
                           f"< {CRIME_RATE_CEILING}",
                           "crime rate above sane ceiling", "WARN",
                           group=_grp(level, domain, metric, lbl, "ceiling"))
        # ---- count present without a rate ----
        if np.isfinite(cnt[i]) and not np.isfinite(mp[i]):
            report.add(domain, metric, geo, lbl, cnt[i], "metric pop = NaN",
                       "count published with no covered population",
                       "BLOCKER",
                       group=_grp(level, domain, metric, lbl, "count-no-pop"))

    # ---- count NaN where a value is expected (rate may still be finite) ----
    for i, lbl in enumerate(labels):
        in_window = (domain != "health"
                     or qof_group_published(condition_of(metric), lbl))
        if not in_window:
            continue
        if not np.isfinite(cnt[i]) and np.isfinite(arr[i]):
            report.add(domain, metric, geo, lbl, cnt[i],
                       f"rate={arr[i]:.6g}",
                       "count is NaN but the rate is present", "BLOCKER",
                       group=_grp(level, domain, metric, lbl, "nan-count"))

    if all_zero or not heuristics:
        # The rate-identity check below is exact arithmetic and must still run
        # for small areas; jump straight to it.
        if not all_zero:
            _check_rate_identity(report, geo, domain, metric, labels, arr, cnt,
                                 mp, level)
        return

    # ---- zero-transition (added/removed indicator, or data absent emitted as
    # exactly 0). Reported separately so the reversal/structural checks below
    # can require non-zero windows and stay free of zero-boundary noise. ----
    has_zero = np.any(np.isfinite(arr) & (np.abs(arr) <= EPS))
    has_nonzero = np.any(np.isfinite(arr) & (np.abs(arr) > EPS))
    below_region = level not in ("england", "region")

    def volume_ok(i):
        """Is this metric carrying enough events for a swing to mean anything?

        Only enforced below Region -- see ANOMALY_MIN_COUNT.
        """
        if not below_region:
            return True
        lo = cnt[i - 1] if i > 0 else np.nan
        hi = cnt[i + 1] if i + 1 < len(cnt) else np.nan
        neighbours = [x for x in (lo, hi) if np.isfinite(x)]
        if not neighbours:
            return False
        return float(np.mean(neighbours)) >= ANOMALY_MIN_COUNT

    def anomaly_severity():
        if not below_region:
            return "BLOCKER"
        return ("BLOCKER" if domain in ANOMALY_BLOCKER_DOMAINS_BELOW_REGION
                else "WARN")

    if has_zero and has_nonzero:
        for i in range(1, len(arr)):
            prev, v = arr[i - 1], arr[i]
            if not (np.isfinite(prev) and np.isfinite(v)):
                continue
            if not volume_ok(i):
                continue
            if abs(prev) > EPS and abs(v) <= EPS:
                report.add(domain, metric, geo, labels[i], v,
                           f"prev={prev:.4g}",
                           "metric drops to exactly 0 (indicator removed or "
                           "data absent emitted as 0)", "WARN",
                           group=_grp(level, domain, metric, labels[i], "zero-drop"))
            elif abs(prev) <= EPS and abs(v) > EPS:
                report.add(domain, metric, geo, labels[i], v,
                           f"prev={prev:.4g}",
                           "metric becomes non-zero from 0 (indicator added)",
                           "WARN",
                           group=_grp(level, domain, metric, labels[i], "zero-rise"))

    # ---- structural break (persistent level shift, non-zero window) ----
    structural_years: set[str] = set()
    for i in range(1, len(arr) - 1):
        prev, v, nxt = arr[i - 1], arr[i], arr[i + 1]
        if not (np.isfinite(prev) and np.isfinite(v) and np.isfinite(nxt)):
            continue
        if prev <= EPS or v <= EPS:
            continue
        if not volume_ok(i):
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
                           "WARN",
                           group=_grp(level, domain, metric, labels[i], "structural"))

    # ---- reversal (interior years, non-zero window only) ----
    for i in range(1, len(arr) - 1):
        prev, v, nxt = arr[i - 1], arr[i], arr[i + 1]
        if not (np.isfinite(prev) and np.isfinite(v) and np.isfinite(nxt)):
            continue
        if prev <= EPS or v <= EPS or nxt <= EPS:
            continue  # zero-boundary handled by the zero-transition check
        if not volume_ok(i):
            continue
        nmean = (prev + nxt) / 2.0
        dev = abs(v - nmean) / abs(nmean)
        spread = abs(prev - nxt) / abs(nmean)
        if dev > REVERSAL_DEV:
            ctx = f"prev={prev:.4g}, next={nxt:.4g}, nmean={nmean:.4g}"
            if spread < REVERSAL_SPREAD:
                report.add(domain, metric, geo, labels[i], v, ctx,
                           f"reversing anomaly: {dev*100:.0f}% off neighbour "
                           f"mean, neighbours agree (spread {spread*100:.0f}%)",
                           anomaly_severity(),
                           group=_grp(level, domain, metric, labels[i], "reversal"))
            elif labels[i] not in structural_years:
                report.add(domain, metric, geo, labels[i], v, ctx,
                           f"large deviation ({dev*100:.0f}%) but neighbours "
                           f"disagree (spread {spread*100:.0f}%) — possible "
                           f"legitimate shock, review", "WARN",
                           group=_grp(level, domain, metric, labels[i], "deviation"))

    _check_rate_identity(report, geo, domain, metric, labels, arr, cnt, mp,
                         level)


def check_series_exact_only(report, geo, domain, area_name, metric, labels,
                            rates, counts, mpops, level="england"):
    """check_series without the year-on-year anomaly heuristics."""
    check_series(report, geo, domain, area_name, metric, labels, rates, counts,
                 mpops, heuristics=False, level=level)


def _grp(level, domain, metric, lbl, kind):
    """Group key for a finding that is the same defect across many areas.

    England and Region are left ungrouped: with 10 areas the per-area detail is
    what makes the report useful, and grouping there would change the output
    the project already has documented.
    """
    if level in ("england", "region"):
        return None
    return (level, domain, metric, lbl, kind)


def _check_rate_identity(report, geo, domain, metric, labels, arr, cnt, mp,
                         level="england"):
    """rate == count / <metric>_pop.

    Exact, not approximate: the pipeline divides these two published columns to
    produce the published rate. Anything beyond floating point is a defect.
    """
    for lbl, r, c, p in zip(labels, arr, cnt, mp):
        if not (np.isfinite(r) and np.isfinite(c) and np.isfinite(p)):
            continue
        if p <= 0:
            report.add(domain, metric, geo, lbl, p, None,
                       "covered population is zero/negative", "BLOCKER",
                       group=_grp(level, domain, metric, lbl, "pop-nonpositive"))
            continue
        implied = c / p
        denom = max(abs(r), EPS)
        if abs(implied - r) / denom > CONSISTENCY_TOL:
            report.add(domain, metric, geo, lbl, r,
                       f"count/{metric}_pop={implied:.10g}",
                       f"rate != count / covered population "
                       f"(off {abs(implied-r)/denom*100:.4f}%)", "BLOCKER",
                       group=_grp(level, domain, metric, lbl, "rate-identity"))


def check_population(report, geo, domain, area_name, labels, pops,
                     level="england"):
    arr = np.asarray(pops, dtype=float)
    for lbl, p in zip(labels, arr):
        if not np.isfinite(p):
            continue
        if p <= 0:
            report.add(domain, "pop", geo, lbl, p, None,
                       "population zero/negative", "BLOCKER",
                       group=_grp(level, domain, "pop", lbl, "pop-nonpositive"))
    for i in range(1, len(arr)):
        prev, p = arr[i - 1], arr[i]
        if not (np.isfinite(prev) and np.isfinite(p)) or prev <= 0:
            continue
        if abs(p - prev) / prev > POP_JUMP:
            report.add(domain, "pop", geo, labels[i], p,
                       f"prev={prev:.0f}",
                       f"population jumped {abs(p-prev)/prev*100:.0f}% "
                       f"year-on-year", "WARN",
                       group=_grp(level, domain, "pop", labels[i], "pop-jump"))


# --------------------------------------------------------------------------- #
# Cross-level checks                                                           #
# --------------------------------------------------------------------------- #
def load_lookups(inputs_root: Path):
    """LSOA21 -> LAD25 -> RGN25. Returns (lsoa_to_lad, lad_to_rgn) or None."""
    lsoa_lad = inputs_root / "geo_lookups" / "lsoa21_to_lad25.csv"
    lad_rgn = inputs_root / "geo_lookups" / "lad25_to_rgn25.csv"
    if not (lsoa_lad.exists() and lad_rgn.exists()):
        return None
    a = pd.read_csv(lsoa_lad, usecols=["LSOA21CD", "LAD25CD"]).drop_duplicates()
    b = pd.read_csv(lad_rgn, usecols=["LAD25CD", "RGN25CD"]).drop_duplicates()
    return (dict(zip(a["LSOA21CD"], a["LAD25CD"])),
            dict(zip(b["LAD25CD"], b["RGN25CD"])))


def check_additivity(report, domain, child_geo, parent_geo, child_data,
                     parent_data, child_to_parent):
    """Sum(child) == parent, for every count column and every population column.

    The pipeline builds each level by summing the one below, so these agree to
    ~4e-16 on a healthy run. A real gap means a level was rebuilt from something
    other than its children — which is how independently-interpolated
    corrections, or a population column redefined at one level only, get into
    the published data.
    """
    for lbl in child_data["__order__"]:
        if lbl not in parent_data:
            continue
        cdf, pdf = child_data[lbl], parent_data[lbl]
        counts = count_columns(cdf, domain)
        cols = []
        for c in counts:
            cols.append(c)
            if metric_pop_col(c) in cdf.columns and metric_pop_col(c) in pdf.columns:
                cols.append(metric_pop_col(c))
        cols.append("pop")

        if child_to_parent is None:
            # region -> england: one parent, sum everything
            grouped = {col: cdf[col].sum(min_count=1) for col in cols
                       if col in cdf.columns}
            pcode = next(iter(pdf.index))
            summed = pd.DataFrame({col: [v] for col, v in grouped.items()},
                                  index=[pcode])
        else:
            key = cdf.index.map(child_to_parent)
            usable = [col for col in cols if col in cdf.columns]
            summed = cdf[usable].groupby(key).sum(min_count=1)
            unmapped = int(pd.isna(pd.Series(key)).sum())
            if unmapped:
                report.add(domain, "(additivity)",
                           f"{child_geo}->{parent_geo}", lbl, unmapped, None,
                           f"{unmapped} {child_geo} area(s) have no "
                           f"{parent_geo} in the lookup, so their values reach "
                           f"no parent total", "BLOCKER")

        for col in summed.columns:
            if col not in pdf.columns:
                continue
            got = pdf[col].reindex(summed.index).astype(float)
            exp = summed[col].astype(float)
            nan_mismatch = got.isna() ^ exp.isna()
            for code in got.index[nan_mismatch]:
                report.add(domain, col, f"{child_geo}->{parent_geo}", lbl,
                           got.get(code), f"sum({child_geo})={exp.get(code)}",
                           f"{parent_geo} {code}: one of the published value "
                           f"and the sum of its {child_geo}s is missing and "
                           f"the other is not", "BLOCKER")
            both = got.notna() & exp.notna()
            if not both.any():
                continue
            g, e = got[both], exp[both]
            denom = np.maximum(g.abs(), e.abs())
            rel = np.where(denom > 0, (g - e).abs() / denom.replace(0, np.nan), 0.0)
            bad = rel > AGG_TOL_HARD
            if bad.any():
                i = int(np.nanargmax(np.where(bad, rel, -1)))
                code = g.index[i]
                report.add(domain, col, f"{child_geo}->{parent_geo}", lbl,
                           float(g.iloc[i]),
                           f"sum({child_geo})={float(e.iloc[i]):.10g}"
                           + (f" (+{int(bad.sum())-1} more)" if bad.sum() > 1 else ""),
                           f"{parent_geo} {code} != sum of its {child_geo}s "
                           f"(off {rel[i]*100:.4f}%)", "BLOCKER")


def check_england_vs_regions(report, base, run, domain):
    """England totals == the sum over the 9 regions.

    The top rung of the additivity ladder, exposed under its original name.
    """
    eng = load_domain(base, "england", domain)
    reg = load_domain(base, "region", domain)
    if not eng["__order__"] or not reg["__order__"]:
        return
    check_additivity(report, domain, "region", "england", reg, eng, None)


def check_relative_level(report, domain, geo, labels, area_pop, matrices,
                         england_matrices):
    """Local coverage collapse, measured against the national figure.

    For each area take the domain's total rate as a fraction of England's for
    the same year, then compare each year against that area's own median
    fraction. A source-coverage failure collapses every metric in the domain at
    once, in one area, without touching the national figure.

    This is the check the year-on-year heuristics cannot do: they need both
    neighbouring years to be finite, and a coverage gap is usually adjacent to
    the nulled years it caused.
    """
    if domain not in REL_LEVEL_DOMAINS:
        return

    def domain_rate(mats):
        if domain == "crime":
            _, counts, mpops = mats["total_crime_rate"]
            return counts / mpops.replace(0, np.nan)
        num, den = None, None
        for metric, (_, counts, mpops) in mats.items():
            num = counts if num is None else num.add(counts, fill_value=0)
            den = mpops if den is None else np.maximum(den, mpops)
        return num / den.replace(0, np.nan)

    local = domain_rate(matrices)
    national = domain_rate(england_matrices).iloc[0]
    ratio = local.div(national, axis=1)
    median = ratio.median(axis=1, skipna=True)
    rel = ratio.div(median.replace(0, np.nan), axis=0)
    # Small areas are excluded: in a 2,200-person authority a single practice
    # or a quiet year moves the whole domain total, and it is not a defect.
    rel = rel.where(area_pop >= REL_POP_FLOOR)

    # How many areas are depressed in each year? A supplier-wide failure shows
    # up as a cluster; a genuine local trend does not.
    below = (rel < REL_LEVEL_WARN).sum(axis=0)

    for code in rel.index:
        for lbl in labels:
            v = rel.at[code, lbl]
            if not np.isfinite(v) or v >= REL_LEVEL_WARN:
                continue
            clustered = int(below.get(lbl, 0)) >= REL_LEVEL_CLUSTER
            sev = ("BLOCKER" if (v < REL_LEVEL_BLOCK or clustered) else "WARN")
            report.add(domain, f"(total {domain} level)", f"{geo}:{code}", lbl,
                       float(local.at[code, lbl]),
                       f"{v*100:.0f}% of this area's usual level vs England",
                       f"whole-domain level collapse: every metric in "
                       f"{domain} is depressed here in this year while "
                       f"England is not — the signature of a source-coverage "
                       f"gap (a force reporting part of a year, a QOF year "
                       f"missing a practice cohort)"
                       + (f"; {int(below.get(lbl, 0))} areas are depressed in "
                          f"this same year, which is a supplier failing rather "
                          f"than a local trend" if clustered else ""), sev,
                       group=_grp(geo, domain, f"(total {domain} level)", lbl,
                                  "relative-level"))


def check_split_families(report, base, run, inputs_root, domains):
    """Children of one split LSOA 2011 must publish the same rate.

    The 2011->2021 crosswalk carries no information that could distinguish two
    children of a split, so they must inherit their parent's rate exactly. They
    did not while the crosswalk was weighted with a population year different
    from the one it was published against: siblings came out up to 3.28x apart
    (Milton Keynes 024E at 0.00931 against 024F at 0.00284 for 2014 claimants),
    a fabricated gradient at the finest grain the ADI publishes.

    Health is structurally immune (its rate is held fixed and the count
    re-derived, so the weight cancels), but it is checked anyway — the immunity
    is a property of today's aggregate node, not a law.
    """
    xwalk = inputs_root / "crosswalk" / "lsoa11_to_lsoa21.csv"
    if not xwalk.exists():
        report.add("(crosswalk)", "(split families)", "lsoa", None, None,
                   str(xwalk), "crosswalk not available, split-family "
                   "coherence not checked", "INFO")
        return
    xw = pd.read_csv(xwalk, usecols=["LSOA11CD", "LSOA21CD", "CHGIND"])
    splits = xw[xw["CHGIND"] == "S"][["LSOA11CD", "LSOA21CD"]]
    if splits.empty:
        return

    for domain in domains:
        ddir = base / "lsoa" / domain
        if not ddir.exists():
            continue
        for f in sorted(ddir.glob(f"{domain}_*.csv")):
            _, lbl = parse_year(domain, f)
            df = pd.read_csv(f)
            code_col = df.columns[0]
            rate_cols = [c for c in df.columns if c.endswith("_rate")]
            j = splits.merge(df[[code_col] + rate_cols],
                             left_on="LSOA21CD", right_on=code_col)
            if j.empty:
                continue
            for c in rate_cols:
                g = j.groupby("LSOA11CD")[c].agg(["min", "max", "count"])
                g = g[g["count"] > 1]
                if g.empty:
                    continue
                spread = (g["max"] - g["min"]).abs()
                scale = g[["min", "max"]].abs().max(axis=1).replace(0, np.nan)
                relspread = (spread / scale).fillna(0.0)
                bad = relspread > SPLIT_RATE_TOL
                if bad.any():
                    worst = relspread.idxmax()
                    report.add(domain, c, "lsoa:split-families", lbl,
                               float(g.at[worst, "max"]),
                               f"sibling min={g.at[worst, 'min']:.6g}, "
                               f"parent={worst}",
                               f"{int(bad.sum())} split LSOA 2011 famil"
                               f"{'ies' if bad.sum() != 1 else 'y'} publish "
                               f"different rates across their children "
                               f"(worst {relspread.max()*100:.2f}% apart) — "
                               f"the crosswalk cannot tell them apart, so this "
                               f"gradient is fabricated", "BLOCKER")


def check_lsoa_level(report, base, run, domain):
    """Vectorised LSOA invariants.

    33,749 areas x 12 years x 3 domains is too much data for the per-area
    heuristics, and those heuristics would be meaningless anyway on counts this
    small. What IS worth checking at this level is exact arithmetic, which
    costs one pass over each column:

      * rate == count / <metric>_pop
      * count is NaN  <=>  <metric>_pop is NaN
      * 0 < <metric>_pop <= pop
      * rates within bounds

    The additivity ladder and split-family coherence are checked separately and
    cover the LSOA level too.
    """
    ddir = base / "lsoa" / domain
    if not ddir.exists():
        return
    for f in sorted(ddir.glob(f"{domain}_*.csv")):
        _, lbl = parse_year(domain, f)
        df = pd.read_csv(f)
        code_col = df.columns[0]
        codes = df[code_col]
        area_pop = df["pop"].astype(float)

        bad_pop = area_pop.notna() & (area_pop <= 0)
        if bad_pop.any():
            report.add(domain, "pop", "lsoa", lbl, int(bad_pop.sum()),
                       f"e.g. {codes[bad_pop].iloc[0]}",
                       f"{int(bad_pop.sum())} LSOA(s) with zero/negative "
                       f"population", "BLOCKER")

        for cnt_col in count_columns(df, domain):
            rate_col, pop_col = f"{cnt_col}_rate", metric_pop_col(cnt_col)
            if rate_col not in df.columns or pop_col not in df.columns:
                continue
            in_window = (domain != "health"
                         or qof_group_published(condition_of(cnt_col), lbl))
            c = df[cnt_col].astype(float)
            p = df[pop_col].astype(float)
            r = df[rate_col].astype(float)

            if not in_window:
                live = c.notna() | p.notna() | r.notna()
                if live.any():
                    report.add(domain, rate_col, "lsoa", lbl, int(live.sum()),
                               f"e.g. {codes[live].iloc[0]}",
                               f"{int(live.sum())} LSOA(s) carry a value for a "
                               f"QOF group NHS Digital did not collect that "
                               f"year", "BLOCKER")
                continue

            # count and covered population must appear and vanish together
            mism = c.isna() ^ p.isna()
            if mism.any():
                report.add(domain, cnt_col, "lsoa", lbl, int(mism.sum()),
                           f"e.g. {codes[mism].iloc[0]}",
                           f"{int(mism.sum())} LSOA(s) where exactly one of "
                           f"the count and its covered population is missing — "
                           f"an excluded area must contribute to neither the "
                           f"numerator nor the denominator", "BLOCKER")

            live = c.notna() & p.notna()
            if not live.any():
                continue
            bad_mp = live & ((p <= 0) | (p > area_pop + 0.5))
            if bad_mp.any():
                i = codes[bad_mp].iloc[0]
                report.add(domain, pop_col, "lsoa", lbl, int(bad_mp.sum()),
                           f"e.g. {i}",
                           f"{int(bad_mp.sum())} LSOA(s) whose covered "
                           f"population is <=0 or exceeds the area population",
                           "BLOCKER")

            ok = live & r.notna() & (p > 0)
            if ok.any():
                implied = c[ok] / p[ok]
                denom = r[ok].abs().clip(lower=EPS)
                off = (implied - r[ok]).abs() / denom
                bad = off > CONSISTENCY_TOL
                if bad.any():
                    i = off.idxmax()
                    report.add(domain, rate_col, "lsoa", lbl, float(r[i]),
                               f"count/{pop_col}={implied[i]:.10g} at "
                               f"{codes[i]}",
                               f"{int(bad.sum())} LSOA(s) where rate != count "
                               f"/ covered population (worst "
                               f"{off.max()*100:.4f}%)", "BLOCKER")

            rr = r[r.notna()]
            if is_rate_in_unit_interval(domain):
                oob = (rr < 0) | (rr > 1)
                bound = "[0,1]"
            else:
                oob = rr < 0
                bound = ">=0"
            if oob.any():
                i = oob[oob].index[0]
                report.add(domain, rate_col, "lsoa", lbl, float(rr[i]), bound,
                           f"{int(oob.sum())} LSOA(s) with a rate outside "
                           f"{bound} (e.g. {codes[i]})", "BLOCKER")


# --------------------------------------------------------------------------- #
# Reporting                                                                    #
# --------------------------------------------------------------------------- #
def fmt_value(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def print_report(report: Report, verbose: bool = False) -> None:
    rows = report.sorted_rows() if verbose else report.collapsed_rows()
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
    widths = [9, 16, 24, 22, 9, 12, 34, 60]
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
    ap.add_argument("--inputs-root", default=None,
                    help="override store/inputs root (geo lookups + crosswalk, "
                         "used by the additivity ladder and the split-family "
                         "check)")
    ap.add_argument("--no-lsoa", action="store_true",
                    help="skip the LSOA-level pass (faster; leaves the "
                         "england/region/lad checks untouched)")
    ap.add_argument("--verbose", action="store_true",
                    help="list every area individually instead of collapsing "
                         "one defect seen across many areas into a single row")
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    root = Path(args.outputs_root) if args.outputs_root else repo_root / "store" / "outputs"
    inputs_root = (Path(args.inputs_root) if args.inputs_root
                   else repo_root / "store" / "inputs")
    base = root / args.run

    if not base.exists():
        print(f"ERROR: outputs not found at {base}", file=sys.stderr)
        return 2

    report = Report()
    do_lsoa = not args.no_lsoa

    # --- england / region / lad: full per-area series treatment ------------- #
    for geo in GEOGRAPHIES:
        for domain in DOMAINS:
            ddir = base / geo / domain
            if not ddir.exists():
                report.add(domain, "(coverage)", geo, None, None, None,
                           f"domain directory missing: {ddir}", "BLOCKER")
                continue
            data = load_domain(base, geo, domain)
            if not data["__order__"]:
                check_coverage(report, geo, domain, data, set())
                continue
            canonical = set().union(*[set(data[lbl].index)
                                      for lbl in data["__order__"]])
            check_coverage(report, geo, domain, data, canonical)

            labels, area_pop, matrices = build_matrices(data, domain)
            names = data[labels[-1]]["name"]

            for code in area_pop.index:
                gname = f"{geo}:{names.get(code, code)}"
                check_population(report, gname, domain, names.get(code, code),
                                 labels, area_pop.loc[code].to_numpy(),
                                 level=geo)
                small = float(np.nanmedian(area_pop.loc[code].to_numpy())) < REL_POP_FLOOR
                for metric, (rates, counts, mpops) in matrices.items():
                    r = rates.loc[code].to_numpy(dtype=float)
                    c = counts.loc[code].to_numpy(dtype=float)
                    p = mpops.loc[code].to_numpy(dtype=float)
                    if small:
                        # Exact-arithmetic checks still apply; the anomaly
                        # heuristics do not -- a handful of events in a
                        # 2,200-person authority reverses every single year.
                        check_series_exact_only(
                            report, gname, domain, names.get(code, code),
                            metric, labels, r, c, p, level=geo)
                    else:
                        check_series(report, gname, domain,
                                     names.get(code, code), metric, labels,
                                     r, c, p, level=geo)

            if geo != "england":
                eng_data = load_domain(base, "england", domain)
                _, _, eng_matrices = build_matrices(eng_data, domain)
                check_relative_level(report, domain, geo, labels, area_pop,
                                     matrices, eng_matrices)

    # --- additivity ladder -------------------------------------------------- #
    lookups = load_lookups(inputs_root)
    if lookups is None:
        report.add("(geography)", "(additivity)", "all", None, None,
                   str(inputs_root / "geo_lookups"),
                   "geo lookups not available, LSOA/LAD/Region additivity not "
                   "checked", "INFO")
    lsoa_to_lad, lad_to_rgn = lookups if lookups else (None, None)
    for domain in DOMAINS:
        cache: dict[str, dict] = {}

        def get(geo):
            if geo not in cache:
                d = base / geo / domain
                cache[geo] = load_domain(base, geo, domain) if d.exists() else None
            return cache[geo]

        for child, parent in LADDER:
            if child == "lsoa" and not do_lsoa:
                continue
            cd, pd_ = get(child), get(parent)
            if cd is None or pd_ is None or not cd["__order__"]:
                continue
            if child == "lsoa":
                mapping = lsoa_to_lad
            elif child == "lad":
                mapping = lad_to_rgn
            else:
                mapping = None  # region -> england: single parent
            if child != "region" and mapping is None:
                continue
            check_additivity(report, domain, child, parent, cd, pd_, mapping)

    # --- LSOA level --------------------------------------------------------- #
    if do_lsoa:
        for domain in DOMAINS:
            check_lsoa_level(report, base, args.run, domain)
        check_split_families(report, base, args.run, inputs_root, DOMAINS)

    if args.json:
        out = {
            "run": args.run,
            "findings": (report.sorted_rows() if args.verbose
                         else report.collapsed_rows()),
            "has_blocker": report.has_blocker(),
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print_report(report, verbose=args.verbose)

    return 1 if report.has_blocker() else 0


if __name__ == "__main__":
    sys.exit(main())
