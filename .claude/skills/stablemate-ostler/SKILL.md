---
name: stablemate-ostler
description: "ostler reference — the system-of-record for a repo's docs/ knowledge graph (epics, stories, seeds, features as OKF Concepts, plus the OKF UI profile's surface/element/behavior/member/concept types — nested and typed): the CLI command interface AND the `from ostler import Ostler` Python API workflow scripts use in-process, epic.md grammar, coverage model, the scaffold→fmt→doctor UI loop, `ostler graph` queries, and when a workflow agent should call it."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/ostler/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-ostler/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [cli, python, docs]
---

# Ostler

Load this skill when a workflow node, script, or prompt needs to read or mutate a repo's planning
docs (`docs/epics`, `docs/features`, `docs/specs`) — or when authoring a new
`workhorse` workflow that should integrate with the doc graph instead of hand-rolling its own
JSON state files.

`ostler` is a standalone, repo-agnostic tool (`pipx install ostler` / `pip install ostler`) that
operates relative to the current working directory (`-C/--chdir DIR` to point elsewhere). It is
**the one tool that reads and writes the graph** — never hand-edit `epic.md`'s `## Seeds`/
`## Stories` sections or allocate ids yourself; call ostler instead so structure stays consistent
while agents/humans author the prose around it. Use it two ways: the **CLI** for humans and
shell, and the **`from ostler import Ostler` Python API** for `workhorse` workflow scripts —
a script commands the graph in-process as a library, never by shelling out to the CLI and
scraping its JSON. Each face has its own reference below.

## Core model

Everything under `docs/` is markdown: an OKF (Open Knowledge Format) **Concept** is one `.md` file
with a YAML frontmatter block (only hard requirement: non-empty `type`) plus a markdown body.
**Identity is the path** — a Concept's id is its bundle-relative path minus `.md`.

There is **no** `seed.json`, `dependencies.json`, `inventory.json`, or `epics-todo.json`. An epic's
seeds and its story dependency-DAG live entirely inside that epic's own `epic.md`.

| `type` | Location | Identity | Required frontmatter |
|---|---|---|---|
| `epic` | `docs/epics/<NNNN-slug>/epic.md` | `<NNNN-slug>` (dir name) | `type`, `id`, `title` |
| `story` | `docs/epics/<NNNN-slug>/stories/<slug>/story.md` | `<slug>` | `type`, `slug`, `status` |
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

## The two faces — pick one, then read its reference

Both faces drive the same functional core, and neither is a wrapper over the other.

- **[references/command-interface.md](references/command-interface.md)** — the CLI. Every
  command with its flags and JSON shape: `doctor`, `trace`, `list`/`search`/`query`,
  `graph`, `next-epic`/`next-story`, `path`, the `create`/`update`/`seed`/`backlog`/`todo`
  mutators, `edit`/`freeze` repair, `scaffold`/`fmt`, `vet`, the `qa` control plane and its
  browser-diagnostics manifest, and `artifact`. Read it when you are writing a shell step,
  a gate, or a prompt that runs ostler from a terminal.
- **[references/python-api.md](references/python-api.md)** — `from ostler import Ostler`,
  the CLI-to-method table, `ostler.path` for deriving a doc path without loading a graph,
  and the snapshot/caching semantics. Read it when you are writing a `workhorse` node,
  script, or test.

A third reference is neither face — it is the format ostler *executes*:

- **[references/qa-plan-authoring.md](references/qa-plan-authoring.md)** — a story's
  `qa_plan.py`: the `plan`/`target`/`background`/`secret`/`input_file` declarations, the `@scenario`
  decorator, everything a scenario reaches through `qa`, and the rules validation enforces. Read
  it when you are writing or repairing a QA plan.

**Short handles.** An id is `<PREFIX>-<26-char ULID>`; ostler abbreviates it git-style to the
shortest unambiguous `<PREFIX>-<6+ chars>`. Human output prints handles, `--json` prints full
ids, and a handle is accepted wherever a command takes an id. Never write a handle into a
document — it lengthens as soon as a colliding id is minted.

## The coverage model

```
story (epic.md ## Stories)  ->  covers: seed (epic.md ## Seeds)
docs/features OKF nodes     ->  code:/links:/reachability/coverage obligations
```

Open questions and missing behavioral coverage belong in `docs/features/` as OKF nodes, links, and
coverage/reachability obligations, or in the epic/story planning graph as seeds and stories.
`ostler doctor` checks OKF conformance (every Concept has a non-empty `type`) plus the typed
referential-integrity contract:

- **cross-epic references** — an id/slug used inside epic E that only resolves in another epic
- **orphan seeds** — an active seed no story covers
- **dangling references** — a seed id or sibling slug that resolves to nothing
- **frozen drift** — an approved (frozen) story/seed that changed or vanished

It exits non-zero when any error-level finding is present (safe to gate a workflow node on).
Warning-level findings (`story-covers-no-seed`, `ungrounded-surface`) are reported but don't fail
the check.

## Id allocation, profiles, templates

- Ostler owns `.agents/ids.json` (`{prefix, frozen}`) — `create epic|story|feature` allocates an id,
  scaffolds the markdown, and (for stories) inserts the `### <slug>` block into the epic's
  `## Stories`. There is no external id allocator.
- An id is `<PREFIX>-<ULID>`: the repo prefix plus 26 Crockford-Base32 chars (ms timestamp + 80 bits
  of randomness). It sorts by mint time and needs no coordination, so parallel worktrees can't
  collide. Older `<prefix>-<n>` counter ids keep resolving — an id is an opaque string.
- Profile is inferred from the tree: `full` when `docs/epics` exists (the epic/story/seed/knowledge
  coverage graph), `exploration` otherwise (knowledge/docs only, no coverage graph). Override via an
  `organization:` block in `ostler.yml`/`agents.yml`.
- For a documentation shape outside epic/story/knowledge/feature/spec, declare custom Concept kinds
  in `.agents/templates.yml` (`ostler template new/edit/find/delete/apply`), then operate on
  instances with the generic `ostler new/find/set/remove <kind> <name>` verbs.

## The OKF UI profile — surfaces, elements, behaviors

A profile of OKF that describes UIs, CLIs, HTTP/WS servers and the concepts they serve as a
navigable graph of typed nodes (`screen`/`cli`/`server`, `component`/`command`/`endpoint`,
`interaction`/`invocation`, `method`/`field`, `flow`, `concept`, `format`) — first-class to
`list`, `search`, `trace`, `scaffold`, `fmt`, `graph`, and to a **hard `doctor` gate**.

**[references/okf-ui-profile.md](references/okf-ui-profile.md)** carries that branch whole:
the role/context type table, file-vs-section identity and how sections nest, where nodes live
per service, the link rules (plain markdown paths, never `[[wikilinks]]`, `parent:`/`extends:`
relations, no orphans), the completeness bar, the scaffold→author→fmt→doctor loop, and every
`doctor` error code with its remedy. Read it when authoring or linting anything under
`docs/features/`; the planning graph above needs none of it.

## When to reach for it

- Any workflow node that needs "what's the next thing to work on" → `next-epic`/`next-story`, not a
  hand-maintained queue file.
- Any node that needs to resolve a slug to a filesystem path (spec dir, story.md, branch name) →
  `ostler path`, not string-concatenation in a script.
- Any gate that checks graph health before letting a workflow proceed (e.g. author's
  `reconcile-artifacts.py`/`check-story-grounding.py`/an `ostler doctor` check) → shell out to
  `ostler doctor`/`ostler query` and branch on exit code or `--json` output, never re-implement
  referential-integrity checks by hand.
- Any resolver prompt that fixes a graph problem (dangling references, orphan seed, cross-epic
  contamination) → `ostler edit relink/rename`, `ostler seed`, or `set-status`, never a raw edit of
  `epic.md`'s generated sections.
- Any node that documents a UI/CLI/server surface or a domain/code concept → the OKF UI profile
  (`scaffold`/`fmt`/`doctor`) above; for the create-or-refresh loop after a story, load
  [[documentation]]; to model a whole app's surface graph from scratch or from existing code, load
  [[okf-modeling]].
