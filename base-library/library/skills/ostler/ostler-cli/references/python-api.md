# `from ostler import Ostler` — the Python API

The library face of [`ostler`](../SKILL.md), and the only way a `workhorse` workflow script
touches the graph — never by shelling out to the CLI and scraping its JSON. Reached when you
are writing a node, a script, or a test that reads or mutates docs. For the same operations
from a shell, [command-interface.md](command-interface.md).

`ostler` ships a library face of the CLI — the analog of GitPython's `Repo` or
PyGithub's `Github`. **Inside a `workhorse` workflow script, command the graph through
this, not by shelling out** to the CLI and scraping its JSON (see the
`workhorse-engine` skill). It is the same functional core the CLI
dispatches to; methods return plain Python objects (`dict`/`list`/`str`, a `Result`
with `.ok`/`.entity_id`/`.message`, an `EditPlan`, a `QaOutcome`), never JSON text.

```python
from ostler import Ostler
okf = Ostler(root)          # root discovered upward, like `ostler -C DIR`; None ⇒ cwd
```

| CLI | facade method |
| --- | --- |
| `list --type T [--epic E] [--status S] [--json]` | `okf.list("T", epic=…, status=…) -> list[dict]` |
| `search Q …` / `query NAME ARG` | `okf.search("Q", …)` / `okf.query("NAME", "ARG")` |
| `next-epic` / `next-story E` | `okf.next_epic()` / `okf.next_story("E") -> dict\|None` |
| `todo list` | `okf.todo() -> list[str]` |
| `backlog list` | `okf.record_listing(repo, status) -> list[str]` · `okf.records()` · `okf.open_records(repo)` |
| `doctor [--epic E] --json` | `okf.doctor(epic=…) -> QaOutcome` (`.data` is the report `.as_dict()`) |
| `path epic E` / `path spec ID` / `path story ID` / `path branch ID` | `okf.epic_path("E")` / `okf.spec_path("ID")` / `okf.story_path("ID")` / `okf.branch("ID", epic=False)` |
| `--handles` rendering | `okf.handle(id) -> str` / `okf.handles() -> dict[str, str]` · `okf.expand(token) -> str` |
| `create epic/story` · `update story` · `delete epic/story` · `seed add` · `set-status` · `conflict` | `okf.create_epic(…)` / `okf.create_story(…)` · `okf.update_story(story_id, title=…, covers=…, depends=…)` · `okf.delete_epic(…)` / `okf.delete_story(…)` · `okf.add_seed(epic, id, status=…, meta={…})` · `okf.set_status(story_id, status)` · `okf.set_conflict(story_id, text)` (`""` clears) → `Result` |
| `backlog add` · `backlog adopt` | `okf.backlog_add(summary, repo=, area=, …)` → `Result` (a committed record) · `okf.backlog_import(file, repo=)` → `Imported` |
| `backlog prune` · `todo add/prune/reorder` | `okf.close_record(id, status, reason)` (commits the close in the artifacts repo) · `okf.todo_add/todo_prune/todo_reorder` → `Result` |
| `qa validate` · `qa run` | `okf.qa_validate(plan, spec=…)` · `okf.qa_run(plan, spec=…)` |
| `artifact vet KIND --spec DIR` | `okf.artifact_vet("KIND", spec) -> QaOutcome` |
| `qa tools list` | `okf.qa_tools_catalog() -> QaOutcome` (`.data` = `{"tools": …, "errors": …}`) |
| `edit settle-review ID --write` | `okf.settle_review(story_id, write=True) -> EditPlan` (`.error`, per-finding ledger) |

### `QaOutcome` — a check that answers instead of raising

Every method in the table above that returns a `QaOutcome` — the whole qa/artifact family,
plus `doctor` — answers a *data*-shaped failure rather than raising it. An
malformed plan, a spec file that will not parse, a graph that will
not load: each comes back as a failed outcome, so a caller branches on fields instead of
wrapping every call in `except (OSError, ValueError, RuntimeError)`.

```python
outcome = okf.doctor()
outcome.ok        # the verdict — the check holds
outcome.status    # "passed" | "failed" | "invalid" | whatever the check names
outcome.message   # one line, the same text the CLI prints
outcome.data      # the payload the CLI would `--json` — always carries "status"
```

`status == "invalid"` is the one worth branching on separately: it means the check never ran,
which is not the same as running and finding nothing. Zero findings because the
graph would not load must not read as "everything is clean".

A **call-site** mistake still raises, and should: an unknown `etype`, a `need` that is neither
`"build"` nor `"author"`, a bad argument type. That is a bug where it was made, and returning
it as an outcome would hide it. The reads that take a name — `list`/`search`/`query`, the
`*_path` resolvers, `expand` — have no data-shaped raises at all: an unmatched name comes back
as `[]`, as `None`, or as the name itself, already the answer an outcome would carry.

### `ostler.path` — path derivation without a graph

`Ostler`'s `*_path` methods answer against a **loaded** graph, and loading reads every
markdown file under every doc root. A caller that only wants to know *where* something goes
imports the derivation module directly instead:

```python
from ostler import path as okf_path

okf_path.epics_root_in(root)                     # <artifacts dir>/epics
okf_path.epics_index_in(root)                    # the epic queue's index.md
okf_path.specs_root_in(root)                     # <artifacts dir>/specs
okf_path.epic_dir_in(root, "checkout-flow")      # → .../<epic-id>, from the id, the folder or the slug
okf_path.epic_slug_in(root, epic)                # the slug the epic's frontmatter declares
okf_path.story_dir_in(root, epic, story)         # → .../stories/<story-id>, from the story's id or slug
```

Every derivation comes in up to three spellings, chosen by what the caller already holds:

| Spelling | Takes | Use when |
| --- | --- | --- |
| `<name>_in(root, …)` | the **repo root** | the normal case — no graph load |
| `<name>(graph, …)` | a loaded `Graph` | you already have one; don't re-read the config |
| `<name>_under(container, …)` | the **directory itself** | you were *told* which one — an operator's `epics_dir`, or a book you already hold |

`_under` is what keeps an override from becoming a second, dumber derivation: ostler's rules
still apply *inside* the directory you passed, so an epic is matched by number-or-slug there
too. **This module is the only place a doc-tree path is derived** — no workflow, node or
script writes `docs/epics` as a literal; see "A
workflow does not spell a doc path" in `workflows/README.md`.

The loaded graph is a **snapshot**: reads reuse one cached load; a mutation applies
against a fresh load and invalidates the cache, so the next read sees it (`reload()`
forces a refresh). A read never returns `None` — an unloadable graph *raises*
`(OSError, ValueError, RuntimeError)`. QA/artifact/edit methods are lazy-imported, so a
read-only script never pays for the QA/vet machinery.

