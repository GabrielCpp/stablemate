---
name: stablemate-ostler
description: "ostler CLI reference — the system-of-record for a repo's docs/ knowledge graph (epics, stories, seeds, knowledge, features as OKF Concepts): command interface, epic.md grammar, coverage model, and when a workflow agent should call it."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/ostler/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run `make agent-install` to regenerate"
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
ostler search <query> [--type T] [--owner O] [--tag G] [--json]
ostler query  gaps-in-story|stories-covering-seed|surfaces-referenced-by-story <arg> [--json]
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

**Visual-fidelity check** (used by `coder`'s QA gates — see [[coder-workflow]])
```bash
ostler vet <screenshot> --manifest M (--cdp-url U | --regions FILE) --slug S [--state s] [--iou-threshold 0.5] [--json]
```

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
