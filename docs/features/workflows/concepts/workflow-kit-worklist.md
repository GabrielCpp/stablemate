---
type: concept
slug: workflow-kit-worklist
title: Workflow kit worklist builder
---
# Workflow kit worklist builder

The worklist builder is one composable answer to the question *what does the book owe the
code?*. It runs the same set of joins whether it is called against the whole tree
(`okf-builder`) or scoped to one story's changed paths (coder docs lane); the only difference
between the two callers is the path filter. The drain receives the rows it has to pick up,
and the recheck agent adjudicates the uncovered units the join surfaced but the builder
must not classify on its own.

The builder imports ostler as a library rather than shelling the CLI. `requires: dist:` makes
ostler import before node one, and the CLI-presence fallbacks that used to sit in front of
that were deliberately removed (`ostler-import-is-a-run-precondition`); shelling would
reintroduce the seam the precondition exists to close.

The deterministic row set is two joins, in drain order:

- **`dangling`** — doctor codes `dangling-code-ref`, `missing-code-symbol`. The
  checkpoint's channel; surfaced as `fix:` rows. A cited symbol's bytes disagreeing with
  the source is doctor's `stale-citation` finding instead, queued by
  `coverage._regrounding` — a different mechanism, not this join.
- **`uncovered`** — units in the inventory nothing cites. The builder surfaces the list; the
  recheck agent decides which are real work, which are helpers, and which are deliberate
  non-units. A symbol that moved to another path is folded in here too: `backfill.plan`
  suppresses the new location's `uncovered` row when its symbol name uniquely matches a
  `dangling` row already surfaced, so the one edit reads as one finding — a symbol name
  that recurs at more than one other path is not provably a move, so both rows stay.

Two further joins sit beside them:

- **`trim`** — an own-repository path the book's own citations name (`coverage.citations`)
  that the tree no longer carries. Citations are dangling in a different way (the file is
  gone), so the bullets are cut, the node is queued for authored removal if it lost its
  last bullet, and the neighbours are queued for review so a journey whose third step
  vanished is read against the book rather than the file. A foreign `repo://` citation is
  never trimmed this way — a checkout-less foreign ref is `unreachable-citation` territory,
  not a deleted path in this tree. A citation whose symbol relocated (`backfill.plan` marks
  the `dangling` row's `relocated_to`) is excluded from trim as well: the file is gone but
  the symbol is not, and trim's own rule against re-pointing a bullet to a neighbour means
  deleting the node instead of fixing the citation — so the row survives as `fix:dangling`
  and drives a repair that re-points it.
- **`unreachable`** — orphan pages `graph --orphans` already computes: a page no edge reaches,
  on the page or any heading in it, so one link clears the page and its sections. Authored removal,
  queued the same way the rest of the work is.

- code: `workflows/src/workhorse_workflows/kit/worklist.py::build_worklist`
- code: `workflows/src/workhorse_workflows/kit/worklist.py::BuildWorklist`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.rescan_coverage`
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs._obligations`
- code: `workflows/tests/okf_builder/test_worklist_builder.py::fresh_repo`
- code: `workflows/tests/okf_builder/test_worklist_builder.py::booked_repo`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_an_unbooked_repo_owes_every_unit_in_missing`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_booked_repo_with_no_drift_is_complete`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_missing_symbol_queues_a_dangling_row`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_deleted_path_emits_trim_bullet_and_review_rows`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_deleted_path_does_not_emit_trim_when_nothing_cited_it`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_relocated_symbol_keeps_the_dangling_row_instead_of_trim`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_repeated_symbol_name_elsewhere_still_trims`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_path_filter_narrows_missing_to_those_paths`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_an_empty_filter_is_a_real_filter_not_whole_tree`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_orphan_concepts_queue_unreachable_rows`

## Fields

### WorklistRow

- type: `dict`
- semantics: the builder row shape the worklist mutator merges in — `kind` decides which
  prompt or repair handler the drain dispatches to, `target` is the node id or unit ref the
  row names, and `context` is the JSON-encoded prompt payload
- code: `workflows/src/workhorse_workflows/kit/worklist.py::WorklistRow`

### BuildWorklist

- type: frozen dataclass
- semantics: the deterministic rows a build queues, plus what the recheck agent adjudicates
- code: `workflows/src/workhorse_workflows/kit/worklist.py::BuildWorklist`

### rows

- type: `tuple[WorklistRow, ...]`
- semantics: the deterministic rows the drain consumes — every dangling `fix:` row, trim
  bullet, trim review, and orphan row
- code: `workflows/src/workhorse_workflows/kit/worklist.py::BuildWorklist.rows`

### missing

- type: `tuple[dict, ...]`
- semantics: the coverage join's whole `missing` list — surfaced separately because the
  recheck agent's read is judgement the builder must not make on its own
- code: `workflows/src/workhorse_workflows/kit/worklist.py::BuildWorklist.missing`

### coverage_complete

- type: `bool`
- semantics: the runner's own convergence verdict — `true` requires the coverage join to
  report complete and every path the book's own citations name to still be present in the
  tree
- code: `workflows/src/workhorse_workflows/kit/worklist.py::BuildWorklist.coverage_complete`

## Methods

### build_worklist

- sig: `build_worklist(repo_root: Path, features_root: Path, service: str, *, paths: Sequence[str] | None = None) -> BuildWorklist`
- does: rejects `repo_root` when the OKF graph cannot load at that root
- verify: exit_status(code=1)
- does: rejects the call when neither the worklist-relative source inventory nor the legacy
  `<features>/.source-inventory.json` exists
- verify: exit_status(code=1)
- does: rejects the call when a present inventory cannot be parsed
- verify: exit_status(code=1)
- does: rejects the call when `backfill.plan` fails against the loaded graph and inventory
- verify: exit_status(code=1)
- does: surfaces a `dangling` row from `backfill.plan` as one `fix:<doctor-code>` row per
  citing node
- verify: count(subject="dangling fix rows from the builder", equals=1)
- does: keeps a `dangling` row standing when its citation's symbol relocated
  (`relocated_to` set) instead of folding it into `uncovered`, so the citation can be
  re-pointed rather than the node deleted
- verify: count(subject="fix:dangling rows carrying relocated_to", equals=1)
- does: drops `uncovered` units from the row list
- verify: absent(subject="uncovered rows in the builder's row list")
- does: surfaces `uncovered` units in `missing` instead, so the recheck agent adjudicates
  whether they are units at all
- verify: json_path(path="$.missing_path", matches="uncovered")
- does: narrows the plan's rows and missing units to `paths` when one is supplied
- verify: json_path(path="$.narrowed_to_paths", equals=true)
- does: emits one `trim-bullet` row per node whose citations name an own-repository path
  the tree no longer carries
- verify: count(subject="trim-bullet rows from the builder", equals=1)
- does: skips a `trim-bullet` for a citation whose symbol relocated, since the standing
  `dangling` row already drives its repair
- verify: absent(subject="trim-bullet rows for relocated citations")
- does: emits one `trim-review` row per caller of a node whose citations now trim
- verify: count(subject="trim-review rows from the builder", equals=1)
- does: emits one `unreachable` row per orphan page, never per heading, when `paths` is `None`
- verify: count(subject="unreachable rows from the whole-tree builder", equals=1)
- does: skips the unreachable join when `paths` is supplied — a scoped build does not own
  the whole graph's reachability
- verify: count(subject="unreachable rows from the scoped builder", equals=0)
- does: marks `coverage_complete` only when the coverage join reports complete
- verify: json_path(path="$.coverage_complete", equals=true)
- does: marks `coverage_complete` false when a citation names a path the tree no longer
  carries
- verify: json_path(path="$.coverage_complete", equals=false)
- returns: a `BuildWorklist` carrying `rows`, `missing`, and `coverage_complete`
- verify: count(subject="BuildWorklist returns from the builder", equals=1)
- code: `workflows/src/workhorse_workflows/kit/worklist.py::build_worklist`
- detail: [OKF-builder main build machine](okf-builder-main-build-machine.md)
- detail: [OKF-builder shared worklist](okf-builder-shared-worklist.md)
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_an_unbooked_repo_owes_every_unit_in_missing`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_booked_repo_with_no_drift_is_complete`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_missing_symbol_queues_a_dangling_row`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_deleted_path_emits_trim_bullet_and_review_rows`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_deleted_path_does_not_emit_trim_when_nothing_cited_it`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_relocated_symbol_keeps_the_dangling_row_instead_of_trim`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_repeated_symbol_name_elsewhere_still_trims`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_a_path_filter_narrows_missing_to_those_paths`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_an_empty_filter_is_a_real_filter_not_whole_tree`
- tests: `workflows/tests/okf_builder/test_worklist_builder.py::test_orphan_concepts_queue_unreachable_rows`