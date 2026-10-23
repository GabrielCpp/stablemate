# nodes

The author nodes two or more machines call, registered on their own blueprint.

## Map

- `blueprint.py`: the node registry every module here decorates against.
- `commit.py`: the author's commit: which paths it ships and the message it ships them under.
- `config.py`: the author's resolved paths for a run, and the proof its intake exists.
- `coverage.py`: whether an epic's stories cover every seed in an acyclic graph.
- `integrity.py`: `ostler doctor` over the planning graph, as a blocking gate.
- `stories.py`: the per-story gates: the story contract, its grounding in the book, and its attempts ledger.
- `story_mode.py`: story mode's register edits: resolve a record, seed its story, close it as promoted.
- `stubs.py`: what the deterministic gates return under `--dry-run`.
