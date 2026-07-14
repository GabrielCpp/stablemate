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

# 2. Scaffold an epic (allocates an id, writes docs/epics/checkout-flow/epic.md)
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
| `epic` | `docs/epics/<epic>/epic.md` | `<epic>` (dir name) | `type`, `id`, `title` |
| `story` | `docs/epics/<epic>/stories/<slug>/story.md` | `<slug>` | `type`, `slug`, `status` |
| `knowledge` | `docs/knowledge/<area>/<name>.md` | path (`surface` alias) | `type`, `surface` |
| `feature` | `docs/features/<area>/<slug>.md` *(or flat `docs/features/<slug>.md`)* | `<area>/<slug>` | `type`, `slug`, `title` |
| `spec.plan` / `spec.review` / `spec.qa` | `docs/specs/<slug>/*.md` | path | `type` |

`spec.*` Concepts are process artifacts: typed and conformance-checked, but ostler does not own their
internal schema. **Not Concepts** (managed markdown, left in place): `docs/backlog.md` (an intake list)
and `docs/epics/index.md` (the epics queue).

### `epic.md` — single source of truth for an epic

An epic's `epic.md` carries the narrative **and** its seeds and story dependency-DAG. Ostler parses two
canonical sections back out of the markdown by exact heading:

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
- `## Stories` → `### <slug>` per story, carrying the **edges**: `covers:` (seed ids) and
  `depends on:` (sibling slugs). The detailed spec lives in the story's own `story.md`.

See [`SPEC.md`](SPEC.md) for the authoritative, formal definition of every field, status enum, and
conformance rule.

## Command interface

All read commands accept `--json`. Mutating commands allocate ids as needed and write canonical
markdown in place.

**Global**

```bash
ostler --version
ostler -C, --chdir DIR <command> …            # operate as if run from DIR
```

**Inspect**

```bash
ostler doctor [--epic SLUG] [--json] [--no-schema]   # conformance + referential integrity; non-zero on a break
ostler trace  <id|slug|gap|surface|path>             # walk the graph from any node
```

**Retrieve**

```bash
ostler list  --type epic|story|knowledge|feature|spec|seed|gap [--epic E] [--status S] [--json]
ostler search <query> [--type T] [--owner O] [--tag G] [--json]
ostler query  gaps-in-story|stories-covering-seed|surfaces-referenced-by-story <arg> [--json]
ostler next-epic [--json]                            # next queued epic with unfinished work
ostler next-story <epic> [--json]                    # next runnable story (deps satisfied, not done)
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

**Verification control plane**

```bash
# Build and validate deterministic base/head impact and obligation scope.
ostler qa context --base <rev> --head WORKTREE --spec docs/specs/<story> \
  --source-root web=web --source-root api=api --story-file docs/epics/.../story.md
ostler qa context-validate --spec docs/specs/<story>

# Review, validate, and execute one universal command/browser/mobile plan.
ostler qa validate docs/specs/<story>/qa-plan.yml --json
ostler qa run docs/specs/<story>/qa-plan.yml --json
```

Version-2 plans declare command, Playwright, and Maestro targets and map every
scenario to acceptance-criterion and OKF obligation IDs. Validation rejects
unknown coverage, unsupported actions and locators, disposable pre-run inputs,
literal secrets, and coverage without a machine assertion. Each run starts with
an empty `qa/`, writes an append-only ledger and content-hashed manifest, and
returns `passed`, `failed`, `blocked`, or `invalid`. Browser and mobile targets
record continuously by default. See
[`docs/QA-RUN.md`](docs/QA-RUN.md) and
[`../docs/ostler-qa-verification.md`](../docs/ostler-qa-verification.md).

## The coverage model

```
knowledge gaps[].owner  ->  story (epic.md ## Stories)  ->  covers: seed (epic.md ## Seeds)
```

`ostler doctor` checks OKF conformance (every Concept has a non-empty `type`) plus the typed
referential-integrity contract:

- **cross-epic references** — an id/slug used inside epic E that only resolves in another epic;
- **orphan seeds** — an active seed no story covers;
- **dangling references** — a `[gap:…]` tag, knowledge path, or sibling slug that resolves to nothing;
- **stale owners** — a non-resolved gap whose `owner` is empty or points at a missing story;
- **frozen drift** — an approved (frozen) story/seed that changed or vanished.

It exits non-zero when any error-level finding is present, so it drops straight into CI or a pre-commit
hook. Warning-level findings (e.g. `story-covers-no-seed`, `ungrounded-surface`) are reported but do
not fail the check.

## Id allocation

Ostler owns `.agents/ids.json` (`{prefix, counter, frozen}`). `create epic|story|feature` allocates the
next `<prefix>-<n>` id atomically, scaffolds the canonical markdown, and (for stories) inserts the
`### <slug>` block into the epic's `## Stories`. There is no external id allocator.

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

See [`SPEC.md` §10](SPEC.md#10-templates-and-template-declared-kinds) for the full YAML schema, a
worked 3-level nesting example, and the bundle-vs-leaf shape rules.

## Versioning

The format is the OKF profile **v1.0**, versioned `<major>.<minor>`. Minor bumps add backward-compatible
fields; major bumps may change required frontmatter or the `epic.md` grammar. A repo may record
`okf_version` and `ostler_profile` in `docs/epics/index.md`.

## License

See [`LICENSE`](LICENSE).
