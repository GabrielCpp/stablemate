# The Python API — `Ostler`, `ostler.markdown`, `ostler.syntax`

This document is ostler's library face: the `Ostler` facade over the graph, the markdown
parser every reader of the book goes through, and the tree-sitter front end that answers
"what does this file declare?". For the command line, see [CLI.md](CLI.md); for what ostler
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

okf.todo()                            # ["checkout-flow", …]        (ostler todo list)
okf.list("story", epic="checkout-flow")   # [{"slug","status",…}]  (ostler list --type story)
okf.next_story("checkout-flow")       # {"slug": …} | None          (ostler next-story)
okf.spec_path("01-cart")              # "docs/specs/01-cart"        (ostler path spec)
okf.doctor()                          # QaOutcome; .data is the report (ostler doctor --json)
okf.query(
    "story-provenance",
    "TEAM-123",
    checkouts={"api-service": "/workspace/api-service"},
)                                     # exact trailers + qa-okf-context.json

res = okf.create_story("checkout-flow", "02-pay", "Payment", covers=["seed-1"])
res.ok, res.entity_id                 # a Result, not parsed JSON   (ostler create story)
okf.update_story("02-pay", title="Payment", covers=["seed-1"], depends=["01-cart"])
item = okf.create_backlog_item("Ship checkout parity", section="Scope")
milestone = okf.create_milestone("checkout-mvp", "Checkout MVP", [item.entity_id])
okf.set_milestone_source_items("checkout-mvp", [item.entity_id])
okf.backlog_adopt("docs/backlog.md")  # name direct unnamed work bullets in place
okf.delete_story("02-pay")             # same mutation surface as `ostler delete story`
okf.delete_epic("checkout-flow")        # also removes milestone and queue references
okf.set_status("01-cart", "QA passed")
```

`doc_roots` overrides configured roots for that facade's reads and mutations; relative values
resolve from the discovered repository root. The loaded graph is a **snapshot**: reads reuse one cached load; a mutation
(`create_*`/`update_story`/`delete_*`/`add_seed`/`set_status`/`backlog_*`/
`set_milestone_*`/`todo_*`/`settle_review`) applies
against a fresh load and invalidates the cache, so the next read reflects it
(`reload()` forces a refresh). A read never returns `None` — an unloadable graph
*raises*. The QA/artifact/edit surface is on the same object
(`qa_context`/`qa_validate`/`qa_run`/`qa_context_validate`, `qa_tools_catalog`,
`artifact_vet`, `settle_review`), lazy-imported so a read-only caller never loads the QA/vet
machinery. `from ostler import load` returns the bare `Graph` if you want the
functional core directly.

The provenance queries are derived reads, not a ledger. `story-provenance` joins exact Git
`Story:` trailer lines to the story-scoped context packet; `commit-story` performs the reverse
trailer lookup; `node-provenance` scans stored packets for direct, contract, and journey roles.
External repository checkouts are supplied by logical repository id and are never written into
the docs repository. Missing history or packets are returned as warnings rather than inferred.

## `QaOutcome` — the checks answer instead of raising

Every check on the facade — the qa/artifact family above, plus `doctor` and `coverage` —
returns a `QaOutcome` rather than a raw dict that raises on the way to producing one:

```python
outcome = okf.coverage(inventory="inventory.json")
outcome.ok        # the verdict: the join is complete / the check holds
outcome.status    # "passed" | "failed" | "invalid" | a status the check names itself
outcome.message   # one line — the same text the CLI prints
outcome.data      # the `--json` payload, always carrying a "status" key
```

A *data*-shaped failure is part of that answer: an unreadable inventory, a malformed plan, a
context file that will not parse, a book that will not load. Each comes back as
`ok=False, status="invalid"`, so no caller wraps the call in
`except (OSError, ValueError, RuntimeError)` — which is what `cli.py` and the coder
workflow's now-deleted `ostler_qa` adapter were each doing independently.

`status == "invalid"` is worth its own branch wherever an empty result would otherwise read
as a pass: zero uncovered units because the inventory would not parse is not "everything is
covered", and the CLI keeps a distinct exit code (2) for it.

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
`Table` are 0-indexed and body-relative; `doc.body_offset` converts to a file line. The
rule this serves, and the parser for every other format, is the
`structured-parsing` skill in the base library; `make check-parsers` enforces
it.

## `ostler.syntax` — the same rule, for source code

The code side of the graph gets the same treatment: `ostler.inventory` answers "what does
this file declare?" for the coverage join, `doctor`'s `code:` citation grounding and the QA
diff mapper, and all three read a **parse**, never a line match. Python goes through the
stdlib `ast`; Go, TypeScript/TSX, PHP and Twig go through `ostler.syntax`, which is
tree-sitter behind a four-function surface (`parse` / `walk` / `text_of` / `lines_of`).

tree-sitter rather than the target language's own toolchain, deliberately: ostler runs in
agent containers and CI against repos it never builds, and `okf-builder` reads working trees
mid-edit. A `go build`-shaped parser would need Go installed and the tree compiling, and the
fallback that absence forces is a second grammar disagreeing with the first — the exact
failure this module exists to end. tree-sitter is a prebuilt wheel, needs nothing from the
repo it reads, and recovers from a syntax error instead of refusing the file.

What that buys, concretely: a commented-out `export function` is no longer a unit the book
owes coverage for, a name inside a template literal no longer grounds a citation, and the
shapes no pattern spelled — `export abstract class`, `export const {a, b} = …`, Go's grouped
`type (…)` — are visible, so a correct citation stops failing with no way to fix it. Where a
file is mid-edit, the region the parser could not read grounds any name it mentions;
everywhere else stays exact.
