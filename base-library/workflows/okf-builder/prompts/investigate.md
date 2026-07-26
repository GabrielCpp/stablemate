---
agent: agent
---

# okf-builder — investigate one worklist item

You are building **the book**: the full, spec-complete OKF graph of a service, one item at a
time. This turn handles exactly **one** worklist item; you document it to the spec-complete bar
and **return the deeper items it reveals** so the crawl continues. The crawl is exhaustive: it
starts at entry points and descends the code **layer by layer**, classifying every finding.

Load the method and obey it: {{ skill_load_ref("stablemate-okf-modeling", skill_dir() + "/stablemate-okf-modeling/SKILL.md") }}
Use **Playbook B (from existing code)**. The type vocabulary, per-type spec-completeness bar (§8),
folder layout, and linter rules are in the `stablemate-ostler` skill it links to. Always finish an
item by running `ostler fmt <touched>` on what you wrote.

## Guardrails (this runs unattended — stay in your lane)

- **Docs only.** You write **only** under `docs/features/**` (via `ostler scaffold`/`fmt` and your
  editor). Never modify source code, never run `git` (no add/commit/push), never run build/test or
  any destructive command. You are documenting the code, not changing it.
- **Stay inside this service.** Descend and reference only the service's **own source** under
  `{{ workhorse_var('source_root') }}`. The repository may contain sibling services; they are not
  part of this run. Also skip the configured paths in
  `{{ workhorse_var('source_excludes') }}`. When a `layer` calls into the
  repo. When a `layer` calls into the **standard library, a third-party package, or code you've
  already documented**, stop — do **not** spawn a `layer` for it (mention it in prose if relevant).
  This bounds the crawl; without it the descent never ends.
- **One bounded item, then stop.** An item may be one complete small surface, one coherent slice of
  a large surface, or one source module/package. Discover deeper bounded items by **returning them**
  in `discovered`; never explode a surface into one model turn per trivial control or route.
- **Scope to `{{ workhorse_var('service') }}`.** Only touch `docs/features/{{ workhorse_var('service') }}/…`.

## This item

- kind: `{{ workhorse_var('item_kind') }}`
- target: `{{ workhorse_var('item_target') }}`
- context: `{{ workhorse_var('item_context') }}`
- service: `{{ workhorse_var('service') }}` — features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- source root: `{{ workhorse_var('source_root') }}`
- excluded source paths: `{{ workhorse_var('source_excludes') }}`

## What to do, by kind

Document to the **spec-complete bar** (enough to regenerate behavior-equivalent code — *what*, not
coding patterns), **merge** into any node that already exists (the book, not a changelog), and set
`code:`/`verify:` to the real `path::symbol`. Then emit the deeper items you discovered.

**Dedup with `ostler graph` before you create anything.** Ask the tree, don't guess: `ostler graph
--bullet 'code=<path::symbol>' --ids` (is this symbol already grounded?) or `ostler graph --path
'<type>:<parent> / <type>:<name>'` (does this nested node already exist?). If it does, **enrich that
node**; never make a second. Use `ostler graph --orphans` / `--has-bullet code` to see what's
missing rather than re-reading the whole tree.

- **surface** (`cli` / `server` / `screen`) — read the entry point. Write the surface node (its
  index). Then enumerate it **exhaustively**:
  - CLI → every command & subcommand. Server → every route & WS channel. **Screen → every
    interactive control: each button, dropdown, link, input, row, toggle** — no skipping.
  - For a small or medium surface (roughly 15 elements or fewer), author all element and behavior
    sections spec-complete **in this item**. Also author the immediate concepts/formats needed to
    state those contracts; emit only grouped deeper source-layer items.
  - For a larger surface, keep the exhaustive element index on the surface and emit one
    **surface-slice** per coherent family (route prefix/domain, command group, or screen region),
    not one item per element: `{"kind":"surface-slice","target":"<surface>:<family>",
    "context":"elements: <complete bounded list>; source: <module/package>"}`.
  - A server that fronts a web GUI MUST also document the executable local runtime contract as
    top-level bullets: `launch:` (a non-interactive command that starts from source without assuming
    an already-built artifact), `working-directory:` (repo-relative), `entry-url:` (loopback URL),
    `health-path:`, and `identity:` (a response-body literal unique to this app at the health URL).
    These are consumed by the live walkthrough; derive them from package scripts/server defaults and
    the rendered shell, never invent them.
- **surface-slice** — author every element and behavior in the supplied family spec-complete in one
  pass. A `screens:<family>` discovery slice contains several routes: write one complete `screen`
  node per listed route, including its controls and interactions. A slice of an existing CLI/server
  writes its command/endpoint sections into that parent surface. Emit deeper source work grouped by
  module/package. Author immediate concepts/formats in this same turn; do not re-emit each screen,
  element, format, or simple concept separately.
- **element** (`component` / `command` / `endpoint`) — write the element node spec-complete
  (fields/flags/props/states with type/required/default). Write its **behavior** (`interaction`
  for a GUI event, `invocation` for a call) with its first-layer `does:` effects. For UI, capture
  **what it contains** (props/dom/states), its **accessibility contract** — `role:` (ARIA/semantic
  role), `name:` (accessible name), `keyboard:` (key/shortcut) — which doubles as the robust
  `getByRole(role, {name})` locator, and **where it leads** (the nav/route target). If a control has
  no discernible role/accessible name in the code (a bare `div`+`onclick`), say so — it's an a11y
  gap worth surfacing, not something to hide behind a class `selector:`. Emit:
  - a **layer** item at its handler symbol: `{"kind":"layer","target":"<path::symbol>",
    "context":"<behavior node id>"}` — to descend the code;
  - the **surface/element** it leads to (if navigation) and any **concept**/**format** it references.
- **layer** — the descent. Read the bounded symbol, file, module, or package in `target`. Extract its
  intent, classify everything it does or uses, and fold it into the graph: append precise effects
  to behaviors; create/enrich the `concept`s and `format`s it touches. Cover all public members when
  the target is a module/package. Emit deeper work **grouped by source module/package**, not one item
  per called function. Author referenced concepts/formats in this item unless one is independently
  too large for the bounded context; only then emit one grouped follow-up for that larger contract.
  Bottom out when it calls nothing new outside already-documented groups.
- **concept** / **format** — write it spec-complete. Model its **members as nested typed sections,
  not prose**: a concept's methods as `### method: <name> …` and a format's fields as `### field:
  <name> …` (or grouped under `## Methods` / `## Fields`), each with its **own** filterable bullets
  — `sig:`/`abstract:`/`raises:` for a method, `type:`/`default:`/`required:` for a field, one per
  attribute. A member buried in a sentence is invisible to `ostler graph`; a section is a queryable
  node. If the concept is an **interface / ABC / base class / protocol**, enumerate **every**
  implementation as its own sibling node (find them by subclass/grep — do **not** just name the rest
  in prose). If it's a **module**, cover **every** public member. Author directly referenced
  concepts/formats in this turn where bounded; only emit a grouped follow-up when genuinely too large.
- **runbook** / **environment** — document the **operational surface** to the spec-complete bar
  (the OKF runbook profile). `ostler scaffold runbook <driver> --service <svc>`
  (or `environment <name>`) writes it under `docs/features/<svc>/ops/`, then author:
  - **`environment`** — its `selector:` (the env-var/env-file that picks it), one nested
    `services:` child per service with its **env-scoped** URL/host (note any host-rewrite + reason),
    `backing:` (DBs/buckets/emulators), and `local-only: true` when tooling must refuse it without an
    override. Derive ports/hosts from the config loader + compose/scripts; never invent them.
  - **`runbook`** — its `driver:` (web/mobile/http/cli/artifact/iac/none), `environment:` link,
    `cli:`/`surfaces:` links to the nodes it exposes, `code:` launch entry point, and the ordered
    `## Steps`. Each `### <id>` step gets a `kind:` (prepare/service/seed/run/health/verify/drive), a
    real `run:` command, and — crucially — a **real readiness signal**: a `service`/`health` step's
    `health:` must be a genuine probe (an API endpoint that exercises the backend, `port-bound`,
    `log:<pattern>`, `ws:<frame>`), **never a UI shell served with the backend down**; a `run` step's
    `produces:` names its output files and `verify:` how success is confirmed (golden/deterministic/
    assertion/test-id). Mark **every step you author `provenance: derived`** — the live walkthrough
    promotes them to `verified` later. Order the steps so a reader can stand the system up from the
    doc alone. Emit any surface/concept the runbook references but that isn't documented yet.
- **harness** — document **one test tier**: how it is run, where its specs live, and how a
  contributor adds one. A `verify:` bullet elsewhere in the book names a test; this is the node that
  says what running it takes, so `verify:` points into something executable instead of a bare string.
  Author it as a `runbook` under `docs/features/<svc>/ops/` (`ostler scaffold runbook <tier>
  --service <svc>`) with `driver:` set to what the tier actually drives — `web` for a browser e2e
  suite, `cli` for a unit/lint runner — plus an `environment:` link when it needs a booted stack.
  Its ordered `## Steps` are the tier's real lifecycle: `prepare` (install deps, install browsers),
  `service` (boot what the suite talks to, with a **real** `health:` probe — not a UI shell served
  with the backend down), `run` (the exact command, with `working-directory:` when it is not the
  repo root), and `verify` (how a pass is recognized: exit code, report artifact, CI job name).
  Beyond the steps, the doc's prose must answer the questions a contributor actually has:
  - **Where specs live and what they are named** — the glob, so a reader knows where a new file goes.
  - **How to run one test, not the whole tier** — the filter flag (`-k`, `--grep`, `-run`). A tier a
    contributor can only run in full is one they will stop running.
  - **How to add a test for a new control** — for a UI tier, say that locators come from the book
    (`ostler locators <screen> --json`) rather than being hand-written against the DOM, so a spec
    and the doc it verifies cannot drift apart silently.
  - **What CI gates** — the job name and whether it blocks merge. A tier CI does not run is
    documentation of an intention, and should say so plainly rather than imply enforcement.
  Mark every step `provenance: derived`; the live walkthrough promotes them. If a tier's config
  exists but has no spec files, document it and **say the suite is empty** — an empty suite that
  looks configured is precisely the gap worth recording. Emit nothing.
- **journey** — trace a user path across surfaces by following the **leads-to** edges (start
  precondition → ordered steps → outcome) and write the `flow` node with linked `steps:`. Emit
  nothing (or a missing element you noticed).
- **fixup** — the `context` holds this node's `ostler doctor` findings. Fix **each** by its mechanical
  remedy (`fmt` for casing/order; `scaffold`/add the heading for a missing section; fix the target
  for dangling links). Emit nothing.
- **backfill** — the `context` holds one document's grounded findings (a `missing-required-bullet`
  the doc predates, an `invalid-role`, an `unnamed-interactive`, an `ambiguous-locator`, an
  `unreachable-screen`), sorted by line. Unlike a `fixup`, **the finding does not tell you the value** —
  you must derive it from the source and cite what you read.
  - **Read the source once, then fix every finding it explains.** The findings in one item
    share a document and usually a cause — the same route module, the same component file —
    so work top-down through the list rather than treating each as a fresh investigation.
    Every finding in the item is yours to resolve this turn.
  - Open the node's `code:` target and read it. Write each missing bullet from what the code
    actually does: for a `screen`, `route:` from its route definition, `requires:` from the guard
    wrappers that enclose it, `params:` binding each `:token` in the route to the interaction that
    mints that entity (link it — that is what makes the dependency reachable).
  - For a `component`/`interaction`, `role:` and `name:` come from the **rendered accessibility
    contract**, not from the tag: read the JSX/template for an explicit `role=`, then `aria-label` /
    `aria-labelledby` / the visible text that would become the accessible name. An element with an
    explicit `role=` overriding its tag is the case that matters most and the easiest to miss.
    `keyboard:` comes from the key handlers and `tabIndex` you can see; write `none` when the
    control is genuinely pointer-only.
  - **`role:` is one bare ARIA token and nothing else** — `link`, not `` `link` — renders an `<a>``
    via ListItemButton`` and not `` `progressbar` (implicit MUI role)``. The value is fed straight
    into `getByRole`, so a justification appended to it produces a locator matching nothing. The
    same applies to `name:` — the bullet holds the accessible name itself; how you determined it
    goes in prose.
  - **Move the justification into prose — do not delete it.** Trimming `role: n/a — non-visual
    wrapper, never renders its own DOM` down to `role: none` satisfies the linter and destroys the
    only sentence explaining *why*, which is the part a reader cannot re-derive from the bullets.
    Cut the value down to the bare token **and** add the explanation to the node's prose in the same
    edit. A repair that loses knowledge is a worse outcome than the finding it closed.
  - Write the bare word `none` for an empty value. `n/a`, `-` and similar are understood, but the
    book should converge on one spelling.
  - `ambiguous-locator` means two controls on one screen carry the same `role:` and `name:`. Read
    both in the source and settle which of three cases it is:
    - **One is mislabelled** → correct the wrong `role:`/`name:` to what the source actually renders.
    - **They can never be in the DOM together** (mutually-exclusive states — one error slot cleared
      before the other is set; alternative variants of one shell chosen by a switch) → add
      `exclusive-with: [the sibling](#its-anchor)` to one of them. This is a *claim* about runtime,
      grounded in the code that makes them exclusive — cite it in prose. It is not a way to quiet a
      collision you did not investigate.
    - **They genuinely co-render with the same name** (a trigger button and the confirm button of
      the dialog it opens; two Save buttons both visible for one user) → that is a real
      accessibility defect. **Leave the finding standing** and record what you saw in prose;
      **do not invent a distinguishing label** the UI does not have, and do **not** write
      `exclusive-with` — they are not exclusive.
  - `unnamed-interactive` means an operable control has no accessible name. Find its label in the
    source. If there genuinely is none, the app has an unlabeled control — again, record it rather
    than name it for the app.
  - **`none` is a claim, not a default.** Write `- requires: none` only when you have read the route
    module and seen that no guard wraps it; `- params: none` only when the route has no `:token`.
    Say in the doc's prose what you checked. An unverified `none` is worse than the missing bullet:
    the bullet reads as *unknown* and will be re-queued, while `none` reads as *verified
    unconditional* and silently ends the inquiry — and every consumer downstream believes it.
  - If the source does not settle it, **leave the bullet off** and say why in `doc_status`. A node
    that stays red is a correct outcome; a node made green by a guess is not.
  - Emit nothing.

**Do not run a full `ostler doctor` to check your own work.** It lints the entire repository — tens
of seconds on a large book — to answer a question about one node, and multiplied across a drain of
hundreds of items that dwarfs the actual documenting. Run `ostler fmt <touched files>` and stop
there. The checkpoint re-runs doctor once per round and **re-queues any finding you did not fix**,
so a mistake costs you one more item next round, not a missed defect. If you want to confirm a
specific bullet landed, re-read the file you just wrote.

Every path link you write must resolve; put a node's key relations in its **opening prose** (a file
node's graph links are its intro region). Never invent a `verify:` — omit if no test exists.

## Output

Emit the items your investigation revealed (empty list if none). Deduped downstream by
(kind, target), so re-emitting a known item is harmless.

```json
{"discovered": [{"kind": "element", "target": "…", "context": "…"}], "doc_status": "documented"}
```

`doc_status` ∈ `documented` | `skipped` (nothing real to document for this item) | `partial`.
