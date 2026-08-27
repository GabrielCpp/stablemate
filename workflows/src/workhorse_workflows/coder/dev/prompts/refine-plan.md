---
agent: agent
---

# Refine A {{ repo.name | title }} Implementation Plan

Use this prompt iteratively to refine an implementation plan with facts from the {{ repo.name | title }} codebase.

## Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

Refine **only** the plan for the story at the story path above, under the spec directory above. Do NOT search the repository, git history, or branch state to guess which story or plan to refine, and do NOT substitute a different story. If the story path above is blank or the file does not exist, return `status: "blocked"` (Machine-Readable Result below) with a summary saying the workflow did not provide a usable story path — that hands it to the operator. Do not pick a story yourself.

If `{{ workhorse_var('spec_dir') }}` is blank, use the story folder name from the story path above as `<story-name>` and refine the plan under `docs/specs/<story-name>/`.

Also read the story and parent epic that the plan belongs to.

### Review / Refinement Notes

{{ workhorse_var('review_notes') }}

### Operator Context

{{ workhorse_var('operator_context') }}

## Which Repair Is This

You are here because a gate rejected the plan, not because someone reviewed it. There are
exactly two ways to arrive, and they want different work. Read the notes above and decide
which one you are in **before** you open anything.

**Mode A — the machine-readable result was rejected.** The notes open with
`Service path validation failed:` and name a bad service `path`, `repo`, `plan_file` or
marker: a directory that does not exist, a repo that is not in this
workspace, an `implementation_order` entry naming a service that was never declared. The
plan's *design* is not in question. Check the offending value against the tree (`ls`, one
`rg`), fix it, and return. Do **not** re-read the standards, do not re-derive the approach,
do not rewrite a section. This is a string repair and should cost a handful of tool calls.

**Mode B — the operator answered a block.** The notes carry a decision the plan could not
make for itself. Re-plan around that answer: change the sections the answer actually moves,
leave the rest alone, and update the plan files on disk. This is real planning, so it is
worth reading the instruction files for the layers the answer touches.

If the notes are silent or you cannot tell which mode you are in, treat it as Mode A and ask
in your summary — a rewrite nobody requested is more expensive than a question.

## Required Context (Mode B only)

Read the story and its parent epic, `AGENTS.md`, and — only for the layers the operator's
answer actually moves — the instruction files below. Skip a layer the answer does not touch.
(Only the layers this repository installs are listed; an absent one means this repo has no
skills for that layer.)
{%- set backend_refs = find_by_tags("backend") %}
{%- set cli_refs = find_by_tags("cli") %}
{%- set web_refs = find_by_tags("web") %}
{%- set mobile_refs = find_by_tags("mobile") %}
{%- set infra_refs = find_by_tags("infra") %}
{%- if backend_refs %}
- {{ template.backend_layer_name | default("Go API") }}: {{ backend_refs }}
{%- endif %}
{%- if cli_refs %}
- Go CLI / `{{ template.go_cli_name | default("appctl") }}`: {{ cli_refs }}
{%- endif %}
{%- if web_refs %}
- {{ template.web_layer_name | default("Web app") }}: {{ web_refs }}
{%- endif %}
{%- if mobile_refs %}
- {{ template.mobile_layer_name | default("Mobile app") }}: {{ mobile_refs }}
{%- endif %}
{%- if infra_refs %}
- {{ template.infra_layer_name | default("Infrastructure") }}: {{ infra_refs }}
{%- endif %}

Do not implement code while refining the plan.

## What You Change

The plan already has its shape — `Approach`, `Changes`, an optional `Blast Radius`,
`Test Scenarios`, `Verification Commands`. Keep it. Edit the sections the rejection or the
answer moves and leave every other line byte-identical; a section rewritten for tidiness is
a diff the next reader has to audit for nothing.

Two rules survive from the old checklist because they still bind:

- **Never invent a verification command.** Copy it from the layer's instruction files or
  from what the plan already carries.
- **`Test Scenarios` is machine-parsed.** If the answer adds or removes one, keep the exact
  `### Scenario N: <title>` heading with its `- **AC**:` and `- **Level**:` bullets. A
  scenario whose shape drifts is a scenario the QA lane never receives.

If the answer settles a question the plan left open, fold the answer into the section it
belongs to rather than adding an "Open Questions" section — the plan is a note between two
nodes, not a record of the conversation.

## Output Format

Return what `plan-story` returns: a short prose summary of what changed and why, then the
JSON below. No findings report, no per-area analysis, no risk register — the summary line
and the diff on disk are the whole of it.

## Commit Trailers

Every commit you write carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_slug') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Machine-Readable Result (required)

Return this exact JSON object as the LAST thing in your final response — these keys at its top level, with no wrapper object around them. Any other shape fails to parse and the node is retried:

```json
{
  "status": "done|blocked",
  "summary": "<one-line summary of the refinements, or the blocker>",
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

- `status`: `"done"` when the plan is repaired and ready for the plan gate, or `"blocked"` if refinement cannot proceed.
- `summary`: a one-line description of what was refined (or the blocker).
- `services`: one entry per **service** (concrete deployable unit) the refined plan changes.
  Each has `repo` (workspace/CWD repo name), `path` (relative path from repo root to the
  service folder, `.` for root), `type` (the key this repo's instructions gate on — take it
  from the repo's own `agents.yml` and skill short-names, not from a taxonomy you remember),
  `skills` (optional — only standards the layer's own tags do not reach), and `plan_file`. This is where a layer
  is pinned to *where* it lives. Set `new_service: true` on a directory this story scaffolds.
- `implementation_order`: `repo::path` keys in build order; every entry must name a declared service.
- `shared_packages`: non-service directories (libs, shared code) changed as part of a dependent service's pass.
- `verification_setup`: the story's verification setup in machine-readable form.
- `fixtures`: the arrangements QA must stand up, one `name`/`provides` entry each. Re-state
  the full list every time, for the same reason `services` is re-stated: what you return
  replaces what the previous turn returned, so a fixture omitted here is one QA is never
  told it may call.

**This reply is the whole of the refinement's structure.** The workflow derives the touched
layers and the per-service run/regression scope from it — a refinement that changed scope and
did not say so here did not change scope. Re-state the full `services` array every time, not
just the delta: what you return replaces what the previous turn returned.
