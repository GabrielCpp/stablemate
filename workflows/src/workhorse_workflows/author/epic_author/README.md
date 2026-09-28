# epic_author

The standalone machine that authors one caller-named epic. It never picks an epic from a worklist.

## Map

- `flow.py`: the epic-author state machine and its rework and resolve budgets.
- `nodes/`: the deterministic steps that resolve and validate the named epic.
- `schemas.py`: the context, evidence and terminal values the epic-author flow passes around.
