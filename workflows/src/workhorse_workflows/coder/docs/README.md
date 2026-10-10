# docs

The docs lane of the coder workflow. One owner agent folds a finished story into the as-built OKF book through its subagents, and the run checks that claim against the diff.

## Map

- `flow.py`: the `Docs` state machine. The owner turn writes, reviews and fixes the book. Ostler's grounding gate is the `check`, and what it refuses goes back to the same session as one report.
- `prompts/document-story.md`: the owner's prompt, with the writer, reviewer and fixer briefs it hands its subagents.
