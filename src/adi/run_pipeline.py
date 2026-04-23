import asyncio
import os
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from netrun.core import Net, NetConfig


def _load_run_defs(run_defs_path: Path) -> dict:
    """Load run definitions from TOML file."""
    with open(run_defs_path, "rb") as f:
        return tomllib.load(f)


def _resolve_run_defs(run_defs: dict, run_name: str) -> tuple[dict, dict]:
    """Resolve run_defs into (global_node_vars, per_node_vars) dicts.

    Merges [defaults] with [runs.<run_name>]. Subtables are per-node overrides,
    scalar values are global vars. Returns dicts compatible with
    NetConfig.from_file(global_node_vars=..., node_vars=...).
    """
    defaults = dict(run_defs["defaults"])
    runs = run_defs["runs"]

    if run_name not in runs:
        available = ", ".join(sorted(runs.keys()))
        raise ValueError(f"Unknown run name {run_name!r}. Available: {available}")

    run_overrides = dict(runs[run_name])

    # Split defaults into globals vs per-node
    default_globals = {}
    default_node = {}
    for k, v in defaults.items():
        if isinstance(v, dict):
            default_node[k] = v
        else:
            default_globals[k] = v

    # Split run overrides into globals vs per-node
    run_globals = {}
    run_node = {}
    for k, v in run_overrides.items():
        if isinstance(v, dict):
            run_node[k] = v
        else:
            run_globals[k] = v

    # Merge: defaults <- run overrides
    merged_globals = {**default_globals, **run_globals}
    merged_globals["run_name"] = run_name

    # Convert to (str_value, type_name) tuples so netrun preserves types
    _TYPE_MAP = {int: "int", float: "float", bool: "bool", str: "str"}

    def _to_node_var(v):
        return (str(v), _TYPE_MAP[type(v)])

    global_node_vars = {k: _to_node_var(v) for k, v in merged_globals.items()}

    # Merge per-node: defaults <- run overrides
    all_node_names = set(default_node) | set(run_node)
    per_node_vars = {}
    for node_name in all_node_names:
        merged = {**default_node.get(node_name, {}), **run_node.get(node_name, {})}
        per_node_vars[node_name] = {k: _to_node_var(v) for k, v in merged.items()}

    return global_node_vars, per_node_vars


async def run_pipeline_async(run_name: str | None = None):
    """Load and run the full pipeline.

    Args:
        run_name: Name of the run definition to use. Falls back to
            RUN_NAME env var. Required (no implicit default).
    """
    load_dotenv()
    from .const import run_defs_path as default_run_defs_path, netrun_config_path

    run_name = run_name or os.environ.get("RUN_NAME")
    if run_name is None:
        raise ValueError(
            "run_name is required. Pass it as an argument or set the RUN_NAME env var."
        )

    run_defs = _load_run_defs(default_run_defs_path)
    global_vars, node_vars = _resolve_run_defs(run_defs, run_name)

    config = NetConfig.from_file(
        str(netrun_config_path),
        global_node_vars=global_vars,
        node_vars=node_vars,
    )
    config.project_root_override = str(Path.cwd())
    print(f"run_pipeline: using run definition {run_name!r}", flush=True)

    async with Net(config) as net:
        made_progress = True
        while made_progress:
            made_progress, _, _ = await net.run_until_blocked()

    print("run_pipeline: done", flush=True)


def main():
    """Sync entry point for the run-pipeline CLI command.

    Usage: run-pipeline [RUN_NAME]
    Falls back to RUN_NAME env var if no argument given.
    """
    args = sys.argv[1:]
    if len(args) > 1:
        print("Usage: run-pipeline [RUN_NAME]", file=sys.stderr)
        sys.exit(1)
    run_name = args[0] if args else None
    asyncio.run(run_pipeline_async(run_name))
