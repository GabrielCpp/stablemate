---
type: concept
slug: the-ostler-facade-and-book-utilities
title: The Ostler facade and book utilities
---
# The Ostler facade and book utilities

`api.py`'s `Ostler` is the in-process alternative to shelling out to the `ostler` CLI: a caller
that already runs Python constructs one against a repository root and gets back the same
operations the CLI exposes — `list`/`search`/`query` for reading the graph, `next_epic`/
`next_story`/`open_stories`/`story`/`next_story_report`/`epic_authored` for planning,
`create_epic`/`create_milestone`/`create_story`/`create_backlog_item`/`create_spec`/`add_seed`/
`update_story`/`delete_story`/`delete_epic` for scaffolding, `doctor`/`fmt`/`gc`/`coverage` for
book health, `qa_context`/`qa_run`/`qa_report`/`qa_lint`/`qa_validate`/`qa_frames`/
`qa_tools_catalog`/`artifact_vet` for the QA pipeline, and `settle_review`/`settle_answers` for
closing out a review, each as a plain method rather than a subprocess call. `graph` and `reload`
expose and refresh the `Graph` the instance holds; `_load`/`_fresh`/`_snapshot_key`/`_recall`
decide whether that `Graph` can be reused from one call to the next. That reuse is what
`Snapshot` and its module-level helpers check: `_snapshot_of` records the content hash of every
file a load actually read (`_file_sha`) and the digest of the book's whole directory listing
(`_listing`, over `pages.py`'s `files_in_book`); `Snapshot.holds` reports whether every one of
those files still reads exactly as recorded, which is what lets a long-lived `Ostler` instance
skip re-parsing the whole book on every call instead of only on the calls that actually touch a
changed file. `_story_candidates` enumerates the paths a story's markdown file could live at, and
`_unreadable` turns a load failure into the same `QaOutcome` shape a QA check would have returned
had the book loaded.

`select.py` is the selection logic behind `Ostler`'s planning methods: `is_done`/`is_blocked`
classify a story's status string, `epic_by_name` resolves an epic by its directory name or slug,
`epic_done`/`epic_authored` roll a whole epic's stories up into one boolean, `dag_order` orders an
epic's stories so a dependency precedes its dependents, and `epic_cycle` finds one dependency
cycle when `dag_order` cannot complete. `next_epic` is the first milestone-ordered epic with
unfinished work; `next_story_report`/`next_story` single out the next runnable story in a named
epic, distinguishing `need="build"` from `need="author"`; `open_stories` and `story_entry` report
every open story's full dependency state in that same shape.

`todo.py` is the epic queue `Ostler.todo`/`todo_add`/`todo_prune`/`todo_reorder` delegate to:
`list_epics` reads the queue's current order, `_milestone_ordered_epics` is the implicit order a
queue falls back to when nothing has reordered it explicitly, `add`/`prune`/`reorder` mutate the
stored order and `_write`/`_render` persist and print it, and `_index_path`/`_queued_as`/
`_title_of` are the small path and lookup helpers underneath. `trace.py`'s `run` and `_find_ui`/
`_trace_ui` answer "how is this UI token reached": given a node id or locator token, it walks the
graph backward to the surface that roots it, the same question `reach.py` and `book_reach.py`
answer in aggregate for every screen at once, here answered for one token on demand.

`server_membership.py`'s `check_server_membership` validates that an endpoint page actually
belongs to the server page that claims it, by resolving a server's `## Endpoints`-style heading
inventory (`_inventory`, `_servers`) and the type of what it names (`_type_of`), flagging one
inlined directly rather than linked out (`_inline`) — the complement to `carve.py`'s
`carve_endpoints`, which is what produces the linked-out shape this check expects.

`source_snapshots.py` is the model behind `sources.json`, the catalog a book's unqualified
`code:` references resolve against: `book_repository`/`set_book_repository` read and write which
repository a book's own `repository.txt` names as the default; `SourceSymbol` pairs one
declaration with the content digest that watermarks it, `SourceFile` is one cataloged file's path,
digest and declared symbols (`digest_of` looking one symbol's watermark up), `RepositorySnapshot`
is one repository's full catalog entry (its resolved base/head commits, `SourceScope`s, and
`source_fingerprint`), and `SourceCatalog` is the whole `sources.json` file, versioned, holding
every repository's `RepositorySnapshot`. `catalog_path`/`load_catalog` locate and parse the file;
`resolved_sha` resolves a revision to a commit, and `source_fingerprint` hashes every path and
byte under a repository's declared scopes so a catalog entry can detect its source has moved
without re-walking the full diff on every run.

- code: ostler/ostler/api.py::Ostler@defd95727723
- code: ostler/ostler/api.py::Snapshot@defd95727723
- code: ostler/ostler/api.py::_snapshot_of@defd95727723
- code: ostler/ostler/api.py::_listing@defd95727723
- code: ostler/ostler/api.py::_file_sha@defd95727723
- code: ostler/ostler/api.py::_story_candidates@defd95727723
- code: ostler/ostler/api.py::_unreadable@defd95727723
- code: ostler/ostler/select.py::is_done@077129549b9f
- code: ostler/ostler/select.py::epic_by_name@077129549b9f
- code: ostler/ostler/select.py::epic_done@077129549b9f
- code: ostler/ostler/select.py::epic_authored@077129549b9f
- code: ostler/ostler/select.py::dag_order@077129549b9f
- code: ostler/ostler/select.py::epic_cycle@077129549b9f
- code: ostler/ostler/select.py::next_epic@077129549b9f
- code: ostler/ostler/select.py::next_story_report@077129549b9f
- code: ostler/ostler/select.py::next_story@077129549b9f
- code: ostler/ostler/select.py::open_stories@077129549b9f
- code: ostler/ostler/select.py::story_entry@077129549b9f
- code: ostler/ostler/todo.py::list_epics@eb0ea0bc4039
- code: ostler/ostler/todo.py::add@eb0ea0bc4039
- code: ostler/ostler/todo.py::prune@eb0ea0bc4039
- code: ostler/ostler/todo.py::reorder@eb0ea0bc4039
- code: ostler/ostler/todo.py::_milestone_ordered_epics@eb0ea0bc4039
- code: ostler/ostler/trace.py::run@627ab268dee3
- code: ostler/ostler/server_membership.py::check_server_membership@692e1d58d870
- code: ostler/ostler/source_snapshots.py::SourceCatalog@40694806c2b5
- code: ostler/ostler/source_snapshots.py::RepositorySnapshot@40694806c2b5
- code: ostler/ostler/source_snapshots.py::SourceFile@40694806c2b5
- code: ostler/ostler/source_snapshots.py::SourceSymbol@40694806c2b5
- code: ostler/ostler/source_snapshots.py::book_repository@40694806c2b5
- code: ostler/ostler/source_snapshots.py::set_book_repository@40694806c2b5
- code: ostler/ostler/source_snapshots.py::catalog_path@40694806c2b5
- code: ostler/ostler/source_snapshots.py::load_catalog@40694806c2b5
- code: ostler/ostler/source_snapshots.py::resolved_sha@40694806c2b5
- code: ostler/ostler/source_snapshots.py::source_fingerprint@40694806c2b5
- detail: [The book's markdown model](the-books-markdown-model.md)
- detail: [ostler](../cli.md)

## Contract

- a snapshot is a cache key, not a lock: `Snapshot.holds` only ever says whether a previously
  loaded `Graph` is still valid to reuse; it never itself re-reads the book, so a stale snapshot
  always triggers a full `_fresh` reload rather than returning stale data silently.
- `Ostler` wraps the CLI's operations, not its process boundary: every method returns the same
  `Result`/`QaOutcome`/plain value the matching CLI command would print, so a caller gets
  structured data instead of parsing text output.
- a catalog entry fingerprints scope, not just content: `source_fingerprint` hashes each declared
  `SourceScope`'s own identity alongside the files under it, so two repositories with identical
  file content but different declared scopes never fingerprint the same.
