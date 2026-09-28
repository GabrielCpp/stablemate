# paddock

The package behind the `paddock` command. It unpacks a seed, drives a task's steps, stages the result, scores it and seals it. What a round measures lives in `../data/`, not here.

## Map

- `archive.py`: zipping a repository tree and restoring it exactly, with its digests and manifests.
- `cli.py`: the `paddock` command line and its subcommands.
- `loader.py`: importing a task module from the data directory and freezing the task it declared.
- `paths.py`: where paddock reads its data and where it keeps seed zips, result zips, pointers and work dirs.
- `pointer.py`: the tracked pointer TOML that stands in for a zip git cannot carry.
- `project.py`: pinning the project a run drives to one git state, and noticing when a round escapes the pin.
- `reap.py`: finding and killing the processes a round left running in its stage.
- `registry.py`: the declarations a task module makes, `task` and `step`, and the records they freeze into.
- `runner.py`: executing one round from seed to sealed, scored result.
- `sandbox.py`: the container image that holds the stablemate tools as installed packages, and running a command in it.
- `seeds.py`: capturing a repo into a seed and putting a seed back on disk.
