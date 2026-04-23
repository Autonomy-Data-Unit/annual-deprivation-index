from pathlib import Path

import adi

# Repo root: const.py lives at src/adi/const.py -> ../../
repo_root = Path(adi.__file__).parent.parent.parent

config_path = repo_root / "config"
store_path = repo_root / "store"
inputs_path = store_path / "inputs"
pipeline_store_path = store_path / "pipeline"
outputs_path = store_path / "outputs"

# Config files
netrun_config_path = config_path / "netrun.json"
run_defs_path = config_path / "run_defs.toml"
qof_schemas_path = config_path / "qof_schemas.toml"

# Input data subdirectories
claimant_data_path = inputs_path / "claimant_counts"
crime_data_path = inputs_path / "crime"
qof_data_path = inputs_path / "qof"
population_data_path = inputs_path / "population"
lsoa_boundaries_path = inputs_path / "lsoa_boundaries"
gp_catchments_path = inputs_path / "gp_catchments"
geo_lookups_path = inputs_path / "geo_lookups"
crosswalk_path = inputs_path / "crosswalk"


def rel(path: Path) -> Path:
    """Return path relative to repo root, for cleaner log output."""
    try:
        return path.relative_to(repo_root)
    except ValueError:
        return path
