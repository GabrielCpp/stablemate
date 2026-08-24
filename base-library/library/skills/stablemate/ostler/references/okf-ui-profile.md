# The OKF UI profile — surfaces, elements, behaviors

The typed-node branch of [`ostler`](../SKILL.md): the profile of OKF that describes UIs, CLIs
and HTTP/WS servers as a navigable graph. Reached when you are authoring or linting nodes
under `docs/features/` — the type table, where nodes live, the completeness bar and the
scaffold→fmt→doctor loop. The format itself — per-type keys, the check vocabulary, every
`doctor` code — is [[ostler-documentation]]'s `references/`. Planning docs (epics, stories,
seeds) do not come here.

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
| **operations** | | | | `runbook`, `environment` |

One reference per type — its keys, required sections, relationships, example and doctor codes —
is in [[ostler-documentation]] → `references/node-types/<type>.md`, and those are the authority
when this file and they disagree.

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

**One provable claim per normative bullet**, and which keys are normative is a flag on the
registry's bullet declaration rather than a list to memorise. The rule, the 700-character
ceiling, and how to split on the real seams are in [[ostler-documentation]] →
`references/bullet-grammar.md`; the per-type key tables are its `references/node-types/`.

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
  `role:`/`name:`/`placement:`/`keyboard:`/`states:` contract. A lone `code:` stub is below bar.
- **Spec, not implementation** — the node says *what* the code does; the *how* (patterns, idioms,
  libraries, structure) lives in the stack skills, never the book. `code:` anchors the impl.
- **The book, not a changelog** — a story is a delta; its doc step *merges* into these nodes so
  they read as the complete current reality (never "this story added X").

Completeness is a **review** standard (the doc gates + the auditor), not a `doctor` gate — a linter
can't judge "enough to regenerate." Reach for [[ostler-documentation]] (one-story merge) or [[okf-modeling]]
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

### The mandatory linter

Unlike the draft profile's original "warns, never blocks" stance, UI conformance is a **hard
`doctor` gate**: every rule carries a `path:line` location and a mechanical fix, so a workflow
node can gate on `ostler doctor` and always converge. The warns are the rules whose remedy is a
judgement about the *source* — only the code can say which clauses are separate requirements,
and cutting a bullet on punctuation invents obligations nobody can prove.

Every code, its severity, its trigger and its remedy are in [[ostler-documentation]] →
`references/doctor-codes.md`. Three facts about the linter are ostler's rather than the
format's, and live here:

- **Link validation is document-wide.** `dangling-link` / `missing-anchor` are checked for
  **every link in every doc file**, not only links inside an indexed node — a broken link is
  broken whether or not the graph happens to cover it. Links **inside code** (fenced blocks and
  `` `inline` `` spans) are skipped, so `arr[i](x)` in a snippet is never mistaken for a link.
- **Convergence contract:** `missing-required-bullet` checks that the **key** is present, not
  its value — so `scaffold`'s stubs clear it.
- **`code:` / `tests:` are code refs** (`path::symbol`) grounded at a *later* QA gate, never at
  author time; doctor deliberately does not flag them as dangling links.

**The bullet grammar itself is written down elsewhere.** Owning keys and what `qa context`
does with them, the check vocabulary behind `verify:`, `fixture:` as the third leg, and the
document-order rule that says which claim a check or an arrangement attaches to are in
[[ostler-documentation]] → `references/bullet-grammar.md` and `references/check-vocabulary.md`.
The bar a check has to clear to be an observation at all — name the state of the world in which
it goes red, assert the before-state rather than assuming it, discriminate the claim from its
nearest plausible defect — is the [[falsifiable-verification]] skill.

### Navigating the UI graph

`ostler list --type screen|component|interaction|cli|command|server|endpoint|invocation|flow|concept|format`
lists nodes (section nodes report their `path#anchor` id + `anchor`); `ostler search <q>` covers
UI-node bodies; `ostler trace <id|slug|anchor>` walks a node's outbound links (with
`[ok]`/`[DANGLING]`/`[MISSING ANCHOR]` status) and inbound referrers.

