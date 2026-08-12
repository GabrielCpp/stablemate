# `from ostler import Ostler` — the Python API

The library face of [`ostler`](../SKILL.md), and the only way a `workhorse` workflow script
touches the graph — never by shelling out to the CLI and scraping its JSON. Reached when you
are writing a node, a script, or a test that reads or mutates docs. For the same operations
from a shell, [command-interface.md](command-interface.md).

`ostler` ships a library face of the CLI — the analog of GitPython's `Repo` or
PyGithub's `Github`. **Inside a `workhorse` workflow script, command the graph through
this, not by shelling out** to the CLI and scraping its JSON (see the
`workhorse-scripting` skill). It is the same functional core the CLI
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
| `todo list` / `backlog list` | `okf.todo() -> list[str]` / `okf.backlog() -> list[dict]` |
| `doctor [--epic E] --json` | `okf.doctor(epic=…) -> dict` (the report `.as_dict()`) |
| `path epic E` / `path spec S` / `path story E S` / `path branch S` | `okf.epic_path("E")` / `okf.spec_path("S")` / `okf.story_path("E","S")` / `okf.branch("S", epic=False)` |
| `--handles` rendering | `okf.handle(id) -> str` / `okf.handles() -> dict[str, str]` · `okf.expand(token) -> str` |
| `create epic/story` · `update story` · `delete epic/story` · `seed add` · `set-status` | `okf.create_epic(…)` / `okf.create_story(…)` · `okf.update_story(slug, title=…, covers=…, depends=…)` · `okf.delete_epic(…)` / `okf.delete_story(…)` · `okf.add_seed(epic, id, status=…, meta={…})` · `okf.set_status(slug, status)` → `Result` |
| `backlog add/prune` · `todo add/prune/reorder` | `okf.backlog_add/backlog_prune` · `okf.todo_add/todo_prune/todo_reorder` → `Result` |
| `qa context` · `qa context-validate` · `qa validate` · `qa run` | `okf.qa_context(base=…, spec=…, …)` · `okf.qa_context_validate(spec=…)` · `okf.qa_validate(plan, spec=…)` · `okf.qa_run(plan, spec=…)` |
| `artifact vet KIND --spec DIR` | `okf.artifact_vet("KIND", spec) -> dict` |
| `edit settle-review SLUG --write` | `okf.settle_review(slug, write=True) -> EditPlan` (`.error`, per-finding ledger) |

### `ostler.path` — path derivation without a graph

`Ostler`'s `*_path` methods answer against a **loaded** graph, and loading reads every
markdown file under every doc root. A caller that only wants to know *where* something goes
imports the derivation module directly instead:

```python
from ostler import path as okf_path

okf_path.epics_root_in(root)                     # <root>/docs/epics, or wherever docRoots: says
okf_path.epics_index_in(root)                    # the epic queue's index.md
okf_path.backlog_path_in(root)                   # docs/backlog.md
okf_path.features_root_in(root, service)         # the book, whole or per-service
okf_path.epic_dir_in(root, "checkout-flow")      # → .../0001-checkout-flow, from the bare slug
okf_path.story_dir_in(root, epic, slug)          # the story folder; join your own story.md
okf_path.waivers_path_in(root)                   # coverage-waivers.json, inside the book
okf_path.screenshots_dir_in(root)                # <book>/gui/screenshots
```

Every derivation comes in up to three spellings, chosen by what the caller already holds:

| Spelling | Takes | Use when |
| --- | --- | --- |
| `<name>_in(root, …)` | the **repo root** | the normal case — no graph load, `docRoots:` still honoured |
| `<name>(graph, …)` | a loaded `Graph` | you already have one; don't re-read the config |
| `<name>_under(container, …)` | the **directory itself** | you were *told* which one — an operator's `epics_dir`, or a book you already hold |

`_under` is what keeps an override from becoming a second, dumber derivation: ostler's rules
still apply *inside* the directory you passed, so an epic is matched by number-or-slug there
too. **This module is the only place a doc-tree path is derived** — no workflow, node or
script writes `docs/epics`, `docs/backlog.md` or `docs/features` as a literal; see "A
workflow does not spell a doc path" in `workflows/README.md`.

The loaded graph is a **snapshot**: reads reuse one cached load; a mutation applies
against a fresh load and invalidates the cache, so the next read sees it (`reload()`
forces a refresh). A read never returns `None` — an unloadable graph *raises*
`(OSError, ValueError, RuntimeError)`. QA/artifact/edit methods are lazy-imported, so a
read-only script never pays for the QA/vet machinery.

