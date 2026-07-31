IMPORTANT: The plan MUST NOT include code snippets, patches, line-by-line edits, or direct instructions to modify source files during the planning stage. Plans may identify expected files, affected functions or contracts, dependencies, risks, and verification steps so the implementation agent can work safely. Implementation happens separately after plan review.

# Planning

## Provided Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

Plan **only** the story at the story path above. Do NOT search the repository, git history, or branch state to guess which story to plan, and do NOT substitute a different story. If the story path above is blank or the file does not exist, stop and report that the workflow did not provide a usable story path — do not pick a story yourself.

## Pre-Planning (REQUIRED — do first)

### Instruction Set Resolution

Load the target layer's coding standard files before planning. Use the template references below so generated prompts point at the target adapter's instruction directory (`{{ skill_dir() }}`).

Use the instruction files that match the layer and files touched. Only the layers this
repository actually installs are listed below — if a layer you expected is absent, this
repo has no skills for it, so use the shared repo guidance rather than inventing a path.
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
- Docs-only work: `AGENTS.md` and `docs/CODEX.md`

Rules:

- One layer → use only that layer's instruction files plus shared repo/docs guidance.
- Multiple layers → load each layer's instruction files and split plan sections by layer.
- Layer unclear → inspect the story and code paths first; if still unclear, stop and ask before planning.

### Story Analysis

1. Read the story description, acceptance criteria, and linked documents. **The story's `## Context`
   cites the OKF nodes it works on** — a node id is a repo-relative path, optionally `path#anchor`,
   so each citation is an ordinary link. Read those nodes and treat them as authoritative grounding
   for how the surface is built today: its components, their interactions, and where their data
   comes from — do not re-derive or guess what the book already records. The Acceptance Criteria,
   not the docs, define the work.
2. Identify scope: API, database, business logic, UI, code generation (protobuf, openapi, mocks, etc.).
3. Check dependencies: prerequisite stories, related work, external dependencies.
4. Review existing code: search for and understand current implementation patterns.
5. Do not include features out of scope for this story.
6. Do not start implementation until the plan is reviewed and approved.

---

## Plan Output Structure

### File Organization

Save all AI planning artifacts under:

`docs/specs/<story-name>/`

Use the story folder name as `<story-name>` unless the caller provides a specific slug. For example:

- Story: `docs/epics/profile-foundation/stories/persist-mvp-profile-fields/story.md`
- Plan directory: `docs/specs/persist-mvp-profile-fields/`

Do not put plan artifacts beside the story unless the caller explicitly overrides this location.

**ALWAYS create `plan.md` as the root reference.** Implementation reads from `plan.md` — do not create subplans without a root.

**Create each markdown artifact through `ostler`, don't hand-write its frontmatter** (when
`ostler` is on PATH): run `timeout 30 ostler create spec <story-name> <file>` — e.g.
`ostler create spec persist-mvp-profile-fields plan.md` — *before* writing the body. It stamps the
`type:` that makes the doc an OKF Concept (`spec.<stem>`: `plan.md` → `spec.plan`, `executive.md` →
`spec.executive`), creates the file if it is absent, and leaves an already-typed doc untouched. Then
write your content **below the `---` frontmatter block, leaving that block in place** — a doc with
no `type:` is an `okf-missing-type` error against the graph.

#### `plan-context.json` (REQUIRED machine-readable resolution)

Also write `docs/specs/<story-name>/plan-context.json` next to `plan.md`. A deterministic workflow step reads it to bootstrap the implementer and QA with the services, instructions, and run/QA tooling this story needs.

**Scaffold it, don't type it from memory** (when `ostler` is on PATH): run
`timeout 30 ostler artifact scaffold plan-context --spec docs/specs/<story-name>` to get the
exact skeleton, fill in the values, then **self-check before you return** with
`timeout 30 ostler artifact vet plan-context --spec docs/specs/<story-name>` — a vet failure is
YOUR bug to fix in this round; a malformed plan-context silently breaks the implementation
dispatcher stages later. Write it as:

```json
{
  "services": [
    {
      "repo": "api-service",
      "path": "cmd/alert",
      "type": "go",
      "skills": ["api-service", "api-service-grpc", "api-service-events"],
      "plan_file": "plan-api-service-alert.md"
    },
    {
      "repo": "web-app",
      "path": "packages/discover",
      "type": "svelte",
      "skills": ["web-app", "web-app-component"],
      "plan_file": "plan-web-app-discover.md"
    }
  ],
  "implementation_order": [
    "api-service::cmd/alert",
    "web-app::packages/discover"
  ],
  "shared_packages": [
    {"repo": "api-service", "path": "pkg/db/alert", "type": "go-lib"}
  ],
  "required_instructions": ["api-service", "api-service-grpc", "web-app", "web-app-component"],
  "qa_stack": {
    "profile": "the stack/compose-profile/seed that renders this surface with realistic data",
    "fixtures": ["the specific records/rows the surface needs to display, and how to create them"],
    "capable_of_rendering": "the surface this stack can actually show (not a thin/empty default)"
  }
}
```

- `services`: one entry per **service** (concrete deployable unit) this story changes. Each has:
  - `repo`: the repo name (must match a folder name in the workspace or the CWD repo name)
  - `path`: relative path from repo root to the service directory (e.g., `cmd/alert`, `packages/discover`, `.` for root)
  - `type`: the technology, using the key **this repo's** instructions/prompts gate on — take it from the skill short-names listed under "Instruction Set Resolution" above and from the repo's own `agents.yml`, not from a taxonomy you remember. `docs` is the type for documentation-only services in every repo.
  - `skills`: instruction short-names the implementer must load for this service
  - `plan_file`: the plan file for this service (relative to spec dir)
- `implementation_order`: ordered list of `repo::path` keys specifying build order. Dependencies first: whatever defines a shared contract before whatever implements it, and whatever implements it before whatever consumes it.
- `shared_packages`: non-service directories that need changes (libs, shared code). These are implemented as part of their dependent service's pass.
- `required_instructions`: union of all services' skills (for backwards-compatible instruction resolution).
- `qa_stack`: copy the story's **`## Verification setup`** into machine-readable form.

**How to identify services**: A service is a directory with a marker file. The repo's own
`agents.yml` (`workspace.service_roots`/`service_markers` and the `template.*_path` hints)
is authoritative for both the `path` and the `type` — read it first. The markers below are
listed only for the layers this repo installs skills for; a layer that is absent from this
list is absent from this repo, so do not go looking for one.
{%- if backend_refs %}
- {{ template.backend_layer_name | default("Go service") }}: `main.go` or `go.mod` at its root (`cmd/<name>/`, or a module root)
{%- endif %}
{%- if web_refs %}
- {{ template.web_layer_name | default("Web app") }}: `package.json`
{%- endif %}
{%- if mobile_refs %}
- {{ template.mobile_layer_name | default("Mobile app") }}: `pubspec.yaml`
{%- endif %}
{%- if infra_refs %}
- {{ template.infra_layer_name | default("Infrastructure") }}: `Pulumi.yaml`/`index.ts`, or `main.tf`
{%- endif %}
- Docs-only service: the documentation root the repo's book is written under

**Single-service stories** collapse to one entry in `services`, one `plan.md`, and a one-element `implementation_order`.

For single-service stories:
- `executive.md` — Human-readable summary (always)
- `plan.md` — Complete plan for the service

For multi-service stories, use per-service plan files:
- `plan.md` — Root plan: high-level design, cross-service contracts, implementation order
- Per-service files named in each service's `plan_file` field (e.g., `plan-api-service-alert.md`, `plan-web-app-discover.md`)
- `executive.md` — Human-readable summary (always, for review)

### Cross-Service Coordination

When a story spans multiple services (across one or more repos), the **plan.md** (root) MUST include:

#### Implementation Order

Specify which service must be implemented first, and derive the order from this story's
own dependencies rather than from a fixed layer ranking:

1. **Shared contracts** — schemas, API definitions, generated-code inputs: whatever both sides agree on
2. **The service that owns the contract** — it has to satisfy the contract before anything can call it
3. **Infrastructure** — once the application contracts it provisions for are settled
4. **The services that consume the contract** — client-side last, against a backend that already answers

State the order explicitly using `repo::path` notation in `implementation_order`. Each service is implemented independently in its own repo CWD.

#### Integration Contracts

For each cross-service boundary, document:

- **API endpoint or event** — Exact path, method, event type
- **Request/response shape** — Field names, types, required vs optional
- **Error cases** — What the consumer should handle
- **Feature flag gating** — If the new behavior is behind a flag, name it
- **Cross-repo dependency** — If api-service changes a proto, specify which web-app/mobile-app consumers must update

#### Per-Service Verification

Each service plan file must reference its applicable instruction files → **"Verification Commands"** section for the exact test/lint/build commands where that section exists. Do not invent commands when the instruction files define them; if a command is missing, state that and choose the narrowest standard command for the affected service.

### 1. Summary

- Story objective in 1-2 sentences
- High-level approach
- Key architectural decisions
- **Coding Standards Alignment**: which instruction file(s) apply

### Required Skill Files Read

- List every generated skill or instruction file read before planning.
- If no layer-specific skill file applies, write `None` and explain why.

### 2. Current State Analysis

- Existing code structure and behavior
- Known issues or tech debt

### 3. Proposed Changes

#### Architecture Decisions

- Design choices and rationale
- Alternatives considered and trade-offs

#### Impact Analysis For Shared Behavior

Use this section when the story changes shared functions, contracts, validation rules, generated models, persistence behavior, navigation behavior, or anything with multiple callers or consumers.

The goal is to avoid a locally successful implementation that leaves another workflow broken.

For each shared function, endpoint, model, provider, command, generated type, or contract likely to be affected, document:

- Current observable responsibility
- Known callers, consumers, or user-facing workflows
- Expected behavior after this story
- Compatibility risks
- Areas that must be verified
- Areas intentionally left unchanged

**Process:**

1. Search the codebase for likely affected shared names and contracts.
2. Document the relevant callers or consumers and assess if they need changes.
3. Follow important chains until reaching entry points, screens, commands, handlers, or external contracts.
4. Summarize the dependency tree only as far as needed to prevent breakage.

**Red flags — stop and reconsider if:**

- Removing a function used by 3+ callers
- Changing shared validation logic without checking all callers
- Modifying data structures passed between layers
- Breaking contracts expected by external APIs

#### Code Generation & Build Artifacts

Identify any generated files affected by the changes:

{%- if backend_refs %}
- API contract changes → the generated server/types under `{{ template.go_api_generated_path | default("the path the backend instructions name") }}/` (run the generation command those instructions give)
{%- endif %}
{%- if mobile_refs %}
- API contract changes → the generated client under `{{ template.dart_api_generated_path | default("the path the mobile instructions name") }}/` (run the generation command those instructions give)
{%- endif %}
- Any other generated artifact this repo builds from a checked-in input — the command lives in that layer's instruction files, never in this prompt
- Database migrations (if schema changes)

For each, list the generation command, input files that change, and output files that will be regenerated.

#### Expected Files To Touch

List the files, directories, or generated artifacts the implementation is expected to modify.

For each item, describe the behavioral responsibility of the change, not the exact code edit. If the exact file is not yet knowable without implementation, name the smallest likely directory or package and explain why.

Examples of the shape — with this repo's own paths, not these:

- `{{ template.openapi_path | default("<the shared contract file>") }}` — add or adjust the contract this story needs.
- `{{ template.api_path | default("<the owning service>") }}/...` — update the behavior that serves it.
- `<the generated client, on each side that consumes the contract>` — regenerate when the contract changes.
- `docs/specs/<story-name>/...` — keep plan, review, and QA artifacts for this story.

### 4. Implementation Checklist

Ordered steps. **Every checklist must end with these closing steps:**

```
- [ ] Run code generation (if applicable): [exact command]
- [ ] Run tests: [exact test command for this layer]
- [ ] Run linter/formatter: [exact lint command for this layer]
- [ ] Verify no compile/type errors remain
```

### 5. Test Scenarios

Write each test case in **Given / When / Should** format:

- Happy path cases
- Error cases
- Edge cases
- Integration/dependency tests

### 6. Verification Commands (CRITICAL)

Copy the exact commands from the layer's instruction files → **"Verification Commands"** section where present. Do not invent commands when the instruction files define them.

For each layer involved, list:

```
## [layer-name] Verification

# Code generation (if applicable)
[copy from the relevant instruction files listed under "Instruction Set Resolution" above]

# Tests
[copy from relevant layer instructions]

# Lint / Format
[copy from relevant layer instructions]

# Build
[copy from relevant layer instructions]

# Local run (smoke) — how to bring this layer up locally and exercise the touched path
[The exact commands to start this layer's local runtime and reach the story's path, copied from
 the layer instruction files and the project's local-stack / "operate the local stack" runbook
 (e.g. start the API server, start the web dev server, run the app on the emulator, or
 `pulumi preview`). State the observable success signal — endpoint returns a real status, the
 route renders the feature, the screen loads — so the implementer can confirm it actually runs,
 not just that unit tests pass. If this layer has no runnable surface (docs-only), write "None".]
```

If no code generation applies for a layer, write "None" — do not omit the section.
For multi-layer stories, list commands for **each layer separately** so the implementer can run them independently. The **Local run (smoke)** block is mandatory for every layer with a runnable surface — the implementer is required to run the touched layers locally before completing the story (it is not optional), so the plan must tell it exactly how.

### 7. Success Criteria

- Functional requirements met
- All tests passing (including new tests) **per layer**
- **The touched path runs in a local environment** — each touched layer's "Local run (smoke)" passes and the story's path was exercised, not just unit-tested
- No broken dependencies
- Code generation outputs up to date
- Cross-layer contracts verified (API shape matches consumer expectations)
- Documentation updated

---

## Before Finalizing Plan

All items must be checked:

- [ ] Loaded the relevant instruction files for **every service** and added **Coding Standards Alignment** to the Summary
- [ ] Added **Required Skill Files Read** to every planning artifact
- [ ] Searched for affected shared functions, contracts, models, providers, commands, and generated types; documented relevant callers or consumers
- [ ] Identified code generation dependencies and listed exact regen commands (or "None")
- [ ] Copied verification commands from each service's instructions files → "Verification Commands" section
- [ ] Specified a **Local run (smoke)** command + observable success signal for every service with a runnable surface (or "None" for docs-only)
- [ ] Wrote `docs/specs/<story-name>/plan-context.json` with `services` array (concrete paths with repo, type, skills, plan_file) — drives the implementer's per-service iteration
- [ ] Listed every changed service in `plan-context.json`'s `services` array — it is the only place the workflow reads them from
- [ ] Verified every service path exists and carries the marker file its `type` implies (see "How to identify services")
- [ ] Added **Given / When / Should** test scenarios for all affected code paths
- [ ] Confirmed no breaking changes to external APIs
- [ ] Implementation checklist ends with: codegen → test → lint → verify
- [ ] Multi-service stories: documented implementation order, integration contracts, and per-service verification

## Common Pitfalls

❌ Don't assume "only one place uses this function" — always search.
❌ Don't invent verification commands — copy them from the layer's instructions files.
❌ Don't forget code generation — stale generated files cause silent failures.
❌ Don't plan a consumer-side change against a contract change without specifying the implementation order.
❌ Don't plan for a layer this repo does not have — the "Instruction Set Resolution" list above is the whole set.
✅ Search exact function names (case-sensitive).
✅ Copy test/lint/build commands from each layer's instruction files → **"Verification Commands"** section where present.
✅ Identify generated files that must be refreshed after contract changes.
✅ For multi-layer stories, document the integration contract so each layer can be implemented independently.

## Machine-Readable Result (required)

After writing the plan artifacts, return this exact JSON object as the LAST thing in your final response — these two keys at its top level, with no wrapper object around them. Any other shape fails to parse and the node is retried:

```json
{"status": "done|blocked", "summary": "<one-line summary of the plan, or the blocker>"}
```

- `status`: `"done"` when the plan artifacts are written and ready for review, or `"blocked"` if you could not produce a plan.
- `summary`: a one-line description of the plan (or the blocker).

The set of services this story changes is **not** part of this reply — the workflow reads it from the `services` array you wrote into `docs/specs/<story-name>/plan-context.json`, which is what drives the implementer's per-service iteration. Get it right there: a frontend-only story lists only its web service, so the implementer never builds a backend one.
