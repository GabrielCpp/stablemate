story: none
date: 2026-11-11
elements: Checks, HooksList
sources: docs/design/agent-commit-checks.md

Checks declare themselves under a new `commit_checks:` key with `{run, budget}` entries, and `farrier checks` lists them. Marking entries under `hooks:` was rejected, because that key means a git-hook stage.

The question was whether commit checks should reuse the `hooks` front-matter key with a marker. The operator answered it at Q18 and Q21 of the grill of 2026-11-11 on agent commit checks. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.
