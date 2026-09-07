---
type: concept
slug: agent-backend-selection
title: Agent backend selection
---
# Agent backend selection

Select [NullBackend](null-backend.md) only for a run with no agent CLI. As
`workhorse/workhorse/runner/backends/null.py::NullBackend` establishes, it implements the
backend port to preserve a non-nullable runner backend, but is deliberately excluded from the
CLI registry: an operator cannot select it with `AGENT_CLI`.

An agent turn on such a run fails with instructions to select a CLI rather than producing
fabricated output. This makes the absent-CLI adapter appropriate for dry runs and script-only
workflows, but not an alternative agent CLI.

- rule: use `NullBackend` only when no agent CLI is selected; it is not a selectable CLI
- prefers: [null-backend](null-backend.md)
