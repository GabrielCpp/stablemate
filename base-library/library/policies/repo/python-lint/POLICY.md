---
name: python-lint
description: "The rule for a Python repository whose `make lint` runs ruff: a commit carries no staged Python file that fails the repository's ruff config. An agent commit check runs ruff over the staged files, and a workflow's commit meets the same check."
commit_checks:
  - run: scripts/check_ruff_staged.py
    budget: 5
---

## Staged Python passes ruff

`make lint` runs ruff over the whole tree, so a staged Python file that fails the
repository's ruff config turns it red. Every agent commit runs ruff over the staged
Python files, as the index holds them, and a refusal lists each finding. Fix the
file, restage, and commit again.
