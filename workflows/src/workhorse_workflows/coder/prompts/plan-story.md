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

### When the plan is already there

Check the spec directory before you write anything. A story is re-selected by the queue
until it reaches `QA passed`, so one that was interrupted after planning — or that is coming
back for documentation or QA — arrives here with `plan.md` (and often `plan-review.md`, a
review, a settlement) already written. That is the normal resumed case, not an error, and
you are not being asked to redo it.

- **The existing plan still covers the story's Acceptance Criteria** → leave every artifact
  exactly as it is and answer `done`, with a summary that says the plan already stands.
  Do not rewrite it: implementation was built against that plan and review compares against
  it, so replacing it invalidates work that is already in the tree.
- **The story has changed since** — a criterion the plan does not cover → amend the plan in
  place for that delta only, leave the rest, and answer `done`.
- Either way this is **never** `blocked`. `blocked` means no plan could be produced; a plan
  that already exists is the opposite of that, and answering it that way sends a story that
  only needs QA to the operator instead.

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

#### The plan's structure (returned, not written)

Your final reply carries the machine-readable resolution of this plan — the services it
changes, the order they are built in, and the run/QA tooling it needs. The workflow validates
that structure and writes it to disk itself; you do not author a machine-read file. The exact
shape is under "Machine-Readable Result" at the end of this prompt, and it is:

- `services`: one entry per **service** (concrete deployable unit) this story changes. Each has:
  - `repo`: the repo name (must match a folder name in the workspace or the CWD repo name)
  - `path`: relative path from repo root to the service directory (e.g., `cmd/alert`, `packages/discover`, `.` for root)
  - `type`: the technology, using the key **this repo's** instructions/prompts gate on — take it from the skill short-names listed under "Instruction Set Resolution" above and from the repo's own `agents.yml`, not from a taxonomy you remember. `docs` is the type for documentation-only services in every repo.
  - `skills`: instruction short-names the implementer must load for this service
  - `plan_file`: the plan file for this service (relative to spec dir)
  - `new_service`: `true` only when the directory does not exist yet and this story scaffolds it
- `implementation_order`: ordered list of `repo::path` keys specifying build order. Dependencies first: whatever defines a shared contract before whatever implements it, and whatever implements it before whatever consumes it. Every entry must name a service you declared.
- `shared_packages`: non-service directories that need changes (libs, shared code). These are implemented as part of their dependent service's pass.
- `verification_setup`: the story's **`## Verification setup`** in machine-readable form.

**How to identify services**: A service is a directory with a marker file. The repo's own
`agents.yml` (`workspace.service_roots`/`service_markers` and the `template.*_path` hints)
is authoritative for both the `path` and the `type` — read it first.
{% if markers %}
Each repo in this workspace declares what marks one of its service directories:

{{ markers }}

A directory holding one of its repo's markers is a service; a marker that is not on its
repo's list is not one, however familiar it looks.
{%- else %}
No repo in this workspace declares `workspace.service_markers`, so there is no list to hand
you: derive the services from `agents.yml`'s `service_roots` and `template.*_path` hints and
from the layout you can see, and name in your summary what you used.
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

This section is the **contract between the acceptance criteria and the test suite** — the
implementation is split into a tests-first pass and a code pass with a deterministic red gate
between them, and the gate and the reviewer both read this list. A scenario missing here is a
scenario nobody writes; an AC no scenario names is an AC the reviewer flags as uncovered.

Write each test case in **Given / When / Should** format, and give every scenario two more
fields:

- **AC**: the acceptance criterion it covers, by number or exact quote. Every AC must be
  covered by at least one scenario; a scenario may also guard an edge case no AC names —
  mark those `AC: none (edge case)`.
- **Level**: where the test lives —
  - `unit` — a pure function or class, no wiring.
  - `component` — the primary target: a component/handler/service exercised through its
    public surface with real wiring and faked leaves.
  - `endpoint` — an HTTP surface exercised through the router.
  - `integration` — added or extended only where the story warrants it (a contract crossing
    services, a persistence shape). An integration test listed here **is part of the red
    gate**, so it must be reachable from this layer's test command in the Verification
    Commands section.
  - `QA-only` — verifiable only by a live walkthrough (visual layout, cross-app flow).
    No test is written for it; QA covers it. Use this sparingly and say why.

Cover happy paths, error cases, and edge cases across the scenarios.

**Regression-only escape (decided here, at plan time — never by the implementer):** if the
story changes no observable behavior (a pure refactor, a rename, a dependency bump), state
`Test scenarios: regression-only` with one line of justification instead of a scenario list.
The implementation then skips the tests-first pass and the red gate, and the existing suite
is the safety net. If any new behavior exists, this escape does not apply.

**QA-only escape (same rule, different reason):** if — having written the list honestly —
*every* scenario in it came out `Level: QA-only`, add the line `Test scenarios: qa-only`
above the list and keep the list. The tests-first pass has nothing it is permitted to write
in that case, so the implementation takes a single turn and the red gate stands aside; the
scenarios are handed to the QA plan as its obligations, which is where they will actually be
verified. This is not a way to avoid writing tests: it costs the story every automated
guarantee, and one scenario at any other level means the escape does not apply and the whole
list goes through the gate as usual. If you find yourself reaching for it, first check
whether a `component` scenario could cover the same AC.

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
 (whatever bringing this layer up locally takes here — a server, a dev server, an emulator,
 a plan-preview). State the observable success signal — endpoint returns a real status, the
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
- [ ] Returned a `services` array (concrete paths with repo, type, skills, plan_file) — it drives the implementer's per-service iteration
- [ ] Listed **every** changed service in it, and nothing the story does not change
- [ ] Verified every service path exists and carries the marker file its `type` implies (see "How to identify services")
- [ ] Added **Given / When / Should** test scenarios for all affected code paths, each with its **AC** reference and **Level** — every acceptance criterion covered by at least one scenario (or the story declared regression-only, with justification)
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

After writing the plan artifacts, return this exact JSON object as the LAST thing in your final response — these keys at its top level, with no wrapper object around them. Any other shape fails to parse and the node is retried:

```json
{
  "status": "done|blocked",
  "summary": "<one-line summary of the plan, or the blocker>",
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
      "type": "web-app",
      "skills": ["web-app", "web-app-component"],
      "plan_file": "plan-web-app-discover.md"
    }
  ],
  "implementation_order": ["api-service::cmd/alert", "web-app::packages/discover"],
  "shared_packages": [{"repo": "api-service", "path": "pkg/db/alert", "type": "go-lib"}],
  "verification_setup": {
    "profile": "the stack/compose-profile/seed that renders this surface with realistic data",
    "fixtures": ["the specific records/rows the surface needs to display, and how to create them"],
    "capable_of_rendering": "the surface this stack can actually show (not a thin/empty default)"
  }
}
```

- `status`: `"done"` when the plan artifacts are written and ready for review — including when
  they were already there and you left them standing — or `"blocked"` if you could not produce
  a plan at all.
- `summary`: a one-line description of the plan (or the blocker).
- the remaining keys are the plan's structure, described under "The plan's structure" above.
  This is the only place the workflow learns which services the story changes, and it drives
  the implementer's per-service iteration: a frontend-only story lists only its web service,
  so the implementer never builds a backend one. A story that changes exactly one service in
  one repo may return `services: []` — the implementer then gets one repo-root layer.
