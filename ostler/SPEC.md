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
(`docs/knowledge/profile/preference-summary.md` → `profile/preference-summary`). Cross-references
are bundle-relative paths or plain markdown links. The `surface:` key on a knowledge Concept is a
retained **alias** for its path identity (back-reference for prose that names a surface).

Reserved filenames per bundle (OKF): **`index.md`** (an ordered listing of the bundle) and
**`log.md`** (chronological history, newest first). All other `.md` files are Concepts.

## 2. Entity types

Every Concept declares `type`. Ostler knows these types (the machine registry is
`ostler/registry.py`):

| `type` | Location (glob, repo-relative) | Identity | Required frontmatter |
|---|---|---|---|
| `epic` | `docs/epics/<epic>/epic.md` | `<epic>` (dir name) | `type`, `id`, `title` |
| `story` | `docs/epics/<epic>/stories/<slug>/story.md` | `<slug>` | `type`, `slug`, `status` |
| `knowledge` | `docs/knowledge/<area>/<name>.md` | path (`surface` alias) | `type`, `surface` |
| `feature` | `docs/features/<area>/<slug>.md` *(or flat `docs/features/<slug>.md`)* | `<area>/<slug>` | `type`, `slug`, `title` |
| `spec.plan` / `spec.review` / `spec.qa` | `docs/specs/<slug>/*.md` | path | `type` |

`spec.*` Concepts are coder **process artifacts**. They are typed and conformance-checked
(`type` present) but ostler does not own their internal schema or relocate them.

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
id: pred-15            # allocated id (ostler-owned, from .agents/ids.json)
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
detailed spec lives in its own `story.md` Concept (§4); this section carries the **edges**:

```markdown
## Stories

### 01-apercu-billing-body
- title: Account Credits "Aperçu" Billing Body (Billed & Unbilled) at Legacy Parity
- id: pred-16
- covers: apercu-landing-body, apercu-subscription-change-plan-link, apercu-recent-bills-list
- depends on: (none)
- phase: 1
- effort: 8-10 hours
```

- `covers:` → the story's `seedItems` (comma-separated seed ids; `(none)`/empty = none).
- `depends on:` → the story's `dependencies` (comma-separated sibling slugs).
- `title`, `id`, `phase`, `effort` map to the same story fields. The `story.md` path is conventional
  (`stories/<slug>/story.md`).

## 4. The story Concept (`story.md`)

```yaml
---
type: story
slug: 01-apercu-billing-body
status: Not started     # free text; the workflow lifecycle (e.g. "QA passed")
surface: account-billing/apercu-billing-body   # optional
---
# Story: …
## Context
## Acceptance Criteria
- … [gap: some-gap-id]          # prose gap tags still resolve against knowledge gaps
## Implementation Status
- **Status**: Not started        # legacy status line still honored if frontmatter absent
```

Edges (`covers`/`depends on`) live in the epic's `## Stories` section, **not** here. Prose may carry
`[gap:<id>]` tags and `docs/knowledge/…` references; ostler resolves both.

## 5. The knowledge Concept

Markdown + frontmatter (already the yenta shape; Predykt `.json` records convert to this). Required:
`type: knowledge`, `surface`. Typed fields (`route`, `sourceRefs`, `old[]`, `new[]`, `gaps[]`,
`openGaps[]`, `journeys[]`, `provenance`) live in frontmatter; the body is free prose
(`## Components`, `## Gaps`, …). A `gap` has `id` (required) and optional `owner` (a story slug),
`disposition` (`scoped|deferred|dropped`), `kind`, `component`.

## 6. The feature Concept and the epics index

- **Feature** Concepts (`type: feature`) are per-surface markdown under `docs/features/`. The feature
  **inventory** is *derived* from these via `ostler list --type feature`; there is no `inventory.json`.
- **`docs/epics/index.md`** is the epics bundle's OKF index: an **ordered** list of the epics to be
  worked (the former `epics-todo.json`). Ostler manages its order via `ostler todo`. The coder's
  runtime queue sidecar (untracked) consumes this ordering.

## 7. Id allocation

Ostler owns `.agents/ids.json` (`{prefix, counter, frozen}`). `ostler epic|story|feature create`
allocates the next `<prefix>-<n>` id atomically, scaffolds the canonical markdown, and (for stories)
adds the `### <slug>` block to the epic's `## Stories`. No external id allocator exists.

## 8. Conformance and validation (`ostler doctor`)

A bundle is **OKF-conformant** when every non-reserved `.md` parses as frontmatter + body with a
non-empty `type` (`okf-missing-type` otherwise). On top of conformance, ostler enforces the typed
referential-integrity contract over the graph parsed from the markdown:

`cross-epic-seed`, `dangling-seed`, `cross-epic-dependency`, `dangling-dependency`,
`missing-story-file`, `dangling-gap-tag` (warn), `dangling-knowledge-path`, `story-covers-no-seed`
(warn), `orphan-seed`, `dangling-owner`, `stale-owner` (warn), `ungrounded-surface` (warn),
`frozen-removed`, `frozen-mutated`, plus `schema` (warn) for per-type frontmatter schema violations.

## 9. Versioning

This profile is versioned `<major>.<minor>`; the current version is **1.0**. A repo may record
`okf_version: "0.1"` (the base OKF version) and `ostler_profile: "1.0"` in `docs/epics/index.md`.
Minor bumps add backward-compatible fields; major bumps may change required frontmatter or the
`epic.md` grammar.
