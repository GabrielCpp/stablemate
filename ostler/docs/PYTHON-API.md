# The Python API: `Ostler`, `ostler.markdown`

This document is ostler's library face: the `Ostler` facade over the graph and the markdown
parser every reader of the graph goes through. For the command line, see [CLI.md](CLI.md); for what ostler
is at all, [README.md](../README.md).

## The `Ostler` facade

The `Ostler` facade exposes the major graph mutations, queries, and workflow-facing
checks in-process. Prefer it over spawning the CLI and parsing JSON when the operation
is present here: you load the graph once and get back plain objects
(`dict`/`list`/`str`, a `Result`, an `EditPlan`, or a `QaOutcome`) instead of a
subprocess and a stdout scrape. CLI-only reporting and maintenance commands remain on
the command line.

```python
from ostler import Ostler

okf = Ostler("path/to/repo")          # graph root discovered upward, like `-C DIR`; None ⇒ cwd
scoped = Ostler("path/to/repo", doc_roots={"epics": "product/epics"})

okf.milestone_epics()                 # ["EPIC-1", …]               (every epic the milestones list, in order)
okf.list("story", epic="checkout-flow")   # [{"slug","status",…}]  (ostler list --type story)
okf.next_story("checkout-flow")       # {"slug": …} | None          (ostler next-story)
okf.spec_path("01-cart")              # "docs/specs/01-cart"        (ostler path spec)
okf.doctor()                          # QaOutcome; .data is the report (ostler doctor --json)
okf.query("stories-covering-seed", "seed-1")   # the stories that cover a seed  (ostler query)

res = okf.create_story("checkout-flow", "02-pay", "Payment", covers=["seed-1"])
res.ok, res.entity_id                 # a Result, not parsed JSON   (ostler create story)
okf.update_story("02-pay", title="Payment", covers=["seed-1"], depends=["01-cart"])
item = okf.create_backlog_item("Ship checkout parity", repo="acme", area="checkout")
milestone = okf.create_milestone("checkout-mvp", "Checkout MVP", [item.entity_id])
okf.set_milestone_source_items("checkout-mvp", [item.entity_id])
okf.backlog_import("docs/backlog.md", repo="acme")  # turn an old bullet list into records, once
okf.delete_story("02-pay")             # same mutation surface as `ostler delete story`
okf.delete_epic("checkout-flow")        # also removes milestone references
okf.set_status("01-cart", "QA passed")
```

`doc_roots` overrides configured roots for that facade's reads and mutations; relative values
resolve from the discovered repository root. The loaded graph is a **snapshot**: reads reuse one cached load; a mutation
(`create_*`/`update_story`/`delete_*`/`add_seed`/`set_status`/`backlog_*`/
`set_milestone_*`/`settle_review`/`settle_answers`) applies
against a fresh load and invalidates the cache, so the next read reflects it
(`reload()` forces a refresh). A read never returns `None` — an unloadable graph
*raises*. The QA/artifact/edit surface is on the same object
(`qa_validate`/`qa_run`, `qa_tools_catalog`,
`artifact_vet`, `settle_review`, `settle_answers`), lazy-imported so a read-only caller never loads the QA/vet
machinery. `settle_review(slug, status_write=False)` writes the settlement ledger and leaves
`story.md` alone. `settle_answers(slug, filed)` settles a markdown Answer list against the finding
ids the caller filed and never writes a status. `open_stories(epic)` lists an epic's unfinished
stories in dependency order, each with its `spec_dir`, `deps` and `open_deps`. `story(slug)` returns
one story in that shape, or `None`. `from ostler import load` returns the bare `Graph` if you want the
functional core directly.

## `QaOutcome` — the checks answer instead of raising

Every check on the facade, the qa/artifact family above plus `doctor`,
returns a `QaOutcome` rather than a raw dict that raises on the way to producing one:

```python
outcome = okf.doctor()
outcome.ok        # the verdict: the join is complete / the check holds
outcome.status    # "passed" | "failed" | "invalid" | a status the check names itself
outcome.message   # one line — the same text the CLI prints
outcome.data      # the `--json` payload, always carrying a "status" key
```

A *data*-shaped failure is part of that answer: a malformed plan, a
book that will not load. Each comes back as
`ok=False, status="invalid"`, so no caller wraps the call in
`except (OSError, ValueError, RuntimeError)` — which is what `cli.py` and the coder
workflow's now-deleted `ostler_qa` adapter were each doing independently.

`status == "invalid"` is worth its own branch wherever an empty result would otherwise read
as a pass: a clean report because the book would not load is not "everything is
fine", and the CLI keeps a distinct exit code (2) for it.

A **call-site** mistake still raises, and should — an unknown `etype`, a `need` that is
neither `"build"` nor `"author"`, a bad argument type is a bug where it was made, and an
outcome would hide it. The name-taking reads (`list`/`search`/`query`, the `*_path`
resolvers, `expand`/`handle`) have no data-shaped raises to convert: an unmatched name comes
back as `[]`, `None`, or the name itself — already the answer.

## `ostler.markdown` — the markdown parser everything reads through

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
`Table` are 0-indexed and body-relative; `doc.body_offset` converts to a file line.
