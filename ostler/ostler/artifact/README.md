# artifact

The `ostler artifact` command: schema-checked workflow artifacts that a workflow scaffolds, then vets.

## Map

- `kinds.py`: the built-in artifact kinds, each with its filename, scaffold skeleton and semantic vet rules.
- `run.py`: the `scaffold`, `vet` and `list` invocations over a spec directory, and the outcome they report.
