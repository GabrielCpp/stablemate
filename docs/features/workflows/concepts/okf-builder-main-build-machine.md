---
type: concept
slug: okf-builder-main-build-machine
title: OKF-builder main build machine
---
# OKF-builder main build machine

The default `OkfBuilder` machine turns a service source tree into a complete OKF book. It is
reached from the [OKF-builder composition root](okf-builder-workflow-composition-root.md) and
is invoked by the [workhorse-okf-builder CLI](../workhorse-okf-builder.md). The machine owns
preparation, surface seeding, one-item-at-a-time investigation, doctor repair, coverage
reconciliation, a two-way semantic audit of source against book, optional web walkthrough
handoff, and the scoped book commit.

Its checkpointed inputs are `service` (the features-book service, empty for the whole tree),
`source_path` (defaulting to `service`), `source_excludes` (comma-separated source-relative
exclusions), `docs_path` (defaulting to the run checkout's docs root), `max_items` (zero means
no per-run investigation ceiling), `runtime_walkthrough` (opt-in live web app walk; the
semantic source/book audit always runs), `audit_turn_budget` (reviewer turns one audit pass may
spend; zero runs the pass to the end of the source tree), `audit_max_passes` (audit passes
before a budget-partial audit ships), `since` (optional revision for a diff-scoped crawl),
`story` (optional commit provenance), `workspace_file`, and `sources`. `recheck_only` and
`diff_base` remain accepted for in-flight runs but are retired, ignored inputs.

The machine first resolves the docs root, source root, feature root, worklist, and optional diff
scope. It refuses to start when the source is outside the repository, is not a directory, the
OKF graph cannot load, the installed OKF reference corpus is incomplete, or an explicitly
requested `since` revision cannot be resolved. An empty book is seeded from entry surfaces; an
existing book is reconciled from its checkpoint, doctor findings, and source watermark.

The drain selects one pending worklist item. A discovery item renders `main/prompts/investigate.md`
and a repair item renders `main/prompts/repair.md`; the result closes the current row and opens
the returned deeper items. The first investigation uses low power and a retry uses medium power.
Repair power is low for a simple first attempt, medium for difficult first attempts or the first
retry, and high after two failed attempts.

The convergence tail canonicalizes the book and reads doctor. Dirty findings become one repair
item per node/code; unchanged findings eventually park on the operator gate. A blocked finding
is adjudicated from both the book and its source/story: `book` requeues it, `code` files a seed
and records `known-defect:`, and `story` records a story conflict or parks when no story exists.
Clean doctor proceeds to a computed source-inventory join. Missing units are rechecked by the
agent, while stale citations are re-grounded. Six coverage re-scans are allowed before an
operator gate; this is a budget stop, not successful convergence. A completed full-scope join
writes the source watermark and hands a complete book to a two-way semantic audit of source
against book. An audit that surfaces repairs queues each as a `behavior-repair` item and returns
to the drain; a clear or budget-partial audit optionally hands off to the web walkthrough — a
no-op when the book has no web surface — and then commits only the service feature directory.

- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::investigation_power`
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::repair_power`
- detail: [OKF-builder workflow composition root](okf-builder-workflow-composition-root.md)
- detail: [workhorse-okf-builder](../workhorse-okf-builder.md)
- detail: [source inventory filtering](source-inventory-filter.md)

## Methods

### setup

- sig: `setup() -> Prepared`
- does: resolves the docs, features, source, and worklist paths from checkpointed inputs
- verify: count(subject="OKF-builder prepared settings", equals=1)
- does: returns a `Prepared` result carrying path resolution, book existence, worklist baseline, and preparation errors
- verify: count(subject="OKF-builder preparation results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.setup`
- tests: `workflows/tests/okf_builder/test_prepare_guard.py::test_accepts_the_bare_install_name`

### labels

- sig: `labels() -> dict[str, str]`
- does: labels the run with its service and, after selection, the current work item and progress
- verify: count(subject="OKF-builder dashboard label sets", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.labels`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_the_labels_name_the_service_and_the_item`

### start

- sig: `start() -> Continue`
- does: fails the run when preparation did not produce a measurable OKF graph and records the features root as failure context
- verify: exit_status(code=1)
- does: routes an existing book to checkpoint reconciliation
- verify: count(subject="existing-book reconciliation starts", equals=1)
- does: routes an empty book to entry-surface enumeration
- verify: count(subject="empty-book surface enumerations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.start`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_an_empty_book_is_filled_top_down_from_the_code_s_surfaces`

### enumerate_surfaces

- sig: `enumerate_surfaces() -> Continue`
- does: asks the low-power agent to identify every entry surface within the configured source scope
- verify: count(subject="OKF-builder surface enumeration turns", equals=1)
- returns: a continuation carrying discovered surface, runbook, environment, and harness work items
- verify: count(subject="OKF-builder surface discovery batches", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.enumerate_surfaces`

### seed_surfaces

- sig: `seed_surfaces(discovered: list[dict]) -> Continue`
- does: records discovered surface items as pending work without closing an existing item
- verify: count(subject="OKF-builder surface worklist seeds", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.seed_surfaces`

### select

- sig: `select(rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = "", refuels: int = 0) -> Continue | Await`
- does: selects the next pending worklist item using the current run allowance and done baseline
- verify: count(subject="OKF-builder worklist selections", equals=1)
- does: parks on an operator gate when the item ceiling is reached while work remains, after canonicalizing the partial book
- verify: visible(locator="OKF-builder item-ceiling gate")
- does: sends a dry worklist to checkpoint reconciliation with convergence counters preserved
- verify: count(subject="OKF-builder dry-drain checkpoints", equals=1)
- does: passes a selected item and its context to investigation with convergence counters preserved
- verify: count(subject="OKF-builder investigation dispatches", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.select`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_the_item_ceiling_blocks_on_an_operator_gate_not_a_finished_book`

### refuel

- sig: `refuel(rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = "", refuels: int = 0) -> Continue`
- does: increments the operator-granted allowance before re-entering selection
- verify: count(subject="OKF-builder refuel allowances", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.refuel`

### investigate

- sig: `investigate(current_item: dict, item_kind: str, item_target: str, item_context: str, item_code: str = "", progress: str = "", rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = "", refuels: int = 0) -> Continue`
- does: selects the investigation prompt for discovery items, the repair prompt for `fix:` items, and the behavior-repair prompt for `behavior-repair` items
- verify: count(subject="OKF-builder investigation prompt selections", equals=1)
- does: supplies the source scope, grammar, check vocabulary, worklist inventory, and item context to the agent
- verify: count(subject="OKF-builder investigation prompt inputs", equals=1)
- does: forwards the agent's discovered items and documentation status to item recording
- verify: count(subject="OKF-builder investigation results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.investigate`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_an_investigation_opens_the_items_it_reveals`

### record_item

- sig: `record_item(current_item: dict, discovered: list[dict], item_kind: str = "", item_context: str = "", doc_status: str = "", note: str = "", rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = "", refuels: int = 0) -> Continue`
- does: advances a stale-citation watermark only when the item is complete, then closes the current row and opens discovered rows
- verify: count(subject="OKF-builder recorded worklist items", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.record_item`

### checkpoint

- sig: `checkpoint(rnd: int = 0, rescan: int = 0, stall: int = 0, signature: str = "", refuels: int = 0) -> Continue | Await`
- does: canonicalizes the feature book and reads all doctor findings before deciding the next convergence action
- verify: count(subject="OKF-builder doctor checkpoints", equals=1)
- does: queues repair work for a dirty book and parks unchanged findings after the stall limit
- verify: visible(locator="OKF-builder stalled-finding gate")
- does: closes a pending `fix:` row as stale when the standing doctor report no longer names it, leaving blocked rows alone
- verify: count(subject="OKF-builder stale fix-item closures", equals=1)
- does: parks a clean but non-converging coverage scan after the rescan limit
- verify: visible(locator="OKF-builder coverage-rescan gate")
- does: routes a clean checkpoint to computed coverage
- verify: count(subject="OKF-builder coverage joins", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.checkpoint`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_warning_is_a_standing_finding`

### adjudicate

- sig: `adjudicate(rnd: int = 0, rescan: int = 0, signature: str = "", refuels: int = 0) -> Continue | Await`
- does: reads one blocked row awaiting adjudication
- verify: count(subject="OKF-builder blocked rows read for adjudication", equals=1)
- does: gathers the blocked row's book, source, and story evidence
- verify: count(subject="OKF-builder adjudication evidence bundles", equals=1)
- does: asks the medium-power adjudication prompt for a verdict
- verify: count(subject="OKF-builder adjudication turns", equals=1)
- does: applies each verdict before moving to the next blocked row
- verify: count(subject="OKF-builder applied adjudication verdicts", equals=1)
- does: parks rows still blocked after adjudication on an operator gate
- verify: visible(locator="OKF-builder blocked-finding gate")
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.adjudicate`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_a_code_verdict_files_a_seed_and_records_the_defect_on_the_nodes`

### retry_blocked

- sig: `retry_blocked(rnd: int = 0, rescan: int = 0, signature: str = "", refuels: int = 0) -> Continue`
- does: unblocks operator-resolved rows and resets the stall counter before returning to selection
- verify: count(subject="OKF-builder blocked-row retries", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.retry_blocked`

### rescan_coverage

- sig: `rescan_coverage(rnd: int = 0, rescan: int = 0, refuels: int = 0) -> Continue`
- does: inventories source units and joins them against the book's grounded citations and waivers
- verify: count(subject="OKF-builder source coverage rescans", equals=1)
- does: requeues stale citations for regrounding before asking an agent to judge missing units
- verify: count(subject="OKF-builder stale-citation requeues", equals=1)
- does: routes computed missing units to the coverage recheck prompt
- verify: count(subject="OKF-builder missing-unit rechecks", equals=1)
- does: hands a complete coverage result to the semantic audit
- verify: count(subject="OKF-builder semantic audit dispatches", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.rescan_coverage`
- tests: `workflows/tests/okf_builder/test_regrounding.py::test_a_symbol_that_changed_under_its_citation_is_queued_not_converged`

### recheck

- sig: `recheck(rnd: int = 0, rescan: int = 0, refuels: int = 0) -> Continue`
- does: passes the computed missing list and coverage evidence to the medium-power recheck prompt
- verify: count(subject="OKF-builder coverage recheck turns", equals=1)
- does: returns the prompt's real gaps for worklist seeding and its waivers for the next computed join
- verify: count(subject="OKF-builder coverage gap batches", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.recheck`

### seed_recheck

- sig: `seed_recheck(discovered: list[dict], rnd: int = 0, rescan: int = 0, refuels: int = 0) -> Continue`
- does: records real coverage gaps and returns to the drain with fresh stall and finding state
- verify: count(subject="OKF-builder coverage gap seeds", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.seed_recheck`

### semantic_audit

- sig: `semantic_audit() -> Continue | Await`
- does: hands the current source and book to the two-way behavior audit, spending at most `audit_turn_budget` reviewer turns this pass
- verify: count(subject="OKF-builder audit passes", equals=1)
- does: queues each audited repair as a `behavior-repair` worklist item and returns to the drain
- verify: count(subject="OKF-builder behavior repair seeds", equals=1)
- does: parks on an operator gate when queued behavior repairs exhaust their attempts
- verify: visible(locator="OKF-builder behavior-repair gate")
- does: runs another pass when the turn budget is spent short of `audit_max_passes`, otherwise proceeds with the unaudited packets listed as a budget-partial audit
- verify: count(subject="OKF-builder audit pass continuations", equals=1)
- does: parks on an operator gate when the audit reports unresolved evidence or an incomplete scope
- verify: visible(locator="OKF-builder unresolved-audit gate")
- does: routes a clear or budget-partial audit to the web walkthrough when requested, otherwise straight to commit
- verify: count(subject="OKF-builder post-audit routes", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.semantic_audit`
- detail: [OKF-builder audit workflow](../flows/okf-builder-audit.md)
- tests: `workflows/tests/okf_builder/test_workflow.py::test_behavior_repair_changes_book_and_reaudits_before_commit`

### walkthrough

- sig: `walkthrough() -> Continue`
- does: continues straight to the semantic audit without a live walk when `runtime_walkthrough` was not requested
- verify: count(subject="OKF-builder walkthrough skips", equals=1)
- does: hands a complete OKF book to the web walkthrough sub-flow when requested, which no-ops when the book has no web surface
- verify: count(subject="OKF-builder walkthrough handoffs", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.walkthrough`

### commit

- sig: `commit(walked: WebApp) -> Done | Continue`
- does: returns to the semantic audit instead of committing when the scope is not clear and the gap is not a spent turn-budget of unaudited-only packets
- verify: count(subject="OKF-builder pre-commit audit re-checks", equals=1)
- does: proceeds to commit a scope left only with unaudited packets once the audit pass cap has been reached, without requiring a further clear pass
- verify: count(subject="OKF-builder budget-partial commit proceeds", equals=1)
- does: commits only the completed service feature directory with optional `Story:` provenance
- verify: persists(subject="completed OKF service book")
- returns: a done result carrying the walkthrough outcome
- verify: count(subject="completed OKF-builder runs", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.commit`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_a_completed_book_is_committed_with_optional_story_provenance`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_budget_partial_audit_ships_after_the_pass_cap`

## Node Modules

The machine's non-agent nodes are split by subject. `prepare` resolves and validates the run
setting; `coverage` inventories source and computes coverage; `adjudicate` reads the other side
of blocked correspondence and routes verdicts; `finalize` performs the scoped commit.

### prepare

- sig: `prepare(logger, docs_path: str = "", service: str = "", source_path: str = "", source_excludes: str = "", repo_dir: str = "", since: str = "", recheck_only: bool = False, diff_base: str = "", story: str = "", workspace_file: str = "", sources: tuple[SourceRequest, ...] = ()) -> Prepared`
- does: resolves the repository, source, feature, and worklist paths and initializes or adopts the stamped worklist
- verify: persists(subject="OKF-builder worklist")
- does: writes a diff scope when `since` resolves and refuses preparation when it cannot be computed
- verify: created(subject="OKF-builder diff scope")
- returns: a `Prepared` result that carries `ostler_ok=false` and an explanatory error for unusable settings
- verify: json_path(path="$.ostler_ok", equals=false)
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/prepare.py::prepare`
- tests: `workflows/tests/okf_builder/test_since_scope.py::test_prepare_writes_the_scope_file_and_carries_it`

### inventory_source

- sig: `inventory_source(logger, source_root: str = "", output_path: str = "", source_excludes: str = "", repo_root: str = "", scope_path: str = "") -> SourceInventory`
- does: records readable source modules and declared symbols while excluding configured, generated, test, cache, and vendor paths
- verify: created(subject="OKF-builder source inventory")
- does: records operational units from make/just targets, compose services, package scripts, console scripts, and `__main__` entry points
- verify: json_path(path="$.operational", matches=".+")
- does: reports an error instead of treating an unreadable or unsupported source tree as an empty covered inventory
- verify: json_path(path="$.inventory_errors", matches=".+")
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::inventory_source`

### compute_coverage

- sig: `compute_coverage(logger, repo_root: str = "", features_root: str = "", service: str = "", inventory_path: str = "", waivers_path: str = "", prev_rescan: int = 0, scoped: bool = False) -> Coverage`
- does: joins the source inventory with grounded book citations and waivers to compute covered, missing, and waived units
- verify: count(subject="OKF-builder coverage calculations", equals=1)
- does: writes the missing-unit artifact for agent recheck
- verify: created(subject="OKF-builder missing-unit artifact")
- does: writes `coverage.json` only for an unscoped full-book measurement
- verify: created(subject="OKF-builder full coverage artifact")
- does: marks coverage incomplete when the graph, inventory, or citation regrounding cannot support a complete verdict
- verify: json_path(path="$.coverage_complete", equals=false)
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::compute_coverage`
- tests: `workflows/tests/okf_builder/test_since_scope.py::test_a_scoped_coverage_does_not_overwrite_the_committed_book_artifact`

### advance_watermark

- sig: `advance_watermark(logger, repo_root: str = "", item_kind: str = "", item_context: str = "", doc_status: str = "") -> Watermarked`
- does: advances the source catalog only for a complete stale-citation regrounding item
- verify: persists(subject="OKF-builder source watermark")
- does: leaves the watermark unchanged for partial or unrelated worklist items
- verify: unchanged(subject="OKF-builder source watermark")
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::advance_watermark`
- tests: `workflows/tests/okf_builder/test_regrounding.py::test_a_partial_turn_advances_nothing`

### method: blocked_rows

- sig: `blocked_rows(logger, worklist_path: str = "") -> BlockedRows`
- does: returns blocked rows that have not already received an adjudication verdict
- verify: count(subject="unadjudicated blocked OKF-builder rows", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/adjudicate.py::blocked_rows`

### gather_evidence

- sig: `gather_evidence(logger, repo_root: str = "", source_root: str = "", row_json: str = "") -> Evidence`
- does: resolves every affected book node and collects its grounded code references and latest covering story
- verify: count(subject="OKF-builder evidence bundles", equals=1)
- does: reads story text only when the story resolves in the planning graph
- verify: count(subject="resolved OKF-builder story evidence", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/adjudicate.py::gather_evidence`

### apply_verdict

- sig: `apply_verdict(logger, repo_root: str = "", worklist_path: str = "", row_json: str = "", verdict: str = "", chain: str = "", seed_summary: str = "", story_slug: str = "", story_epic: str = "") -> Applied`
- consistency: adjudication-verdict — raises `ValueError` when the adjudication verdict is not `book`, `code`, or `story`
- verify: json_path(path="$.exception.type", equals="ValueError")
- does: requeues a `book` verdict with its adjudication chain and fresh attempts
- verify: count(subject="book-side OKF-builder requeues", equals=1)
- does: files a seed and records `known-defect:` for every affected node on a `code` verdict
- verify: created(subject="OKF-builder code-defect seed")
- does: records a story conflict for a `story` verdict with a covering story and leaves the row blocked otherwise
- verify: visible(locator="OKF-builder story-conflict record")
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/adjudicate.py::apply_verdict`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_a_story_verdict_with_no_story_parks_with_the_chain_on_the_gate`

### commit_book

- sig: `commit_book(logger, repo_root: str, features_root: str, story: str = "") -> Committed`
- raises: raises `WorkflowFailed` when the feature book is outside the repository
- verify: exit_status(code=1)
- does: commits only the feature-book path with the fixed docs subject and optional story trailer
- verify: persists(subject="scoped completed OKF-builder book commit")
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/finalize.py::commit_book`
