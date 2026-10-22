# nodes

The deterministic steps of the PM.

## Map

- `_blueprint.py`: the blueprint that registers the PM's dry-run agent stubs.
- `ledger.py`: the steps that read and append the `grills/pm.md` ledger.
- `receipt.py`: the step that writes `pm-receipt.json` after a passing review.
