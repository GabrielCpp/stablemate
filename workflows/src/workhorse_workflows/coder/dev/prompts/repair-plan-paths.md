---
agent: agent
---

# Repair The Plan's Service Paths

The path validator rejected the machine-readable plan structure, not the plan's design.
Fix the offending values and return the corrected structure. This is a string repair: a
handful of tool calls, no re-reading of standards, no re-derived approach, no rewritten
section.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

### What the validator rejected

{{ workhorse_var('review_notes') }}

## What To Do

Check each rejected value against the tree — a `ls`, at most one `rg` — and correct it:

- a `path` that names no directory under its repo,
- a `repo` that is not a repo in this workspace,
- an `implementation_order` entry naming a service the plan never declared,
- a `plan_file` that is not there.

The validator re-runs on what you return, so a value you guessed at comes straight back.
Leave every other line of the plan on disk byte-identical.

## Commit Identity

Every commit carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as footers, spelled exactly so and nowhere else
in the message — not bracketed into the subject — the run record
ties a commit back to its story through them.

## Machine-Readable Result (required)

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}

Re-state the **full** structure every time, not just the corrected field: what you return
replaces what the previous turn returned, so a service or fixture omitted here is one the
workflow is never told about again.
