# story_edit

The entry point for a story-level edit. Epic-edit owns the reconciliation that follows.

## Map

- `flow.py`: the story-edit state machine, which hands its result to epic-edit.
- `nodes.py`: turning a story add or remove command into the binding intent epic-edit receives.
