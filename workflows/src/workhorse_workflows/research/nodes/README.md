# nodes

The research workflow's non-agent work, grouped by subject.

## Map

- `_blueprint.py`: the one `Blueprint` every research node registers against.
- `dossier.py`: the program dossier a program review is judged on, computed from the program folder with no model call.
- `history.py`: the program's `history.jsonl` event log.
- `measure.py`: the experiment run outside the agent turn: the envelope check, the detached job, and how its result is classified.
- `program.py`: which research program a run drives, its manifest, and its spend ledger.
- `publish.py`: getting a gate's work off the machine by committing it onto the result branch and pushing.
- `setup.py`: the working tree a run uses, cloned or adopted.
