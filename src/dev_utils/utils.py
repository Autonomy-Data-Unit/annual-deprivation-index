import asyncio
import builtins
import importlib
import inspect
import sys
from pathlib import Path

from netrun.core import Net, NetConfig
from netrun.net._net._context import NodeExecutionContext
from netrun.net.config._nodes import NodeVariable


def _load_net_config(run_name: str | None = None) -> NetConfig:
    """Load the pipeline NetConfig with run_defs injected.

    Args:
        run_name: Which run definition to use for filling node vars.
            Defaults to RUN_NAME env var, then "default".
    """
    import os
    from adi.const import run_defs_path, netrun_config_path
    from adi.run_pipeline import _load_run_defs, _resolve_run_defs

    run_name = run_name or os.environ.get("RUN_NAME", "default")
    run_defs = _load_run_defs(run_defs_path)
    global_vars, node_vars = _resolve_run_defs(run_defs, run_name)

    config = NetConfig.from_file(
        str(netrun_config_path),
        global_node_vars=global_vars,
        node_vars=node_vars,
    )
    return config


def _get_merged_node_vars(config: NetConfig, node_name: str) -> dict[str, NodeVariable]:
    """Get merged global + per-node NodeVariable dict for a specific node."""
    resolved_config = config.resolve_env_vars()
    merged = dict(resolved_config.node_vars or {})
    if resolved_config.graph:
        for node in resolved_config.graph.nodes:
            if node.name == node_name:
                if node.execution_config and node.execution_config.node_vars:
                    for name, var in node.execution_config.node_vars.items():
                        if var.inherit and name in merged:
                            if var.value is not None:
                                global_var = merged[name]
                                merged[name] = NodeVariable(
                                    value=var.value,
                                    type=global_var.type,
                                    options=global_var.options,
                                )
                        else:
                            merged[name] = var
                break
    return merged


def _resolve_node_name(config: NetConfig, bare_name: str) -> str:
    """Resolve a bare node name to its (possibly prefixed) name in the graph."""
    resolved = config.graph.resolve(net_config=config)
    all_names = [n.name for n in resolved.nodes]

    if bare_name in all_names:
        return bare_name

    matches = [n for n in all_names if n.endswith(f".{bare_name}")]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise ValueError(
            f"Ambiguous node name '{bare_name}': matches multiple nodes: {matches}"
        )

    raise ValueError(
        f"Node '{bare_name}' not found in graph. "
        f"Available nodes: {sorted(all_names)}"
    )


def _get_node_func(config: NetConfig, node_name: str):
    """Import and return the Python function for a node."""
    resolved = config.graph.resolve(net_config=config)
    node_map = {n.name: n for n in resolved.nodes}
    if node_name not in node_map:
        raise ValueError(f"Node '{node_name}' not found in graph.")
    node = node_map[node_name]
    func_path = node.factory_args["func"]
    module_path, _, attr_name = func_path.rpartition(".")
    mod = importlib.import_module(module_path)
    return getattr(mod, attr_name)


async def _get_input_salvo(config: NetConfig, node_name: str, verbose: bool = True) -> dict[str, list]:
    """Get input salvo for a node. Uses cache if available, otherwise runs upstream."""
    net = Net(config)
    try:
        node_cfg = net.get_node_config(node_name)
        if not node_cfg.in_ports:
            if verbose:
                print(f"set_node_func_args: '{node_name}' is a source node (no inputs)")
            return {}

        cached = net.cache.input_salvos(node_name)
        if cached:
            if verbose:
                print(f"set_node_func_args: using cached inputs for '{node_name}' ({len(cached)} cached run(s))")
            return cached[-1]

        if verbose:
            print(f"set_node_func_args: no cache for '{node_name}', running upstream nodes...")
            _running = {}

            def _on_start(name, epoch_id):
                print(f"  Running {name}...", end="", flush=True)
                _running[epoch_id] = name

            def _on_end(name, epoch_id, record):
                if epoch_id in _running:
                    print(" done")
                    del _running[epoch_id]

            net.on_epoch_start(_on_start)
            net.on_epoch_end(_on_end)

        salvos = await net.run_to_targets(node_name)
        if not salvos:
            return {}
        return salvos[0].packets
    finally:
        await net.close()


def _run_async(coro):
    """Run an async coroutine, handling Jupyter's already-running event loop."""
    try:
        asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
    except RuntimeError:
        pass
    return asyncio.run(coro)


def set_node_func_args(node_name: str, *, run_name: str | None = None, return_args=False, load_env=True, verbose=True):
    """Populate the caller's namespace with the inputs a pipeline node would receive.

    Loads input data for a node from the netrun cache (or by running upstream
    nodes via Net.run_to_targets) and injects the values into the caller's
    global namespace so that subsequent notebook cells can use them directly.

    Args:
        node_name: The node name (e.g. "fetch_data").
        run_name: Which run definition to use.
        return_args: If True, return args as a namedtuple instead of injecting.
        load_env: If True, load .env via dotenv first.
        verbose: If True, print progress messages.
    """
    if load_env:
        from dotenv import load_dotenv
        load_dotenv()

    config = _load_net_config(run_name)
    name = _resolve_node_name(config, node_name)
    func = _get_node_func(config, name)
    salvo = _run_async(_get_input_salvo(config, name, verbose=verbose))

    args = {}
    for port_name, values in salvo.items():
        args[port_name] = values[0] if len(values) == 1 else values

    sig = inspect.signature(func)
    if "ctx" in sig.parameters:
        node_vars = _get_merged_node_vars(config, name)
        args["ctx"] = NodeExecutionContext(
            epoch_id="dev-0",
            node_name=name,
            _node_vars=node_vars,
        )
    if "print" in sig.parameters:
        args["print"] = builtins.print

    if return_args:
        from collections import namedtuple
        NodeArgs = namedtuple("NodeArgs", list(args.keys()))
        return NodeArgs(**args)

    caller_globals = sys._getframe(1).f_globals
    caller_globals.update(args)


def show_node_vars(node_name: str, *filter_names: str, run_name: str | None = None, load_env=True):
    """Print the node variables available to a pipeline node.

    Args:
        node_name: The node name (e.g. "fetch_data").
        *filter_names: Optional variable names to filter by.
        run_name: Which run definition to use.
        load_env: If True, load .env via dotenv first.
    """
    if load_env:
        from dotenv import load_dotenv
        load_dotenv()

    config = _load_net_config(run_name)

    from adi.const import netrun_config_path
    raw_config = NetConfig.from_file(str(netrun_config_path))
    declared_types: dict[str, str] = {
        k: v.type for k, v in (raw_config.node_vars or {}).items()
    }

    name = _resolve_node_name(config, node_name)
    resolved_config = config.resolve_env_vars()

    global_vars: dict[str, NodeVariable] = dict(resolved_config.node_vars or {})

    per_node_raw: dict[str, NodeVariable] = {}
    if resolved_config.graph:
        for node in resolved_config.graph.nodes:
            if node.name == name:
                if node.execution_config and node.execution_config.node_vars:
                    per_node_raw = dict(node.execution_config.node_vars)
                break

    all_var_names = sorted(set(global_vars) | set(per_node_raw))
    if filter_names:
        all_var_names = [n for n in all_var_names if n in filter_names]

    rows = []
    for var_name in all_var_names:
        in_global = var_name in global_vars
        in_node = var_name in per_node_raw

        if in_node and per_node_raw[var_name].inherit:
            if per_node_raw[var_name].value is not None:
                value = per_node_raw[var_name].value
                source = "inherited (overridden)"
            else:
                value = global_vars[var_name].value
                source = "inherited"
        elif in_node:
            value = per_node_raw[var_name].value
            source = "node-level"
        else:
            value = global_vars[var_name].value
            source = "global"

        if var_name in declared_types:
            var_type = declared_types[var_name]
        elif var_name in global_vars:
            var_type = global_vars[var_name].type
        else:
            var_type = per_node_raw[var_name].type

        rows.append((var_name, value, var_type, source))

    if not rows:
        print(f"No node vars for '{name}'")
        return

    headers = ("Name", "Value", "Type", "Source")
    col_widths = [len(h) for h in headers]
    str_rows = []
    for var_name, value, var_type, source in rows:
        vals = (var_name, str(value), var_type, source)
        str_rows.append(vals)
        for i, v in enumerate(vals):
            col_widths[i] = max(col_widths[i], len(v))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(f"Node vars for '{name}':")
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in col_widths)))
    for vals in str_rows:
        print(fmt.format(*vals))
