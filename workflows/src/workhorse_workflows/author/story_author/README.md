# story_author

The standalone machine that authors one caller-named story. It never picks a story, branches or commits.

## Map

- `flow.py`: the story-author state machine: mockup, write, validate, ground, audit and their rework budgets.
- `nodes/`: the steps that resolve the named story and record its audit.
- `schemas.py`: the target, audit receipt and terminal values of the story-author flow.
