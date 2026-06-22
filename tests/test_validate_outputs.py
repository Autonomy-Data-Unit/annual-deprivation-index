"""Pytest wrapper around the ADI output validator.

Runs the validator over the local ``default`` outputs and asserts the key
acceptance criteria from issue #1:
  - the DEP 2023-24 reversal IS caught as a BLOCKER (national + regional)
  - the genuine 2020 COVID employment spike is NOT a blocker

Skips cleanly if the outputs are not present (so CI without data does not fail).
Run with:  uv run --with pandas --with numpy pytest tests/test_validate_outputs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import validate_outputs as v  # noqa: E402

OUTPUTS = REPO / "store" / "outputs" / "default"


def _run():
    report = v.Report()
    for geo in v.GEOGRAPHIES:
        for domain in v.DOMAINS:
            ddir = OUTPUTS / geo / domain
            if not ddir.exists():
                continue
            data = v.load_domain(OUTPUTS, geo, domain)
            v.check_coverage(report, geo, domain, data)
            if not data["__order__"]:
                continue
            last = data["__order__"][-1]
            for code in list(data[last].index):
                gname = f"{geo}:{data[last].loc[code, 'name']}"
                pop_labels = data["__order__"]
                pop_vals = [
                    float(data[lbl].loc[code, "pop"])
                    if code in data[lbl].index and "pop" in data[lbl].columns
                    else float("nan")
                    for lbl in pop_labels
                ]
                v.check_population(report, gname, domain, code,
                                   pop_labels, pop_vals)
                for metric, rc, cc in v.metric_specs(domain):
                    labels, rates, counts, pops = v.build_series(
                        data, code, rc, cc, domain)
                    v.check_series(report, gname, domain, code, metric,
                                   labels, rates, counts, pops)
    for domain in v.DOMAINS:
        if (OUTPUTS / "england" / domain).exists() and \
           (OUTPUTS / "region" / domain).exists():
            v.check_england_vs_regions(report, OUTPUTS, "default", domain)
    return report


@pytest.fixture(scope="module")
def report():
    if not OUTPUTS.exists():
        pytest.skip(f"no outputs at {OUTPUTS}")
    return _run()


def test_dep_2023_24_is_blocker(report):
    """The motivating bug: England DEP 2023-24 must be a BLOCKER."""
    hits = [
        r for r in report.rows
        if r["metric"] == "DEP_afflicted_rate"
        and r["year"] == "2023-24"
        and r["geography"] == "england:England"
        and r["severity"] == "BLOCKER"
    ]
    assert hits, "DEP 2023-24 reversal was not flagged as BLOCKER"


def test_dep_2023_24_flagged_across_regions(report):
    """The dip is index-wide; every region's DEP 2023-24 should blocker."""
    hits = {
        r["geography"] for r in report.rows
        if r["metric"] == "DEP_afflicted_rate" and r["year"] == "2023-24"
        and r["severity"] == "BLOCKER" and r["geography"].startswith("region:")
    }
    assert len(hits) == 9, f"expected 9 regional DEP blockers, got {len(hits)}"


def test_covid_2020_employment_not_blocker(report):
    """The genuine 2020 COVID claimant spike must not be a BLOCKER."""
    bad = [
        r for r in report.rows
        if r["domain"] == "claimant_counts" and str(r["year"]) == "2020"
        and r["severity"] == "BLOCKER"
    ]
    assert not bad, f"COVID 2020 employment wrongly blocked: {bad}"
