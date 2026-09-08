---
type: concept
slug: groom-archive-module
title: Groom archive module
---
# Groom archive module

The Groom archive module is the one place a run's telemetry stops being a set of SQL rows and becomes a file. It reads the spans, logs and kept metric series of a run whose activity ended more than `GROOM_RETENTION_DAYS` ago, writes them as a single ordered `telemetry.jsonl` beside that run's transcripts, moves the whole directory from the live `transcripts/` root to the frozen `archives/` root, and only then lets the [groom store](groom-state-module.md) delete the rows. Nothing else in groom deletes a run's telemetry.

The two roots are the design, not a filing convention. `transcripts/<run_id>/` is where the harvester writes and is the only root it knows; `archives/<run_id>/` is where a run lives once it is frozen. Both are children of the database's own directory, so promotion is one same-filesystem `os.rename` — atomic, and therefore a run is in exactly one of two states with no third state to reason about. Immutability is then structural rather than enforced: the harvester cannot append to an archived run because it never looks in `archives/`, and a second archival of the same name cannot overwrite the first because the destination already exists and the module declines it. The archive has no retention of its own: there is no expiry knob on `archives/`, deliberately, since a knob defaulting to keep-everything is still a knob and adding one would reintroduce the data loss this module exists to remove. `GROOM_RETENTION_DAYS` therefore governs only how long a run stays queryable in SQL, never how long its file survives on disk.

Order matters and is the fail-closed half of the contract. The file is written to a `.tmp`, fsynced, counted against the row counts the store reported, renamed into place, and its directory fsynced; the directory move happens next; the SQL delete happens last. Every failure before the delete leaves the run in the database, so the worst outcome is a run archived twice as far as the file system is concerned and never a run deleted without a copy on disk. `groom.store.prune` refuses to delete any run this module has not confirmed archived — the exceptions are the never-archived metric series (liveness gauges and the derived per-node activity gauges, which describe a live groom and mean nothing once the run is over) and scratch test runs.

Nothing here may raise into groom's tick. The sweep catches per run, records the failure in its result, and continues; a run that fails today is simply eligible again on the next pass.

- code: groom/groom/archive.py
- refs: [groom state module](groom-state-module.md), [groom projection module](groom-projection-module.md)

The archival contract is covered by `groom/tests/test_archive.py`.

## Contract

- purpose: move a finished run's telemetry out of SQLite and onto disk as one JSONL file per run, so retention is a database-size dial rather than a data-loss dial.
- roots: exactly two — `transcripts/` for live runs and `archives/` for frozen ones, both siblings under the directory holding `groom.db`, so promotion is a rename on one filesystem.
- one file: a run's telemetry is a single `telemetry.jsonl`. Line 1 is a manifest record; every following line is one span, log or metric, discriminated by `kind` and ordered by `ts`. Plain text, not gzipped, because the reader is `jq` and a stream more often than it is a loader.
- join key: every record carries `run_id` and `node`, and a span additionally carries `generation` and `seq` — the same keys the transcript archive is indexed by, so the telemetry of a node joins its transcript without a lookup table.
- what is archived: every span, every log, and the four budget metric series named by `ARCHIVED_METRICS`. The liveness heartbeats and the per-node activity gauges are dropped, deliberately: they are the in-memory groom's own signal.
- no index: what is archived is what is on disk. The directory name is the run id, so `ls` answers the question and there is no second source of truth to fall out of step with the first.
- consistency rule: run — archive immutability — once a run's directory exists in `archives/`, it is never overwritten or merged with another run's data: a repeat archival of the same run reuses the existing file rather than rewriting it, and a different run reusing that run id is archived under a name derived from its identity instead.
- verify: unchanged(subject="archived run directory contents")
- never raises into the tick: every public entry point either returns a result object recording what failed or raises only for a caller that asked for one run by name.

## Fields

### field-archive-every-s

- type: `float`
- default: `21600.0` (six hours), from `GROOM_ARCHIVE_EVERY_S`
- required: true
- code: groom/groom/archive.py::ARCHIVE_EVERY_S
- meaning: how often the background task sweeps. The task is seeded already-expired, so a `groom serve` launch runs one pass immediately rather than six hours later.

### field-runs-per-pass

- type: `int`
- default: `25`, from `GROOM_ARCHIVE_RUNS_PER_PASS`
- required: true
- code: groom/groom/archive.py::RUNS_PER_PASS
- meaning: how many runs one pass may archive, oldest first. The bound is what keeps a first sweep over a year of backlog from holding the writer for an hour; the remainder is reported as pending and taken next pass.

### field-telemetry-file

- type: `str`
- default: `telemetry.jsonl`
- required: true
- code: groom/groom/archive.py::TELEMETRY_FILE
- meaning: the file's name inside an archived run directory. One name, so a reader needs no glob.

## Structures

### SweepResult

Dataclass that records the outcome of one archival pass for reporting to operators and for `groom archive status` to compute current state.

- code: groom/groom/archive.py::SweepResult

#### field-archived

- type: `list[str]`
- default: `[]`
- required: false
- semantics: the run ids successfully moved to the archives in this pass
- code: groom/groom/archive.py::SweepResult.archived

#### field-resumed

- type: `list[str]`
- default: `[]`
- required: false
- semantics: the run ids whose archive already existed from a prior pass, requiring no file rewrite — an interrupted sweep's signal
- code: groom/groom/archive.py::SweepResult.resumed

#### field-failed

- type: `dict[str, str]`
- default: `{}`
- required: false
- semantics: mapping of run id to error message for runs that could not be archived; the run remains in SQL and is eligible for retry
- code: groom/groom/archive.py::SweepResult.failed

#### field-held

- type: `list[str]`
- default: `[]`
- required: false
- semantics: the run ids whose newest record predates the retention cutoff but which are still emitting telemetry, so neither archived nor pruned
- code: groom/groom/archive.py::SweepResult.held

#### field-pending

- type: `int`
- default: `0`
- required: false
- semantics: the count of runs eligible for archival but not yet archived in this pass, because the pass was bounded by `limit`
- code: groom/groom/archive.py::SweepResult.pending

#### field-rows

- type: `int`
- default: `0`
- required: false
- semantics: the total number of telemetry rows deleted from SQL in this pass
- code: groom/groom/archive.py::SweepResult.rows

#### field-bytes

- type: `int`
- default: `0`
- required: false
- semantics: the total size in bytes of all telemetry files written in this pass
- code: groom/groom/archive.py::SweepResult.bytes

#### field-started

- type: `float`
- default: `0.0`
- required: false
- semantics: Unix timestamp when this pass began
- code: groom/groom/archive.py::SweepResult.started

#### field-finished

- type: `float`
- default: `0.0`
- required: false
- semantics: Unix timestamp when this pass completed
- code: groom/groom/archive.py::SweepResult.finished

#### method-as_dict

- sig: `as_dict() -> dict[str, Any]`
- abstract: false
- does: Serializes the sweep result to a flat dictionary for JSON output and storage in process memory
- verify: json_path(path="archived", matches="^\\[.*\\]$")
- returns: a dictionary with all fields listed above as top-level keys
- raises: none intentionally raised
- code: groom/groom/archive.py::SweepResult.as_dict

## Methods

### method-archives-root

- sig: `archives_root() -> Path`
- abstract: false
- does: Returns the frozen root, the sibling of the live transcripts root under the database's directory.
- verify: created(subject="archives root path")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::archives_root

### method-archive-dirs

- sig: `archive_dirs() -> list[Path]`
- abstract: false
- does: Reads every frozen run directory from the archives root, returning directory paths in sorted order
- verify: created(subject="list of archived run directory paths")
- does: Catches and recovers from OSError by returning an empty list, so the caller need not handle filesystem unavailability
- verify: json_path(path="exception.type", absent=True)
- raises: none intentionally raised into the caller
- code: groom/groom/archive.py::archive_dirs

### method-is-archived

- sig: `is_archived(run_id: str) -> bool`
- abstract: false
- does: Checks whether a run has been frozen to the archives by verifying the run's `telemetry.jsonl` file exists in the archives root
- verify: http_status(200)
- raises: none intentionally raised
- returns: `True` if the run has been archived with a complete telemetry file; `False` otherwise
- code: groom/groom/archive.py::is_archived

### method-archived-run-ids

- sig: `archived_run_ids() -> set[str]`
- abstract: false
- does: Reads the frozen root's directory names as the authoritative set of archived run ids, without opening a file.
- verify: created(subject="set of archived run ids")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::archived_run_ids

### method-manifest

- sig: `manifest(path: Path) -> dict`
- abstract: false
- does: Reads the first line of the telemetry file as a JSON dictionary when the file exists and is valid
- verify: json_path(path="$.kind", equals="manifest")
- does: Returns an empty dictionary when the file is absent or unreadable
- verify: json_path(path="$", matches="^\\{\\}$")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::manifest

### method-eligible

- sig: `eligible(bounds=None, retention_days=store.RETENTION_DAYS, now=None) -> tuple[list[RunBounds], list[RunBounds]]`
- abstract: false
- does: Splits the store's per-run bounds into the runs whose newest record is older than the cutoff and the runs that straddle it.
- verify: created(subject="archivable and held run lists")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::eligible
- step: Skip scratch test runs, which prune deletes without an archive.
- step: Treat a run as archivable only when its newest record predates the cutoff and it has rows — a run still emitting is held whole rather than half-archived.
- step: Sort both lists by newest record, so a bounded pass drains the oldest backlog first.

### method-records

- sig: `records(run_id: str) -> Iterator[dict]`
- abstract: false
- does: Merges the run's span, log and metric streams into one sequence ordered by `(ts, rowid)`, each page fetched by keyset so no query holds the whole run in memory.
- verify: emitted(event="record")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::records

### method-write-telemetry

- sig: `write_telemetry(run: RunBounds, target: Path, now: float | None = None) -> int`
- abstract: false
- does: Writes a manifest record as the first line, followed by all span, log and metric records, to a temporary file
- verify: created(subject="telemetry.jsonl.tmp")
- does: Fsyncs the temporary file to persist it to disk
- does: Verifies the written record count matches the store's reported count
- does: Renames the temporary file to the target path and fsyncs the directory for durability
- verify: created(subject="telemetry.jsonl")
- raises: `RuntimeError` when the written counts do not match the store's, so a short file is never renamed into place.
- raises: `OSError` from the file system, which leaves the run in SQL.
- returns: The file's size in bytes
- code: groom/groom/archive.py::write_telemetry

### method-derived-name

- sig: `derived_name(run: RunBounds) -> str`
- abstract: false
- does: Returns `<run_id>-<token>`, the token being a short hash of the run id and its newest timestamp, for the case where a run id is already frozen under its own name.
- verify: created(subject="derived name string")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::derived_name

### method-archive-run

- sig: `archive_run(run: RunBounds, now: float | None = None) -> tuple[Path | None, int]`
- abstract: false
- does: Writes one run's telemetry into its live directory, moves that directory into the frozen root, and deletes the run's rows from SQL — in that order.
- verify: created(subject="run archive")
- raises: `RuntimeError` when both the run's own name and its derived name are taken by archives that describe a different run.
- verify: created(subject="a RuntimeError because archive names are unavailable")
- verify: json_path(path="exception.type", equals="RuntimeError")
- returns: `(destination, rows_deleted)` where `destination` is the frozen archive path or `None` if the archive already existed, and `rows_deleted` is the count of telemetry rows removed from SQL
- code: groom/groom/archive.py::archive_run
- step: Return `(None, 0)` when a matching archive already exists, which is how an interrupted sweep is told apart from a name collision: the manifest either describes this run or it does not.

### method-sweep

- sig: `sweep(limit=RUNS_PER_PASS, retention_days=store.RETENTION_DAYS, now=None, dry_run=False) -> SweepResult`
- abstract: false
- does: Archives up to `limit` eligible runs oldest first, catching per run so one bad run cannot end the pass, and records the outcome as the process's last sweep.
- verify: created(subject="archived runs")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=True)
- code: groom/groom/archive.py::sweep

### method-status

- sig: `status(now: float | None = None) -> dict`
- abstract: false
- does: Reads the frozen root and pending run information to compute the current archive status.
- verify: json_path(path="root", matches=".+")
- raises: none intentionally raised.
- verify: json_path(path="exception.type", absent=true)
- returns: `root`, the frozen archive root path
- verify: json_path(path="root", matches=".+")
- returns: `archived_runs`, the count of archived runs
- verify: json_path(path="archived_runs", matches="[0-9]+")
- returns: `pending`, the count of runs eligible for archival but not yet archived
- verify: json_path(path="pending", matches="[0-9]+")
- returns: `held_by_activity`, the ids of runs whose newest record predates the cutoff but which are still emitting, held whole rather than archived
- verify: json_path(path="held_by_activity", matches="^\\[.*\\]$")
- returns: `every_s`, the archive task's sweep cadence in seconds
- verify: json_path(path="every_s", matches="[0-9.]+")
- returns: `runs_per_pass`, the archive task's per-pass batch size
- verify: json_path(path="runs_per_pass", matches="[0-9]+")
- returns: `last_sweep`, the previous sweep's statistics, or `None` when no sweep has run yet
- verify: json_path(path="last_sweep", matches=".*")
- code: groom/groom/archive.py::status

## Algorithms

### algorithm-write-move-delete

- step: The background task in the [groom server](../http/groom.md) wakes, having been seeded to fire on the first tick after launch.
- step: `eligible` reads the store's per-run bounds once and splits them at the retention cutoff.
- step: For each of the oldest `RUNS_PER_PASS` archivable runs, `write_telemetry` streams the run into `transcripts/<run_id>/telemetry.jsonl.tmp`, fsyncs, verifies the counts, and renames.
- step: `os.rename` moves `transcripts/<run_id>` to `archives/<run_id>`, which is atomic because both are on one filesystem.
- step: `store.delete_run_telemetry` deletes the run's rows in chunks, dropping the writer lock between chunks.
- consistency rule: run — the delete is last and is reached only from a successful move, so a crash at any point leaves rows in SQL rather than a run with neither a file nor a table.
- step: The next prune pass is handed `archived_run_ids()` and deletes only runs in that set, plus the never-archived series and scratch runs.

## Failure Semantics

- Interrupted sweep: a run whose file and directory landed but whose rows were not deleted is recognised on the next pass by comparing the existing manifest to the run's current identity, and its rows are deleted without rewriting the file.
- Name collision: a different run archived under an id already frozen is written under `derived_name`; when that is taken too, the run is reported as failed and left in SQL rather than overwriting a frozen archive.
- Held run: a run whose oldest record predates the cutoff but which is still emitting is neither archived nor pruned. It is reported by `groom archive status`, because a run held forever is a stuck run, not a retention setting.
- consistency rule: run — an `OSError` anywhere in a run's archival is caught by `sweep` and not propagated into groom's tick
- verify: json_path(path="exception.type", absent=True)

- consistency rule: archival-oserror — file system error, error recorded — the error is recorded against that run in the sweep result
- verify: json_path(path="sweep_result.failed", matches=".+")

- consistency rule: archival-oserror — file system error, rows persist — when archival fails with an `OSError`, the run's rows are left in SQL rather than deleted
- verify: persists(subject="run's telemetry rows in database")

- consistency rule: archival-oserror — file system error, run retried — a run whose archival failed is still eligible and is retried whole on the next pass
- verify: created(subject="run in next eligible set")
- Count mismatch: a `RuntimeError` from `write_telemetry` leaves the temporary file behind and the run in SQL; the next pass overwrites the temporary file.
