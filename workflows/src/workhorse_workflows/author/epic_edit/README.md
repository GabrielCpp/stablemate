# epic_edit

The machine that reconciles one epic after a direct scope change or a story-edit handoff.

## Map

- `flow.py`: the epic-edit state machine: plan, review, apply, rewrite, rework the affected stories and commit.
- `nodes/`: the deterministic steps that snapshot, check, apply and verify an epic edit.
