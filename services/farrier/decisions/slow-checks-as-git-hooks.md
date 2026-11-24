story: none
date: 2026-11-11
elements: Checks, HooksInstall
sources: docs/design/agent-commit-checks.md

Slow checks leave git and run only when an agent commits inside a harness session. A separate slow tag on git hooks was rejected, because a human commit would still pay for it and a commit from workhorse's Python would too.

The question was whether slow commit checks should stay git hooks under a separate slow tag. The operator answered it at Q11 and Q17 of the grill of 2026-11-11 on agent commit checks. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.
