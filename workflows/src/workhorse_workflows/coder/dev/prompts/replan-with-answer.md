---
agent: agent
---

# Re-Plan Around The Operator's Answer

The plan raised a question it could not settle for itself and an answer came back. Fold
that answer into the plan files on disk and return the plan's structure as it now stands.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

Re-plan **only** the story at that path. Read it and its parent epic before you edit.

### What blocked the plan

{{ workhorse_var('review_notes') }}

### The answer

{{ workhorse_var('operator_context') }}

## What To Change

The plan already has its shape — `Approach`, `Changes`, an optional `Blast Radius`,
`Test Scenarios`, `Verification Commands`. Keep it. Edit the sections the answer actually
moves and leave every other line byte-identical; a section rewritten for tidiness is a diff
the next reader has to audit for nothing. Fold the answer into the section it belongs to
rather than adding an "Open Questions" section — the plan is a note between two nodes, not a
record of the conversation.

Do not implement code while re-planning.

`Test Scenarios` is machine-parsed. If the answer adds or removes one, it keeps the exact
`### Scenario N: <title>` heading with its `- **AC**:` and `- **Level**:` bullets — the QA
lane reads that shape and receives nothing else.

The plan re-enters the same gate that blocked it, so an answer folded in halfway comes back
to you as the same block.

## Commit Trailers

Every commit you write carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_slug') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Machine-Readable Result (required)

Return a short prose summary of what changed and why, then this exact JSON object as the LAST thing in your final response — these keys at its top level, with no wrapper object around them. Any other shape fails to parse and the node is retried:

```json
{
  "status": "done|blocked",
  "summary": "<one-line summary of what the answer moved, or the blocker>",
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

- `status`: `"done"` when the re-planned plan is ready for the gate, or `"blocked"` if the
  answer did not settle the question — which re-gates the operator rather than proceeding.
- `services`: one entry per **service** (concrete deployable unit) the plan changes. Each
  has `repo` (workspace/CWD repo name), `path` (relative path from repo root to the service
  folder, `.` for root), `type` (the key this repo's instructions gate on — take it from the
  repo's own `agents.yml` and skill short-names, not from a taxonomy you remember) and
  `plan_file`. Set `new_service: true` on a directory this story scaffolds.
- `implementation_order`: `repo::path` keys in build order; every entry must name a declared service.
- `shared_packages`: non-service directories (libs, shared code) changed as part of a dependent service's pass.
- `verification_setup`: the story's verification setup in machine-readable form.
- `fixtures`: the arrangements QA must stand up, one `name`/`provides` entry each.

**This reply is the whole of the re-plan's structure.** The workflow derives the touched
layers and the per-service run/regression scope from it — a re-plan that changed scope and
did not say so here did not change scope. Re-state the full structure every time, not just
the delta: what you return replaces what the previous turn returned.
