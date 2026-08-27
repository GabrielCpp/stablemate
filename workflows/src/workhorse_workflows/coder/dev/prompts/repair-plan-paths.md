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

## Commit Trailers

Every commit you write carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_slug') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Machine-Readable Result (required)

Return this exact JSON object as the LAST thing in your final response — these keys at its top level, with no wrapper object around them. Any other shape fails to parse and the node is retried:

```json
{
  "status": "done|blocked",
  "summary": "<one-line summary of what was corrected, or the blocker>",
  "services": [
    {"repo": "acme", "path": "api", "type": "<type>", "plan_file": "plan.md"},
    {"repo": "acme", "path": "web", "type": "<type>", "plan_file": "plan.md"}
  ],
  "implementation_order": ["acme::api", "acme::web"],
  "shared_packages": [],
  "verification_setup": {},
  "fixtures": [{"name": "<fixture>", "provides": "<the state it guarantees>"}]
}
```

- `status`: `"done"` when the structure is corrected, or `"blocked"` if the rejected value
  cannot be resolved from the tree — a service that genuinely does not exist anywhere.
- `services`: one entry per **service** (concrete deployable unit) the plan changes. Each
  has `repo` (workspace/CWD repo name), `path` (relative path from repo root to the service
  folder, `.` for root), `type` (the key this repo's instructions gate on — take it from the
  repo's own `agents.yml` and skill short-names, not from a taxonomy you remember) and
  `plan_file`. Set `new_service: true` on a directory this story scaffolds.
- `implementation_order`: `repo::path` keys in build order; every entry must name a declared service.
- `shared_packages`: non-service directories (libs, shared code) changed as part of a dependent service's pass.
- `verification_setup`: the story's verification setup in machine-readable form.
- `fixtures`: the arrangements QA must stand up, one `name`/`provides` entry each.

Re-state the **full** structure every time, not just the corrected field: what you return
replaces what the previous turn returned, so a service or fixture omitted here is one the
workflow is never told about again.
