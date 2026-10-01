# finalize

The machine that validates and delivers a roadmap that is already authored. It authors no new scope.

## Map

- `flow.py`: the finalize state machine: reconcile and integrity gates, the roadmap status change and the commit.
- `nodes/`: the reconcile and artifact gates, and the roadmap milestone check and advance.
