---
name: python-lint
description: "The rule for a Python repository whose `make lint` runs ruff, ty and basedpyright: a commit carries no staged Python file that fails the repository's config for any of them. An agent commit check runs the three over the staged files, and a workflow's commit meets the same check."
commit_checks:
  - run: scripts/check_ruff_staged.py
    budget: 5
  - run: scripts/check_types_staged.py
    budget: 30
---

## Staged Python passes ruff, ty and basedpyright

`make lint` runs all three over the whole tree. Every agent commit runs them over
the staged Python files as the index holds them, and a refusal lists each finding.
Fix the file, restage, and commit again. A change that breaks a caller in an
unstaged file shows up only in `make lint`.
