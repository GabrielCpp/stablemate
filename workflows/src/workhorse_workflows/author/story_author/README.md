# story_author

The standalone machine that authors one caller-named story. It never picks a story, branches or commits.

## Map

- `flow.py`: the story-author state machine: mockup, write, validate, ground, the PM review and their rework and answer budgets.
- `nodes/`: the steps that resolve the named story, gate its mockup, and read the operator's notes.
- `schemas.py`: the target and terminal values of the story-author flow.
