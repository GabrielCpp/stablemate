# ostler

> Tend your documentation graph.

`ostler` is the single system-of-record for a repository's `docs/` knowledge graph. It **defines,
validates, searches and mutates** your planning docs — epics, stories, seeds, knowledge records and
features — as plain markdown **Concepts** (a strict profile of the
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)).

Everything is markdown. An epic's seeds and its story dependency-DAG live inside its `epic.md`; there
is **no** `seed.json`, `dependencies.json`, `inventory.json` or `epics-todo.json`. Ostler owns id
allocation and is the one tool that reads and writes the graph — so structure stays consistent while
humans (or agents) author the prose.

It is a standalone, repo-agnostic CLI that operates relative to the **current working directory**:
roots default to `<cwd>/docs/{epics,knowledge,features,specs}` and the organization name to the repo
folder name. Point it at any repo with `-C/--chdir`.

## Install

```bash
pipx install ostler          # recommended: isolated CLI on your PATH
# or
pip install ostler
```

For development against a local checkout:

```bash
pipx install --editable /path/to/stablemate/ostler --force
```

The package installs one console entry point, `ostler`.

## Quickstart

Ostler creates the *structure and ids*; you author the *content* into the skeletons it scaffolds.

```bash
# 1. See if the graph is healthy
ostler doctor

# 2. Scaffold an epic (allocates an id, writes docs/epics/0001-checkout-flow/epic.md —
#    the directory carries the order it was created in; `--json` reports the name it used)
ostler create epic checkout-flow --title "Checkout Flow at Parity"

# 3. Record a seed (a unit of intended work) in that epic's ## Seeds
ostler seed add checkout-flow address-step --status researched \
  --surface checkout/address --summary "Collect & validate the shipping address"

# 4. Cut a story that covers the seed (adds it to the epic's ## Stories, scaffolds story.md)
ostler create story checkout-flow 01-address-step \
  --title "Address step" --covers address-step

# 5. Ask what to work on next, then list the epic's stories as JSON
ostler next-story checkout-flow
ostler list --type story --epic checkout-flow --json
```

Then open the scaffolded `epic.md` / `story.md` and write the narrative, acceptance criteria, and
prose — ostler keeps the seeds, edges, ids and queue coherent around it.

## The hierarchy

A repository's knowledge lives under `docs/` as OKF **bundles** (directories of markdown Concepts).
A **Concept** is one `.md` file with a YAML **frontmatter** block (whose only hard requirement is a
non-empty `type`) and a markdown **body** using conventional headings.

**Identity is the path.** A Concept's id is its bundle-relative path without `.md`
(`docs/knowledge/profile/preference-summary.md` → `profile/preference-summary`). The reserved
filenames `index.md` (an ordered listing of a bundle) and `log.md` (history) are not Concepts.

### Entity types

| `type` | Location (repo-relative) | Identity | Required frontmatter |
|---|---|---|---|
| `epic` | `docs/epics/<NNNN-slug>/epic.md` | `<NNNN-slug>` (dir name) | `type`, `id`, `title` |
| `story` | `docs/epics/<NNNN-slug>/stories/<slug>/story.md` | `<slug>` | `type`, `slug`, `status` |
| `knowledge` | `docs/knowledge/<area>/<name>.md` | path (`surface` alias) | `type`, `surface` |
| `feature` | `docs/features/<area>/<slug>.md` *(or flat `docs/features/<slug>.md`)* | `<area>/<slug>` | `type`, `slug`, `title` |
| `spec.<stem>` (`spec.plan`, `spec.review`, `spec.qa`, `spec.executive`, `spec.vet`, …) | `docs/specs/<slug>/*.md` | path | `type` |

**Epic directories carry their creation order** — `create epic checkout-flow` writes
`docs/epics/0001-checkout-flow/`, so a listing of `docs/epics` reads as the work order rather than
as an alphabetized set. The number is *not* an identity (that is the minted `id`, which never
changes), so the bare slug still names the epic in every command: `ostler todo add checkout-flow`,
`--epic checkout-flow`, `create story checkout-flow …`. Use `ostler path epic <slug>` when you need
the directory itself, and read `--json`'s `name` back after `create epic` rather than assuming one.

`spec.*` Concepts are process artifacts: typed and conformance-checked, but ostler does not own their
internal schema. The subtype is the file's stem (`executive.md` → `spec.executive`); mint them with
`ostler create spec <slug> <doc>`, which is idempotent and also retro-stamps free-form docs.
**Not Concepts** (managed markdown, left in place): `docs/backlog.md` (an intake list)
and `docs/epics/index.md` (the epics queue).

### `epic.md` — single source of truth for an epic

An epic's `epic.md` carries the narrative **and** its seeds and story dependency-DAG. Ostler parses two
canonical sections back out of the markdown by exact heading:

```markdown
---
type: epic
id: ACME-01JBXR7K9QZ4M2T8VNF3HD6PWC
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
- id: ACME-01JBXR7M4E0S9YCG5NAKQ2TZVJ
- covers: apercu-landing-body, apercu-subscription-change-plan-link
- depends on: (none)
- phase: 1
- effort: 8-10 hours
```

- `## Seeds` → `### <seed-id>` per seed (omit the whole section for a seedless epic).
- `## Stories` → `### <slug>` per story, carrying the **edges**: `covers:` (seed ids) and
  `depends on:` (sibling slugs). The detailed spec lives in the story's own `story.md`.

See [SPEC.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/SPEC.md) for the
authoritative, formal definition of every field, status enum, and conformance rule.

## Command interface

All read commands accept `--json`. Mutating commands allocate ids as needed and write canonical
markdown in place. `ostler --version` prints the version; `-C/--chdir DIR` runs any command as if
from `DIR`; `--handles` / `--full-ids` choose how ids are printed (see
[Short handles](#short-handles) — human output abbreviates, `--json` does not, and a handle is
accepted as input either way).

| Verbs | What they do |
|---|---|
| `doctor` `trace` | check conformance and referential integrity; walk the graph from any node |
| `list` `search` `query` `next-epic` `next-story` `path` | read the graph — what exists, what covers what, what to work on next |
| `create` `delete` `seed` `set-status` `backlog` `todo` | mutate it — scaffold an epic/story/feature/spec, record a seed, move the queue |
| `edit` `freeze` `unfreeze` | repair a rename across the whole graph, or pin an approved story as ground truth |
| `template` `new` `find` `set` `remove` | declare a repo's own Concept kinds and operate on their instances |
| `graph` `reach` `locators` `coverage` `scaffold` `fmt` `vet` | the `docs/features/` node/edge book — see below |
| `qa` `artifact` | the verification control plane — see below |

`edit` is **dry-run unless `--write`**, so a rename across a whole graph is reviewable before it
happens; `create … --json` returns
`{"ok": true, "id": "<allocated-id>", "name": "<name-on-disk>", "message": "…"}` — `name` is what
`create epic` numbered the directory, which is why it is reported rather than assumed.

Every verb, with its real flags and what each one operates on, is in
[docs/CLI.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/CLI.md).

### The feature graph

Alongside the epic/story planning graph, ostler tends `docs/features/` — a typed node/edge book
describing a product's actual surfaces (screens, components, endpoints, flows). `graph` queries it,
`reach` derives the documented click-path between two screens, `locators` emits the Playwright
locator for every documented control, `coverage` joins the book's `code:` citations against a source
inventory, and `vet` checks a rendered screenshot against what the book claims. The visual-fidelity
contract is in
[docs/VET.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/VET.md).

### Verification control plane

`ostler qa` owns the bookkeeping of a QA run. `qa context` turns a base/head diff into a
deterministic obligation scope for one story; `qa validate` and `qa run` then execute a version-2
plan that declares command, Playwright and Maestro targets and maps every scenario to
acceptance-criterion and OKF obligation ids. Validation rejects unknown coverage, unsupported actions
and locators, disposable pre-run inputs, literal secrets, and coverage without a machine assertion.
Each run starts with an empty `qa/`, writes an append-only ledger and content-hashed manifest, and
returns `passed`, `failed`, `blocked`, or `invalid`. `ostler artifact` schema-checks what a workflow
produces (a plan, a review resolution, a QA outcome) against a registered contract.

```bash
ostler qa context --base <rev> --head WORKTREE --spec docs/specs/<story> \
  --source-root web=web --source-root api=api --story-file docs/epics/.../story.md
ostler qa validate docs/specs/<story>/qa-plan.yml --json
ostler qa run      docs/specs/<story>/qa-plan.yml --json
```

The run contract is in
[docs/QA-RUN.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/QA-RUN.md), the
artifact contracts in
[docs/ARTIFACT-CONTRACTS.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/ARTIFACT-CONTRACTS.md),
and the design rationale in
[docs/plans/ostler-qa-verification.md](https://github.com/GabrielCpp/stablemate/blob/main/docs/plans/ostler-qa-verification.md).

## Python API

Everything the CLI does is available in-process through the `Ostler` facade — the
library face of the tool (the analog of GitPython's `Repo` or PyGithub's `Github`).
Prefer it over spawning the CLI and parsing its JSON when you're calling ostler from
Python: you load the graph once and get back plain objects (`dict`/`list`/`str`, a
`Result`, an `EditPlan`, a `QaOutcome`) instead of a subprocess and a stdout scrape.

```python
from ostler import Ostler

okf = Ostler("path/to/repo")          # graph root discovered upward, like `-C DIR`; None ⇒ cwd

okf.todo()                            # ["checkout-flow", …]        (ostler todo list)
okf.list("story", epic="checkout-flow")   # [{"slug","status",…}]  (ostler list --type story)
okf.next_story("checkout-flow")       # {"slug": …} | None          (ostler next-story)
okf.spec_path("01-cart")              # "docs/specs/01-cart"        (ostler path spec)
okf.doctor()                          # {...} referential-integrity report (ostler doctor --json)

res = okf.create_story("checkout-flow", "02-pay", "Payment", covers=["seed-1"])
res.ok, res.entity_id                 # a Result, not parsed JSON   (ostler create story)
okf.set_status("01-cart", "QA passed")
```

The loaded graph is a **snapshot**: reads reuse one cached load; a mutation
(`create_*`/`add_seed`/`set_status`/`backlog_*`/`todo_*`/`settle_review`) applies
against a fresh load and invalidates the cache, so the next read reflects it
(`reload()` forces a refresh). A read never returns `None` — an unloadable graph
*raises*. The QA/artifact/edit surface is on the same object
(`qa_context`/`qa_validate`/`qa_run`/`qa_context_validate`, `artifact_vet`,
`settle_review`), lazy-imported so a read-only caller never loads the QA/vet
machinery. `from ostler import load` returns the bare `Graph` if you want the
functional core directly.

### `ostler.markdown` — the markdown parser everything reads through

The graph is markdown, so `ostler.markdown` is the one parser for it, and it is a public
module: workhorse workflows, benchmarks and any other caller query documents through it
rather than matching their own regexes. `split(text)` returns a `MarkdownDoc` carrying the
parsed `frontmatter` (a real front-matter token, not a fence regex) alongside a byte-exact
`body` — `render()` round-trips a document a human wrote without reflowing it.

```python
from ostler import markdown

doc = markdown.split(path.read_text(encoding="utf-8"))
doc.frontmatter["type"]                    # YAML decided the types, not a line split
doc.find_section("Stories").bullets        # Bullet.label / .value / .bracketed
doc.find_bullet("status").value            # `- **Status**: Done` → "Done"
for table in doc.walk_tables():            # GFM pipe tables: .headers / .rows
    table.records                          # rows keyed by header; also .column("Type")
for label, href, line in markdown.iter_links(text):
    ...                                    # never a link inside a fence or code span
```

A heading, bullet, table row or link inside a fenced code block is not one — that falls
out of the token stream rather than being approximated. Line numbers on `Section` and
`Table` are 0-indexed and body-relative; `doc.body_offset` converts to a file line. The
rule this serves, and the parser for every other format, is the
`stablemate-structured-parsing` skill in the base library; `make check-parsers` enforces
it.

## The coverage model

```
story (epic.md ## Stories)  ->  covers: seed (epic.md ## Seeds)
```

`ostler doctor` checks OKF conformance (every Concept has a non-empty `type`) plus the typed
referential-integrity contract:

- **cross-epic references** — an id/slug used inside epic E that only resolves in another epic;
- **orphan seeds** — an active seed no story covers;
- **dangling references** — a knowledge path or sibling slug that resolves to nothing;
- **frozen drift** — an approved (frozen) story/seed that changed or vanished.

It exits non-zero when any error-level finding is present, so it drops straight into CI or a pre-commit
hook. Warning-level findings (e.g. `story-covers-no-seed`, `ungrounded-surface`) are reported but do
not fail the check.

## Id allocation

Ostler owns `.agents/ids.json` (`{prefix, frozen}`). `create epic|story|feature` allocates an id,
scaffolds the canonical markdown, and (for stories) inserts the `### <slug>` block into the epic's
`## Stories`. There is no external id allocator.

An id is `<PREFIX>-<ULID>` — the repo prefix (first four letters of the repo name, pinned on first
use) plus a monotonic ULID: 26 Crockford-Base32 chars encoding a millisecond timestamp and 80 bits
of randomness. It sorts by mint time and needs **no coordination**, so two worktrees, two processes
or two clones never collide and there is no counter to lock or merge. (The former `<prefix>-<n>`
counter could not be distributed; ids minted under it keep resolving — an id is an opaque string.)

### Short handles

A 26-char id is not a thing anyone retypes, so ostler abbreviates it git-style to a **handle** —
`<PREFIX>-<6+ chars>`, the shortest slice unambiguous among the ids currently in the repo:

```bash
ostler list --type seed                # ACME-K3XQ7P    ← handles, the default for human output
ostler list --type seed --json         # ACME-01JB…     ← full ids, the default for --json
ostler --full-ids list --type seed     # full ids in human output
ostler --handles  list --type seed --json
```

The split is the point: a person wants a token short enough to copy, while a program wants the
identity that never changes. A handle **lengthens** the moment a colliding id is minted, so it is a
display form — never what gets written into a document.

Input is not modal. A handle is accepted wherever ostler takes an id, in either mode and from either
surface, so a token copied out of one command goes straight into the next:

```bash
ostler query stories-covering-seed ACME-K3XQ7P
ostler seed add checkout ACME-K3XQ7P --status resolved
ostler backlog prune ACME-K3XQ7P
```

The slice is of a *hash* of the ULID rather than of the id itself: monotonic ids minted in the same
millisecond differ only in their low bits, and hashing decorrelates them so even a burst abbreviates
to six characters. From Python, `okf.handle(id)` / `okf.handles()` render and `okf.expand(token)`
resolves — though every ostler entry point already expands its own id arguments.

## Profiles

`ostler` infers a profile from the tree: **`full`** when `docs/epics` exists (the epic/story/seed/
knowledge coverage graph), **`exploration`** otherwise (knowledge/docs only, no coverage graph).
Override any default in an optional `organization:` block in `ostler.yml` / `agents.yml` at the repo
root.

## Templates (custom hierarchies)

The built-in types above (epic/story/knowledge/feature/spec) are fixed. For a *different*
documentation shape — your own Concept kinds, nesting, required fields, status enums — declare it
per-repo in **`.agents/templates.yml`** (git-tracked, alongside `.agents/ids.json`). A kind is live
for `new`/`find`/`set`/`remove`/`doctor` the moment it's written — no separate activation step.

```bash
ostler template new    <name> [kind ...]        # declare a template, optionally with stub kinds
ostler template edit   <name> --set <kind>.<field>[.<subfield>]=<value>
ostler template find   [<name>]                 # list templates, or one template's definition
ostler template delete <name>
ostler template apply  <name>                   # mkdir -p each doc_root + inject CLAUDE.md guidance
```

Once a template's kinds are declared, use the same generic verbs against instances:

```bash
ostler new    <kind> <name> [field=value ...]   # <parent-kind>=<name> scopes nesting
ostler find   <kind> [<name>]
ostler set    <kind> <name> field=value ...
ostler remove <kind> <name>
```

See
[SPEC.md §10](https://github.com/GabrielCpp/stablemate/blob/main/ostler/SPEC.md#10-templates-and-template-declared-kinds)
for the full YAML schema, a worked 3-level nesting example, and the bundle-vs-leaf shape rules.

## Versioning

The format is the OKF profile **v1.0**, versioned `<major>.<minor>`. Minor bumps add backward-compatible
fields; major bumps may change required frontmatter or the `epic.md` grammar. A repo may record
`okf_version` and `ostler_profile` in `docs/epics/index.md`.

## License

MIT. See [LICENSE](https://github.com/GabrielCpp/stablemate/blob/main/ostler/LICENSE).
