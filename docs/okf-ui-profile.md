# OKF UI profile — describing UI & concepts as a loose knowledge graph

> **Status:** approved & shipped. This document specifies a *profile* of the ostler
> Open Knowledge Format (OKF) for describing user interfaces and the concepts they
> serve. The tooling is implemented (see `docs/ostler-okf-ui-support.md`) and the
> `stablemate-ostler` / `stablemate-documentation` / `stablemate-okf-modeling` skills
> teach it. Where this draft and the shipped tooling differ, the shipped behavior wins
> and is called out inline (see §2.4 and §6 on gating vs "warns, never blocks").

## 1. Why this profile exists

A UI feature today is written as free prose (see `docs/features/groom/*.md`).
Prose is great for *why*, but a tool can't parse it: you can't enumerate a screen's
components, follow which interaction fires on a click, tell whether a documented
selector still exists in the code, or later derive a test from a described click.

This profile adds just enough **structure** to make UI knowledge *navigable* and
*machine-readable* — while staying as **loose** as OKF itself. It does **not**
replace how you write; it gives eleven node types (see §3) and a couple of
conventions you reach for when a structured hook is useful.

### Goal — the docs are the source spec

**A node is authored to be complete enough to regenerate the code.** A competent agent
(or human) reading only the doc — no source — should be able to reimplement
**behavior-equivalent** code: every field with its type/default/required, every flag and
argument, every effect and guard, the algorithm as ordered steps, the errors/exit codes,
and (for visual nodes) the DOM/props/state contract. `code:` / `verify:` still anchor the
*current* implementation, but they **point at** the code the spec describes — they are not
a substitute for describing it. See §8, "Spec completeness," for the per-type bar. (This is
a deliberately raised bar: the original draft listed code-generation as a non-goal.)

### Non-goals (deliberately out of scope)

- Not a JSON-Schema validator. The *format* stays loose — the linter checks conformance +
  link integrity, not completeness. Spec-completeness is a **review** standard (the author/
  coder doc gates and the story auditor), not a `doctor` gate, because "is this enough to
  regenerate the code?" is a judgment a linter can't make.
- Not a general prose dumping ground — a node is a *spec*, not an essay. Keep the *why* to a
  sentence and let the structured bullets carry the contract.

## 2. Design principles

1. **Loose format, high bar.** OKF's only hard rule is a non-empty `type`; a bullet-less
   node is still *valid* OKF. But the *authoring standard* is spec-completeness (§8): a
   sparse node is valid yet **below bar**. Loose is what the tool enforces; complete is what
   you write.
2. **The graph is the book, not the changelog.** OKF is the **full, always-current
   specification** of the system — complete enough to regenerate the code (§8). A user
   **story is a delta**: it changes the world, and its documentation step **merges that
   delta into the book** so the affected nodes describe the *new current reality* in full.
   Never append "this story added X" notes; edit the node so a reader who never saw the
   story gets the complete, correct spec. The story lives in `docs/epics/**`; the book lives
   in `docs/features/**`.
3. **Spec, not implementation. OKF says *what*; skills say *how*.** A node specifies
   **behavior and contract** — fields, types, defaults, effects, guards, states, errors,
   DOM/props — everything you'd need to know *what* the code must do. It does **not** command
   *how* to build it: coding patterns, idioms, library choices, class/file structure, and
   stack conventions are owned by the **skill files** (`go`, `react-router`, `python-testing`,
   …), not the book. So "regenerate the code" = **OKF (the spec) + the skills (the patterns)**
   — together, not OKF alone. `code:` / `verify:` anchor the *current* implementation, but the
   node never prescribes a technique; if a sentence reads like a coding instruction, it
   belongs in a skill.
4. **Neutral — meaning lives in prose.** The format never bakes in a
   relationship *verb* (no `realizes`, `serves`, `owns`). Links are plain
   links; what a link *means* is whatever the surrounding sentence says.
5. **Keep OKF organization.** Nodes are ordinary OKF Concepts: markdown files under
   `docs/`, identity = path, minimal frontmatter (`type` / `slug` / `title`).
6. **Ostler parses, navigates, *and gates on shape*.** Ostler recognizes the types,
   resolves the links, and lets you `list` / `search` / `trace` the graph. Structure
   *inside* a profile doc is a hard `doctor` gate — but every rule has a deterministic
   mechanical remedy (`ostler fmt` or `ostler scaffold`), so conformance is always
   reachable, never a judgment call. (This tightened from the draft's original
   "warns, never blocks" once the tooling shipped — see §6.)

## 3. Node types

A **fixed vocabulary**, organized by **role** so one graph spans GUI, CLI, HTTP/WS
servers, and data formats. Ostler recognizes each the light way it already handles
`spec.*` — recognized, listed, traversable, no bundled JSON Schema, no strict body
grammar.

| Role | GUI | CLI | HTTP / WS | shared |
|---|---|---|---|---|
| **surface** (a thing you interact with) | `screen` | `cli` | `server` | |
| **element** (a part of a surface) | `component` | `command` | `endpoint` | |
| **behavior** (one event *or* one call) | `interaction` | `invocation` | `invocation` | |
| **journey** (an ordered multi-step path) | | | | `flow` |
| **noun** (domain *or* code) | | | | `concept` |
| **artifact / data shape** | | | | `format` |

- `concept` — a durable noun the system is *about*. Two flavors, same type: a
  **domain concept** (Worker, Diff, Gate) or a **code concept** — a function / module /
  class (`load_workflow`, `WorkflowContext`) that carries a `code:` bullet.
- `screen` / `cli` / `server` — a **surface**: a composed GUI, a command-line app, or
  an HTTP/WebSocket server.
- `component` / `command` / `endpoint` — an **element** of a surface: a UI element, a
  (sub)command, or a route / WS channel.
- `interaction` — a **GUI event** behavior: a human manipulating a component (click,
  hover, keyboard, drag, drop, submit).
- `invocation` — a **call/message** behavior: running a `command`, hitting an
  `endpoint`, or a **websocket message** (`ws-send` / `ws-push`). The non-GUI twin of
  `interaction`.
- `flow` — an ordered multi-step journey (its steps may mix `interaction`s and
  `invocation`s).
- `format` — the shape of a file / artifact: a workflow file, a config, or an
  **OpenAPI** document (the machine source for an HTTP surface).

**Operational profile (extension).** Three further built-in types model *how the system
is run and observed* — `runbook` and `environment` (file-level) and `step` (section-level,
under a runbook's `## Steps`). They reuse the surface types above via a runbook's
`surfaces:` link; there is no new "surface" type. The full spec — driver/kind vocabularies,
the spec-completeness bar, and how okf-builder generates and consumes them — lives in
[okf-runbook.md](okf-runbook.md); their optional bullets are summarized below.

### Optional structured bullets (conventions, never required)

When a machine-readable hook helps, add a plain bullet. All optional.

**`screen`**
- `route:` — the landed URL path, captured live during a walkthrough.
- `screenshot:` — a full-page capture of the screen in a named state, living **in the
  book** at `docs/features/<service>/gui/screenshots/<screen-slug>-<state>.png`
  (repo-relative path; one bullet per captured state). Evidence, not a code ref —
  never in `code:`/`verify:`.
- `vet:` — a link to the screen's visual-registration Concept,
  `docs/specs/<screen-slug>/vet.md` (`type: spec.vet`), written by `ostler vet --write`.

**`component`**
- `selector:` — the stable DOM hook (`#detail`, `.tree-file`, `[data-worker-id]`).
- `screenshot:` — the component's own visual snippet, cropped by `ostler vet` from the
  screen capture when the component visually registers
  (`docs/specs/<screen-slug>/vet/<state>-<component>.png`).
- `code:` — where it's rendered, `path::symbol` (`groom/groom/render.py::_inbox_row`).
- `parent:` — a link to its containing component/screen (see §5).
- `extends:` — a link to a shared/library component it reuses (see §5).
- `states:` — comma-separated visual states (`active, collapsed, default`).

**`interaction`** (GUI event)
- `on:` — a link to the `component` the interaction fires on.
- `trigger:` — the GUI event. Suggested vocabulary (open, not enforced):
  `click`, `dblclick`, `hover`, `focus`, `keydown:<key>` (e.g. `keydown:⌘K`,
  `keydown:j`), `drag`, `drop`, `submit`.
- `when:` — a guard/precondition in plain words (`mode == changes`).
- `does:` — the effect(s) as a **nested bullet list**, one effect per child bullet.
  (ostler parses nested bullets today — `markdown.py::_parse_bullets` builds a
  `Bullet.children` tree — so a reader just walks the `does:` bullet's children.) A
  single trivial effect may stay one-line. Effect kinds: `state:` (DOM/CSS state),
  `dom:` (render/swap), `net:<METHOD path>` (a request), `emit:<event>` (a custom
  event), `nav:` (navigation).
- `code:` — the handler, `path::symbol` or a `file` region.
- `verify:` — the test that proves it (`test_render.py::test_changes_...`).

**`invocation`** (a call / message — the non-GUI twin of `interaction`)
- `on:` — a link to the `command` or `endpoint` invoked.
- `trigger:` — how it's called: `run` (a CLI command), the HTTP method (`GET` / `POST`
  / …), or `ws-send:<msg>` / `ws-push:<event>` (a websocket message).
- `when:` — a guard/precondition; `does:` — effect(s), same nested-bullet form and
  effect kinds as `interaction` (`state:` / `dom:` / `net:` / `emit:` / `nav:`), plus
  `emits:` / `consumes:` for messages.
- `code:` — the handler `path::symbol`; `verify:` — the test that proves it.

**`flow`**
- `steps:` — an ordered list; each step links to an `interaction` / `invocation` /
  `command` / `endpoint` / `screen` and adds a short line of prose. This ordering *is*
  the journey.
- `start:` / `end:` — optional entry/exit state or precondition.
- `verify:` — the end-to-end test or journey id that walks the whole path (the
  natural place a Playwright scenario is derived from later).

**`cli` / `server` (surfaces)**
- `binary:` (cli) or `code:` — the entry point (`workhorse`; `app.py::create_app`).
- `openapi:` (server) — link to the OpenAPI `format` node, when the server publishes
  one (omit when it opts out — e.g. groom's htmx routes set `include_in_schema=False`).

**`command`**
- `usage:` — the invocation line (`workhorse run <workflow> [<flow>] [--params JSON]`).
- `parent:` — a link to the parent command (a subcommand's owner).
- `flags:` / `args:` — the options and positional arguments. Prefer the **nested form**:
  one child bullet per flag / positional, each being the token in backticks, an em-dash,
  and a sentence on **what it does and in which context it applies** (fresh start vs
  resume, which mode, its default), with **inline links** to the nodes it touches — a
  `format` it consumes, a `concept` it selects, another command. A short, self-evident
  option set may stay a one-line comma list, but reach for the nested form the moment a
  flag needs explaining (see "Documenting flags & arguments" below).
- `does:` — the effect(s), nested-bullet form; `code:` — the handler `path::symbol`.
- `detail:` — a link to a **detailed own-file version** of the command (see §4).

**`endpoint`**
- `method:` + `path:` (HTTP, `GET /worker/{id}`) *or* `channel:` + `message:` (WS,
  `/ws` · `cmd=answer`).
- `code:` — the handler `path::symbol`; `openapi:` — the operationId in the server's
  OpenAPI `format` node; `does:` — the effect; `emits:` / `consumes:` for WS messages.
- `detail:` — a link to a detailed own-file version.

**`format`**
- `file:` — the glob it applies to (`**/workflow.yaml`); `code:` — the loader/model
  (`graph/loader.py::load_workflow`) or the OpenAPI doc path. Fields as `### <key>`
  sections.

**`runbook`** (operational profile — [okf-runbook.md §4.1](okf-runbook.md))
- `driver:` — the observe/drive mechanism: `web` / `mobile` / `http` / `cli` / `artifact`
  / `iac` / `none`. **Required** — it selects which walkthrough consumer boots this recipe.
- `environment:` — link to the `environment` node this boots (default: the repo's `local`).
- `cli:` — link to the dev-CLI `cli` node this runbook drives with, when one exists.
- `surfaces:` — links to the `screen` / `server` / `cli` / `format` nodes it exposes.
- `code:` — the launch entry point (`path::symbol`), when there is one.
- Required section: `## Steps` — the ordered `### <id>` `step` nodes.

**`environment`** ([okf-runbook.md §4.2](okf-runbook.md))
- `selector:` — how this environment is chosen (a stage env-var value, an env-file).
- `services:` — nested; one child per service giving its URL/host **in this environment**
  (ports/hosts are env-scoped; a child may carry a host-rewrite note with its reason).
- `backing:` — nested; backing projects, databases, buckets, emulators it uses.
- `local-only:` — `true` when tooling must refuse to target it without an explicit override.

**`step`** (a `### id` under a runbook's `## Steps` — [okf-runbook.md §4.3](okf-runbook.md))
- `kind:` — **required**: `prepare` / `service` / `seed` / `run` / `health` / `verify` /
  `drive`.
- `run:` — the exact bounded command; `working-directory:` — cwd when not the repo root;
  `env:` — nested env-var wiring the step needs.
- `health:` — for `service`/`health` steps, the **real** readiness signal (a URL to poll, a
  command, `port-bound` / `log:<pattern>` / `ws:<frame>`) — never a shell served with the
  backend down.
- `produces:` — for `run` steps, the output artifact path(s)/glob(s) — the observable surface.
- `verify:` — for `run`/`verify` steps, how success is confirmed (a golden compare, a
  deterministic re-run, an assertion string, a test id).
- `optional:` — `true` for best-effort steps; `depends-on:` — ordering hint (default:
  document order); `provenance:` — `derived` (build pass) or `verified` (walkthrough §7).

### Visual evidence & registration (walkthrough outputs)

The live walkthrough proves each screen doc against the running app and leaves committed
visual evidence in two places:

- **Screen captures** — full-page PNGs under `docs/features/<service>/gui/screenshots/`,
  named `<screen-slug>-<state>.png` and referenced by `screenshot:` bullets on the screen
  and flow docs. Captured at top scroll so document and screenshot coordinates agree.
- **Per-component registration** — `ostler vet` cross-checks a manifest derived from the
  screen doc's component `selector:` bullets against its own CDP scan of the live DOM.
  Its artifacts live under `docs/specs/<screen-slug>/vet/`: the authored
  `<state>-manifest.json`, the scanned `<state>-regions.json`, the `<state>-report.json`
  (matched / missing / unexpected / unlabeled), and one crop PNG per **matched**
  documented component (`<state>-<component>.png`, the component's `screenshot:` bullet
  target). The accumulating per-state summary is the `spec.vet` Concept at
  `docs/specs/<screen-slug>/vet.md`, linked from the screen via its `vet:` bullet.
  A `missing` finding means a documented component did not render; `unexpected` /
  `unlabeled` means the page shows UI the book doesn't know — both are drift the
  walkthrough heals.

### Documenting flags & arguments (context + pointers)

A CLI's real knowledge is *what each flag and argument does and when you reach for it* —
so document them individually, not as a bare token list. Under `flags:` / `args:`, write a
**nested bullet list**: each child names the token, says what it does and the context it
applies in, and **links to the other nodes in the tree it touches**. ostler parses the
nested bullets (the same mechanism as `does:`) and resolves every inline link, so the
pointers are checked, not decorative.

```markdown
### run
- usage: `workhorse run <workflow> [<flow>] [--params JSON]`  (the default command)
- args:
  - `<workflow>` — the named [workflow](concepts/workflow.md) to run (resolved from the
    prompt library), or a path via `--workflow`. Required.
  - `<flow>` — optional: run one named [flow](workflow-format.md#flows) standalone, as a
    re-entry point, instead of the whole graph.
- flags:
  - `--params <json>` / `--params-file <path>` — override the workflow's
    [vars](workflow-format.md#vars) on a *fresh start*; ignored on resume.
  - `--cli <name>` — pick the agent harness for the run: selects an
    [AgentBackend](concepts/agent-backend.md) via [get_backend](concepts/get-backend.md);
    `<name>` ∈ `claude` (default) · `codex` · `copilot` · `aider` · `opencode`.
  - `--resume-run <id>` / `--resume-latest` — resume a checkpointed run instead of the
    default auto-resume-in-place.
- code: `workhorse/workhorse/main.py::_run_run`
```

The same nesting fits an `endpoint`'s query/body parameters and any bullet whose items each
need their own note.

### Discoverability — no orphans, link from the surface root

Everything in a service subtree must be **reachable from the surface root** (the
`screen` / `cli` / `server` index doc) by following links — a reader or `ostler trace`
should walk from the root to every node. Two rules keep it so:

- **Link outward.** Every node points to the nodes it relates to: a `format` links the
  command/endpoint that consumes it *and* the `concept` it models; a `concept` links its
  neighbors; a `command` links (via its flags/args) the concepts and formats it drives. A
  node no other node links to is an **orphan** — link it from the most relevant place (the
  surface index, the command that uses it, the abstraction it `extends:`).
- **Don't bury structural pointers in prose.** If a flag selects a `concept`, put that link
  in the flag's own bullet — not only in a paragraph below — so the pointer is part of the
  node's structure and `ostler trace` surfaces it. The surface index itself should link its
  key concepts/formats in its own body (its own region), so a trace from the root reaches
  them directly, not only through a section node.
- **A file node's graph links are its opening region** (before the first `##` subheading) —
  that is what `ostler trace` walks and the linter checks. State a node's key relations there;
  links that live only in a `## Details`-style subsection render for a human but are invisible
  to the graph. And a `concept` should be a real explanation of its *parts* with a pointer to
  the more specific node for each — not a lone `code:` stub.

> A `flow` node captures a journey — a GUI path *or* a workhorse workflow-flow told
> as steps. It is distinct from the `type: flow` **key inside a workflow file**
> (data described by a `format` node), even though both mean "a multi-step sequence".

## 4. Organization — file vs section (author's choice)

A node may be **its own file** *or* a **`### <id>` section** inside a larger node's
file, *or both* — a brief section that links to a detailed own-file version:

- **Own file** when the node is reused or referenced by others — every `concept`
  gets one. Its path is its identity; others link to it.
- **A section** when the node lives inside a larger surface or library doc — a
  one-off `component` / `command` / `endpoint` / `interaction` lives as a `### id`
  under a `## Components` / `## Commands` / `## Endpoints` / `## Interactions`
  heading, reachable by anchor. A **shared/library `component`** is a section too:
  it lives under `## Components` in the GUI context's component-library doc (e.g.
  `gui/components/design-system.md#tree-node`), so others `extends:` it by anchor.
- **Section + detail file (hub + detail).** A surface (a `cli`, a `server`) is an
  **index**: each element is a brief `### id` section that `detail:`-links to its full
  own-file node (`[run](commands/run.md)`). The index gives the at-a-glance surface;
  the detail file carries the complete bullets, prose, and — crucially — links to the
  **code concepts** the element depends on (§ code concepts, §7.10). Use it whenever
  a command/endpoint has more to say than one section should hold.

A section node's type is **implied by its containing `## <Section>` heading** — no
per-heading marker needed:

| Section heading | its `### id` children are… |
|---|---|
| `## Components` | `component` |
| `## Commands` | `command` |
| `## Endpoints` | `endpoint` |
| `## Interactions` | `interaction` (GUI events) |
| `## Invocations` | `invocation` (calls / messages) |
| `## Steps` (in a `runbook`) | `step` (operational profile — [okf-runbook.md](okf-runbook.md)) |
| `## Fields` (in a `format`) | fields (not nodes) |

The file's own `type:` frontmatter sets the whole-file surface node
(`screen` / `cli` / `format` / `flow` / `concept`). An author *may* still add an
explicit `<!-- type: … -->` comment for an unusual grouping, but it is never
required — the section heading is the source of truth.

**Where nodes live — per service, then by context (this repo is multi-service).**
Each service owns its subtree under `docs/features/<service>/`, so groom / workhorse
/ farrier stay self-contained. Within a service, group **by surface context** —
`gui/` (screens + their components), `http/` (the server + endpoints), `cli/`
(commands) — with a matching **type folder** underneath (`gui/screens/`,
`gui/components/`). Context-neutral nodes stay at the service root: `concepts/`
(nouns) and `flows/` (journeys). Flows sit at the root on purpose — a journey often
crosses contexts (the answer-a-gate flow in §7.5 fires GUI interactions *and* a
server invocation), so a single root `flows/` gives every journey one home and avoids
arbitrating which context a cross-context flow "belongs" to. A flow (or concept)
that is genuinely confined to one context *may* instead live under that context's
folder (`gui/flows/…`) — author's choice, same as file-vs-section.

Split into context folders **only when a service genuinely spans more than one
context.** groom is GUI + HTTP, so it splits; workhorse is CLI-only, so it stays
flat. (These folders are for humans — ostler resolves `type` from frontmatter and
globs `features/**/*.md` recursively, so `ostler list --type screen` finds a screen
wherever it sits. Folder-by-context is navigation ergonomics, not semantics; don't
over-fold a single-context service.)

```
docs/features/
  groom/                          # GUI + HTTP → split by context
    gui/
      screens/
        groom.md                  # screen — the shell
        changes-view.md           # screen
        operator-inbox.md         # screen
      components/
        design-system.md          # shared components (## Components → ### tree-node)
    http/
      server.md                   # server (index of endpoints + /ws)
    concepts/diff.md              # concept (domain) — context-neutral, at root
    flows/answer-a-gate.md        # flow — may cross contexts, at root
  workhorse/                      # CLI-only → single context, stays flat
    workhorse.md                  # cli (index of commands, each detail:-linked)
    commands/run.md               # command (detailed own-file version)
    workflow-format.md            # format
    concepts/workflow.md          # concept (domain)
    concepts/load-workflow.md     # concept (code: graph/loader.py::load_workflow)
  farrier/
    farrier.md                    # cli
```

- `screen`/`cli`/`server` surfaces and their section-level element nodes: the surface
  file in its context folder (`gui/screens/`, `http/`); detailed elements in a
  `commands/` / `endpoints/` subdir, `detail:`-linked from the index.
- shared/library `component`s: a component-library doc in the GUI context
  (`gui/components/design-system.md`), holding `### id` sections under `## Components`.
- `concept`s: `docs/features/<service>/concepts/`, one file each — domain *and* code
  concepts, scoped to the service that owns them.

**Cross-service concepts (loose rule):** when a noun is genuinely shared (e.g.
`Repository`, `Worker` appear in both groom and workhorse), the **owning** service
defines it once and the other **path-links** to it
(`[Worker](../../workhorse/concepts/worker.md)`) — no shared global namespace, no
duplication forced. Which service "owns" it is the author's call.

## 5. References & relations — standard markdown path links

Links are ordinary OKF path links — **not** `[[wikilinks]]` (those aren't standard
markdown and don't resolve on GitHub or in ostler's parser). Ostler already
extracts, resolves, validates, and rewrites these.

- **Whole-file node:** `[diff](concepts/diff.md)`
- **Section node:** `[changes-file-row](changes-view.md#changes-file-row)`
- **Same-file section:** `[changes-file-row](#changes-file-row)`

A bare link is **neutral** — no relationship verb. Meaning is the prose beside it.

Two *optional, unenforced* conventions layer a light relationship name onto a link:

- `parent:` — **part-of / containment.** Works within a file or across files:
  `- parent: [groom shell](../screens/groom.md#main-panel)`.
- `extends:` — **is-a / reuse.** A local node inherits a shared node's fields and
  overrides/adds only what's local:
  `- extends: [tree-node](../components/design-system.md#tree-node)`.

Everything else — "presents", "is about", "part of the review loop" — stays prose
with a plain inline link. Don't invent bullet keys for it.

## 6. How ostler treats a profile document

> **Shipped behavior (updates the draft).** The draft below proposed "warns, never
> blocks." As implemented (`docs/ostler-okf-ui-support.md`), UI conformance is a
> **mandatory `doctor` gate** — every rule is `error`-severity — because each rule has
> a deterministic remedy, so a workflow can gate on `ostler doctor` and always
> converge. The relaxed clause is superseded by the rule table here.

- **Recognizes** the eleven `type:` values (§3) as first-class node types — loaded,
  and (for `### id` sections) modeled by the containing heading.
- **Navigates** via existing verbs: `ostler list --type component`,
  `ostler search <q>`, `ostler trace <slug>` (walks the path links, flagging
  dangling/missing-anchor).
- **Authors & canonicalizes:** `ostler scaffold <type> <name>` places a new node in
  its canonical path/heading with bullet stubs; `ostler fmt` canonicalizes frontmatter
  key order, bullet order/spacing, `does:` nesting, heading casing, and `### id`
  anchors (never touching prose).
- **Gates (all `error`, each with a mechanical fix):** `unknown-type`,
  `bad-heading-type` (→ `fmt`), `missing-required-section` / `missing-required-bullet`
  (→ `scaffold`; the bullet rule checks *key* presence, not value, so stubs clear it),
  `unresolved-relation` / `dangling-link` / `missing-anchor` (→ fix the link). **`code:`
  and `verify:` are code refs grounded at a later QA gate — deliberately *not*
  link-checked by `doctor`.**

---

## 7. Worked examples (real groom)

The examples below all belong to one service, **groom** (a GUI + HTTP/WS service).
Because it spans two contexts, its subtree splits into `gui/` and `http/`, with
context-neutral `concepts/` and `flows/` at the root. Here is how the §7.x nodes sit
in the filesystem:

```
docs/features/
  groom/
    gui/                             # the GUI context
      screens/
        groom.md                     # screen  — the shell (§7.1)
        changes-view.md              # screen  — Changes view (§7.3)
        operator-inbox.md            # screen  — the inbox (referenced by §7.5)
      components/
        design-system.md             # component library — holds `### tree-node` (§7.2)
    http/                            # the HTTP/WS context
      server.md                      # server  — Litestar routes + /ws (§7.9)
    concepts/                        # context-neutral nouns
      diff.md                        # concept — Diff, a domain noun (§7.4)
      worker.md                      # concept — Worker (referenced)
      gate.md                        # concept — Gate (referenced)
      repository.md                  # concept — Repository (referenced)
    flows/                           # journeys (may cross contexts)
      answer-a-gate.md               # flow    — the operator's core loop (§7.5)
```

A `screen`/`server` surface and its one-off elements live in a single file (its
`### id` sections); reused nouns (`concept`s) and journeys (`flow`s) each get their
own file so others can path-link them. The shared `tree-node` `component` is a
section under `## Components` in `gui/components/design-system.md`, referenced by
anchor. A single-context service (e.g. CLI-only workhorse, §7.6) skips the context
folders and stays flat.

### 7.1 A `screen` with a slot — the groom shell

`docs/features/groom/gui/screens/groom.md` (the shell/overview) as a `screen`. It
owns the top-level layout components; other screens mount into its `main-panel`.

```markdown
---
type: screen
slug: groom-shell
title: groom shell — the IDE layout
---
# groom shell

The VS Code-style shell: an activity bar switches modes; the picker lists the
fleet; the detail pane shows the selected worker or the active mode. Realtime
frames arrive over `/ws` and swap regions out-of-band.

## Components

### activitybar
- selector: `#activitybar`
- code: `groom/groom/templates/dashboard.html`
- states: (per-mode active button)

The mode switcher (Inbox / Fleet / Changes / Settings). Each `.act-btn[data-mode]`
click calls `setMode`.

### main-panel
- selector: `#detail`
- code: `groom/groom/render.py::render_worker_detail`

The right-hand surface. Other screens (e.g. [Changes](changes-view.md)) render into
it. Pulled on demand via `GET /worker/{id}` so a live push never clobbers a
half-typed answer.

## Interactions

### switch-mode
- on: [activitybar](#activitybar)
- trigger: click
- does:
  - state: toggle `.app[data-mode]`
  - dom: for `changes`, `GET /changes` into `#detail`
- code: `groom/groom/templates/dashboard.html::setMode`
```

### 7.2 A shared/library `component` — `tree-node`

A standard row reused by more than one screen. It lives as a `### tree-node`
section under `## Components` in the GUI context's component-library doc
(`gui/components/design-system.md`), so others `extends:` it by anchor. An excerpt
of that file:

```markdown
---
type: feature
slug: design-system
title: groom — IDE console design system
---
# groom — IDE console design system

...

## Components

### tree-node
- selector: `.tree-file` (leaf) / `.repo` (group header)
- states: active, collapsed, default

A single row of an indented, collapsible tree: an optional chevron, an icon/badge,
a label, and an optional trailing summary. Selection and hover are instant. Reused
by [worker-tree](../screens/worker-tree.md) and [changes-view](../screens/changes-view.md);
both render tree rows, so the row is described once here and referenced there via
`extends: [tree-node](../components/design-system.md#tree-node)`.
```

### 7.3 A `screen` composed of section nodes — Changes view

`docs/features/groom/gui/screens/changes-view.md`, reauthored. One-off components
and interactions are `### id` sections; the reused row links out via `extends:`.

```markdown
---
type: screen
slug: changes-view
title: Changes view — per-repo tree of working-tree diffs
---
# Changes view

Groups every worker's working-tree diff per repo as a browsable file tree. Part of
the [groom shell](groom.md#main-panel); presents the [diff](../../concepts/diff.md)
concept. Diffs are **click-to-reveal** — nothing renders until a file is clicked.

## Components

### changes-file-row
- selector: `.tree-file`
- extends: [tree-node](../components/design-system.md#tree-node)
- parent: [changes-worker](#changes-worker)
- code: `groom/groom/render.py::_changes_worker`

A leaf of the per-worker file tree. It carries **no** `data-worker-id` on purpose,
so the global worker-select can't hijack a file click.

### file-diff-panel
- selector: `[data-filediff-for]`
- parent: [changes-worker](#changes-worker)
- code: `groom/groom/templates/dashboard.html::wireChanges`

The right pane; a single file's diff is rendered here client-side by diff2html.

## Interactions

### click-file-opens-diff
- on: [changes-file-row](#changes-file-row)
- trigger: click
- when: `mode == changes`
- does:
  - state: mark row `.active`, clear siblings
  - dom: render single-file diff into `[data-filediff-for]`
- code: `groom/groom/templates/dashboard.html::wireChanges`
- verify: `groom/tests/test_render.py::test_changes_groups_diffs_per_repo`

The click drives the tree, **never** the gate detail: the global body click handler
early-returns inside `.changes`, and this view owns its own delegated listener.
That is *why* the row omits `data-worker-id`.
```

### 7.4 A `concept` — Diff

`docs/features/groom/concepts/diff.md`. A durable domain noun, no UI structure.

```markdown
---
type: concept
slug: diff
title: Diff — a file's working-tree change
---
# Diff

A unified diff of one file's uncommitted change in a worker's repo. Produced by
`git diff` host-side and rendered client-side. Presented by the
[Changes view](../gui/screens/changes-view.md); a diff is always shown for exactly
one file at a time, never in bulk.

Related concepts: [Repository](repository.md), [Worker](worker.md).
```

### 7.5 A `flow` — answer a blocked worker's gate

`docs/features/groom/flows/answer-a-gate.md`. A multi-step journey stitching GUI
interactions *and* a server invocation into one end-to-end path — the unit a
Playwright scenario is later derived from. Because it crosses the `gui/` and `http/`
contexts, it lives at the service root under `flows/`, not inside either context.

```markdown
---
type: flow
slug: answer-a-gate
title: Answer a blocked worker's gate
---
# Answer a blocked worker's gate

The operator's core loop: clear a [Worker](../concepts/worker.md) parked on an
operator [Gate](../concepts/gate.md).

- start: a worker has pushed `blocked` and appears in the inbox.
- steps:
  1. [switch to Inbox](../gui/screens/groom.md#switch-mode) — the inbox lists only gated workers.
  2. [select the worker](../gui/screens/operator-inbox.md#select-worker) — the detail pane
     loads via `GET /worker/{id}` (pulled, so a live push can't wipe a half-typed answer).
  3. read the gate question — untrusted markdown on the escaped `data-md` path.
  4. submit the answer — a `submit` [interaction](../gui/screens/operator-inbox.md#submit-answer)
     on the form fires the [answer-message](../http/server.md#answer-message) `invocation`
     (`ws-send cmd=answer` over `/ws`).
  5. the worker flips `BLOCKED → RUNNING`; a `groom:answered` toast confirms.
- end: the worker's last gate cleared (if others remain it stays in the inbox).
- verify: `groom/tests/test_app.py::test_answer_clears_gate` (+ a future end-to-end
  Playwright journey).
```

### 7.6 A `cli` with `command` sections — workhorse

`docs/features/workhorse/workhorse.md`. The same surface/element/behavior pattern,
for a command line: a `cli` surface whose `command`s are section-level elements.

```markdown
---
type: cli
slug: workhorse
title: workhorse — fail-soft runner for YAML agent workflows
---
# workhorse

Walks a directed graph of nodes defined by a [workflow](concepts/workflow.md),
checkpointing after each step so a run resumes exactly where it stopped.

- binary: `workhorse`
- code: `workhorse/workhorse/main.py::main`

## Commands

### run
- usage: `workhorse run <workflow> [<flow>] [--params JSON]`  (the default command)
- flags: `--workflow`, `--params/--params-file`, `--cli claude|codex|…`, `--resume-latest`, `--no-cache`
- does: run: execute the [workflow](concepts/workflow.md) graph — or a named flow
  standalone — checkpointing per node
- code: `workhorse/workhorse/main.py::_run_run`

Runs a whole workflow, or one named flow as a re-entry point:
`workhorse run coder qa --params '{"story":"CASE-1234"}'` runs the coder workflow's
`qa` [flow](workflow-format.md#flows) on its own.

### test
- usage: `workhorse test <workflow_dir> [-k FILTER]`
- does: run: pytest from the workflow's `tests/` dir
- code: `workhorse/workhorse/main.py::_run_test`

### dot
- usage: `workhorse dot --workflow <path> [--pin K=V] [-o out.dot]`
- does: run: render the workflow graph to Graphviz DOT
- code: `workhorse/workhorse/main.py::_run_dot`
```

And `farrier` as a second `cli` (`docs/features/farrier/farrier.md`), abbreviated:

```markdown
---
type: cli
slug: farrier
title: farrier — install the prompt library into a repo
---
# farrier

Renders an agent-neutral prompt library into a repo's assistant adapter files,
driven by the repo's `agents.yml`.

- binary: `farrier`
- code: `farrier/farrier/install.py::main`

## Commands

### install
- usage: `farrier install [--repo PATH] [--check]`  (the default command)
- flags: `--repo`, `--config`, `--check` (drift check, no writes), `--library`
- does: run: render packs/skills/prompts into Claude/Codex/Copilot adapters + `.agents/`
- code: `farrier/farrier/install.py::_run_install`
```

### 7.7 A `concept` that a `command` consumes — Workflow

`docs/features/workhorse/concepts/workflow.md`.

```markdown
---
type: concept
slug: workflow
title: Workflow — a YAML-defined agent graph workhorse executes
---
# Workflow

A directed graph of nodes that [workhorse](../workhorse.md) executes fail-soft,
checkpointing after each node so a run resumes where it stopped. Its on-disk shape
is the [workflow file format](../workflow-format.md); a run's live state is a
`WorkflowContext` plus resumable run artifacts (`graph/context.py`, `artifacts.py`).

Related: [Flow](flow.md) (a named sub-graph), [Agent](agent.md).
```

### 7.8 A `format` — the workflow file format

`docs/features/workhorse/workflow-format.md`. A file format made navigable: the
top-level keys as `### <key>` field sections, the node types, and a real sample.

```markdown
---
type: format
slug: workflow-format
title: The workflow file format (workflow.yaml)
---
# Workflow file format

The YAML shape of a [workflow](concepts/workflow.md), loaded and validated into a
pydantic `Graph`.

- file: `**/workflow.yaml`
- code: `workhorse/workhorse/graph/loader.py::load_workflow`  (schema: `graph/nodes.py::Graph`)

## Fields

### start    <!-- required -->
The entry node id; must resolve to a node in `nodes:`.

### nodes    <!-- required -->
The graph, a list of nodes. Each has an `id` and a `type` (below); every
`next`/branch target must resolve — only `terminal`/`fail` may omit `next`.

### flows
A map of named sub-graphs, each itself a full workflow. A `flow` node runs one; a
flow can also run standalone via `workhorse run <workflow> <flow>`.

### vars / env
Initial context (`vars`) and env injected into every script node (`env`). A flow
`var` with a null default is a required parameter.

## Node types

`agent` (LLM against a Jinja `prompt`), `script` (run a script), `flow` (call a
sub-graph in `flows:`), `branch` (route on a context dot-path), `call` (a builtin
`fn`), `terminal` / `fail` (exit 0 / 1).
```

The `format` node embeds a real, load-valid sample (from `workhorse/docs/WORKFLOW.md`):

```yaml
name: example
start: step
vars:
  subject: "the Fibonacci sequence"
nodes:
  - id: step
    type: agent
    prompt: prompts/step.md
    args: { subject: "{{ subject }}" }
    outputs:
      - key: result
        default: { status: error }
    next: decide
  - id: decide
    type: branch
    path: result.status
    cases: { ok: done }
    default: failed
  - id: done
    type: terminal
  - id: failed
    type: fail
```

### 7.9 A `server` with `endpoint`s and a websocket message

`docs/features/groom/http/server.md`. groom is *also* an HTTP/WebSocket server; its
routes are the index and the `/ws` channel carries the message protocol. (A GUI
`interaction`'s `net:` effect links here, tying the two graphs together.)

```markdown
---
type: server
slug: groom-server
title: groom server — Litestar routes + /ws
---
# groom server

Serves the [groom shell](../gui/screens/groom.md) as htmx fragments and pushes live
updates over `/ws`. The routes are htmx/webhook, not a public JSON API — every handler sets
`include_in_schema=False`, so there is **no** OpenAPI doc (see the note in §7.10).

- code: `groom/groom/app.py::create_app`

## Endpoints

### get-worker
- method: GET
- path: `/worker/{container_id}`
- code: `groom/groom/app.py::worker_detail`
- does: dom: return the detail-pane fragment for one worker (pulled, never pushed)

### push-blocked
- method: POST
- path: `/push/blocked`
- code: `groom/groom/app.py::push_blocked`
- consumes: a sidecar `blocked` event
- does:
  - state: upsert worker + gate
  - emit: broadcast the shell
  - emit: `groom:blocked`

### ws
- channel: `/ws`
- code: `groom/groom/app.py::dashboard_ws`
- consumes: `cmd=answer` (client `ws-send`)
- emits: `blocked` / `progress` / `exited` broadcasts; `groom:answered`
```

The **`/ws` messages are `invocation`s** (a `### id` under `## Invocations`, on the
`ws` endpoint) — a message is a call, not a GUI event. The human form-submit that
sends it is a separate `interaction` (`trigger: submit`) whose `does:` includes
`net: /ws cmd=answer`, linking the GUI graph to this invocation:

```markdown
## Invocations

### answer-message
- on: [ws](#ws)
- trigger: ws-send:answer
- does:
  - state: worker `BLOCKED→RUNNING` on last gate cleared
  - emit: `groom:answered`
- code: `groom/groom/app.py::_handle_command`
- verify: `groom/tests/test_app.py::test_answer_clears_gate`
```

### 7.10 Hub + detail: a `command` file linking **code concepts**

The `workhorse` `cli` (§7.6) is an **index**; its `run` command `detail:`-links to a
full own-file node that links the code it drives — each a **code `concept`**.

```markdown
---
type: command
slug: run
title: workhorse run — execute a workflow
---
# workhorse run

Loads a [workflow](../concepts/workflow.md), walks its graph, checkpointing per node.

- usage: `workhorse run <workflow> [<flow>] [--params JSON]`
- parent: [workhorse](../workhorse.md)
- code: `workhorse/workhorse/main.py::_run_run`
- does: run: parse → step-loop → checkpoint; resumes from the last node on re-run

Drives these code concepts: [load_workflow](../concepts/load-workflow.md) (parse YAML
→ Graph), [run_agent](../concepts/run-agent.md) (invoke an agent node),
[ArtifactWriter](../concepts/artifact-writer.md) (checkpoint / resume state).
```

A **code concept** — a `concept` node that *is* a code unit (a `code:` bullet, no
domain prose):

```markdown
---
type: concept
slug: load-workflow
title: load_workflow — parse a workflow.yaml into a Graph
---
# load_workflow

Reads a workflow YAML with `yaml.safe_load`, keys `nodes:` by `id`, recurses into
`flows:`, then validates into a pydantic `Graph`. The parse entry for the
[workflow format](../workflow-format.md).

- code: `workhorse/workhorse/graph/loader.py::load_workflow`
```

> **OpenAPI connection.** When a `server` *does* publish an OpenAPI document (a
> JSON-API service — unlike groom, which opts out), model that document as a `format`
> node (`code:` its `openapi.json` / schema route) and give each `endpoint` an
> `openapi:` bullet naming its `operationId`. The `endpoint` node is the human/graph
> view; the OpenAPI `format` is the machine contract — **linked, not duplicated**, so
> the generated schema stays the source of truth for shapes.

### 7.11 An abstraction + implementations, selected by a flag — the harness backend

`workhorse`'s `--cli` flag picks the agent harness: an ABC (`AgentBackend`) with one
concrete class per CLI, chosen at runtime by `get_backend(name)`. Model the
abstraction and each implementation as **code `concept`s** in an `extends` (is-a)
fan, and let the flag `refs` the abstraction.

The abstraction — `docs/features/workhorse/concepts/agent-backend.md`:

```markdown
---
type: concept
slug: agent-backend
title: AgentBackend — the harness backend abstraction
---
# AgentBackend

The abstract base every agent harness implements: spawn a CLI, stream its events,
detect completion. `get_backend(name)` returns the concrete one whose registry key
matches [workhorse run](../commands/run.md)'s `--cli` value.

- code: `workhorse/workhorse/runner/backends.py::AgentBackend`

Implementations (each `extends:` this): [claude](claude-backend.md) (default) ·
[codex](codex-backend.md) · [copilot](copilot-backend.md) ·
[opencode](opencode-backend.md) · [aider](aider-backend.md).
Selector: [get_backend](get-backend.md).
```

One implementation — `concepts/codex-backend.md` (each concrete class is a leaf that
`extends:` the base and adds only its `code:` anchor):

```markdown
---
type: concept
slug: codex-backend
title: CodexBackend — the codex harness
---
# CodexBackend

Runs the `codex` CLI, parsing its `thread.started` / `item.completed` event stream.

- extends: [AgentBackend](agent-backend.md)
- code: `workhorse/workhorse/runner/backends.py::CodexBackend`
```

The flag that selects one — a nested bullet on the `run` command links its values to
the implementations (the value *is* each backend's slug):

```markdown
- flags:
  - `--cli <name>` — selects an [AgentBackend](../concepts/agent-backend.md)
    implementation; `<name>` is a backend's registry key: `claude` (default) ·
    `codex` · `copilot` · `opencode` · `aider`.
```

> **Pattern — abstraction + implementations + selector.** An abstraction is a code
> `concept`; each implementation is a code `concept` that **`extends:`** it (the is-a
> fan); whatever *chooses* one at runtime — a `--cli` flag, a config key, a registry,
> the workflow format's node `type` — is a plain **`refs:`** link to the abstraction,
> its value equal to the chosen implementation's slug. No new relation: `extends`
> builds the hierarchy, `refs` binds the selector, prose says "selects". `ostler trace
> agent-backend` then walks both the implementations *and* the flag that picks them.

---

## 8. Spec completeness — enough to regenerate the code

The bar: **reading only the node (and the nodes it links) plus the team's skills, a competent
agent can reimplement behavior-equivalent code.** Not byte-identical — behavior-equivalent:
same fields, same defaults, same effects, same errors. If a detail changes behavior, it's in
the doc. The node specifies **what** the code does; **how** it's built (patterns, idioms,
libraries, structure) comes from the skill files (§2.3), not here — so don't write coding
instructions, write the contract. The `does:` effect list, the field/flag attributes, and
(for code) the algorithm-as-contract are the behavioral spec; prose carries the *why*.

**Field & argument attributes (used by `format`, `command`, `endpoint`).** Give every field,
flag, and positional its machine facts, then a sentence of behavior:
- `type:` (`int` / `float | null` / `enum{a,b,c}` / `path` / a linked `concept`),
- `required:` (yes/no), `default:` (the literal, or "engine default (`ENV`, 600)"),
- shape modifiers where they apply: `repeatable`, `mutually-exclusive with …`, `min/max`,
- validation + failure (`negative → ValueError at load`), and what it *does*.

**`does:` is the behavior contract.** Each child is one effect, ordered, specific:
`state:` (which class/flag flips), `dom:` (what renders where), `net:<METHOD path>` (the
call), `emit:<event>`, `nav:`. A reader turns the list into code. For a `command`/`concept`
whose behavior is an algorithm, use an ordered `## Algorithm` (numbered steps, one op each)
plus inputs (typed), output (typed), invariants, and `raises:`.

Per type, "regenerable" requires:

- **`concept` (code)** — `code:` anchor; a `## Algorithm` / `## Contract`: typed inputs,
  typed output, the ordered transformation steps (what it computes, not which library),
  invariants, `raises:`. Enough to reimplement the unit's behavior.
- **`concept` (domain)** — definition, identity, lifecycle/**states** and the transitions
  between them, invariants, and links to related nouns.
- **`format`** — every field as a `### <field>` section with `type:`/`required:`/`default:`
  + constraints; all *variant/nested* shapes (e.g. each node `type`'s own fields) so the full
  data contract is specified (the *shape*, not the parser library); a load-valid sample.
- **`cli`** — `binary:` + `code:` entry; every command (below), and the dispatch/default-
  command rule.
- **`command` / `invocation`** — `usage:`; **every** flag and positional as a nested bullet
  with the field attributes above; `does:` ordered effects; **exit codes**; `code:`.
- **`server`** — `code:` entry (`create_app`), transport, auth model; every endpoint (below).
- **`endpoint`** — `method:`+`path:` (or `channel:`+`message:`); request params/body (typed),
  response shape + **status codes**, `does:` effects, `emits:`/`consumes:`, `code:`.
- **`screen`** — layout regions, the components it composes (links), entry/route, realtime
  channels; enough to reconstruct the shell and where each part mounts.
- **`component`** — `element:` (tag), `selector:`, `props:` (name: type, required, default),
  `states:` **and the class/style per state**, `dom:` (structure), the events it fires
  (links to its `interaction`s), `a11y:` (role/aria), `code:`.
- **`interaction`** — `on:` (component), `trigger:` (the exact event), `when:` (guard),
  `does:` (ordered effects, specific), `code:`, `verify:`.
- **`flow`** — `start:` precondition, ordered `steps:` (each a link + what happens), `end:`
  state, `verify:` (the e2e test). Enough to script the journey.

This is a **review** standard, not a `doctor` gate (§6): the linter can't judge "enough to
regenerate," so the author/coder documentation gates and the story auditor hold the bar.

## 9. Reviewer questions

The vocabulary now stands at **eleven** types across three surfaces — GUI
(`screen`/`component`/`interaction`), CLI (`cli`/`command`), HTTP/WS
(`server`/`endpoint`), and shared (`invocation`/`flow`/`concept`/`format`) — plus the
operational-profile extension (`runbook`/`environment`/`step`; [okf-runbook.md](okf-runbook.md)).
Open calls:

1. ~~`interaction.does` shape~~ — **RESOLVED: nested bullet list**, one effect per
   child bullet (ostler already parses nested bullets — `markdown.py::_parse_bullets`
   → `Bullet.children`; no new capability). A single trivial effect may stay one-line.
2. **`flow.steps` linkage** — is a numbered list of links (as drafted) enough, or
   should each step be its own addressable node (heavier, but individually testable)?
3. ~~CLI/WS behavior type~~ — **RESOLVED: a dedicated `invocation` type.**
   `interaction` = GUI events (click/hover/keyboard/drag); `invocation` = a call or
   message (a CLI command `run`, an HTTP request, a `ws-send`/`ws-push`). A WS channel
   is one `endpoint`; each message on it is a separate `invocation`.
4. **`endpoint`/`server` naming** — `server`/`endpoint` as drafted, vs `api`/`route`.
5. **Hub+detail default** — `detail:` own-files for commands/endpoints only when
   they outgrow a section (as drafted), or always split (heavier, more navigable)?
6. ~~Concept location~~ — **RESOLVED: per-service `docs/features/<service>/concepts/`**
   to keep a multi-service repo self-contained; shared nouns are defined by the
   owning service and path-linked (see §4).
7. ~~Section type marker~~ — **RESOLVED: implicit by section heading** (`## Components`
   → `component`, `## Interactions` → `interaction`, `## Commands` → `command`); no
   per-heading marker needed. See §4.
