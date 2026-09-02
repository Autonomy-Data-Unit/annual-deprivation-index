# ---
# jupyter:
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # nodes.validate
#
# Run `scripts/validate_outputs.py` over the outputs `aggregate` just wrote, print
# the result, and record it as `store/outputs/{run_name}/validation_report.json`.
#
# This is the last node in the graph, so no run can produce outputs without the
# validator having seen them.
#
# ## Why a node and not CI
#
# The validator reads `store/outputs/`, which is gitignored and is derived from
# ~31 GB of `store/inputs/`. A GitHub Actions job checking out this repo has no
# store at all, so it cannot run this check — it would have to download every
# source again on every push, which is both slow and rude to Nomis, NHS Digital
# and data.police.uk. The check belongs where the data is, which is here.
#
# ## What fails the run, and what does not
#
# Not every BLOCKER means the pipeline malfunctioned, and conflating the two would
# make this node either useless or permanently red. Two kinds:
#
# * **Structural.** England != the sum of its regions, a rate that is not its own
#   count over its own denominator, one split LSOA's children disagreeing. These
#   can only be produced by a bug in this pipeline, and they are the ones this
#   node **raises** on. They are all green today, so the gate costs nothing and
#   would have caught both of the aggregation bugs found on 2026-09-02 (#6's split
#   families, and England summing a different LSOA set than its LADs).
# * **Source anomalies.** A prevalence series that dips 90% for one year and
#   returns (QOF changed the DEP register basis in 2023-24), a crime spike that
#   reverses. The pipeline is faithfully reproducing what its sources published;
#   correcting those is `site/scripts/build_data.py`'s job, downstream. Failing the
#   pipeline for accurately reporting bad source data would be a category error, so
#   these are **printed in full and recorded**, and the run continues.
#
# The distinction is drawn on the finding's geography: the additivity ladder
# reports against `child->parent` (`lsoa->lad`, `lad->region`, `region->england`),
# every per-area check against `level:area name`.

# %%
#|default_exp validate
#|export_as_func true

# %%
#|top_export
from adi import const

# %%
#|set_func_signature
async def main(ctx, print, outputs_ready) -> bool:
    """Validate the published outputs and record the report."""
    ...

# %% [markdown]
#
# Retrieve input arguments

# %%
from dev_utils import *
run_name = 'default'
set_node_func_args('validate', run_name=run_name)
show_node_vars('validate', run_name=run_name)

# %% [markdown]
# # Function body

# %%
#|export
import json
import subprocess
import sys
from collections import Counter

# %%
#|export
run_name = ctx.vars["run_name"]

outputs_dir = const.outputs_path / run_name
report_path = outputs_dir / "validation_report.json"
script_path = const.repo_root / "scripts" / "validate_outputs.py"

if not outputs_dir.exists():
    raise FileNotFoundError(
        f"No outputs to validate at {const.rel(outputs_dir)}. The aggregate node "
        f"should have written them before this node ran."
    )
if not script_path.exists():
    raise FileNotFoundError(f"Validator not found at {const.rel(script_path)}.")

print(f"validate: checking {const.rel(outputs_dir)}")

# %% [markdown]
# ## Run the validator
#
# As a subprocess, deliberately: `scripts/validate_outputs.py` is the one place the
# checks and their thresholds live, and it is what a human runs by hand. Importing
# and re-driving its internals would fork that orchestration into a second copy
# that could quietly disagree with the first.

# %%
#|export
proc = subprocess.run(
    [sys.executable, str(script_path), "--run", run_name, "--json"],
    capture_output=True, text=True, cwd=str(const.repo_root),
)

# The validator exits 0 (clean) or 1 (blockers present). Anything else -- 2 for
# missing outputs, or a traceback -- means the check did not happen, which is not
# something to shrug off and continue from.
if proc.returncode not in (0, 1):
    raise RuntimeError(
        f"validate_outputs.py exited {proc.returncode} without completing.\n"
        f"stderr:\n{proc.stderr.strip()}"
    )
try:
    report = json.loads(proc.stdout)
except json.JSONDecodeError as exc:
    raise RuntimeError(
        f"validate_outputs.py produced output that is not the JSON report: {exc}\n"
        f"stdout starts: {proc.stdout[:400]!r}\nstderr:\n{proc.stderr.strip()}"
    ) from exc

findings = report["findings"]

# %% [markdown]
# ## Record it
#
# Written next to the data it describes, so the report travels with the outputs
# and a later reader can see what was known about them when they were made.

# %%
#|export
report_path.write_text(json.dumps(report, indent=2, default=str))
print(f"  report written to {const.rel(report_path)}")

# %% [markdown]
# ## Report and gate

# %%
#|export
counts = Counter(f["severity"] for f in findings)
print(f"  {counts.get('BLOCKER', 0)} BLOCKER, {counts.get('WARN', 0)} WARN, "
      f"{counts.get('INFO', 0)} INFO")

structural = [f for f in findings
              if f["severity"] == "BLOCKER" and "->" in str(f["geography"])]
source_blockers = [f for f in findings
                   if f["severity"] == "BLOCKER" and "->" not in str(f["geography"])]

# Print every blocker. A finding nobody reads is not a check, and this is the
# only place the whole picture is put in front of whoever ran the pipeline.
for f in source_blockers:
    print(f"    BLOCKER {f['domain']}/{f['metric']} {f['geography']} "
          f"{f['year']}: {f['reason']}")
if source_blockers:
    print(f"  {len(source_blockers)} source-data blocker(s) above. The pipeline "
          f"reproduces its sources faithfully; correcting these is build_data.py's "
          f"job. Not failing the run on them.")

if structural:
    for f in structural:
        print(f"    STRUCTURAL {f['domain']}/{f['metric']} {f['geography']} "
              f"{f['year']}: {f['reason']} (value={f['value']}, {f['neighbours']})")
    raise ValueError(
        f"{len(structural)} structural blocker(s): the published levels do not "
        f"reconcile with each other. Only a bug in this pipeline can produce that, "
        f"so the run is failed rather than published. Full report at "
        f"{const.rel(report_path)}."
    )

print(f"validate: done, no structural blockers")

# %%
#|export
True  #|func_return_line
