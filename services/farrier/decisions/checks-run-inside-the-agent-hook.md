story: none
date: 2026-11-11
elements: Checks
sources: docs/design/agent-commit-checks.md

The guard rewrites the agent's command so the checks run before `git commit`, and raises the call's timeout by their budgets. Running the checks inside the hook was rejected, because every harness lets the call through when its hook times out.

The question was whether the agent hook should run the commit checks itself instead of rewriting the command. The operator answered it at Q19 of the grill of 2026-11-11 on agent commit checks. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.
