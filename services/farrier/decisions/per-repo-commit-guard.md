story: none
date: 2026-11-11
elements: Checks
sources: docs/design/agent-commit-checks.md

One global guard in the agent-library, rendered by farrier into every harness home, serves every repository. A per-repository guard, such as a repo-level `.codex/hooks.json`, was rejected.

The question was whether each repository should carry its own agent commit guard. The operator answered it at Q10 and Q12 of the grill of 2026-11-11 on agent commit checks. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.
