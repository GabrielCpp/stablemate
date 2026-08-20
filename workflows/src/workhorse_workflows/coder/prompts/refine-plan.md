---
agent: agent
---

# Refine A {{ repo.name | title }} Implementation Plan

Use this prompt iteratively to refine an implementation plan with facts from the {{ repo.name | title }} codebase.

## Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

Refine **only** the plan for the story at the story path above, under the spec directory above. Do NOT search the repository, git history, or branch state to guess which story or plan to refine, and do NOT substitute a different story. If the story path above is blank or the file does not exist, stop and report that the workflow did not provide a usable story path — do not pick a story yourself.

If `{{ workhorse_var('spec_dir') }}` is blank, use the story folder name from the story path above as `<story-name>` and refine the plan under `docs/specs/<story-name>/`.

Also read the story and parent epic that the plan belongs to.

### Review / Refinement Notes

{{ workhorse_var('review_notes') }}

### Operator Context

{{ workhorse_var('operator_context') }}

## Required Context

Before refining the plan, read:

- `AGENTS.md`
- `docs/CODEX.md` when the work touches docs, epics, stories, or roadmap artifacts
- Relevant instruction files for each touched layer (only the layers this repository
  installs are listed; an absent one means this repo has no skills for that layer):
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

## Refinement Goals

Review the implementation plan and improve it by:

1. Running validation searches against the current codebase.
2. Answering open questions with direct code or documentation references.
3. Replacing guesses, placeholders, and broad areas with actual file paths, functions, endpoints, providers, commands, and dependencies.
4. Identifying incorrect assumptions, missing dependencies, cross-layer contract gaps, and verification gaps.
5. Updating the plan so it is ready for a separate implementation pass.

Do not implement code while refining the plan.

## Current Iteration Focus

When using this prompt, specify the focus for the pass. Pick the ones that apply to the
layers this story actually touches:

- Service and package paths on the owning side of the change
- Shared contract and generated-client impact
- Client-side data flow and screen/route structure
- Command-line surface shape, where the story adds or changes one
- Verification commands and any environment the tests need standing up
- Safety/privacy edge cases

## Search And Document Pattern

For each search area:

### 1. Run Searches

Prefer `rg` for text search and `rg --files` for file discovery.

Examples:

```bash
rg -n "CreateProfile|UpdateProfile|GetProfile" {{ template.api_path | default("api") }}/internal
rg --files {{ template.app_path | default("app") }}/lib/features/profile
rg -n "getProfile|updateProfile" {{ template.app_path | default("app") }}/lib {{ template.app_path | default("app") }}/test
```

### 2. Analyze Results

For each relevant result:

- Show file path and line number.
- Identify the function, type, endpoint, provider, widget, command, or model.
- Explain its current purpose.
- Search for callers or consumers.
- Assess the impact of the planned change.

### 3. Update The Plan

Add findings to the most relevant plan section:

- `Current State Analysis`
- `Proposed Changes`
- `Function Dependency Analysis`
- `Code Generation & Build Artifacts`
- `Implementation Checklist`
- `Test Scenarios`
- `Verification Commands`
- `Success Criteria`

If the plan has no place for evidence, add a short `Evidence From Codebase` section.
If the plan has open questions but no section for them, add `Open Questions And Answers`.

### 4. Replace Placeholders

Replace vague items such as:

- `TBD`
- `expected file`
- `probably`
- `some provider`
- `server side`
- `client side`
- `run tests`

with repository-specific paths, layer names, and commands, taken from this repo. The layer
names to use are the ones listed under "Instruction Set Resolution" above, plus `docs`.

## Refinement Checklist

Only the phases for layers this repository installs skills for are listed. Use only the
ones the plan actually touches; a layer absent here is absent from this repo.
{% if backend_refs %}
### {{ template.backend_layer_name | default("Backend service") }}: Domain And Service Layer

- [ ] Search the services the story touches, under the path the backend instructions name (`{{ template.api_path | default("the service root") }}/`)
- [ ] Document service functions and their call sites
- [ ] Identify domain model changes
- [ ] Check that errors follow the conventions those instruction files set
- [ ] Update the plan with actual file paths and function names

### {{ template.backend_layer_name | default("Backend service") }}: Entry Points, Wiring And Storage

- [ ] Search the handlers/controllers that expose the change
- [ ] Map the request path end to end: entry point → service → persistence
- [ ] Check dependency wiring wherever this repo composes it
- [ ] Document error-response behavior and authorization checks
- [ ] Identify the storage/external-IO adapters involved, their query patterns, and the fixtures or local emulators the tests need
{% endif %}
### Contracts And Code Generation

- [ ] Identify the shared contract files that change, if any (`{{ template.openapi_path | default("wherever this repo keeps them") }}`)
- [ ] Identify every generated artifact downstream of them, on both the producing and consuming sides
- [ ] Add exact generation commands from the codegen instruction files this repo installs
      {%- set codegen_refs = find_by_tags("codegen") %}
      {%- if codegen_refs %} ({{ codegen_refs }}){% endif %}
{% if web_refs %}
### {{ template.web_layer_name | default("Web app") }}

- [ ] Identify affected routes, components, loaders/actions and API calls
- [ ] Map the data flow, including the loading, error and empty states
- [ ] Check routing and navigation impact where the story changes it
- [ ] Add component/unit/end-to-end coverage, and the accessibility checks the web instructions require
- [ ] Add exact commands from the web instruction files
{% endif %}
{%- if mobile_refs %}
### {{ template.mobile_layer_name | default("Mobile app") }}

- [ ] Identify affected screens, widgets, state holders, models and generated API use under `{{ template.app_path | default("the app root") }}/`
- [ ] Map the state flow, including the loading, error and empty states
- [ ] Check routing impact when navigation changes
- [ ] Add widget/unit/manual verification coverage
- [ ] Add exact commands from the mobile instruction files
{% endif %}
{%- if cli_refs %}
### Command-Line Surface

- [ ] Identify which command tree owns the change
- [ ] Check the command conventions the CLI instruction files set ({{ cli_refs }})
- [ ] Map the fixture, auth and local-environment needs of each command
- [ ] Confirm development-only commands cannot be pointed at production
{% endif %}
{%- if infra_refs %}
### {{ template.infra_layer_name | default("Infrastructure") }}

- [ ] Identify the modules/stacks the change provisions or alters
- [ ] Document what is created, replaced or destroyed, and the blast radius of each
- [ ] Confirm the application contracts it provisions for are settled first
- [ ] Add the plan/preview command from the infra instruction files, and what a safe diff looks like
{% endif %}
### Docs / Product Decisions

- [ ] Check `docs/roadmaps/mvp.md`, parent epic, and story scope
- [ ] Identify product decisions that must be documented before implementation
- [ ] Confirm no non-MVP scope is added
- [ ] Confirm safety, privacy, and debug-surface constraints remain explicit

## Output Format

After each refinement pass, provide:

### Summary Of Findings

The blocks below show the *shape* of each section. Fill them with this repo's layers,
paths and commands — the names in them are stand-ins, not a stack to plan for.

```text
Area: <layer> — <the part of it the story changes>
Files analyzed: 5
Key findings:
- <the function the story changes> is in <its actual path>
- Called by <its actual call sites>
- <what the current implementation is missing for this story>

Critical issues:
- <the shared contract> must change before <the consumer> can use the new fields

Next step:
- Refine the <contract> and <consumer> sections
```

### Plan Updates Made

```text
Updated:
- Current State Analysis: added the actual paths for every layer the story touches
- Proposed Changes: replaced vague wording with concrete files
- Verification Commands: copied the commands for each touched layer from its instruction files
```

### Open Questions Answered

```text
Q: <the question the plan left open>
A: <the answer, with the file that settles it>
```

### Remaining Risks Or Blockers

```text
Risk: <changing the shared contract regenerates artifacts on both sides>
Mitigation: <which side regenerates first, and what breaks if the order is reversed>
```

## Completion Criteria

The plan is ready when:

- [ ] All placeholders are replaced with actual paths, names, or explicit decisions.
- [ ] Relevant function/provider/endpoint call sites have been searched and documented.
- [ ] Cross-layer contracts are clear wherever the story changes both sides of one.
- [ ] Code generation inputs and outputs are identified.
- [ ] Verification commands are copied from relevant instruction files where present.
- [ ] Test scenarios cover happy paths, errors, edge cases, and integration boundaries.
- [ ] Safety, privacy, and production/debug constraints are represented where relevant.
- [ ] The plan remains scoped to the story and does not implement future stories.
- [ ] Returned a `services` array matching the refined plan (add/drop a service or adjust its `skills` if refinement changed scope) — **preserve the structure the planner returned; do not collapse it to a flat layer list.**

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `docs`: this commit writes specification, not product code, and must not
   release a version of anything. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

## Machine-Readable Result (required)

After refining the plan artifacts, return this exact JSON object as the LAST thing in your final response — these keys at its top level, with no wrapper object around them. Any other shape fails to parse and the node is retried:

```json
{
  "status": "done|blocked",
  "summary": "<one-line summary of the refinements, or the blocker>",
  "services": [
    {"repo": "acme", "path": "api", "type": "<type>", "skills": ["<skill>"], "plan_file": "plan.md"},
    {"repo": "acme", "path": "web", "type": "<type>", "skills": ["<skill>"], "plan_file": "plan.md"}
  ],
  "implementation_order": ["acme::api", "acme::web"],
  "shared_packages": [],
  "verification_setup": {}
}
```

- `status`: `"done"` when the plan is refined and ready for re-review, or `"blocked"` if refinement cannot proceed.
- `summary`: a one-line description of what was refined (or the blocker).
- `services`: one entry per **service** (concrete deployable unit) the refined plan changes.
  Each has `repo` (workspace/CWD repo name), `path` (relative path from repo root to the
  service folder, `.` for root), `type` (the key this repo's instructions gate on — take it
  from the repo's own `agents.yml` and skill short-names, not from a taxonomy you remember),
  `skills` (instruction short-names for that service), and `plan_file`. This is where a layer
  is pinned to *where* it lives. Set `new_service: true` on a directory this story scaffolds.
- `implementation_order`: `repo::path` keys in build order; every entry must name a declared service.
- `shared_packages`: non-service directories (libs, shared code) changed as part of a dependent service's pass.
- `verification_setup`: the story's verification setup in machine-readable form.

**This reply is the whole of the refinement's structure.** The workflow derives the touched
layers and the per-service run/regression scope from it — a refinement that changed scope and
did not say so here did not change scope. Re-state the full `services` array every time, not
just the delta: what you return replaces what the previous turn returned.
