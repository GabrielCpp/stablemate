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
- Relevant instruction files for each touched layer:
  - {{ template.backend_layer_name | default("Go API") }}: `{{ instruction_ref("go") }}`, `{{ instruction_ref("go-architecture") }}`, `{{ instruction_ref("go-di") }}`, `{{ instruction_ref("go-errors") }}`, `{{ instruction_ref("go-openapi") }}`, `{{ instruction_ref("go-repository") }}`, `{{ instruction_ref("go-server") }}`, `{{ instruction_ref("go-storage") }}`, and `{{ instruction_ref("go-testing") }}`
  - Go CLI / `{{ template.go_cli_name | default("appctl") }}`: `{{ instruction_ref("go-cli") }}`, `{{ instruction_ref("go-cli-commands") }}`, and `{{ instruction_ref("go-testing") }}`
  - {{ template.mobile_layer_name | default("Flutter app") }}: `{{ instruction_ref("flutter") }}`, `{{ instruction_ref("flutter-architecture") }}`, `{{ instruction_ref("flutter-api") }}`, `{{ instruction_ref("flutter-state") }}`, `{{ instruction_ref("flutter-navigation") }}`, `{{ instruction_ref("flutter-forms") }}`, `{{ instruction_ref("flutter-models") }}`, `{{ instruction_ref("flutter-theme") }}`, and `{{ instruction_ref("flutter-testing") }}`
  - {{ template.infra_layer_name | default("Pulumi infrastructure") }}: `{{ instruction_ref("pulumi") }}`

## Refinement Goals

Review the implementation plan and improve it by:

1. Running validation searches against the current codebase.
2. Answering open questions with direct code or documentation references.
3. Replacing guesses, placeholders, and broad areas with actual file paths, functions, endpoints, providers, commands, and dependencies.
4. Identifying incorrect assumptions, missing dependencies, cross-layer contract gaps, and verification gaps.
5. Updating the plan so it is ready for a separate implementation pass.

Do not implement code while refining the plan.

## Current Iteration Focus

When using this prompt, specify the focus for the pass, for example:

- Go service and repository paths
- OpenAPI and generated client impact
- Flutter provider and screen flow
- `{{ template.go_cli_name | default("appctl") }}` CLI command shape
- Verification commands and emulator requirements
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

with repository-specific paths, layer names, and commands. Use `{{ template.backend_layer_name | default("Go API") }}`, `Go CLI`, `{{ template.mobile_layer_name | default("Flutter app") }}`, `Pulumi`, and `docs` as layer names.

## Refinement Checklist

Use only the phases relevant to the plan.

### Phase 1: {{ template.backend_layer_name | default("Go API") }} Service Layer

- [ ] Search relevant services in `{{ template.api_path | default("api") }}/internal/core/services/`
- [ ] Document service functions and call sites
- [ ] Identify domain model changes
- [ ] Check whether errors follow relevant Go error conventions
- [ ] Update plan with actual file paths and function names

### Phase 2: {{ template.backend_layer_name | default("Go API") }} Controller And Server Layer

- [ ] Search controllers in `{{ template.api_path | default("api") }}/internal/app/controllers/`
- [ ] Map request → controller → service → repository flow
- [ ] Check dependency wiring in `{{ template.api_path | default("api") }}/internal/app/container.go`
- [ ] Check route/server wiring if applicable
- [ ] Document error response behavior and authorization checks

### Phase 3: Firestore / Storage / External IO

- [ ] Search repositories and entities in `{{ template.api_path | default("api") }}/internal/io/`
- [ ] Identify collection names, entity mappings, and Firestore query patterns
- [ ] Check Firebase Auth, Firestore, Storage, or OpenRouter clients where relevant
- [ ] Document emulator requirements and fixture needs

### Phase 4: OpenAPI And Code Generation

- [ ] Identify `{{ template.openapi_path | default("api/pkg/api/openapi.yaml") }}` changes if any
- [ ] Identify generated Go files affected under `{{ template.go_api_generated_path | default("api/pkg/api") }}/`
- [ ] Identify generated Dart client files affected under `{{ template.dart_api_generated_path | default("app/lib/generated/api") }}/`
- [ ] Add exact generation commands from `{{ instruction_ref("go-openapi") }}` and `{{ instruction_ref("flutter-api") }}`

### Phase 5: Flutter App

- [ ] Identify affected screens, widgets, providers, models, services, and generated API use under `{{ template.app_path | default("app") }}/lib/`
- [ ] Map Riverpod state flow and loading/error/empty states
- [ ] Check routing impact in app router files when navigation changes
- [ ] Add widget/provider/unit/manual verification coverage
- [ ] Add exact commands from relevant Flutter instruction files

### Phase 6: Go CLI / `{{ template.go_cli_name | default("appctl") }}`

- [ ] Identify command ownership under the chosen Go command tree
- [ ] Check Cobra command conventions from `{{ instruction_ref("go-cli") }}` and `{{ instruction_ref("go-cli-commands") }}`
- [ ] Map fixture, auth, emulator, and authenticated request needs
- [ ] Confirm commands are development-only and block production targets

### Phase 7: Docs / Product Decisions

- [ ] Check `docs/roadmaps/mvp.md`, parent epic, and story scope
- [ ] Identify product decisions that must be documented before implementation
- [ ] Confirm no non-MVP scope is added
- [ ] Confirm safety, privacy, and debug-surface constraints remain explicit

## Output Format

After each refinement pass, provide:

### Summary Of Findings

```text
Area: {{ template.backend_layer_name | default("Go API") }} Service Layer
Files analyzed: 5
Key findings:
- UpdateProfile is in {{ template.api_path | default("api") }}/internal/core/services/profile/service.go
- Called by profile controller and tests
- Existing update input omits several MVP fields

Critical issues:
- OpenAPI and generated Dart client must change before mobile can consume new fields

Next step:
- Refine OpenAPI and Flutter provider sections
```

### Plan Updates Made

```text
Updated:
- Current State Analysis: added actual controller/service/repository paths
- Proposed Changes: replaced vague server-side wording with concrete {{ template.backend_layer_name | default("Go API") }} files
- Verification Commands: copied Go and Flutter commands from the relevant instruction files
```

### Open Questions Answered

```text
Q: Where is the OpenRouter client initialized?
A: {{ template.api_path | default("api") }}/internal/io/openai/client.go initializes the client and is used by the AI conversation service.
```

### Remaining Risks Or Blockers

```text
Risk: OpenAPI changes affect generated Go and Dart files.
Mitigation: {{ template.backend_layer_name | default("Go API") }} OpenAPI generation must run before Flutter API client generation.
```

## Completion Criteria

The plan is ready when:

- [ ] All placeholders are replaced with actual paths, names, or explicit decisions.
- [ ] Relevant function/provider/endpoint call sites have been searched and documented.
- [ ] Cross-layer contracts are clear when {{ template.backend_layer_name | default("Go API") }} and {{ template.mobile_layer_name | default("Flutter app") }} both change.
- [ ] Code generation inputs and outputs are identified.
- [ ] Verification commands are copied from relevant instruction files where present.
- [ ] Test scenarios cover happy paths, errors, edge cases, and integration boundaries.
- [ ] Safety, privacy, and production/debug constraints are represented where relevant.
- [ ] The plan remains scoped to the story and does not implement future stories.
- [ ] Rewrote `docs/specs/<story-name>/plan-context.json` so its `services` array + `required_instructions` match the refined plan (add/drop a service, its `skills`, or an instruction if refinement changed scope) — **preserve the `services` structure the planner wrote; do not collapse it back to a flat layer list.**

## Update `plan-context.json` (required)

Rewrite `docs/specs/<story-name>/plan-context.json` to match the refined plan — a deterministic workflow step reads it to bootstrap the implementer/QA with the instructions and run/QA tooling this story needs. Keep the **`services`** array as the source of truth (one entry per repo::service the story changes); the workflow derives the touched layers and regression platform from each service's `type` and `path`:

```json
{
  "services": [
    {"repo": "acme", "path": "api", "type": "go",           "skills": ["go", "go-architecture", "go-testing", "go-openapi"], "plan_file": "plan.md"},
    {"repo": "acme", "path": "web", "type": "react-router", "skills": ["react-router", "react-router-testing", "web-api"], "plan_file": "plan.md"}
  ],
  "implementation_order": ["acme::api", "acme::web"],
  "required_instructions": ["go", "go-architecture", "go-testing", "go-openapi", "react-router", "react-router-testing", "web-api"]
}
```

- `services`: one entry per **service** (concrete deployable unit) the refined plan changes. Each has `repo` (workspace/CWD repo name), `path` (relative path from repo root to the service folder — e.g. `web`, `api`, `report`, `pulumi`, `.` for root), `type` (`go`, `react-router`, `svelte`, `flutter`, `terraform`, `docs`), `skills` (instruction short-names for that service), and `plan_file`. This is where a layer is pinned to *where* it lives — e.g. `react-router` → the `web/` folder.
- `required_instructions` is the union of all services' `skills` (kept for backwards-compatible instruction resolution). Keep it in sync with the human-facing **Required Skill Files Read** section.

If refinement changed scope, add/drop a `services` entry or adjust its `skills` — do not hand-author a flat `touched_layers` list (it is derived from `services`).

## Machine-Readable Result (required)

After refining the plan artifacts, return this exact JSON object as the LAST thing in your final response. The workflow captures it under the `plan_result` key — without it the node fails to parse and is retried:

```json
{"plan_result": {"status": "done|blocked", "summary": "<one-line summary of the refinements, or the blocker>", "services": [{"repo": "acme", "path": "web", "type": "react-router"}, {"repo": "acme", "path": "api", "type": "go"}]}}
```

- `status`: `"done"` when the plan is refined and ready for re-review, or `"blocked"` if refinement cannot proceed.
- `summary`: a one-line description of what was refined (or the blocker).
- `services`: the repo::service entries the refined plan changes (`repo` + `path` + `type`, matching the `services` array above). Re-emit this every time — the workflow derives the touched layers and per-service run/regression scope from it (no flat `touched_layers` needed).
