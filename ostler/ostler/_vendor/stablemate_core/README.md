# stablemate_core

The runtime state every stablemate tool must agree on: the home config, where the base library is found, and its shared cache. `make vendor` copies this directory into each tool, so edit it here and never in a `_vendor/` copy.

## Map

- `base_cache.py`: the shared cache of the base library under `~/.cache/stablemate`. It is the one place that fetches or refreshes it from the remote.
- `clock.py`: wall-clock time and waiting, as a port that code takes instead of calling `time` directly.
- `config.py`: the home config file: its path, its `config_version` guard, legacy merging and key writes.
- `discovery.py`: the resolution order that finds the base library, from `$STABLEMATE_BASE_DIR` down to the cache.
- `layout.py`: what counts as a library directory on disk.
- `profiles.py`: which profile a run resolves from, and the model, effort, timeout scale, harness env and default CLI it yields.
