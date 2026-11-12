---
repo: stablemate
status: accepted
summary: Should commit checks reuse the hooks front-matter key with a marker?
---

## Question

Should commit checks reuse the hooks front-matter key with a marker?

## Decided

Checks declare themselves under a new `commit_checks:` key with `{run, budget}` entries, and `farrier checks` lists them. Marking entries under `hooks:` was rejected, because that key means a git-hook stage.

## Grounded in

The operator's answers to Q18 and Q21 of the grill.

## Context

The grill of 2026-11-11 on agent commit checks, recorded in docs/design/agent-commit-checks.md. At stake: a human commit waited about seventeen seconds on git hooks that only an agent's commit needs.

