# paddock

The package behind the `paddock` command. It loads a benchmark from the paddock root, copies its data into a workspace, drives a task's steps, scores the result and writes the run down. What a round measures lives in the benchmark under `gold/`, not here.

## Map

- `_vendor/`: the vendored copy of `core`, written by `make vendor`. Do not edit it.
- `archive.py`: restoring a tree exactly, with its digests and manifests.
- `cli.py`: the `paddock` command line and its subcommands.
- `homeconfig.py`: reading a benchmark's base home config and merging a task's override over it.
- `loader.py`: importing a benchmark's `tasks.py` from the paddock root and freezing the tasks it declared.
- `names.py`: naming a run by its axes and picking the next unused run number.
- `paths.py`: where the paddock root, its `gold/` benchmarks and the stablemate checkout live.
- `project.py`: pinning the stablemate checkout a run drives to one git state, and noticing when a round escapes the pin.
- `reap.py`: finding and killing the processes a round left running in its stage.
- `registry.py`: the declarations a tasks module makes, `task` and `step`, and the records they freeze into.
- `runner.py`: executing one round from the copied data to a scored run.
- `sandbox.py`: the container image that holds the stablemate tools as installed packages, and running a command in it.
