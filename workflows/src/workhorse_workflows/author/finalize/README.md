# finalize

The machine that validates and delivers a milestone that is already authored. It authors no new scope.

## Map

- `flow.py`: the finalize state machine: reconcile and integrity gates, the milestone status change and the commit.
- `nodes/`: the reconcile and artifact gates, and the milestone epic check and advance.
