---
name: python-lint
description: "The rule for a Python repository whose `make lint` runs ruff, ty and basedpyright: a commit carries no staged Python file that fails the repository's config for any of them. An agent commit check runs the three over the staged files, and a workflow's commit meets the same check."
commit_checks:
  - run: scripts/check_ruff_staged.py
    budget: 5
  - run: scripts/check_types_staged.py
    budget: 30
---

## Staged Python passes ruff

`make lint` runs ruff over the whole tree, so a staged Python file that fails the
repository's ruff config turns it red. Every agent commit runs ruff over the staged
Python files, as the index holds them, and a refusal lists each finding. Fix the
file, restage, and commit again.

## Staged Python passes ty and basedpyright

`make lint` also runs ty and basedpyright, so a staged Python file that fails either
turns it red. Every agent commit exports the index to a scratch tree and runs both
over the staged Python files there, under the repository's `pyproject.toml` and the
root's `.venv`. Each file is judged as the index holds it, next to the other files
the index holds. A refusal lists each finding with its file and line. Fix the file,
restage, and commit again.

Both checkers run over the staged files only. A file that is not staged is not
re-judged, so a change that breaks a caller in an unstaged file shows up in
`make lint` and not in this check.
