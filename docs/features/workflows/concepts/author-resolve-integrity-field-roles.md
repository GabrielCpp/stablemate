---
type: concept
slug: author-resolve-integrity-field-roles
title: Author resolve-integrity field roles
---
# Author resolve-integrity field roles

The `author-resolve-integrity-prompt` format carries six fields that the finalize flow passes to the integrity resolver agent and expects back. The three input fields define what the agent is investigating; the three output fields carry the agent's findings and decision.

## Input fields — what the agent is asked to investigate

**`context_path`** — the path to the operator context file the resolver must preserve and append its answers to, written by prior resolver passes or the human operator.

**`epics_dir`** — the repository-relative path to the epics directory whose documents and references the resolver inspects and edits using `ostler edit`.

**`integrity_errors`** — the ostler doctor error-level findings the resolver is asked to reconcile. Each line is a single doctor code, scope, and message. The resolver reads this to categorize the breaks (dangling references, orphaned entities, cross-epic dependencies) and chooses a repair strategy for each.

## Output fields — the agent's resolution

**`decision`** — the resolution outcome. Must be `answered` when the agent reconciles all breaks or escalates none, or `escalated` when a correct target does not exist and the agent cannot create it safely.

**`notes`** — a one-line plain-language statement of what was reconciled (when answered) or what remains unsolvable (when escalated), appended to the context file for human review.

**`tried`** — concrete investigations and dead ends the agent ruled out, supplied one line per attempt. Omit when nothing was ruled out. This is the diagnosis the agent already paid for; sending it saves a human from re-running every dead end on a retry.

- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity`
- detail: [author resolve-integrity prompt](../author-resolve-integrity-prompt.md)

