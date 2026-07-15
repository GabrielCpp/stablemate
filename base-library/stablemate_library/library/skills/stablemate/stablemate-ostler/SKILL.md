---
name: stablemate-ostler
description: "ostler CLI reference — the system-of-record for a repo's docs/ knowledge graph (epics, stories, seeds, knowledge, features as OKF Concepts, plus the OKF UI profile's surface/element/behavior/member/concept types — nested and typed): command interface, epic.md grammar, coverage model, the scaffold→fmt→doctor UI loop, `ostler graph` queries, and when a workflow agent should call it."
---

# Ostler

Load this skill when a workflow node, script, or prompt needs to read or mutate a repo's planning
docs (`docs/epics`, `docs/knowledge`, `docs/features`, `docs/specs`) — or when authoring a new
`workhorse` workflow that should integrate with the doc graph instead of hand-rolling its own
JSON state files.

`ostler` is a standalone, repo-agnostic CLI (`pipx install ostler` / `pip install ostler`) that
operates relative to the current working directory (`-C/--chdir DIR` to point elsewhere). It is
**the one tool that reads and writes the graph** — never hand-edit `epic.md`'s `## Seeds`/
`## Stories` sections or allocate ids yourself; call ostler instead so structure stays consistent
while agents/humans author the prose around it.

## Core model

Everything under `docs/` is markdown: an OKF (Open Knowledge Format) **Concept** is one `.md` file
with a YAML frontmatter block (only hard requirement: non-empty `type`) plus a markdown body.
**Identity is the path** — a Concept's id is its bundle-relative path minus `.md`.

There is **no** `seed.json`, `dependencies.json`, `inventory.json`, or `epics-todo.json`. An epic's
seeds and its story dependency-DAG live entirely inside that epic's own `epic.md`.

| `type` | Location | Identity | Required frontmatter |
|---|---|---|---|
| `epic` | `docs/epics/<epic>/epic.md` | `<epic>` (dir name) | `type`, `id`, `title` |
| `story` | `docs/epics/<epic>/stories/<slug>/story.md` | `<slug>` | `type`, `slug`, `status` |
| `knowledge` | `docs/knowledge/<area>/<name>.md` | path (`surface` alias) | `type`, `surface` |
| `feature` | `docs/features/<area>/<slug>.md` (or flat `docs/features/<slug>.md`) | `<area>/<slug>` | `type`, `slug`, `title` |
| `spec.plan` / `spec.review` / `spec.qa` | `docs/specs/<slug>/*.md` | path | `type` |

Not Concepts (managed markdown, left in place as-is): `docs/backlog.md` (intake list), `docs/epics/index.md`
(epics queue).

## `epic.md` — single source of truth for an epic

```markdown
---
type: epic
id: pred-15
title: Account Credits "Aperçu" Billing Body at Legacy Parity
status: in-progress        # optional: planned | in-progress | done
---

Free narrative prose (any headings: ## Goal, ## Method, ## Acceptance, …).

## Seeds

### apercu-landing-body
- status: researched       # backlog | researched | covered | resolved | dropped | deferred
- surface: account-billing/apercu-billing-body
- legacySurface: /{_locale}/employe/profile/edit (BuyCreditsAction)
- backing: GET /billing/customer → CustomerDetails

The first paragraph after the metadata bullets is the seed summary; further prose is free markdown.

## Stories

### 01-apercu-billing-body
- title: Account Credits "Aperçu" Billing Body at Legacy Parity
- id: pred-16
- covers: apercu-landing-body, apercu-subscription-change-plan-link
- depends on: (none)
- phase: 1
- effort: 8-10 hours
```

- `## Seeds` → `### <seed-id>` per seed (omit the whole section for a seedless epic).
- `## Stories` → `### <slug>` per story, carrying the edges: `covers:` (seed ids) and
  `depends on:` (sibling slugs).

## Command interface

All read commands accept `--json`. Mutating commands allocate ids as needed and write canonical
markdown in place.

**Global**: `ostler --version`, `ostler -C/--chdir DIR <command> …`

**Inspect**
```bash
ostler doctor [--epic SLUG] [--json] [--no-schema]   # conformance + referential integrity; non-zero on a break
ostler trace  <id|slug|gap|surface|path>             # walk the graph from any node
```

**Retrieve**
```bash
ostler list   --type epic|story|knowledge|feature|spec|seed|gap [--epic E] [--status S] [--json]
ostler search <query> [--type T] [--owner O] [--tag G] [--json]   # full-text match over node prose
ostler query  gaps-in-story|stories-covering-seed|surfaces-referenced-by-story <arg> [--json]
ostler graph  [selectors…] [--tree|--ids|--json]     # query the node/edge/bullet graph
```

`ostler graph` is the **structural** query `search` can't do — it walks the *typed, nested* node
tree (every node carries its `- key: value` bullets, its resolved out-edges, and its
`title_path`/`type_path` hierarchy), so you filter precisely instead of by prose, **without `jq`**.
Selectors compose (AND); output is `--tree` (default), `--ids`, or `--json`:

```bash
ostler graph --surface SVC                       # the whole service, as an outline tree
ostler graph --path 'concept:agent / field:timeout'   # relative hierarchy query (/ =descendant, > =direct)
ostler graph --type field --under <id> --depth 1 # a node's direct children of a type
ostler graph --bullet 'code=mod.py::Sym' --ids   # dedup: is this symbol already grounded?
ostler graph --has-bullet code                   # coverage: every grounded node
ostler graph --orphans                           # nodes no edge points to (unreachable)
```

- **dedup before you scaffold** — `--bullet 'code=<symbol>'`: if a node already grounds it, enrich
  that node, don't make a second one. (`--path` for "does *this* nested node already exist?")
- **inventory coverage** — `--has-bullet code` lists every grounded node; diff against source symbols.
- **orphans** — `--orphans` is unreachable nodes, first-class (no `jq` walk).
```bash
ostler next-epic [--json]                            # next queued epic with unfinished work
ostler next-story <epic> [--json]                    # next runnable story (deps satisfied, not done)
ostler path spec <slug> | story <epic> <slug> | branch <slug> [--epic] [--is_epic emits feat/<slug>]
```

**Mutate** (allocates ids, writes markdown)
```bash
ostler create epic    <name>  --title T [--prefix P] [--json]
ostler create story   <epic> <slug> --title T [--covers a,b] [--depends a,b] [--prefix P] [--json]
ostler create feature <slug>  --title T [--area A] [--route R] [--prefix P] [--json]
ostler delete epic|story|feature <name>

ostler seed add    <epic> <id> [--status S] [--summary …] [--surface …] \
                               [--legacy-surface …] [--backing …] [--prerequisites …] [--source-bullet …]
ostler seed remove <epic> <id>
ostler set-status  <story> <status>

ostler backlog add <id> <text> [--section S] | ostler backlog prune <id> | ostler backlog list [--json]
ostler todo add <epic> [--front] | ostler todo prune <epic> | ostler todo reorder <e…> | ostler todo list [--json]
```
`create … --json` returns `{"ok": true, "id": "<allocated-id>", "message": "…"}`.

**Repair / approve**
```bash
ostler edit set-owner <gap> <story> [--write]   # dry-run by default; --write applies
ostler edit relink    <old-path> <new-path> [--write]
ostler edit rename    <old-slug> <new-slug> [--write]
ostler freeze   <ident> [--by WHO] [--note …]   # pin an approved story/seed as immutable ground truth
ostler unfreeze <ident>
```

**OKF UI profile** (surfaces / elements / behaviors — see "The OKF UI profile" below)
```bash
ostler scaffold <type> <name> [--service SVC] [--in FILE] [--title T] [--json]  # new node, canonically placed
ostler fmt [PATH…] [--check]              # canonicalize frontmatter/bullets/headings; --check = no writes, exit 1 if unclean
```

**Visual-fidelity check** (used by `coder`'s QA gates — see [[coder-workflow]])
```bash
ostler vet <screenshot> --manifest M (--cdp-url U | --regions FILE) --slug S [--state s] [--iou-threshold 0.5] [--json]
```

**QA context and execution control plane**
```bash
ostler qa context --base REV [--head REV|WORKTREE] --spec DIR \
  --source-root SURFACE=PATH [--source-root SURFACE=PATH ...] \
  [--story-file PATH] --json
ostler qa context-validate --spec DIR --json
ostler qa validate DIR/qa-plan.yml --spec DIR --json
ostler qa run DIR/qa-plan.yml --spec DIR --json
```

`qa context` writes `qa-okf-context.json` and its Markdown rendering beside the plan.
Blocking unmapped production changes use a nonzero process exit but still produce JSON;
workflow adapters must route that as `invalid`, not crash. Plan validation reports
`passed|invalid`. Execution reports `passed|failed|blocked|invalid` and owns deletion and
recreation of `qa/`, service/driver cleanup, `qa-run.ndjson`, `run-manifest.json`, and
evidence. `qa-plan.yml` and static `qa-inputs/` remain outside disposable `qa/`.

**Schema-checked workflow artifacts** (a workflow's plan/review/qa docs under `docs/specs/<slug>/`)
```bash
ostler artifact scaffold <kind> --spec DIR [--force]   # write the kind's skeleton into the spec dir
ostler artifact vet      <kind> --spec DIR [--json]    # validate the artifact against its contract
ostler artifact list     [--json]                      # show registered artifact kinds
```

## The coverage model

```
knowledge gaps[].owner  ->  story (epic.md ## Stories)  ->  covers: seed (epic.md ## Seeds)
```

`ostler doctor` checks OKF conformance (every Concept has a non-empty `type`) plus the typed
referential-integrity contract:

- **cross-epic references** — an id/slug used inside epic E that only resolves in another epic
- **orphan seeds** — an active seed no story covers
- **dangling references** — a `[gap:…]` tag, knowledge path, or sibling slug that resolves to nothing
- **stale owners** — a non-resolved gap whose `owner` is empty or points at a missing story
- **frozen drift** — an approved (frozen) story/seed that changed or vanished

It exits non-zero when any error-level finding is present (safe to gate a workflow node on).
Warning-level findings (`story-covers-no-seed`, `ungrounded-surface`) are reported but don't fail
the check.

## Id allocation, profiles, templates

- Ostler owns `.agents/ids.json` (`{prefix, counter, frozen}`) — `create epic|story|feature`
  atomically allocates the next `<prefix>-<n>`, scaffolds the markdown, and (for stories) inserts
  the `### <slug>` block into the epic's `## Stories`. There is no external id allocator.
- Profile is inferred from the tree: `full` when `docs/epics` exists (the epic/story/seed/knowledge
  coverage graph), `exploration` otherwise (knowledge/docs only, no coverage graph). Override via an
  `organization:` block in `ostler.yml`/`agents.yml`.
- For a documentation shape outside epic/story/knowledge/feature/spec, declare custom Concept kinds
  in `.agents/templates.yml` (`ostler template new/edit/find/delete/apply`), then operate on
  instances with the generic `ostler new/find/set/remove <kind> <name>` verbs.

## The OKF UI profile — surfaces, elements, behaviors

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
mechanical fix, so a workflow node can gate on `ostler doctor` and always converge.

| Code | Means | Remedy |
|---|---|---|
| `unknown-type` | `type:` isn't a recognized OKF type | fix the frontmatter `type:` |
| `bad-heading-type` | `## interactions` (wrong casing of a known heading) | `ostler fmt` |
| `missing-required-section` | a surface lacks a required `## Heading` (e.g. `cli` without `## Commands`) | `ostler scaffold` / add the heading |
| `missing-required-bullet` | a node lacks a required **key** (e.g. `interaction` without `on:`/`does:`) | `ostler scaffold` stubs it (key presence, not value) |
| `unresolved-relation` | a `parent:`/`extends:`/`detail:`/`on:` link doesn't resolve | fix the link target |
| `dangling-link` | a plain link's target **file** is missing | fix the path or create the target |
| `missing-anchor` | file exists but `#anchor` heading isn't there | fix the anchor |

**Link validation is document-wide.** `dangling-link` / `missing-anchor` are checked for **every
link in every doc file**, not only links inside an indexed node — a broken link is broken whether or
not the graph happens to cover it. Links **inside code** (fenced blocks and `` `inline` `` spans) are
skipped, so `arr[i](x)` in a snippet is never mistaken for a link.

**Convergence contract:** `missing-required-bullet` checks that the **key** is present, not its
value — so `scaffold`'s stubs clear it. **`code:` / `verify:` bullets are code refs
(`path::symbol`), grounded at a *later* QA gate, never at author time** — doctor deliberately does
*not* flag them as dangling links.

### Navigating the UI graph

`ostler list --type screen|component|interaction|cli|command|server|endpoint|invocation|flow|concept|format`
lists nodes (section nodes report their `path#anchor` id + `anchor`); `ostler search <q>` covers
UI-node bodies; `ostler trace <id|slug|anchor>` walks a node's outbound links (with
`[ok]`/`[DANGLING]`/`[MISSING ANCHOR]` status) and inbound referrers.

## When to reach for it

- Any workflow node that needs "what's the next thing to work on" → `next-epic`/`next-story`, not a
  hand-maintained queue file.
- Any node that needs to resolve a slug to a filesystem path (spec dir, story.md, branch name) →
  `ostler path`, not string-concatenation in a script.
- Any gate that checks graph health before letting a workflow proceed (e.g. author's
  `verify-surface-coverage.py`/`reconcile-artifacts.py`/an `ostler doctor` check) → shell out to
  `ostler doctor`/`ostler query` and branch on exit code or `--json` output, never re-implement
  referential-integrity checks by hand.
- Any resolver prompt that fixes a graph problem (dangling owner, orphan seed, cross-epic
  contamination) → `ostler edit set-owner/relink/rename` or `ostler seed`/`set-status`, never a raw
  edit of `epic.md`'s generated sections.
- Any node that documents a UI/CLI/server surface or a domain/code concept → the OKF UI profile
  (`scaffold`/`fmt`/`doctor`) above; for the create-or-refresh loop after a story, load
  [[documentation]]; to model a whole app's surface graph from scratch or from existing code, load
  [[okf-modeling]].
