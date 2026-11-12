---
repo: stablemate
status: accepted
summary: Should slow commit checks stay git hooks under a separate slow tag?
---

## Question

Should slow commit checks stay git hooks under a separate slow tag?

## Decided

Slow checks leave git and run only when an agent commits inside a harness session. A separate slow tag on git hooks was rejected, because a human commit would still pay for it and a commit from workhorse's Python would too.

## Grounded in

The operator's answers to Q11 and Q17 of the grill.

## Context

The grill of 2026-11-11 on agent commit checks, recorded in docs/design/agent-commit-checks.md. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.

