# story_split

The machine that splits one named epic into stories and converges it through the PM's review before any story is written.

## Map

- `flow.py`: the story-split state machine, its lint, the PM review handoff and its rework and answer budgets.
- `nodes/`: the step that derives each story's services.
- `schemas.py`: the terminal value of the story-split flow.
