---
repo: stablemate
status: accepted
summary: Should each repository carry its own agent commit guard?
---

## Question

Should each repository carry its own agent commit guard?

## Decided

One global guard in the agent-library, rendered by farrier into every harness home, serves every repository. A per-repository guard, such as a repo-level `.codex/hooks.json`, was rejected.

## Grounded in

The operator's answers to Q10 and Q12 of the grill.

## Context

The grill of 2026-11-11 on agent commit checks, recorded in docs/design/agent-commit-checks.md. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.

