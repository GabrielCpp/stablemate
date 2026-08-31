# The ostler knowledge format (OKF profile v1)

This document is the authoritative definition of the `docs/` knowledge hierarchy that **ostler**
owns: its on-disk layout, the entity types, their identity and frontmatter, the `epic.md` body
grammar, and the conformance rules ostler enforces. It is a *strict profile* of the
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(OKF): every knowledge document is an OKF **Concept** (a markdown file with YAML frontmatter whose
only hard requirement is a non-empty `type`), and ostler layers typed schemas, referential
integrity, retrieval, and CRUD on top — which OKF permits a consumer to do for `type`s it knows.

There is **no legacy format**. `seed.json`, `dependencies.json`, `epics-todo.json`, and
`features/inventory.json` do not exist in this format; everything is markdown, and ostler is the
single tool that defines, validates, reads, and mutates it.

## 1. Bundles and Concepts

A repository's knowledge lives under `docs/` as a set of OKF **bundles** (directories of markdown
Concepts). A **Concept** is one `.md` file with:

- a YAML **frontmatter** block delimited by `---`, carrying a required `type` and any typed fields;
- a markdown **body** using conventional section headings.

**Identity is the path.** A Concept's id is its bundle-relative path without the `.md` suffix
(`docs/features/profile/preference-summary.md` → `profile/preference-summary`). Cross-references
are bundle-relative paths or plain markdown links.

Reserved filenames per bundle (OKF): **`index.md`** (an ordered listing of the bundle) and
**`log.md`** (chronological history, newest first). All other `.md` files are Concepts.

## 2. Entity types

Every Concept declares `type`. Ostler knows these types (the machine registry is
`ostler/registry.py`):

| `type` | Location (glob, repo-relative) | Identity | Required frontmatter |
|---|---|---|---|
| `epic` | `docs/epics/<NNNN-slug>/epic.md` | `<NNNN-slug>` (dir name) | `type`, `id`, `title` |
| `story` | `docs/epics/<NNNN-slug>/stories/<slug>/story.md` | `<slug>` | `type`, `slug`, `status` |
| `feature` | `docs/features/<area>/<slug>.md` *(or flat `docs/features/<slug>.md`)* | `<area>/<slug>` | `type`, `slug`, `title` |
| `spec.<stem>` (`spec.plan`, `spec.review`, `spec.qa`, `spec.executive`, `spec.vet`, …) | `docs/specs/<slug>/*.md` | path | `type` |

An epic's directory is minted `NNNN-<slug>` (four digits minimum, one past the highest number
currently under `docs/epics/`), so the bundle listing is the order the epics were decomposed in.
The number is **presentation, not identity** — identity is the `id` in frontmatter, which never
changes — so every command that takes an epic *name* accepts either form: `0007-checkout-flow` and
the bare `checkout-flow` name the same epic. A name that already carries a number is matched
literally, so `0009-checkout-flow` is a miss rather than a silent re-point at `0007-`. Directories
that predate the numbering are left unnumbered and keep resolving; survivors are never renumbered
to close a missing number.

`spec.*` Concepts are coder **process artifacts**. They are typed and conformance-checked
(`type` present) but ostler does not own their internal schema or relocate them.

The subtype is the file's stem — `plan.md` → `spec.plan`, `executive.md` → `spec.executive`,
`plan-go.md` → `spec.plan-go` — so a doc's kind stays queryable without a fixed vocabulary to
maintain. Nothing dispatches on it: only the `spec` base type is checked. Mint these with
`ostler create spec <slug> <doc>` rather than hand-writing frontmatter; it is idempotent, so it
also retro-stamps a doc that was written free-form.

**Not Concepts** (managed markdown, not part of the typed graph): `docs/backlog.md` (an
ostler-managed intake list), `docs/roadmaps/*`, and operational files written by the workflows
(`context.md`, `attempts.md`, `feedback.md`, `qa/`). These are named here for completeness and left
in place.

## 3. The epic Concept (`epic.md`) — single source of truth for an epic

An epic's `epic.md` is the source of truth for the epic's narrative **and** its seeds and its story
dependency-DAG. There are no separate `seed.json` / `dependencies.json` files. Ostler reads the
seeds and stories back out of the markdown body with its hierarchical parser (`markdown.py`:
`Section`/`Bullet` tree with source line spans).

### Frontmatter
```yaml
---
type: epic
id: ACME-01JBXR7K9QZ4M2T8VNF3HD6PWC   # allocated id (ostler-owned, from .agents/ids.json)
title: Account Credits "Aperçu" Billing Body at Legacy Parity
status: in-progress    # optional: planned | in-progress | done
---
```

### Body
Free narrative prose (any headings: `## Goal`, `## Method`, `## Acceptance`, …) plus two
**canonical sections** ostler parses by exact heading:

#### `## Seeds`
Zero or more `### <seed-id>` subsections. Omit the whole section for a seedless epic. Each seed
subsection is a leading **metadata bullet list** followed by free prose:

```markdown
## Seeds

### apercu-landing-body
- status: researched
- surface: account-billing/apercu-billing-body
- legacySurface: /{_locale}/employe/profile/edit (BuyCreditsAction)
- backing: GET /billing/customer → CustomerDetails (built)

Replace the `/dashboard` developer-stub body with the account-credits "Aperçu" overview…
(prose: currentState, prerequisites, notes — free markdown)
```

- The first paragraph after the metadata bullets is the seed `summary`.
- Recognized metadata keys: `status` (one of `backlog|researched|covered|resolved|dropped|deferred`;
  default `backlog`), `surface`, `legacySurface`, `backing`, `prerequisites`, `sourceBullet`.
  Unknown keys are preserved as raw fields.

#### `## Stories`
Zero or more `### <slug>` subsections, each a metadata bullet list (+ optional prose). The story's
detailed spec lives in its own `story.md` Concept (§4); this section carries the **coverage edge**
— which seeds a story answers. What *blocks* a story is stated in that story's own file (§4), so a
reader has it in front of them rather than one file up:

```markdown
## Stories

### 01-apercu-billing-body
- title: Account Credits "Aperçu" Billing Body (Billed & Unbilled) at Legacy Parity
- id: ACME-01JBXR7M4E0S9YCG5NAKQ2TZVJ
- covers: apercu-landing-body, apercu-subscription-change-plan-link, apercu-recent-bills-list
- phase: 1
- effort: 8-10 hours
```

- `covers:` → the story's `seedItems` (comma-separated seed ids; `(none)`/empty = none).
- `title`, `id`, `phase`, `effort` map to the same story fields. The `story.md` path is conventional
  (`stories/<slug>/story.md`).

## 4. The story Concept (`story.md`)

```yaml
---
type: story
id: ACME-01JBXR7M4E0S9YCG5NAKQ2TZVJ
externalKey: TEAM-123   # optional provider-neutral lookup alias
slug: 01-apercu-billing-body
status: Not started     # free text; the workflow lifecycle (e.g. "QA passed")
surface: account-billing/apercu-billing-body   # optional
---
# Story: …
## Dependencies
- Blocked by: 00-sign-in       # one bullet per blocker, or the bare `(none)`
## Fixtures
(none)
## Context
## Acceptance Criteria
## Non-Functional Acceptance Criteria
## Technical Notes
## Implementation Status
- **Status**: Not started        # legacy status line still honored if frontmatter absent
```

`## Dependencies` is the story's edge in the DAG, and this file is the only place it is written —
so what blocks a story is visible to whoever has the story open. The section states one
`- Blocked by: <sibling-slug>` per blocker; when nothing blocks it the body is the bare word
`(none)` and **no bullet**, which says "decided, and the answer is nothing" where an empty section
would not. A blocker may name only a story in the same epic. Change edges with
`ostler update story --depends`, never by hand-editing a body a workflow will rewrite: a bullet
under this heading that states anything else is a `malformed-dependency-bullet` error, which is
what stops a rewrite from emptying the DAG quietly.

The body separates behavior the coder builds (`## Acceptance Criteria`) from inherited invariants
and constraints QA must still prove (`## Non-Functional Acceptance Criteria`). `## Technical
Notes` carries concise existing-code references and mechanism evidence without becoming an
implementation plan.

**There is one story contract and no version key.** Every story is judged by the sections it
carries, in the order above; a document cannot declare which rules apply to it. A story missing a
required heading is `unwritten-story` whatever its age, and `ostler` will add the heading in
contract position on request — the same operation for a story written last year, a story a rework
emptied, and one scaffolded a moment ago.

The coverage edge (`covers`) is *not* here — it names seeds defined in the epic, so it lives in the
epic's `## Stories` section (§3). Prose may link to `docs/features/…` OKF nodes with ordinary
markdown links.

The generated `id` is canonical and immutable. `externalKey`, when present, is an opaque alias for
resolving tracker-named work; it does not replace the id or move an existing spec directory. A slug,
id, or external key that identifies more than one story is a `story-key-collision` error, and the id
recorded here must agree with the copy in the parent epic's `## Stories` block.

## 5. The feature Concept and the epics index

- **Feature** Concepts (`type: feature`) are per-surface markdown under `docs/features/`. The feature
  **inventory** is *derived* from these via `ostler list --type feature`; there is no `inventory.json`.
- **`docs/epics/index.md`** is the epics bundle's OKF index: an **ordered** list of the epics to be
  worked (the former `epics-todo.json`). Ostler manages its order via `ostler todo`. The coder's
  runtime queue sidecar (untracked) consumes this ordering.

## 6. Id allocation

Ostler owns `.agents/ids.json` (`{prefix, frozen}`). `ostler create` allocates ids for backlog items,
milestones, epics, stories, and features, scaffolds their canonical Markdown, and (for stories) adds
the `### <slug>` block to the epic's `## Stories`. No external id allocator exists. The registry has
no counter: only the repo prefix and optional frozen-entity records are persisted.

An id is `<PREFIX>-<ULID>`: the repo prefix (first four letters of the repo name, pinned in the
registry on first use) followed by a monotonic ULID — 26 Crockford-Base32 chars, a 48-bit
millisecond timestamp plus 80 bits of randomness. It is lexicographically sortable by mint time and
allocates with **no coordination**, so concurrent worktrees, processes and clones cannot collide.
Ids minted by the former `<prefix>-<n>` counter keep resolving; an id is an opaque, sortable string.

A **short handle** — `<PREFIX>-<slice of a hash of the ULID>`, minimum six characters — abbreviates
an id git-style: the shortest slice unambiguous among every id written down in the tree, lengthened
on collision. Handles are display and input only. Ostler prints them by default in human-readable
output and prints full ids under `--json` (`--handles` / `--full-ids` override either), and accepts
a handle wherever it accepts an id regardless of how the run prints. Because a handle lengthens when
a colliding id is later minted, **only the full id is ever written into a document**.

## 7. Conformance and validation (`ostler doctor`)

A bundle is **OKF-conformant** when every non-reserved `.md` parses as frontmatter + body with a
non-empty `type` (`okf-missing-type` otherwise). On top of conformance, ostler enforces the typed
referential-integrity contract over the graph parsed from the markdown:

`cross-epic-seed`, `dangling-seed`, `cross-epic-dependency`, `dangling-dependency`,
`missing-story-file`, `story-covers-no-seed`
(warn), `orphan-seed`,
`frozen-removed`, `frozen-mutated`, plus `schema` (warn) for per-type frontmatter schema violations.

## 8. Versioning

This profile is versioned `<major>.<minor>`; the current version is **1.0**. A repo may record
`okf_version: "0.1"` (the base OKF version) and `ostler_profile: "1.0"` in `docs/epics/index.md`.
Minor bumps add backward-compatible fields; major bumps may change required frontmatter or the
`epic.md` grammar.

## 9. Templates and template-declared kinds

The entity types in §2 are **built in** (`ostler/registry.py`) and fixed for every repo. A repo
that needs a *different* OKF hierarchy — its own Concept kinds, nesting, required frontmatter,
and status enums — declares one in a **per-repo** file: `.agents/templates.yml`. This sits
alongside `.agents/ids.json` (§6): `.agents/` is ostler's repo-local, non-`docs/` state, and
`.agents/templates.yml` extends that same convention rather than a global `~/.config/` store.

A template kind is **live the moment it's written** — `ostler new/find/set/remove` and `ostler
doctor` pick it up on every run via `model.load()`, with no separate activation step. A kind
behaves exactly like a built-in `type` for conformance purposes (§7: a non-reserved `.md` under
its `location` glob must carry a non-empty `type`), but its required-field and enum validation is
enforced only by ostler's own CRUD (`new`/`set`), not by `doctor`.

`.agents/templates.yml` maps **template name → definition**, so a repo can define more than one
hierarchy in one file:

```yaml
research:
  title: Research Program
  kinds:
    - name: program                             # top-level, bundle-shaped (own directory)
      doc_root: research                        # key into the Graph.doc_roots dict
      default_path: specs                        # repo-relative dir for that key
      path_template: "{name}/program.md"         # -> specs/<name>/program.md
      required: [type, title, status]
      fields: {status: {enum: [proposed, active, paused, complete]}}
      extra_files:                                # written once, at creation time only
        - {path: "README.md", content: "# {title}\n\n## Gate Ladder\n"}
        - {path: "log.md", content: "# Progress Log\n"}
    - name: gate                                 # nested under program, bundle-shaped
      doc_root: research
      default_path: specs
      parent: program
      path_template: "{parent}/gates/{name}/gate.md"   # -> specs/<program>/gates/<gate>/gate.md
      required: [type, gate, status]
      fields: {status: {enum: [pending, in-review, passed, reopened, blocked]}}
    - name: finding                              # nested under gate, leaf-shaped (no children)
      doc_root: research
      default_path: specs
      parent: gate
      path_template: "{parent}/findings/{name}.md"
      required: [type, title]
```

**`path_template` placeholders.** `{name}` is the instance's own name (the `ostler new <kind>
<name>` positional). `{parent}` (only valid when `parent` is set) is the directory containing the
parent instance's own file, resolved relative to `doc_root` — located by scanning the parent
kind's `location` glob for an instance with the given name, the same way `ostler story` commands
locate a story by slug without stating its epic. A child only ever needs its **immediate**
parent's name: `ostler new finding f1 gate=G0 title=...` does not also need `program=SMCNv3`.

**Bundle vs. leaf shape.** A `path_template` ending in `{name}/<literal>.md` is *bundle-shaped*
(each instance gets its own directory, so it can itself be a `parent`). One ending in `{name}.md`
or `<literal>/{name}.md` is *leaf-shaped* — valid for a kind with no children, but rejected as a
`parent` target (all children would collide into one shared directory) and cannot declare
`extra_files` (it has no directory of its own to hold them).

**CRUD grammar** — generic, kind-agnostic verbs parallel to the built-in `create`/`edit`/`delete`:

```
ostler new    <kind> <name> [field=value ...]   # create; <parent-kind>=<name> scopes nesting
ostler find   <kind> [<name>]                    # list, or one instance's fields
ostler set    <kind> <name> field=value ...      # edit fields (never touches extra_files)
ostler remove <kind> <name>                      # delete (rmtree if bundle-shaped, else unlink)
```

**Template CRUD** manages the YAML itself:

```
ostler template new    <name> [kind ...]   # declare a template, optionally with stub kinds
ostler template edit   <name> --set <kind>.<field>[.<subfield>]=<value>
ostler template find   [<name>]            # list templates, or one template's full definition
ostler template delete <name>              # remove the template (does not touch instance files)
ostler template apply  <name>              # mkdir -p each doc_root + inject CLAUDE.md guidance
```

`template edit`/`new` hard-validate before saving: a kind name colliding with a built-in type or
another template's kind is rejected, as is a `parent` pointing at a leaf-shaped or nonexistent
kind, or `extra_files` on a leaf-shaped kind. `template apply` is the only step with disk side
effects beyond the YAML write itself — idempotent and safe to re-run (directory creation is
deduplicated across kinds sharing a `doc_root`; the injected `CLAUDE.md` section is
marker-delimited and replaced in place, never duplicated).
