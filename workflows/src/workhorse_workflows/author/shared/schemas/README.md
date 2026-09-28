# schemas

The pydantic models the author machines share, grouped the way the machines are.

## Map

- `_base.py`: the base model every author reply and node return derives from.
- `edit.py`: the edit intent, graph snapshots and edit plan the epic-edit and story-edit flows share.
- `main.py`: the node returns and agent replies of the main author graph and the story machines.
- `parity.py`: the parity survey's config.
- `survey.py`: the surveyor's node returns and agent replies.
