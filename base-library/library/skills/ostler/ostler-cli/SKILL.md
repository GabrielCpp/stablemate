---
name: ostler-cli
description: "Drive the ostler tool: a repo's planning graph of epics, stories, seeds, the register and decisions, short handles and id allocation, templates, the QA run of a hand-written qa_plan.py, local stacks with `ostler env`, and the CLI command interface AND the `from ostler import Ostler` Python API workflow scripts use in-process. Load it to read or change the planning graph, to run or repair a QA plan, to bring up a stack, or to call ostler from a workflow node. The service book under services/ is written with ostler-book."
tags: [cli, python, docs]
commit_checks:
  - run: scripts/check_staged_files.py
    budget: 0.5
---

# Ostler

Load this skill when a workflow node, script, or prompt needs to read or mutate a repo's planning
docs (`docs/epics` and the story spec folders) — or when authoring a new
`workhorse` workflow that should integrate with the planning graph instead of hand-rolling its own
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

Everything under `docs/` is markdown: a **Concept** is one `.md` file with a YAML frontmatter
block (only hard requirement: non-empty `type`) plus a markdown body. **Identity is the path**:
a Concept's id is its bundle-relative path minus `.md`.

There is **no** `seed.json`, `dependencies.json`, `inventory.json`, or epics queue. An epic's
seeds and its story dependency-DAG live entirely inside that epic's own `epic.md`.

| `type` | Location | Identity | Required frontmatter |
|---|---|---|---|
| `epic` | `<artifacts_dir>/epics/<epic-id>/epic.md` | the `id`, which names the folder; `slug` names it in commands | `type`, `id`, `slug`, `title` |
| `story` | `<artifacts_dir>/epics/<epic-id>/stories/<story-id>/story.md` | the `id`, which names the folder | `type`, `slug`, `status` |
| `spec.plan` / `spec.review` / `spec.qa` | `<artifacts_dir>/specs/<story id>/*.md` | path | `type` |

Spec folders live in the user's artifacts folder, outside git, and are named by the story id. `ostler path spec <story-id>` prints the folder.

The milestones order the work: a milestone's `dependsOn` milestones first, then its `epics:` list in
order. `okf.milestone_epics()` returns that list.

## `epic.md` — single source of truth for an epic

```markdown
---
type: epic
id: pred-15
title: Account Credits "Aperçu" Billing Body at Legacy Parity
status: in-progress        # optional: planned | in-progress | done
followups: true            # optional: a backlog of filed follow-ups that no milestone owns
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
- phase: 1
- effort: 8-10 hours
```

- `## Seeds` → `### <seed-id>` per seed (omit the whole section for a seedless epic).
- `## Stories` → `### <slug>` per story, carrying the coverage edge `covers:` (seed ids). A
  story's blockers are *not* here: its own `story.md` carries a `## Dependencies` section listing
  one `- Blocked by: <sibling-slug>` per blocker, or the bare `(none)`.

## The two faces — pick one, then read its reference

Both faces drive the same functional core, and neither is a wrapper over the other.

- **[references/command-interface.md](references/command-interface.md)** — the CLI. Every
  command with its flags and JSON shape: `doctor`, `list`/`search`/`query`,
  `next-epic`/`next-story`, `path`, the `create`/`update`/`seed`/`backlog`/`milestone`
  mutators, `edit` repair, `vet`, the `ostler book` group, the `qa` control plane and its
  browser-diagnostics manifest, and `artifact`. Read it when you are writing a shell step,
  a gate, or a prompt that runs ostler from a terminal.
- **[references/stack.md](references/stack.md)** — the book's `stack.yml`: every key, the
  template values, and the copies and `ostler env` commands that run them. Read it when you
  are writing or repairing a stack file, or when a command needs the environment's variables.
- **[references/python-api.md](references/python-api.md)** — `from ostler import Ostler`,
  the CLI-to-method table, `ostler.path` for deriving a doc path without loading a graph,
  and the snapshot/caching semantics. Read it when you are writing a `workhorse` node,
  script, or test.

A third reference is neither face — it is the format ostler *executes*:

- **[references/qa-plan-authoring.md](references/qa-plan-authoring.md)** — a story's
  `qa_plan.py`: the `plan`/`target`/`background`/`secret`/`input_file` declarations, the `@scenario`
  decorator, everything a scenario reaches through `qa`, and the rules validation enforces. Read
  it when you are writing or repairing a QA plan.
- **[references/qa-harness-reference.md](references/qa-harness-reference.md)** — each `qa.*`
  call's arguments, return value and failure: `qa.http`, `qa.fixture`, `@node.key` and `$name`
  references, the address book behind `{name}` in a `base_url`, `qa.window()`,
  `qa.diagnostics` and `qa.tree`. Read it before a plan calls anything the authoring guide
  does not show.

**[scripts/check_staged_files.py](scripts/check_staged_files.py)** is the commit check half of
that format: a run writes traces, videos and a ledger under `<spec>/qa/`, and this refuses to
commit them — any staged blob over 1.5 MB, and anything staged from a directory a run wrote.
The repo that motivated it had committed 2,167 such files and 297 MB before anyone noticed. An
exception is a path glob in `[check-staged-files] allow` of `.agent-checks.toml`, tracked so a
reviewer sees it; an agent's commit runs the check, and farrier installs the `.gitignore` line.

**Short handles.** An id is `<PREFIX>-<26-char ULID>`; ostler abbreviates it git-style to the
shortest unambiguous `<PREFIX>-<6+ chars>`. Human output prints handles, `--json` prints full
ids, and a handle is accepted wherever a command takes an id. Never write a handle into a
document — it lengthens as soon as a colliding id is minted.

## Planning graph checks

```
story (epic.md ## Stories)  ->  covers: seed (epic.md ## Seeds)
```

`ostler doctor` checks the planning graph (every Concept has a non-empty `type`) plus the typed
referential-integrity contract:

- **cross-epic references** — an id/slug used inside epic E that only resolves in another epic
- **orphan seeds** — an active seed no story covers
- **dangling references** — a seed id or sibling slug that resolves to nothing

It exits non-zero when any error-level finding is present (safe to gate a workflow node on).
Warning-level findings (`story-covers-no-seed`, `ungrounded-surface`) are reported but don't fail
the check.

**The service book.** A service's behaviour lives in the book under `services/<name>/`, written
with [[ostler-book]] and read with `ostler book search|explain|decisions`. A search term may be a label in any of the book's
languages, a source file or a part of its path, or several words in any order, and `--kind question`
finds an open question.

## Id allocation, profiles, templates

- `create epic|story` allocates an id,
  scaffolds the markdown, and (for stories) inserts the `### <slug>` block into the epic's
  `## Stories`. There is no external id allocator.
  The prefix is `repo.id_prefix` in the `agents.yml` at the graph root; a mint refuses while it is unset.
- An id is `<PREFIX>-<ULID>`: the repo prefix plus 26 Crockford-Base32 chars (ms timestamp + 80 bits
  of randomness). It sorts by mint time and needs no coordination, so parallel worktrees can't
  collide. Older `<prefix>-<n>` counter ids keep resolving — an id is an opaque string.
- Profile is inferred from the tree: `full` when `docs/epics` exists (the epic/story/seed
  coverage graph), `exploration` otherwise (docs only, no coverage graph). Override via an
  `organization:` block in `agents.yml` (the legacy `ostler.yml` name still loads).
- For a documentation shape outside epic/story/spec, declare custom Concept kinds
  in `.agents/templates.yml` (`ostler template new/edit/find/delete/apply`), then operate on
  instances with the generic `ostler new/find/set/remove <kind> <name>` verbs.

## When to reach for it

- Any workflow node that needs "what's the next thing to work on" → `okf.milestone_epics()`,
  `next-epic`/`next-story`, not a hand-maintained queue file.
- Any node that needs to resolve a story id to a filesystem path (spec dir, story.md, branch name) →
  `ostler path`, not string-concatenation in a script.
- Any gate that checks graph health before letting a workflow proceed (e.g. author's
  `reconcile-artifacts.py`/`check-story-grounding.py`/an `ostler doctor` check) → shell out to
  `ostler doctor`/`ostler query` and branch on exit code or `--json` output, never re-implement
  referential-integrity checks by hand.
- Any resolver prompt that fixes a graph problem (dangling references, orphan seed, cross-epic
  contamination) → `ostler edit relink/rename`, `ostler seed`, or `set-status`, never a raw edit of
  `epic.md`'s generated sections.
