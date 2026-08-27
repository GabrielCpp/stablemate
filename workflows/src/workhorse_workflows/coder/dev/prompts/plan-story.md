IMPORTANT: The plan MUST NOT include code snippets, patches, line-by-line edits, or direct instructions to modify source files during the planning stage. Plans may identify expected files, affected functions or contracts, dependencies, risks, and verification steps so the implementation agent can work safely. Implementation happens separately after plan review.

# Planning

## Provided Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`

Plan **only** the story at the story path above. Do NOT search the repository, git history, or branch state to guess which story to plan, and do NOT substitute a different story. If the story path above is blank or the file does not exist, return `status: "blocked"` (Machine-Readable Result below) with a summary saying the workflow did not provide a usable story path — that hands it to the operator. Do not pick a story yourself.

## Pre-Planning (REQUIRED — do first)

### Read the standards the design turns on

Read the standards that bear on the decisions this story asks you to make — the layer it
touches, and within that layer the files whose rules the design turns on. Not the whole set:
reading one that changes no decision buys nothing. A handful is normal; a dozen means you are
reading the layer rather than planning the story. What this repo installs advertises itself
through the repo's own instruction mechanism and each skill's frontmatter; load from there.

Rules:

- One layer → that layer's standards plus shared repo/docs guidance, nothing else.
- Multiple layers → the ones each layer's decisions turn on, and split the plan by layer.
- Layer unclear → inspect the story and code paths first; if still unclear, stop and ask before planning.

### When the plan is already there

Check the spec directory before you write anything. A story is re-selected by the queue
until it reaches `QA passed`, so one that was interrupted after planning — or that is coming
back for documentation or QA — arrives here with `plan.md` (and often a
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
6. Do not start implementation. The workflow gates this plan and runs the implementer itself.

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
`type:` that makes the doc an OKF Concept (`spec.<stem>`: `plan.md` → `spec.plan`, `qa.md` →
`spec.qa`), creates the file if it is absent, and leaves an already-typed doc untouched. Then
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
  - `type`: the technology, using the key **this repo's** instructions/prompts gate on — take it from the repo's own `agents.yml` and the short-names of the skills it installs, not from a taxonomy you remember. `docs` is the type for documentation-only services in every repo.
  - `plan_file`: the plan file for this service (relative to spec dir)
  - `new_service`: `true` only when the directory does not exist yet and this story scaffolds it
- `implementation_order`: ordered list of `repo::path` keys specifying build order. Dependencies first: whatever defines a shared contract before whatever implements it, and whatever implements it before whatever consumes it. Every entry must name a service you declared.
- `shared_packages`: non-service directories that need changes (libs, shared code). These are implemented as part of their dependent service's pass.
- `verification_setup`: the story's **`## Verification setup`** in machine-readable form.
- `fixtures`: the arrangements QA must stand up before it can observe anything, one entry
  each with a `name` and what it `provides`. A fixture is held to the same bar as a test:
  it is named, declared, and shared — the app's own integration tests and the QA lane run
  the same one. Name what the story's scenarios need to already be true; do not describe
  how to build it here, and do not invent an arrangement the story does not need.

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
- `plan.md` — Complete plan for the service

For multi-service stories, use per-service plan files:
- `plan.md` — Root plan: high-level design, cross-service contracts, implementation order
- Per-service files named in each service's `plan_file` field (e.g., `plan-api-service-alert.md`, `plan-web-app-discover.md`)

### Cross-Service Coordination

**Multi-service stories only** — a single-service story skips straight to `### Approach`.

The root `plan.md` carries what the per-service files cannot: the order and the contracts
between them.

**Implementation order.** Derive it from this story's own dependencies, not from a fixed
layer ranking: whatever both sides agree on (schemas, API definitions, generated-code
inputs) first, then the service that owns the contract, then the infrastructure those
contracts provision for, then the consumers — client-side last, against a backend that
already answers. State it as `repo::path` keys in `implementation_order`. Each service is
implemented independently in its own repo CWD.

**Integration contracts.** For each boundary the story crosses: the exact endpoint or event
(path, method, type), the request/response shape (field names, types, required vs optional),
the error cases the consumer must handle, the flag gating it if there is one, and — when a
shared contract changes — which consumers have to regenerate.

### Approach

Two to five sentences: the story's objective, the design decision you made, and — where the
tree already has something to say about it — what exists today that this builds on or
changes. Cite the rule behind each decision by the skill that carries it rather than
restating the rule; the reviewer loads those files itself.

This is the one section read by a reviewer who does not share your session. Everything below
it is read either by a node that does share it or by a parser, so write those for use, not
for an amnesiac reader.

### Changes

The units to build, one line each, in the order they should be built. Give each the
behavioral responsibility and the standard it follows — not the code:

- `internal/<domain>/service.go` — mint and resolve codes; validation lives here, not in the
  controller (per the architecture skill).
- `internal/<domain>/repository.go` — the port and its adapter; the port takes no HTTP type.
- `<the shared contract file>` + regenerate — the command and the generated output path are
  in that layer's instruction files, never in this prompt.

Name the smallest directory or package when the exact file is not knowable yet, and say why.
Generated artifacts and migrations get their own lines, each with its generation command and
the input that changes. Omit anything the story does not change.

### Stages

**Write this section when the story is big enough to build in more than one sitting** — the
same phases an interactive session falls into by itself: make the contract exist, then make
it real, then wire the surface to it. A small story is one stage and does not need the
heading; do not manufacture phases to fill it.

One `**Stage N — <name>**` line per phase, each with the units from **Changes** it covers and
**how the implementer proves that stage works before moving on** — the command to run, the
endpoint to hit, the screen to load. A stage nobody can check is not a stage, it is a pause.

The implementer builds its todo list from these, so they are the story's real order of work:

- **Stage 1 — the port and its contract.** `internal/<domain>/repository.go` +
  `service.go`. Proven by the package's unit tests: `<the layer's test command>`.
- **Stage 2 — the HTTP surface.** the controller + the regenerated client. Proven by
  booting the API and posting the story's request once.

### Testability (required)

**Every plan says how the work it describes can be tested, and this is not optional.** The
implementer is handed this plan verbatim and writes the tests from it, so a plan that
describes only what to build hands the test suite to guesswork.

Concretely: name the seam each unit in **Changes** is tested through (the port to fake, the
fixture to record, the route to drive), and say what has to exist before that test can run —
a seeded row, a migration, a captured payload, a running emulator. Where the honest answer is
that a unit cannot be tested as designed, that is a design finding: say so here and change
the design rather than planning untestable code.

**Test Scenarios** below is the parsed contract; this section is how the implementer gets
there.

### Blast Radius

**Write this section only when the story changes a symbol, contract, validation rule,
generated model or persistence shape that already has callers.** Greenfield and purely
additive stories omit it entirely — do not write it to say "none".

Search for the affected names first. Then for each: what it does today, who calls it, what it
does after this story, and what must be re-verified. Follow a chain only as far as an entry
point, screen, handler or external contract.

Stop and reconsider if you are removing something with three or more callers, changing shared
validation without checking them all, or breaking a contract an external consumer expects.

### Test Scenarios

This section is the **contract between the acceptance criteria and the test suite**, and it
is parsed. `Level: QA-only` scenarios are handed to the QA plan as its obligations — a
scenario nobody writes a test for and nobody hands to QA is covered by nothing in the run.

**The shape is load-bearing.** Each scenario is its own `###` heading with a title after the
colon, and its fields are bullets. A numbered list does not parse and yields no scenarios at
all:

```markdown
### Scenario 1: rejects a relative destination

**Given** a request whose `url` is relative, **when** it is posted to `/links`,
**should** return `400` with a JSON `title` naming the destination as unacceptable.

- **AC**: 2
- **Level**: endpoint
```

- **AC** — the criterion it covers, by number or exact quote. Every AC needs at least one
  scenario; an edge case no AC names is `AC: none (edge case)`.
- **Level** — where the test lives:
  - `unit` — a pure function or class, no wiring.
  - `component` — the primary target: a component/handler/service through its public surface,
    real wiring, faked leaves.
  - `endpoint` — an HTTP surface through the router.
  - `integration` — only where the story warrants it (a contract crossing services, a
    persistence shape); it must be reachable from this layer's test command.
  - `QA-only` — verifiable only by a live walkthrough (visual layout, cross-app flow). No
    test is written; QA covers it. Use it sparingly and say why — before reaching for it,
    check whether a `component` scenario could cover the same AC.

Cover happy paths, error cases and edge cases. If the story changes no observable behavior at
all — a pure refactor, a rename, a dependency bump — say so in one line instead of a scenario
list; the existing suite is the safety net.

### Verification Commands

Copy the exact commands from the layer's instruction files → **"Verification Commands"**
section where present. Do not invent commands when the instruction files define them; if one
is missing, say so and choose the narrowest standard command for that service.

For each layer involved:

```
## [layer-name] Verification

# Code generation (if applicable — "None" if not)
# Tests
# Lint / Format
# Build
# Local run (smoke) — how to bring this layer up locally and exercise the story's path,
#   with the observable success signal (endpoint returns a real status, route renders the
#   feature, screen loads) so the implementer can confirm it runs. "None" if docs-only.
```

For multi-layer stories list each layer separately so the implementer can run them
independently. The **Local run (smoke)** block is mandatory for every layer with a runnable
surface — the implementer is required to run the touched layers locally, so the plan must say
exactly how.

---

## Before You Return

- [ ] Every acceptance criterion is covered by at least one scenario, and every scenario is a
      `### Scenario N: <title>` heading with `- **AC**:` and `- **Level**:` bullets.
- [ ] Verification commands are copied from each layer's instruction files, not invented, and
      every runnable layer has a Local run (smoke) with its success signal.
- [ ] `services` lists every service the story changes and nothing it does not; each path
      exists and carries the marker file its `type` implies.
- [ ] Multi-service stories document implementation order and the integration contract.
- [ ] The plan says how the work is tested — the seam per unit, and what has to exist first.
- [ ] A story too big for one sitting carries **Stages**, each with the check that closes it.

❌ Don't plan for a layer this repo does not have — what it installs is the whole set.
❌ Don't forget code generation — stale generated files cause silent failures.

## Commit Trailers

Every commit you write carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_slug') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

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
      "plan_file": "plan-api-service-alert.md"
    },
    {
      "repo": "web-app",
      "path": "packages/discover",
      "type": "web-app",
      "plan_file": "plan-web-app-discover.md"
    }
  ],
  "implementation_order": ["api-service::cmd/alert", "web-app::packages/discover"],
  "shared_packages": [{"repo": "api-service", "path": "pkg/db/alert", "type": "go-lib"}],
  "verification_setup": {
    "profile": "the stack/compose-profile/seed that renders this surface with realistic data",
    "capable_of_rendering": "the surface this stack can actually show (not a thin/empty default)"
  },
  "fixtures": [
    {"name": "signed_in_adjuster", "provides": "a session for an adjuster who may decide claims"}
  ]
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
