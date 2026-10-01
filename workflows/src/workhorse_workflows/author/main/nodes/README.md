# nodes

The nodes the main author flow and several standalone machines call.

## Map

- `_blueprint.py`: the node registry every module here decorates against.
- `_stubs.py`: what the deterministic gates return under `--dry-run`.
- `artifacts.py`: the whole-run gates on what a run wrote, and the git commit that ships what they passed.
- `config.py`: the author's resolved paths for a run, and the proof its intake exists.
- `coverage.py`: whether an epic's stories cover every seed in an acyclic graph.
- `intake.py`: the durable inputs Author consumes: backlog ids and the roadmap's milestone and status.
- `planner.py`: which one authoring stage runs next, read from the artifacts on disk.
- `stories.py`: the per-story gates: validate, ground, attempt ledger and operator feedback. It also owns story mode's backlog seed and prune.
