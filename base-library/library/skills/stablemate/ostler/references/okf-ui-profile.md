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
`raises:`, `status:`, `errors:`, `auth:`, a command's `errors:`/`exits:`, `persistence:`, `emits:`,
`consumes:`, `concurrency:`, `idempotency:`, `required:`, `default:`, `semantics:`, a flow's
`start:`/`end:` — is minted as **one obligation** and proved by **one QA scenario**. Which keys
are normative on which type is a flag on the registry's bullet declaration
(`registry.BulletKey.normative`), so a graded key is by construction one `fmt` orders and
`doctor` recognizes. So a bullet that carries a paragraph is several
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
`undeclared-obligation`, `unknown-bullet`, `unminted-claim`, `weak-check` and
`unstated-precondition` (warns),
whose remedy is a judgement about the *source*: only the code can say which clauses are separate
requirements, and cutting the bullet on punctuation invents obligations nobody can prove.

| Code | Means | Remedy |
|---|---|---|
| `unknown-type` | `type:` isn't a recognized OKF type | fix the frontmatter `type:` |
| `bad-heading-type` | `## interactions` (wrong casing of a known heading) | `ostler fmt` |
| `missing-required-section` | a surface lacks a required `## Heading` (e.g. `cli` without `## Commands`) | `ostler scaffold` / add the heading |
| `missing-required-bullet` | a node lacks a required **key** (e.g. `interaction` without `on:`/`does:`) | `ostler scaffold` stubs it (key presence, not value) |
| `overlong-normative-bullet` | one obligation-minting bullet runs past 700 characters of prose | split it into one bullet per provable claim |
| `compound-normative-bullet` (warn) | one bullet states several observations — enumerated status codes, several error names, semicolon-joined clauses | split it: one bullet is one obligation, proved by one scenario |
| `unknown-bullet` (warn) | a profile key on a type that does not declare it — `verify:` on a concept, `does:` on a component, `exits:` on a method — so here it is inert: nothing orders, grades or grounds it, and no `verify:` binds to it. A key no type declares (`meaning:`) is the author's own and is not reported | move the claim under a key the type mints from, the observation onto the node that states the claim, or the bullet into prose |
| `unminted-claim` (warn) | a node that mints no obligation at all, yet one of its bullets reads like a claim — a status code, an error name, a lifecycle verb, a `must`/`returns`/`rejects` — under a key the type does not declare (`errors:` on a concept, `outcome:` in an untyped section, an author's own `rules:`). Nothing will ever ask a plan to prove it. Reported once per node, at the first such bullet; a node that mints even one obligation is never asked | move the claim under a normative key of that type (the message lists them), or onto the node that states it, or rewrite it as prose if it was description all along |
| `unparsed-check` | a `verify:` value is not a call from the check vocabulary (a test id, an unknown name, a bad argument) | rewrite it as `name(arg=…)`; a test citation belongs in `tests:` |
| `undeclared-obligation` (warn) | the node mints obligations and declares no `verify:` at all — nothing says what observing them looks like | declare a check per observation; the node is the only place that knows what the behaviour promised |
| `weak-check` (warn) | every check the node declares passes on the defect it is meant to catch — a field asserted by presence with no value, a `2xx` naming neither `path:` nor `title:` | name the value, the route or the title the claim turns on |
| `unstated-precondition` (warn) | a bullet says the node creates or removes something, and the checks read only the state afterwards — the same state a no-op leaves | declare the change as a change: `created(subject=…)` / `removed(subject=…)` |
| `qa-fixture-bullet` | a `fixture:` value is not `name [arg ...] [— prose]` — a capitalised name, unbalanced quoting, nothing at all | rewrite the head as the key `agents.yml` declares it under |
| `unknown-book-fixture` | a `fixture:` names an arrangement the repo never declared under `qa: {fixtures:}` | declare it, or name the one that already reaches that state |
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

**Owning keys.** `qa context` maps a story's changed files onto the book through the bullets whose
value names a file the node is documented against: `code:` on every type, plus `openapi:` on a
`server`/`endpoint`, `file:` on a `format`, and `config:` on an `environment` or a `format`
(`registry.owning_keys`, the `BulletKey.owns` flag). A changed file no owning bullet claims is an
`unmapped-change` error in the packet; a file a typed bullet names needs no second `code:`
citation, and citing one path under two keys is one owner, not two. `tests:` never owns — a test
is evidence, not the node's subject. `config:` does one thing more: the packet drops stack
configuration (`Pulumi.<stack>.yaml`, build manifests) from the change surface by default, and a
path declared under `config:` is a production unit regardless — one bullet per file
(`- config: pulumi/Pulumi.dev.yaml`), beside the program's `code:`. It is not a grounding key; a
config file may be gitignored or env-local.

**`verify:` is not one of them.** It declares the *observation* that fulfils the node's
obligations, as a named check with typed arguments from ostler's vocabulary — `http_status`,
`json_path`, `unchanged`, `keys_unchanged`, `count`, `absent`, `created`, `removed`, `visible`,
`persists`, `emitted`, `omits`, `conflict_on_stale`:

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
bullet: the pairing *is* written down — each `verify:` observes the nearest normative bullet above
it, and one written before any of them belongs to the node's contract — but the per-claim version of
this gap is `qa validate`'s `claimed-but-unasserted`, raised against the plan that has to prove it.
So what this asks is whether the node declares any observation at all. A node that
declared and got the call wrong gets `unparsed-check` and not this, for the same reason an overlong
bullet is not also reported as compound: one defect, one finding, one thing to waive.

**Declaring something is not declaring an observation.** A check that is green whatever the code
does leaves the obligation exactly as unprovable as no check at all, and `weak-check` /
`unstated-precondition` are the two shapes of that a linter can see: a value asserted by presence
alone, a success status naming neither route nor title, a creation or a delete read only after the
action. The bar itself — name the state of the world in which the check goes red, assert the
before-state rather than assuming it, discriminate the claim from its nearest plausible defect —
is the [[falsifiable-verification]] skill.

**`fixture:` is the third leg of the same triple.** The normative bullets say what the node
claims, `verify:` says what observing the claim looks like, and `fixture:` says how to reach the
state the claim is true in. It goes in the book for the same reason the check does: which
arrangement a claim is documented in is a fact about the claim, not about whichever plan happens
to check it this week — so a plan compiled from the book alone opens with the arrangement instead
of a marker an author fills in by reading the implementation.

```markdown
- fixture: seeded_accounts — two holders and one adjuster exist in the auth emulator
- fixture: seeded-ledger 3 draft — three draft policies on file
```

The grammar is `name [arg ...] [— what state it leaves behind]`, not a call: `qa.fixture` takes a
name the repo declared under `qa: {fixtures:}` plus positional strings appended to the declared
argv, and spelling it as Python would invite a book to write arguments the harness cannot bind.
The head is what the harness runs; the tail is what a person reads, and it becomes the scenario's
precondition. Doctor grounds the name (`unknown-book-fixture`) and the grammar
(`qa-fixture-bullet`).

**Attribution is deliberately not the check's.** A `verify:` written above every normative bullet
observes the node's own contract and nothing else — an observation is specific by nature, and
crediting it to claims it was not written for is how a weak check comes to cover a sharp one. An
arrangement written there is the state the node *as a whole* is documented in, so it fans out to
every obligation the node mints; one written under a claim adds a second state to reach rather
than replacing the ambient one. Give a node no `fixture:` when it needs none — an endpoint that
reads no state and asks for no identity is documented in the empty arrangement, and naming one
would describe a state nothing needs.

### Navigating the UI graph

`ostler list --type screen|component|interaction|cli|command|server|endpoint|invocation|flow|concept|format`
lists nodes (section nodes report their `path#anchor` id + `anchor`); `ostler search <q>` covers
UI-node bodies; `ostler trace <id|slug|anchor>` walks a node's outbound links (with
`[ok]`/`[DANGLING]`/`[MISSING ANCHOR]` status) and inbound referrers.

