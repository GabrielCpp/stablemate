---
repo: stablemate
status: accepted
summary: Should the agent hook run the commit checks itself instead of rewriting the command?
---

## Question

Should the agent hook run the commit checks itself instead of rewriting the command?

## Decided

The guard rewrites the agent's command so the checks run before `git commit`, and raises the call's timeout by their budgets. Running the checks inside the hook was rejected, because every harness lets the call through when its hook times out.

## Grounded in

The operator's answer to Q19 of the grill.

## Context

The grill of 2026-11-11 on agent commit checks, recorded in docs/design/agent-commit-checks.md. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.

