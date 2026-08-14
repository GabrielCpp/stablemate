# The OKF UI profile — surfaces, elements, behaviors

The typed-node branch of [`ostler`](../SKILL.md): the profile of OKF that describes UIs, CLIs
and HTTP/WS servers as a navigable graph. Reached when you are authoring or linting nodes
under `docs/features/` — the type table, where nodes live, the completeness bar, the
scaffold→fmt→doctor loop, and every `doctor` error with its remedy. Planning docs (epics,
stories, seeds) do not come here.

A *profile* of OKF for describing UIs, CLIs, HTTP/WS servers, and the concepts they serve as a
navigable graph (full spec: `docs/okf-ui-profile.md`). Ostler recognizes these UI types as
first-class Concepts — listed, searched, traced, scaffolded, formatted, **linted**, and queryable
with `ostler graph`. Use these instead of prose when you want a machine-readable hook: enumerate a
screen's components, a concept's methods, a format's fields, or follow which interaction fires.

| Role | GUI | CLI | HTTP/WS | shared |
|---|---|---|---|---|
| **surface** (you interact with it) | `screen` | `cli` | `server` | |
| **element** (part of a surface) | `component` | `command` | `endpoint` | |
| **behavior** (one event or call) | `interaction` | `invocation` | `invocation` | |
| **member** (of a concept/format) | | | | `method`, `field` |
| **journey** (ordered path) | | | | `flow` |
| **noun** (domain *or* code) | | | | `concept` |
| **artifact / data shape** | | | | `format` |

**File vs section (author's choice).** A node is either its **own file** (identity = path; every
top-level `concept` gets one so others can link it) *or* a **section** inside a larger doc,
identified by `path#anchor`. A section gets its type two ways — use whichever reads best:
- **container heading** — a `### <id>` under a typed `## Heading`: `## Components`→`component`,
  `## Commands`→`command`, `## Endpoints`→`endpoint`, `## Interactions`→`interaction`,
  `## Invocations`→`invocation`, `## Methods`→`method`, `## Fields`→`field`.
- **inline `type:` prefix** — `## concept: the agent node runs a turn`, `### field: timeout` — the
  token before the first `:` is the type, the rest is a human summary.

**Sections nest.** A typed section's typed descendants become its children at any depth, so a
`concept` can hold `### method:`s, a `format` can hold `### field:`s, and `ostler graph --path
'concept:agent / field:timeout'` walks straight to it. Put a member's precise, filterable attributes
in its own `- key: value` bullets (`sig:`/`abstract:` for a method; `type:`/`default:`/`required:`
for a field) — the heading is the summary, the bullets are what you query.

**Where nodes live — per service, then by context.** Each service owns `docs/features/<service>/`.
A multi-context service splits by context (`gui/screens/`, `gui/components/`, `http/`); a
single-context service (CLI-only workhorse) stays flat. Context-neutral nodes sit at the service
root: `concepts/` (nouns) and `flows/` (journeys). `ostler scaffold` places files here for you —
don't hand-pick paths.

**Links are plain markdown path links, never `[[wikilinks]]`** — `[diff](../concepts/diff.md)`,
`[row](changes-view.md#changes-file-row)`, same-file `[row](#changes-file-row)`. A bare link is
**neutral**; meaning lives in the prose beside it. Two optional relation bullets layer a name on a
link: `parent:` (part-of/containment) and `extends:` (is-a/reuse). A selector chooses one
implementation of an abstraction via a plain `refs:` link (see the profile §7.11 pattern).

**Document flags & arguments item-by-item, not as a token dump.** Write `flags:` / `args:` as a
**nested bullet list** — one child per flag / positional — each saying *what it does, in which
context it applies* (fresh start vs resume, which mode, its default), with inline links to the
`concept`/`format`/command it touches. `- flags: --a, --b, --c` with no explanation is a smell.

**One provable claim per normative bullet.** A normative bullet — `does:`, `when:`, `returns:`,
`raises:`, `status:`, `error:`, `auth:`, `persistence:`, `emits:`, `consumes:`, `concurrency:`,
`idempotency:`, `required:`, `default:`, `semantics:`, a flow's `start:`/`end:` — is minted as **one
obligation** and proved by **one QA scenario**. So a bullet that carries a paragraph is several
requirements wearing one id, and the scenario covering it proves whichever clause the planner
happened to read; the rest is documented, claimed as covered, and never tested. Split on the seams
that are really separate: the success effect, each error case, what is persisted, what is emitted.
Repeat the key — a repeated `- does:` is a list of obligations, which is exactly what you want.
`doctor` errors past 700 characters of prose.

**No orphans — everything reachable from the surface root.** Every node links outward to what it
relates to, and the `screen`/`cli`/`server` index links its key concepts/formats in its *own*
body so `ostler trace <root>` walks to every node. Don't bury a structural pointer (a flag that
selects a concept, a format's consumer) in prose only — put it in the node's bullets. After
authoring, `ostler trace <root>` should reach the whole subgraph; a node nothing links to needs a
home.

### The completeness bar — the book, not a changelog

OKF is the **full, always-current spec** of the system, authored to be **complete enough to
regenerate behavior-equivalent code** from the docs plus the team's stack skills (profile §8):

- **Spec-complete per node** — fields with `type`/`required`/`default`, flags/args item-by-item,
  `does:` as ordered effects, algorithms as ordered steps, errors/exit/status codes, and for UI the
  `dom:`/`props:`/`states:`/`a11y:` contract. A lone `code:` stub is below bar.
- **Spec, not implementation** — the node says *what* the code does; the *how* (patterns, idioms,
  libraries, structure) lives in the stack skills, never the book. `code:` anchors the impl.
- **The book, not a changelog** — a story is a delta; its doc step *merges* into these nodes so
  they read as the complete current reality (never "this story added X").

Completeness is a **review** standard (the doc gates + the auditor), not a `doctor` gate — a linter
can't judge "enough to regenerate." Reach for [[documentation]] (one-story merge) or [[okf-modeling]]
(bulk build) to apply it.

### Scaffold → author → fmt → doctor (the authoring loop)

```bash
ostler scaffold screen changes-view --service groom --title "Changes view"   # file node → gui/screens/
ostler scaffold interaction click-file-opens-diff --in <the screen doc>       # section node under ## Interactions
```
`scaffold` writes the node in its canonical place with frontmatter, the H1, its bullet **stubs**,
and (for surfaces) the `required_sections` skeleton. Then **author the prose and fill the bullets
by editing the `.md` directly** — the body is yours. Finally:

```bash
ostler fmt docs/features/<svc>/…      # canonicalize: frontmatter key order, bullet order/spacing,
                                       # `does:` → nested, heading casing, `### id` kebab anchors
ostler doctor                          # gate: non-zero exit on any error
```

`ostler fmt` is the mechanical shape-fixer (the `ruff format` to doctor's `ruff check`); it never
touches prose. Scaffold output is already canonical.

### The mandatory linter (doctor errors — all with a deterministic remedy)

Unlike the draft profile's original "warns, never blocks" stance, UI conformance is a **hard
`doctor` gate**: every rule is `error`-severity, carries a `path:line` location, and has a
mechanical fix, so a workflow node can gate on `ostler doctor` and always converge. The
exceptions are `overlong-normative-bullet`, `compound-normative-bullet`,
`undeclared-obligation`, `weak-check` and `unstated-precondition` (warns), whose remedy is a
judgement about the *source*: only the code can say which clauses are separate requirements, and
cutting the bullet on punctuation invents obligations nobody can prove.

| Code | Means | Remedy |
|---|---|---|
| `unknown-type` | `type:` isn't a recognized OKF type | fix the frontmatter `type:` |
| `bad-heading-type` | `## interactions` (wrong casing of a known heading) | `ostler fmt` |
| `missing-required-section` | a surface lacks a required `## Heading` (e.g. `cli` without `## Commands`) | `ostler scaffold` / add the heading |
| `missing-required-bullet` | a node lacks a required **key** (e.g. `interaction` without `on:`/`does:`) | `ostler scaffold` stubs it (key presence, not value) |
| `overlong-normative-bullet` | one obligation-minting bullet runs past 700 characters of prose | split it into one bullet per provable claim |
| `compound-normative-bullet` (warn) | one bullet states several observations — enumerated status codes, several error names, semicolon-joined clauses | split it: one bullet is one obligation, proved by one scenario |
| `unparsed-check` | a `verify:` value is not a call from the check vocabulary (a test id, an unknown name, a bad argument) | rewrite it as `name(arg=…)`; a test citation belongs in `tests:` |
| `undeclared-obligation` (warn) | the node mints obligations and declares no `verify:` at all — nothing says what observing them looks like | declare a check per observation; the node is the only place that knows what the behaviour promised |
| `weak-check` (warn) | every check the node declares passes on the defect it is meant to catch — a field asserted by presence with no value, a `2xx` naming neither `path:` nor `title:` | name the value, the route or the title the claim turns on |
| `unstated-precondition` (warn) | a bullet says the node creates or removes something, and the checks read only the state afterwards — the same state a no-op leaves | declare the change as a change: `created(subject=…)` / `removed(subject=…)` |
| `unresolved-relation` | a `parent:`/`extends:`/`detail:`/`on:` link doesn't resolve | fix the link target |
| `dangling-link` | a plain link's target **file** is missing | fix the path or create the target |
| `missing-anchor` | file exists but `#anchor` heading isn't there | fix the anchor |

**Link validation is document-wide.** `dangling-link` / `missing-anchor` are checked for **every
link in every doc file**, not only links inside an indexed node — a broken link is broken whether or
not the graph happens to cover it. Links **inside code** (fenced blocks and `` `inline` `` spans) are
skipped, so `arr[i](x)` in a snippet is never mistaken for a link.

**Convergence contract:** `missing-required-bullet` checks that the **key** is present, not its
value — so `scaffold`'s stubs clear it. **`code:` / `tests:` bullets are code refs
(`path::symbol`), grounded at a *later* QA gate, never at author time** — doctor deliberately does
*not* flag them as dangling links.

**`verify:` is not one of them.** It declares the *observation* that fulfils the node's
obligations, as a named check with typed arguments from ostler's vocabulary — `http_status`,
`json_path`, `unchanged`, `keys_unchanged`, `count`, `absent`, `created`, `removed`, `visible`,
`persists`, `emitted`, `conflict_on_stale`:

```markdown
- verify: http_status(409, title="Manifest Conflict")
- verify: unchanged(subject="manifest", except_fields=["pages.getting-started.fr.slug"])
- tests: `api/publish_test.go::TestPublish_Conflict`
```

Doctor grounds it against that vocabulary (`unparsed-check`), `ostler qa validate` refuses a QA
scenario that does not invoke the declared call, and the harness implements each name. A test id
names the code that ran, not the thing observed — which is why it moved to `tests:`, where its one
reader is regression failure attribution. On a runbook `step:`, `verify:` keeps its own older
meaning (how to tell the step ran) and is not a check.

**Declaring nothing is the failure `unparsed-check` cannot see.** `verify:` is required on no type,
so a node whose `does:`/`raises:`/`states:` bullets carry none is green while every obligation it
mints reaches QA with nothing to bind: `qa validate` has no declaration to enforce, and the evidence
map reports no deficit. `undeclared-obligation` is that gap, reported per **node** rather than per
bullet — `verify:` sits on the node, and pairing one check to one bullet is a judgement nobody has
written down yet — so what it asks is whether the node declares any observation at all. A node that
declared and got the call wrong gets `unparsed-check` and not this, for the same reason an overlong
bullet is not also reported as compound: one defect, one finding, one thing to waive.

### Navigating the UI graph

`ostler list --type screen|component|interaction|cli|command|server|endpoint|invocation|flow|concept|format`
lists nodes (section nodes report their `path#anchor` id + `anchor`); `ostler search <q>` covers
UI-node bodies; `ostler trace <id|slug|anchor>` walks a node's outbound links (with
`[ok]`/`[DANGLING]`/`[MISSING ANCHOR]` status) and inbound referrers.

