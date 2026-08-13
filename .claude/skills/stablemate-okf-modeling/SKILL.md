---
name: stablemate-okf-modeling
description: "How to model a whole app's UI/CLI/server surface graph as an OKF UI-profile subgraph under docs/features/<service>/ — two playbooks that produce the same conformant output: FROM A DESCRIPTION (a human hands you intent, greenfield/design-time) and FROM EXISTING CODE (you interrogate a running codebase, reverse-engineering surfaces, elements, behaviors and concepts). Load when building or backfilling a service's OKF docs in bulk, not for a single-story update."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/okf-modeling/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-okf-modeling/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [standards, docs]
---

# OKF modeling — building a service's surface graph

Load this skill to model an **entire service's** surfaces (screens/CLIs/servers), their elements,
behaviors, concepts, flows, and formats as a conformant OKF UI-profile subgraph under
`docs/features/<service>/`. This is the *bulk build* skill. For a single story's incremental doc
update, load [[documentation]] instead; for the type vocabulary, folder layout, and linter rules,
[[ostler]] is the reference — read its "The OKF UI profile" section first, this skill assumes it.

You are writing **the book**: OKF is the full, always-current *spec* of the system, complete enough
that an agent could **regenerate behavior-equivalent code** from it plus the team's stack skills.
Three rules govern the content (profile §2, §8):

- **Spec-complete for every node** — surfaces, elements, behaviors, concepts, flows, formats *and*
  visual nodes. Each carries its full contract: fields with `type`/`required`/`default`, flags/args
  item-by-item, `does:` as ordered effects, algorithms as ordered steps, errors/exit/status codes,
  and for UI the `dom:`/`props:`/`states:` contract. The per-type checklist is profile §8
  (mirrored in [[ostler]]). A one-line stub is below bar.
- **Every interactive control carries its accessibility contract** — `role:` (the ARIA/semantic
  role), `name:` (the accessible name), `keyboard:` (the key/shortcut to reach or fire it), on the
  `component`/`interaction` node. This is the same data twice over: it's what makes the UI
  *accessible* **and** the robust basis for automation — an interaction maps to
  `getByRole(role, {name})` (stable across CSS churn), with the brittle `selector:` only as a
  fallback. A control you can't give a role + accessible name is an a11y gap *and* a doc gap —
  flag it, don't paper over it with a class selector.
- **Every structural component says where it sits** — a `placement:` bullet on the `component`
  node whose `role:` is `main`, `article`, `navigation`, `banner`, `complementary`, `region`,
  `form` or `dialog`, as bands over the viewport: `- placement: width 60-100%, x 0-20%` (keys
  `x`/`y`/`width`/`height`, an omitted key unconstrained). QA registers what actually rendered
  against it, so it is the only bullet that can tell a correct page from one crushed into a
  narrow column against a margin — `role:` and `selector:` hold either way. Read the numbers off
  the running UI, never invent them; **state a band, never a point**, wide enough to survive a
  resize; and never widen one to make a red run green. Buttons and other leaf controls get no
  `placement:` — their position is brittle and uninteresting.
- **Structure it so the graph can *see* it — don't bury spec in prose.** A field or method described
  in a sentence is invisible to `ostler graph`; the same thing as a **nested typed section** is a
  first-class node you can query. Model a concept's methods as `### method:` sections and a format's
  fields as `### field:` sections (or under `## Methods`/`## Fields`), and give each its **own
  filterable bullets** — `sig:`/`abstract:`/`raises:` for a method, `type:`/`default:`/`required:`
  for a field — one per attribute, never crammed into one line. Then
  `ostler graph --path 'concept:X / method:foo'` walks straight to it. Reserve prose for the summary,
  not the spec.
- **One provable claim per normative bullet.** A bullet QA mints an obligation from — `does:`,
  `when:`, `returns:`, `raises:`, `status:`, `error:`, `auth:`, `persistence:`, `emits:`,
  `consumes:`, `concurrency:`, `idempotency:`, `required:`, `default:`, `semantics:` — is proved
  by exactly one scenario. A bullet holding a paragraph is several requirements sharing one id,
  and the scenario proves whichever clause the planner read; the rest ships claimed-as-covered
  and untested. Split on real seams — the success effect, each error case, what is persisted,
  what is emitted — by repeating the key. `doctor` errors past 700 characters of prose.
- **Spec, not implementation** — document *what* the code does; the *how* (patterns, idioms,
  libraries, structure) is owned by the stack skills, never the book. `code:` anchors the impl; the
  prose never prescribes a technique.
- **The book, not a changelog** — model the current reality in full; when a later story changes it,
  its delta is merged into these nodes (that is [[documentation]]'s job).

There are **two playbooks** that converge on the *same output* — a spec-complete, referentially-
complete subgraph that `ostler doctor` passes — and share the *same mechanics* (the scaffold →
author → fmt → doctor loop). Only the **input** differs:

- **From a description** — a human gives you intent (a feature brief, a mockup, "here's the screen
  I want"). Design-time / greenfield, before the code exists.
- **From existing code** — you read a running codebase and recover the graph it already implements.
  Archaeology-time. The **coder** workflow and dogfooding use this.

Do not invent a third way. Both end at the same convergence gate (§ *Convergence & verification*).

## Shared method — how any surface decomposes

Whichever playbook you're in, model in this order. Each layer links down to the next with plain
markdown path links (never `[[wikilinks]]`).

1. **Surfaces first.** One `screen` per composed GUI view, one `cli` per command-line app, one
   `server` per HTTP/WS service. The surface file is the *index* of its elements.
2. **Elements of each surface.** `component` (a UI part), `command` (a subcommand), `endpoint` (a
   route or WS channel). One-offs are `### id` **sections** under the surface's typed heading
   (`## Components` / `## Commands` / `## Endpoints`); anything reused or large enough to outgrow a
   section gets its **own file**, `detail:`-linked from the index.
3. **Behaviors.** `interaction` for a GUI event (click/hover/keyboard/drag/submit), `invocation`
   for a call or message (running a command, an HTTP request, a `ws-send`/`ws-push`). Sections
   under `## Interactions` / `## Invocations`. Each links `on:` its element and carries a `does:`
   nested-bullet effect list.
4. **Concepts.** Every durable noun the system is *about* — domain (`Worker`, `Diff`, `Gate`) or
   **code** (a function/class/module, carrying a `code:` bullet and no domain prose). Each `concept`
   gets its **own file** under `docs/features/<service>/concepts/` so others can link it. Abstraction
   + implementations: model the base as a code concept, each impl as a code concept that `extends:`
   it, and whatever *selects* one at runtime `refs:` the base (profile §7.11).
   - **A concept is a real explanation, not a stub.** Cover its *parts* (a "Workflow" explains its
     states, transitions, and inputs/env; a format explains its fields) and **point to the more
     specific nodes** for each — the format that holds the on-disk shape, the code concept that
     implements a piece, the command that drives it. A one-line concept with a lone `code:` bullet
     is incomplete.
   - **State the key relations in the opening prose.** A file node's *graph* links are the ones in
     its intro region (before the first `##` subheading) — that is what `ostler trace` surfaces and
     the linter checks. Put the relations you want discoverable there; use subsections to elaborate.
5. **Flows.** A `flow` per multi-step journey; its `steps:` are an ordered list of links into the
   interactions/invocations/screens it traverses. Flows live at the service root (`flows/`) because
   a journey often crosses contexts.
6. **Formats.** A `format` per file/artifact shape (an `agents.yml`, an OpenAPI doc), fields as
   `### <key>` sections.

**Placement is per-service, then by context.** `docs/features/<service>/`; split into `gui/`,
`http/`, `cli/` **only if the service genuinely spans contexts** (groom = GUI+HTTP → split;
workhorse = CLI-only → stays flat). `concepts/` and `flows/` sit at the service root. Don't
hand-pick paths — `ostler scaffold` places every node for you.

**Referential completeness is the target.** A subgraph is done when every `on:` / `parent:` /
`extends:` / `detail:` / `steps:` link resolves and every required section/bullet is present — i.e.
`ostler doctor` is green. Model breadth-first so links have targets: scaffold the concept before the
component that `extends:` it, the endpoint before the interaction whose `does:` has `net:` into it.

**Code-inventory completeness is the *other* target** (Playbook B especially). Reachable-from-the-root
is necessary but not sufficient: entry-point descent alone misses **siblings** and **non-entry
modules**. Before you call a service done, diff the graph against the source: every public class /
module / function is either its own node or explicitly folded into a documented behavior/concept.
Two blind spots to hunt deliberately:
- **Every implementation of an interface/ABC gets its own node** — not one example with the rest
  named in prose. A base with five subclasses (e.g. an `AgentBackend` → claude/codex/copilot/opencode/
  cline) is *five* sibling concepts, each with its own contract.
- **Library/utility modules the entry points never reach** (a `scriptutil`/SDK imported by other
  tooling) are still part of the book — document them too.

---

## `verify:` — declaring the observation

Every normative bullet mints a QA obligation, and `verify:` is where the node says **what would be
observed** if that obligation holds. It is a call from ostler's check vocabulary with typed
arguments — `http_status`, `json_path`, `unchanged`, `keys_unchanged`, `count`, `absent`, `visible`,
`persists`, `emitted`, `conflict_on_stale` — never a test id, never prose:

```markdown
- does: on conflict the manifest is left byte-identical
- verify: unchanged(subject="manifest", except_fields=["pages.getting-started.fr.slug"])
- verify: http_status(409, title="Manifest Conflict")
- tests: `api/publish_test.go::TestPublish_Conflict`
```

`doctor` grounds each call against the vocabulary (`unparsed-check`, an **error**), `ostler qa
validate` refuses a QA plan that claims the obligation without invoking the declared call with the
declared arguments, and the harness implements each name. That chain is the point: **an assertion
cannot come out weaker than the declaration, because the assertion *is* the declaration.** Every
argument you leave off is a defect the QA of every future story is licensed to miss — a mask over a
field, a comparison that never inventories keys — and nobody downstream can put it back, because
only this node knows what the behaviour promised. A test id names the code that ran rather than the
thing observed, which is why it lives in `tests:`, whose one reader is regression attribution.

**A node whose normative bullets declare no observation is unfinished**, and `doctor` says so:
`undeclared-obligation`. It is a warning rather than an error only because books written before the
rule are full of them — treat it as queued work, not as noise. It follows that when you merge into
a node that already exists and its `does:`/`raises:`/`states:` bullets carry no `verify:`, declaring
them is part of the merge, not optional polish. The rule table and the full vocabulary are in
[[ostler]] → "The OKF UI profile".

---

## Playbook A — from a high-level description

You're handed intent, not code. Turn it into the graph, then leave `code:`/`tests:` bullets as
**stubs** (they're grounded later, when the code exists — never fabricate a `path::symbol`).
`verify:` is the opposite: it is the *most* writable bullet on the node at design time, because the
observation that would prove a behaviour is knowable before the code producing it exists.

1. **Interview the description for the six layers above.** From the brief, list: what surface(s)?
   what parts does the user see? what can they do (each verb → a behavior)? what nouns recur (each →
   a concept)? what end-to-end journeys does it enable (each → a flow)? Ask the human to fill gaps
   in *that* structure — you're eliciting nodes, not prose.
2. **Scaffold breadth-first, concepts and shared components first** so downstream links resolve:
   ```bash
   ostler scaffold concept diff   --service groom --title "Diff"
   ostler scaffold screen  changes-view --service groom --title "Changes view"
   ostler scaffold interaction click-file-opens-diff --in docs/features/groom/gui/screens/changes-view.md
   ```
3. **Author the prose and structured bullets** from the description — the *why*, the states, the
   guards (`when:`), the effects (`does:`). Set relation bullets (`on:`/`parent:`/`extends:`) to real
   links between the nodes you just scaffolded. Leave `code:`/`tests:` as scaffolded stubs (or omit),
   and declare a `verify:` check for every normative bullet you write.
4. **Converge:** `ostler fmt …` then `ostler doctor`. Because `code:`/`tests:` aren't link-checked,
   an intent-only graph is fully green before a line of code is written — that's the point: the graph
   is the spec the coder later grounds. `verify:` *is* checked, but against the vocabulary rather
   than against the repo, which is exactly why it is writable this early.

> This is the greenfield pass: emit the OKF-UI skeleton at design time so the coder inherits a
> target, not a blank page. The **author** workflow never runs it — author reads the book to ground
> its stories and is forbidden from writing to it. The book belongs to this workflow.

---

## Playbook B — from existing code

You're recovering the graph an app *already* implements. Read the code, then ground each node's
`code:`/`tests:` to the real `path::symbol` (here you *do* fill them — the code exists).

1. **Discover surfaces from entry points.**
   - **GUI** — templates/render functions and their top-level containers → `screen`s; repeated
     rendered fragments (rows, panels, badges) → `component`s.
   - **CLI** — the argparse/click/typer tree: the app → a `cli`; each subparser → a `command`.
     Document each flag and positional as its **own nested bullet** under `flags:` / `args:` —
     what it does, the context it applies in, and a link to the `concept`/`format` it drives (a
     `--cli` flag → the backend abstraction; a `--params` flag → the format's `vars` field). A
     bare token list is not enough.
   - **HTTP/WS** — the route table (decorators, a router include, a `create_app`) → a `server`; each
     route/WS channel → an `endpoint`.
2. **Recover behaviors from handlers.** Each event handler / click wiring → an `interaction`; each
   request handler, command body, or WS message case → an `invocation`. Read the handler to fill
   `does:` (the state/dom/net/emit effects it actually performs) and `when:` (its guards).
3. **Recover concepts from the type/domain layer.** Domain models, core nouns in names and docstrings
   → domain `concept`s. Key functions/classes/modules the surfaces depend on → **code** `concept`s
   (`code: path::symbol`). An ABC with a registry/factory and concrete subclasses → the base +
   `extends:` fan + a `refs:` from the selector (profile §7.11 — the `--cli` backend pattern).
4. **Ground every node to code as you go.**
   - `code:` = the `path::symbol` that renders/handles it (a template region is a `file` ref).
   - `tests:` = the existing test that proves it (`tests/…::test_…`). If none exists, omit rather
     than invent — a missing `tests:` is fine; a wrong one is a lie.
   - `verify:` = the observation, in the check vocabulary above — and reading the code is what tells
     you which one and with which arguments. The handler that returns 409 on a stale write declares
     `http_status(409, …)`; the one that writes through a store before answering declares
     `persists(subject=…)`. Omitting it is not neutral: it is the one bullet nobody downstream can
     supply for you.
5. **Scaffold, author, converge** — same loop as Playbook A, but the prose is *as-built* (describe
   what the code does, not what you wish it did) and `code:`/`tests:` are real.

> This is what the **coder** workflow does after implementing a story, and what dogfooding a service
> (workhorse/groom/ostler/farrier) does: walk the code, land the subgraph, prove it green.

---

## Convergence & verification

Both playbooks finish here. A service's subgraph is **done** when:

```bash
ostler fmt docs/features/<service>          # every file canonical (or: ostler fmt --check → exit 0)
ostler doctor                                # 0 errors
ostler list --type screen                    # spot-check: the surfaces you expect are present
ostler trace <surface-root>                  # from the cli/screen/server index — must reach every node
```

**No orphans.** Trace from the surface root (the `cli`/`screen`/`server` index) and confirm you can
walk to *every* node in the subtree. A node nothing links to is an orphan — link it from the most
relevant place (the surface index's own body, the command whose flag drives it, the abstraction it
`extends:`). Put structural pointers in the node's bullets, not only in prose, so `trace` surfaces
them. The surface index should link its key concepts/formats in its own region, so a root trace
reaches them directly.

Sequencing on a fresh service, to keep links resolving throughout:

1. `concept`s and any shared/library `component`s (the link *targets*), then
2. surfaces (`screen`/`cli`/`server`) with their element sections, then
3. behaviors (`interaction`/`invocation`) that link `on:` those elements, then
4. `flow`s that stitch the behaviors, then
5. `format`s.

If `doctor` reports an error, its code names the mechanical fix (see the rule table in [[ostler]]):
`bad-heading-type`/bullet-order → `ostler fmt`; `missing-required-section`/`missing-required-bullet`
→ `ostler scaffold` (or add the heading/key); `dangling-link`/`missing-anchor`/`unresolved-relation`
→ fix the target. Never silence a finding by deleting the bullet that carries real meaning; fix the
link. Loop until green.

## Neighbors

- **Type vocabulary, per-type bullets, folder layout, verbs, full linter rules** → [[ostler]].
- **One-story incremental update** (not a bulk build) → [[documentation]].
