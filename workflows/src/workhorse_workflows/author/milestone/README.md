# milestone

The machine that builds or reuses exactly one milestone for an approved roadmap.

## Map

- `flow.py`: the milestone state machine, which reaches no epic, git or later stage.
- `nodes/`: the deterministic checks around the milestone turn.
- `schemas.py`: the context, reply and validation values of the milestone flow.
