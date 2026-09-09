---
type: concept
slug: groom-store
title: Telemetry store (SQLite)
---
# Telemetry store (SQLite)

The persistent, queryable half of groom's telemetry collection: a SQLite database providing durable ingest and cross-run search. The other half is the in-memory [run-telemetry](run-telemetry.md) cache holding the live picture for a single run, which is ephemeral and process-local. Each run's `events.jsonl` on disk remains the record of truth; SQLite exists for the queries no append-only file can answer (slowest nodes, error spans by run, cost per run, who waited on what), and for the retention window before rows are pruned.

Connection discipline is load-bearing: one process-wide writer with an `RLock`, many readers with per-thread read-only connections, both autocommit and explicit `BEGIN IMMEDIATE`, and resilience that retries once on failure. The design separates read and write contention so a cold dashboard query does not stall OTLP ingest, which used to cause collector 500s under load. Query methods use keyset pagination (cursor-based) rather than OFFSET, which remains stable when new rows are inserted by concurrent writers — essential for live telemetry queries where OFFSET would drift across page boundaries.

- code: `groom/groom/store.py`
- extends: [run-telemetry](run-telemetry.md)
- tests: `groom/tests/test_store.py`
- tests: `groom/tests/test_store_resilience.py`
- detail: [_Store class connection lifecycle](_store-class.md) — the process-wide singleton managing connection discipline, resilience, and thread-safety

## Contract

- **Role**: queryable durable telemetry index, one per groom process
- **Lifecycle**: opened lazily on first write, re-opened on connection failure, closed on process exit; tests reset between cases via `GROOM_DB` env var
- **Data scope**: spans (traces), metrics (periodic readings), logs (structured records), turns (archived transcript index), attend_sessions (operator gate dispatch log)
- **Retention**: `RETENTION_DAYS` (default 30) bounds queryability; older rows are deleted once archival writes them to disk (`archived` set passed to `prune`)
- **Concurrency**: SQLite WAL mode, one write lock per transaction, readers isolated per thread — no connection sharing between threads even within a pool
- **Fault tolerance**: transient failures retry once; persistent failures (disk full, corruption) are recorded and surfaced via `health()` but not masked
- **Health**: tracks opener count, failure count, last error, last good statement, last write and prune times, WAL size, and checkpoint busy state

## Storage and indices

Four main tables with indices for the common queries:

- **spans**: trace events with identity, timing, status, attributes, and promoted cost columns (15 indices covering query patterns)
- **metrics**: time-series gauge and counter points with run and name indices
- **logs**: structured log records keyed by run and severity (3 indices)
- **turns**: index of archived transcript files, keyed by visit (generation, seq, session) for replay order
- **attend_sessions**: dispatch log for the operator gate attendant, one row per run needing rescue

Schema is versioned via `_ADDED_*_COLUMNS` so a new groom can backfill columns on an existing store without migration tooling.

## Methods

### ingest

- sig: `insert_spans(spans: list[dict[str, Any]]) -> None` and `insert_metrics(points: list[dict[str, Any]]) -> None` and `insert_logs(records: list[dict[str, Any]]) -> None
- does: INSERT OR REPLACE spans (keyed by span_id) to handle exporter retries without duplication
- verify: count(subject="span rows with matching span_id after duplicate ingest", equals=1)
- does: plain INSERT metrics and logs (no dedup key) — batch retries are accepted as cosmetic duplication
- verify: count(subject="metric rows after duplicate ingest", equals=2)
- does: filter out liveness metrics ahead of the store lock (`insert_metrics` pre-filters before calling `_write_metrics`) to avoid contention on metrics-only exports
- verify: absent(subject="liveness metrics in storage")
- does: promote high-value span attributes (cost, token counts, git state, workspace path) to indexed columns for performance
- verify: persists(subject="promoted span attribute columns like input_tokens")
- does: compute estimated cost at ingest using `groom.prices` rate card and the reported token counts
- verify: persists(subject="estimated cost populated in span record")
- code: `groom/groom/store.py::insert_spans`
- code: `groom/groom/store.py::insert_metrics`
- code: `groom/groom/store.py::insert_logs`
- tests: `groom/tests/test_store.py::test_span_upsert_deduplicates_retries`
- tests: `groom/tests/test_store.py::test_metrics_are_appended_not_replaced`

### query_spans

- sig: `query_spans(run: str = "", node: str = "", status: str = "", slower_than: float | None = None, limit: int = 200, before_ts: float | None = None, since_ts: float | None = None) -> list[dict[str, Any]]`
- does: filter spans by run_id, node, status, minimum duration, and timestamp window
- verify: count(subject="results when filtering for a nonexistent run_id", equals=0)
- does: use keyset pagination via `before_ts` (the start_ts of the last row from the prior page) instead of OFFSET
- verify: json_path(path="$[0].start_ts", matches="^[0-9.]+$")
- returns: newest spans first, each with raw attributes and promoted columns like cost and token counts
- verify: json_path(path="$[0].attrs_json", matches="^\\{")
- code: `groom/groom/store.py::query_spans`
- tests: `groom/tests/test_store.py::test_query_spans_pages_with_keyset_cursor`
- limit: clamped to max 1000 rows

### query_logs

- sig: `query_logs(run: str = "", node: str = "", level: str = "", contains: str = "", limit: int = 200, before_ts: float | None = None) -> list[dict[str, Any]]`
- does: filter logs by run_id, node, severity floor (not equality), text search
- verify: count(subject="non_matching_logs_when_filtered_by_run", equals=0)
- does: treat severity as a floor: asking for WARNING returns warnings and errors, not just warnings
- verify: omits(subject="severities below the requested floor", matches="^(INFO|DEBUG|TRACE)$")
- does: use keyset pagination via `before_ts` for live concurrent exports
- verify: json_path(path="$[*].ts", matches="^\\d+(\\.\\d+)?$")
- returns: newest logs first, each with attributes parsed from JSON and snapshot fields (head commit, workspace path, git branch)
- verify: json_path(path="$[0].attrs", matches="^\\{")
- code: `groom/groom/store.py::query_logs`
- tests: `groom/tests/test_store.py::test_log_severity_is_a_floor_not_equality`

### query_turns

- sig: `query_turns(run: str = "", node: str = "", session: str = "", workflow: str = "", limit: int = 200) -> list[dict[str, Any]]`
- does: index and query archived transcript metadata (file path, size, hash) without reading transcript bodies
- verify: json_path(path="$[0].path", matches=".+")
- does: order by visit key (generation, seq) to preserve run sequence across generations — this survives checkpoint rewinds where wall-clock order would not
- verify: json_path(path="$[0].generation", matches="^\\d+$")
- returns: newest visit last (so `[1:]` is "every pass after the first" for loop analysis)
- code: `groom/groom/store.py::query_turns`
- tests: `groom/tests/test_store.py::test_turns_ordered_by_visit_across_generations`

### run_summaries

- sig: `run_summaries(limit: int = 50, now: float | None = None, run: str = "") -> list[dict[str, Any]]`
- does: GROUP BY run_id over the active window (last 24h by default, `ACTIVE_WINDOW_S`) to fetch fleet telemetry without scanning retained history
- verify: count(subject="result rows for a single run with multiple spans", equals=1)
- does: return workflow, repo, span/error counts, and timestamp bounds for the fleet view
- verify: json_path(path="$[0].first_ts", matches="^\\d+(\\.\\d+)?$")
- does: explicitly does not report whether a run is currently running (that is liveness, not durable history)
- verify: absent(subject="is_running field in result")
- code: `groom/groom/store.py::run_summaries`
- tests: `groom/tests/test_store.py::test_fleet_view_respects_active_window`
- limit: clamped to max 500 rows

### run_profile

- sig: `run_profile(run: str) -> dict[str, Any] | None`
- does: partition one run's wall time by activity: agent, deterministic, infra, waits, resume gaps
- verify: json_path(path="$.time_s", matches="\\{.*\\}")
- does: aggregate rework statistics by attempting node and gate verdict
- verify: json_path(path="$.attempt_groups", matches="^\\[.*\\]$")
- does: sum metrics and spans to bound the wall clock (gauges only for metrics, since heartbeat ticks are not stored)
- verify: json_path(path="$.observed_start_ts", matches="^\\d+(\\.\\d+)?$")
- returns: time partitions, work summary (turns per work item, zero-cost-output turns), verdict and attempt groupings (how many times each gate reached each verdict, how many times each attempt number was reached)
- verify: json_path(path="$.work.turns", matches="^\\d+$")
- code: `groom/groom/store.py::run_profile`
- tests: `groom/tests/test_store.py::test_run_profile_partitions_wall_time_by_activity`

### node_costs

- sig: `node_costs(run: str = "", limit: int = 100) -> list[dict[str, Any]]`
- does: sum cost, tokens, and duration per node, only counting `agent_turn` spans to avoid double-counting node wrappers
- verify: json_path(path="$[0].turns", matches="^\\d+$")
- does: compute rework ratio as turns per work item (story slug or work_id label)
- verify: json_path(path="$[0].turns_per_work_id", matches="^(\\d+(\\.\\d+)?|null)$")
- does: report both billed cost (`cost_usd` from harness) and estimated cost (`est_cost_usd` from `groom.prices`) separately, never summed
- verify: json_path(path="$[0].cost_usd", matches="^(null|-?\\d+(\\.\\d+)?([eE][+-]?\\d+)?)$")
- verify: json_path(path="$[0].est_cost_usd", matches="^(null|-?\\d+(\\.\\d+)?([eE][+-]?\\d+)?)$")
- does: flag cost reporting gaps: turns with no cost when output tokens exist (subscription auth), and zero-cost turns (also suspicious under subscription)
- verify: json_path(path="$[0].cost_turns", matches="^\\d+$")
- verify: json_path(path="$[0].zero_cost_turns", matches="^\\d+$")
- does: sort by cost descending, breaking ties by wall time descending (cheap turns spread over many hours are less expensive than expensive ones in seconds)
- verify: json_path(path="$[0].minutes", matches="^(null|\\d+(\\.\\d+)?)$")
- returns: per-node row with share of total, turns per work item, and coverage metrics
- verify: json_path(path="$[0].share", matches="^(0(\\.\\d+)?|1(\\.0*)?)$")
- code: `groom/groom/store.py::node_costs`
- tests: `groom/tests/test_telemetry.py::test_node_costs_totals_agent_spend_and_exposes_the_rework_ratio`
- tests: `groom/tests/test_telemetry.py::test_node_costs_counts_turns_that_priced_themselves_at_exactly_zero`

### loop_convergence

- sig: `loop_convergence(run: str = "", workflow: str = "", min_work_items: int = 3, since_ts: float | None = None) -> list[dict[str, Any]]`
- does: per-node per-work-item lap distributions to separate loops that converge from loops that churn
- verify: json_path(path="$[0].node", matches=".+")
- does: order laps chronologically and compute exit rate as work_items / turns (probability any given lap succeeds)
- verify: json_path(path="$[0].exit_rate", matches="^(0(\\.\\d+)?|1(\\.0*)?)$")
- does: classify verdict by exit rate (0.8+ converged, 0.5+ loose, 0.3+ churning, <0.3 thrashing)
- verify: json_path(path="$[0].verdict", matches="^(converged|loose|churning|thrashing)$")
- does: report excess turns and cost as the laps after the first, surfaced for cost accountability
- verify: json_path(path="$[0].excess_turns", matches="^\\d+$")
- does: handle capped loops: report max_laps and at_max but mark them as "suggestive, not a verdict" since censored distributions hide whether a gate actually converged
- verify: json_path(path="$[0].max_laps", matches="^\\d+$")
- does: report both billed and estimated cost separately with coverage counts (turns with any cost, zero-cost-output turns, est_turns priced at the rate card)
- verify: json_path(path="$[0].est_turns", matches="^\\d+$")
- returns: rows sorted by excess cost descending, then excess turns descending
- verify: json_path(path="$[0].excess_cost_usd", matches="^(null|-?\\d+(\\.\\d+)?([eE][+-]?\\d+)?)$")
- code: `groom/groom/store.py::loop_convergence`
- tests: `groom/tests/test_store.py::test_loop_convergence_identifies_churning_nodes`

### reprice and apply_estimates

- sig: `reprice(run: str = "", missing_only: bool = True) -> dict[str, Any]` and `apply_estimates(updates: list[tuple[float, str, str]]) -> int
- does: recompute estimated cost for `agent_turn` spans with token counts, using newly-added or corrected rates from `groom.prices
- verify: persists(subject="estimated cost in repriced span")
- does: with `missing_only=True` only reprice spans with NULL `est_cost_usd`
- verify: unchanged(subject="span with pre-existing est_cost_usd", except_fields=[])
- does: with `missing_only=False` reprice all spans, overwriting existing estimates
- verify: unchanged(subject="span record except est_cost_usd", except_fields=["est_cost_usd", "priced_model"])
- returns: count of considered/priced turns and unpriced models (the answer to "what models do I need to add to the override file")
- verify: json_path(path="$.considered", matches="^\\d+$")
- verify: json_path(path="$.priced", matches="^\\d+$")
- verify: json_path(path="$.unpriced", matches="^\\{")
- verify: json_path(path="$.est_cost_usd", matches="^\\d+(\\.\\d+)?$")
- code: `groom/groom/store.py::reprice`
- code: `groom/groom/store.py::apply_estimates`
- tests: `groom/tests/test_store.py::test_reprice_identifies_unpriced_models`

### prune

- sig: `prune(retention_days: float = 30, now: float | None = None, archived: set[str] | None = None) -> int`
- does: delete spans, logs, and metrics older than the retention window, but only for runs in the `archived` set (fail-closed: no archived set means nothing deletes)
- verify: removed(subject="aged spans for archived run")
- verify: removed(subject="aged logs for archived run")
- verify: removed(subject="aged metrics for archived run")
- does: delete unarchived metric series (liveness gauges, never written to disk) unconditionally for all runs
- verify: removed(subject="liveness metrics")
- does: delete legacy empty-run_id rows unconditionally
- verify: removed(subject="rows with empty run_id")
- does: delete test-run telemetry unconditionally (heuristic: run_dir matching scratch patterns)
- verify: removed(subject="test run telemetry")
- does: call `checkpoint()` afterward to reclaim WAL space
- does: update `last_prune_ts` in health
- verify: persists(subject="last_prune_ts in health")
- returns: total rows removed
- code: `groom/groom/store.py::prune`
- tests: `groom/tests/test_store.py::test_prune_deletes_aged_runs_only_when_archived`

### purge_test_runs

- sig: `purge_test_runs(dry_run: bool = False, vacuum: bool = True) -> dict[str, int]`
- does: delete every span, metric, log, and turn belonging to a test run (detected by is_scratch_run_dir heuristic)
- verify: removed(subject="test run spans")
- verify: removed(subject="test run metrics")
- verify: removed(subject="test run logs")
- verify: removed(subject="test run turns")
- does: with `dry_run=True` count without deleting
- verify: unchanged(subject="database", except_fields=["any"])
- does: VACUUM the file afterward by default to reclaim disk space (freed pages stay in the file until vacuumed)
- returns: counts by table and run count, same whether dry or live
- code: `groom/groom/store.py::purge_test_runs`
- tests: `groom/tests/test_store.py::test_purge_test_runs_reclaims_space`

### checkpoint

- sig: `checkpoint() -> None`
- does: fold the write-ahead log back into the database file and truncate it
- verify: persists(subject="WAL folded into database file")
- does: use `PRAGMA wal_checkpoint(TRUNCATE)` rather than PASSIVE because auto-checkpoint starves when concurrent readers hold snapshots (the common state on a live groom)
- does: record checkpoint busy count if a reader blocked it, for health dashboard visibility
- verify: persists(subject="checkpoint busy count in health")
- raises: logs warning but does not raise on failure — checkpoint is an optimization, not critical
- verify: exit_status(code=0)
- code: `groom/groom/store.py::checkpoint`
- code: `groom/groom/store.py::_checkpoint`
- tests: `groom/tests/test_store_resilience.py::test_checkpoint_reports_busy_when_reader_blocks`

### health and health_dict

- sig: `health() -> StoreHealth` and `health_dict() -> dict[str, Any]`
- does: return snapshot of connection state: path, ok flag (true if last ok is newer than last error), opener count, failure count, last error and timestamp, last write/prune/checkpoint busy
- verify: json_path(path="$.reopens", matches="^\\d+$")
- does: compute WAL file size as current (if the WAL exists, else 0)
- verify: json_path(path="$.wal_bytes", matches="^\\d+$")
- does: ok flag distinguishes "a blip that healed" from "currently down" (used by the dashboard)
- verify: json_path(path="$.ok", equals=true)
- returns: StoreHealth dataclass or its asdict() for JSON
- verify: json_path(path="$.ok", matches="^(true|false)$")
- code: `groom/groom/store.py::StoreHealth`
- code: `groom/groom/store.py::health`
- tests: `groom/tests/test_store_resilience.py::test_health_ok_flag_requires_newer_success_than_failure`

### reset

- sig: `reset() -> None`
- does: close the connection and clear all failure counters (used between tests to switch $GROOM_DB without residual state)
- verify: json_path(path="$.failure_count", equals=0)
- does: retire every thread's read connection (they are thread-local and must not outlive the DB file they point to)
- verify: json_path(path="$.ok", equals=true)
- code: `groom/groom/store.py::reset`
- tests: `groom/tests/test_store.py::test_reset_clears_connection_state`

### RunBounds and run_bounds

- sig: `run_bounds() -> dict[str, RunBounds]`
- does: per-run timestamp bounds, archivable row counts, and identity (workflow, repo, branch, run_dir)
- verify: persists(subject="timestamp bounds for each run")
- verify: persists(subject="archivable row counts")
- does: count only rows that would be written to archive (filtered metrics per ARCHIVED_METRICS config)
- does: derive identity from newest span for each run (SQLite resolves bare columns from that row)
- verify: persists(subject="newest span identity per run")
- returns: dict mapping run_id to RunBounds, covering all runs with spans or logs or (archivable) metrics
- code: `groom/groom/store.py::RunBounds`
- code: `groom/groom/store.py::run_bounds`
- tests: `groom/tests/test_store.py::test_run_bounds_counts_archivable_rows`

### archive_page

- sig: `archive_page(run_id: str, kind: str, after: tuple[float, int] = (0.0, 0), limit: int = 5000) -> list[dict[str, Any]]`
- does: stream one page of a run's archivable rows, keyset-paginated by (timestamp, rowid) to support concurrent ingest
- does: filter metrics to ARCHIVED_METRICS (subset of the full metrics table)
- verify: omits(subject="non-archivable metrics", text="excluded")
- returns: rows with `_ts` and `_rowid` for cursor positioning in the next call
- code: `groom/groom/store.py::archive_page`
- tests: `groom/tests/test_store.py::test_archive_page_uses_keyset_pagination`

### Lap

- sig: `Lap(cost: float | None, suspect_zero: bool, est: float | None)`
- abstract: One turn of a loop (review→rework cycle), with three independent cost readings to prevent decision collapse
- does: distinguish billed cost (what a vendor charged) from estimated cost (what `groom.prices` says tokens are worth) — essential when the harness does not report cost (subscription auth, free models)
- verify: persists(subject="cost and est fields as separate independent readings")
- does: flag `suspect_zero`: turns reporting exactly $0 while emitting output tokens, which sum into a bill and hide the actual spend
- verify: persists(subject="suspect_zero flag for zero-cost output turns")
- code: `groom/groom/store.py::Lap`
- semantics: `cost` is NULL when the harness did not report it, not 0; `est` is NULL when the model has no rate card entry; `suspect_zero=true` means the turn's money is unknown, not free

### insert_turns

- sig: `insert_turns(rows: list[dict[str, Any]]) -> int`
- does: index archived turn transcripts: INSERT OR REPLACE on (run_id, generation, seq, session_id) so re-harvesting a run updates the row rather than duplicating it
- verify: count(subject="turn rows with matching visit key after re-ingest", equals=1)
- does: store metadata only (file path, size, sha256) — transcript bodies live under `groom.turns.transcripts_root` and this table is how they are found
- verify: persists(subject="turn metadata columns (path, bytes, sha256)")
- returns: rows added or updated
- verify: count(subject="turn rows indexed by insert_turns", equals=1)
- code: `groom/groom/store.py::insert_turns`
- tests: `groom/tests/test_store.py::test_insert_turns_upserts_on_visit_key`

### run_directories

- sig: `run_directories() -> list[dict[str, Any]]`
- does: return distinct (run_id, run_dir, workflow) tuples — every run telemetry has seen a directory for
- verify: persists(subject="run telemetry directory inventory")
- does: feed the archive harvester inventory: a run that moved between directories is two rows and both may hold records
- returns: rows ordered by uniqueness, not chronologically
- code: `groom/groom/store.py::run_directories`
- tests: `groom/tests/test_store.py::test_run_directories_lists_inventory_for_archive`

### is_test_run_dir

- sig: `is_test_run_dir(run_dir: str) -> bool`
- does: classify a run_dir as certainly from a test process via unambiguous path markers
- verify: absent(subject="false positives on non-test paths")
- does: match pytest's `pytest-of-<user>/`, workhorse/groom suites' `.workhorse-test/` and `.groom-test/
- verify: created(subject="true when pytest marker found")
- returns: true only for certain test markers
- verify: absent(subject="/tmp alone does not match")
- returns: `/tmp` alone does not count — producer may be container, collector may be host
- code: `groom/groom/store.py::is_test_run_dir`
- tests: `groom/tests/test_store.py::test_is_test_run_dir_matches_pytest_marker`

### is_scratch_run_dir

- sig: `is_scratch_run_dir(run_dir: str) -> bool`
- does: wider net than `is_test_run_dir`: includes certain test markers *and* Python `tempfile.mkdtemp()` heuristic
- verify: created(subject="true when is_test_run_dir returns true")
- does: match `tempfile.mkdtemp()` naming (`tmp` + 6+ random chars) under temp roots (`/tmp` or `tempfile.gettempdir()`)
- verify: created(subject="true for mkdtemp-named dirs under temp roots")
- returns: true for test markers or temp dirs — used only in deliberately-preview-able commands (`groom purge --dry-run`), not ingest
- code: `groom/groom/store.py::is_scratch_run_dir`
- tests: `groom/tests/test_store.py::test_is_scratch_run_dir_catches_mkdtemp`
- semantics: heuristic — a real run launched from a temp dir matches too — so confined to explicit purges rather than ingest filtering

### test_run_ids

- sig: `test_run_ids() -> set[str]`
- does: query distinct run_ids whose run_dir matches `is_scratch_run_dir` — all test runs in the store
- verify: absent(subject="non-scratch run_ids")
- returns: set of run_ids only (run_dir is queried but not returned)
- verify: json_path(path="$[0]", matches=".+")
- returns: empty set if none found
- verify: count(subject="run_ids when no test runs exist", equals=0)
- code: `groom/groom/store.py::test_run_ids`
- code: `groom/groom/store.py::_test_run_ids`
- tests: `groom/tests/test_store.py::test_test_run_ids_discovers_scratch_runs`

### unarchived_row_counts

- sig: `unarchived_row_counts() -> dict[str, int]`
- does: count rows the archival system will never touch, so `prune` may delete them unconditionally
- does: count liveness metrics (never-archived gauges + heartbeat counters)
- verify: persists(subject="never_archived_metrics count")
- does: count scratch run telemetry (test runs detected by `is_scratch_run_dir`)
- verify: persists(subject="scratch_runs count")
- does: count legacy empty-run_id rows (ingest refuses them now)
- verify: persists(subject="no_run_id counts for each table")
- returns: dict with keys `never_archived_metrics`, `scratch_runs`, `no_run_id_spans`, `no_run_id_logs`, `no_run_id_metrics
- code: `groom/groom/store.py::unarchived_row_counts`
- tests: `groom/tests/test_store.py::test_unarchived_row_counts_reports_what_prune_deletes_unconditionally`

### delete_run_telemetry

- sig: `delete_run_telemetry(run_id: str) -> int`
- does: drop every span, log, and metric belonging to run_id unconditionally (no retention window, no archive check)
- verify: removed(subject="all spans for run_id")
- verify: removed(subject="all logs for run_id")
- verify: removed(subject="all metrics for run_id")
- does: called by the archiver once the run's file is written to disk — rows younger than the retention window must leave with the archive or the archive stops being the single copy
- returns: total rows removed
- code: `groom/groom/store.py::delete_run_telemetry`
- tests: `groom/tests/test_store.py::test_delete_run_telemetry_removes_all_three_tables`

### unpriced_models

- sig: `unpriced_models(run: str = "") -> dict[str, int]`
- does: models with agent_turn spans reporting tokens but no rate in `groom.prices`, and how many turns each has
- verify: json_path(path="$", matches="^\\{.+\\}")
- does: query the store read-only without any database modifications — safe to print from `groom prices`
- verify: unchanged(subject="spans table", except_fields=[])
- returns: dict mapping model name to turn count, ordered most-common first
- verify: json_path(path="$", matches="^\\{.*\\}")
- code: `groom/groom/store.py::unpriced_models`
- tests: `groom/tests/test_prices.py::test_a_known_model_is_priced_at_ingest`

### unpriceable_turns

Input to any recovery that goes looking outside the span for what the model really was — the turn's own attributes have already been shown not to answer.

- sig: `unpriceable_turns(run: str = "") -> list[dict[str, Any]]`
- does: turns with tokens, no estimate, and a model the rate card does not cover
- verify: json_path(path="$[0].est_cost_usd", equals=null)
- returns: list of turn records with span_id, model, session_id, and token counts for recovery attempts
- verify: json_path(path="$[0].span_id", matches=".+")
- code: `groom/groom/store.py::unpriceable_turns`
- tests: `groom/tests/test_store.py::test_unpriceable_turns_lists_turn_details_for_recovery`

### attend_* (attendant gate support)

- sig: `attend_start(job_id, *, run_id, ..., session_id, pid, started_at)` and `attend_append_session(job_id, session_id, pid)` and `attend_finish(job_id, *, exit_code, released_state, ended_at)` and `attend_running_for_run(run_id)` and `attend_latest_for_run(run_id)` and `attend_recent(limit)
- does: track attendant dispatch: when groom sends a Claude session to rescue a stopped run, the row records the job, run, session history (for multi-generation rescues), exit code, and outcome
- verify: created(subject="attendance record for stopped run")
- does: one row per run, serial (no parallel attendants), status is running or completed
- verify: count(subject="running attendance records per run", equals=1)
- does: session_ids is an ordered list (newest last) so earlier attempts are findable and the latest is the active one
- verify: persists(subject="session_ids list across multi-generation rescues")
- returns: one row per call, or list/dict for the collection queries
- verify: json_path(path="$.session_ids", matches="^\\[.*\\]$")
- code: `groom/groom/store.py::attend_start`
- code: `groom/groom/store.py::attend_running_for_run`
- code: `groom/groom/store.py::attend_recent`
- tests: `groom/tests/test_store.py::test_attend_session_tracks_dispatch_and_outcome`

## Implementation

### Connection pooling and thread safety

The module maintains **one writer, many readers**:

- `_STORE`: process-wide singleton `_Store` object holding the write connection and RLock
- `_Store.connect()` opens or returns the write connection; the locking contract is documented on [connect](_store-class.md#connect)
- `_Store.read_connection()`: returns a thread-local read-only connection, not locked — a reader holding a snapshot does not block writers, and writers do not block readers
- `_resilient`: decorator that serializes store calls under the lock and retries once on sqlite3.Error
- `_reading`: decorator that retries once on sqlite3.Error without locking (reads already serialize through the thread-local handle)

### Autocommit mode and transaction discipline

- `isolation_level=None`: SQLite autocommit mode, no implicit transactions — every statement is its own transaction by default
- `_Store.writing()`: explicit `BEGIN IMMEDIATE` to take the write lock upfront and detect snapshot conflicts before half-way through the write
- `PRAGMA synchronous=NORMAL` under WAL: one fsync per checkpoint, not per commit (each OTLP batch is one commit, so FULL would cost a disk sync per export)
- `PRAGMA busy_timeout=5000`: wait up to 5s for lock contention from concurrent processes (CLI, tests, exports)

### Resilience and error recovery

- `_resilient` and `_reading` decorators catch `sqlite3.Error` (base class covering transient wedges, permanent corruption, and mismatches)
- On first failure: recycle the connection (close and mark `_generation` incremented so read handles detect stale snapshots), then retry the statement once
- On second failure within `REOPEN_COOLDOWN_S` (5s): raise the exception — the file itself is the problem and retrying will not help
- `health()` surfaces failure counts, last error, and ok flag for operator visibility

### Attribute promotion and indexing

Attributes frequently queried are promoted from the JSON `attrs_json` column to real columns:

- Cost: `total_cost_usd`, `est_cost_usd` (estimated at ingest), `priced_model` (which rate card priced it)
- Tokens: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens
- Git state: `head_start`, `head_end` (whether HEAD moved during the span)
- Workspace: `workspace_start`, `workspace_end`, `vcs_start`, `vcs_end`, `origin_start`, `origin_end`, `branch_start`, `branch_end
- Backfilled: `pid`, `resume_generation`, `run_dir`, `duration_ms

Old spans lack these columns (NULL), so queries use `COALESCE(column, json_extract(...))` to fall back to the attribute for backward compatibility.

