---
type: concept
slug: _store-class
title: Store connection lifecycle (_Store class)
---
# Store connection lifecycle (_Store class)

The process-wide singleton that holds the SQLite connection, enforces connection discipline, and recovers from transient failures. Three design choices are load-bearing and each was discovered by a production serve that silently stopped storing: autocommit mode (`isolation_level=None`), one `RLock` around every write, and automatic connection recycling on failure.

The class maintains one writer connection with a process-wide lock and many per-thread reader connections with no locking. Readers are isolated because WAL mode already gives a reader a consistent snapshot alongside the writer; the lock was never buying correctness there. Putting reads under it bought an outage: one slow cold read on a saturated disk held the lock, and every OTLP receiver behind it queued behind a query none of them had asked for.

- code: `groom/groom/store.py::_Store`
- extends: [groom-store](groom-store.md)
- tests: `groom/tests/test_store.py`
- tests: `groom/tests/test_store_resilience.py`

## Fields

The instance attributes set in [`__init__`](#init) and read/mutated by the methods below. Each is initialized to a process-wide default; the writer attributes (the connection, its path, the lock, the failure counters) are mutated together by [`reset()`](#reset) when tests switch `$GROOM_DB` between cases. `code:` is omitted per field because the class-level `code:` already owns the file; the attribute lives where `__init__` typed it.

### monotonic

- type: `Callable[[], float]` (a clock function)
- default: `time.monotonic`
- required: false — defaults to `time.monotonic` if not injected
- semantics: clock used by [`recycle()`](#recycle) to enforce `REOPEN_COOLDOWN_S` (5s) — the elapsed time between recycled writes decides whether the file itself is the problem
- semantics: injectable so the cooldown is testable without a real sleep — `time.monotonic` advances with wall time, and a test cannot stand still without freezing the process

### _conn

- type: `sqlite3.Connection | None`
- default: `None`
- required: false — None until first `connect()` call, and None again after `_close_quietly()`
- semantics: the open write-mode connection for the writer singleton, or `None`; held in instance memory only, never persisted, and never observed outside the class except through [`connect()`](#connect) returning the descriptor
- semantics: every read and write happens under [`lock`](#lock) — `connect()`, `writing()`, `recycle()`, and `_close_quietly()` all enter the RLock before touching `_conn`, so concurrent callers serialize on the same descriptor rather than racing two opens against the same file

### _path

- type: `Path | None`
- default: `None`
- required: false — None before [`connect()`](#connect) has opened the connection, and None again after [`reset()`](#reset) clears it
- semantics: path the writer connection was opened against — read on every [`connect()`](#connect) call and compared against `db_path()` so a `$GROOM_DB` change between calls reopens the handle at the new path rather than answering the old file
- semantics: the writer's known-good path used by [`read_connection()`](#read_connection) when opening a thread-local reader — `self._path or path` falls back to `db_path()` only when the writer has not opened yet, because a reader opened against a file the writer never opened would find no schema and have nothing to attach to
- semantics: cleared by [`reset()`](#reset) along with every failure counter — a test that switches `$GROOM_DB` between cases cannot let the previous path leak into the next, since `_close_quietly()` does not touch `_path` on its own
- persistence: instance-only — held in instance memory only, never persisted to disk, never observed outside the class except through [`reset()`](#reset) clearing it

### lock

- type: `threading.RLock`
- default: a fresh `threading.RLock()` instance
- required: true — every write goes through `@_resilient` which takes this lock
- semantics: `threading.RLock()` serializing every write and connection-state mutation
- idempotency: write-nesting — reentrant so write operations can nest without deadlock

### _readers

- type: `threading.local`
- default: a fresh `threading.local()` instance
- required: true — readers are isolated per thread so concurrent readers do not share snapshots
- semantics: `threading.local()` holding per-thread read connections in `.handle: _Reader`
- concurrency: isolation — thread-local storage means no lock needed
- concurrency: ownership — each thread owns its handle

### _generation

- type: `int`
- default: `0`
- required: true — incremented in `_close_quietly()` so `read_connection()` sees when the writer has recycled
- semantics: monotonic counter incremented each time the write connection is closed, so read handles can detect stale snapshots

### _reopens

- type: `int`
- default: `0`
- required: false — observation counter, never set by callers
- semantics: count of writer connection recyclings completed, incremented once per [`recycle()`](#recycle) call that closes `_conn`
- semantics: a recycle() call suppressed by the cooldown gate raises instead of closing, and leaves `_reopens` where it was
- semantics: consulted by the cooldown gate at the top of [`recycle()`](#recycle), so a non-zero value means another reopen has happened recently
- semantics: cleared only by [`reset()`](#reset), which the test harness calls between cases to switch `$GROOM_DB`
- tests: `groom/tests/test_telemetry.py::test_a_closed_connection_heals_on_the_next_write`
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited`
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- concurrency: lock-protected — written inside `_Store.lock` from `recycle()`, so concurrent callers serialize through the RLock before incrementing
- verify: count(subject="_reopens", equals=1)
- verify: count(subject="_reopens", equals=1)
- verify: count(subject="_reopens", equals=0)

### _failures

- type: `int`
- default: `0`
- required: false — observation counter, never set by callers
- semantics: count of connection errors observed, incremented once per `recycle()` call and once per `recycle_reader()` call
- semantics: the increment from `recycle()` happens before the cooldown gate, so a recycle that raises inside the cooldown still bumps `_failures`
- semantics: stamped in the same call sites as `_last_error`, so a viewer reads the count and the most recent message together
- semantics: stamped in `recycle_reader()` without taking `_Store.lock`, deliberately trading accuracy under a race for the wait the lock would cost
- semantics: cleared only by [`reset()`](#reset)
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited`
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- concurrency: writer-path-locked — incremented inside `_Store.lock` from `recycle()`, so concurrent writers serialize on the increment
- concurrency: reader-path-unlocked — incremented without `_Store.lock` from `recycle_reader()`
- verify: count(subject="_failures", equals=2)
- verify: count(subject="_failures", equals=0)

### _last_error, _last_error_ts

The paired fields [`health()`](#health) reads to discriminate "nothing has failed yet"
from "the last call failed and no success has followed." Stamped together at every failure
site ([`recycle()`](#recycle), [`recycle_reader()`](#recycle_reader)); cleared together by
[`reset()`](#reset); surfaced together as `last_error` and `last_error_ts` on
[`StoreHealth`](#field-storehealth). The two attributes have different types and different
defaults, so each is documented as its own nested field below.

#### _last_error

- type: `str` — the formatted exception message
- default: `""`
- required: false — `""` is the "no failure observed yet" sentinel [`health()`](#health) reads when the store has never recorded an error
- semantics: formatted as `f"{type(exc).__name__}: {exc}"` so the exception class name is the prefix and the message follows after a `: ` separator (`OperationalError: database is locked`, `DatabaseError: file is not a database`, ...)
- semantics: stamped by [`recycle()`](#recycle) inside `_Store.lock` so concurrent writers serialize through the RLock before the assignment
- semantics: stamped by [`recycle_reader()`](#recycle_reader) **without** taking `_Store.lock` — deliberately trading accuracy under a race for the wait the lock would cost (the value feeds a health display, not a correctness check)
- semantics: cleared by [`reset()`](#reset), which the test harness calls between cases to switch `$GROOM_DB`; without the clear, a previous case's failure message would leak into the next case's first `health()` call
- semantics: read by [`health()`](#health) as `StoreHealth.last_error` for the operator dashboard — the raw text, not the parsed exception
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited`
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- concurrency: writer-path-locked — written inside `_Store.lock` from `recycle()`, so concurrent callers serialize on the assignment
- concurrency: reader-path-unlocked — written without `_Store.lock` from `recycle_reader()`, so a concurrent `recycle()` and `recycle_reader()` may interleave their assignments
- verify: count(subject="the message captured after recycle()", equals=1)
- verify: count(subject="the message cleared by reset()", equals=1)

#### _last_error_ts

- type: `float` — wall-clock seconds since the epoch from `time.time()`
- default: `0.0`
- required: false — `0.0` is the "no failure timestamp" sentinel; [`health()`](#health)'s `ok = _last_error_ts <= _last_ok_ts` is True when both timestamps are zero, which is the boot state
- semantics: stamped together with [`_last_error`](#_last_error) at every failure site using `time.time()` (not `self.monotonic()` — wall time so it is comparable to `last_write_ts` and `last_ok_ts`)
- semantics: cleared together with [`_last_error`](#_last_error) by [`reset()`](#reset)
- semantics: read by [`health()`](#health) as the upper bound against which `ok = _last_error_ts <= _last_ok_ts` is computed — a failure timestamp older than the last success has been healed; one newer has not
- semantics: read by [`health()`](#health) as `StoreHealth.last_error_ts` so a viewer can render the staleness of the most recent failure
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited`
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- concurrency: writer-path-locked — written inside `_Store.lock` from `recycle()`
- concurrency: reader-path-unlocked — written without `_Store.lock` from `recycle_reader()`
- verify: json_path(path="$._last_error_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- verify: json_path(path="$._last_error_ts", equals=0)

### _last_reopen_at

The paired writer state with [`_reopens`](#_reopens) — read on every call into [`recycle()`](#recycle) once `_reopens` is non-zero, written only on a successful recycle, cleared by [`reset()`](#reset). The cooldown gate at `if self._reopens and now - self._last_reopen_at < REOPEN_COOLDOWN_S` is the one behavior in the entire class that depends on this field; without it, every recycle would reopen and a broken file would thrash on every request.

- type: `float` — monotonic-clock seconds from the injected [`monotonic`](#monotonic) callable (`self.monotonic()`), not wall-clock seconds from `time.time()`
- default: `0.0` — `0.0` is the "no reopen yet" sentinel; the gate short-circuits on `_reopens and …` so the default is never actually consulted while a decision is being made
- required: true — `recycle()` reads this on every call after the first successful reopen to decide whether to re-raise; the contract this field carries is the cooldown itself
- semantics: stamped using `self.monotonic()` (the same injectable clock [`monotonic`](#monotonic) declares) rather than `time.time()`, so the cooldown comparison `now - self._last_reopen_at < REOPEN_COOLDOWN_S` runs on a single monotonic timeline that does not jump when wall-clock does — and that the test suite can advance by injection, the reason the cooldown is testable in the first place
- semantics: stamped only after the cooldown gate has passed — the assignment sits after the `raise exc` branch inside the cooldown, so a `recycle()` that raises inside the cooldown leaves `_last_reopen_at` unchanged (the timer is for successful reopens, not attempts; a raise counts as an attempt but not a reopen)
- semantics: consulted only by the cooldown gate — the only reader is the `if self._reopens and now - self._last_reopen_at < REOPEN_COOLDOWN_S` line itself, and the `_reopens and …` short-circuit means `_last_reopen_at` is not consulted at all until the first `_reopens += 1`
- semantics: cleared by [`reset()`](#reset) alongside the other failure-tracking state, so a test that switches `$GROOM_DB` between cases cannot let one case's reopen time leak into the next — and the same set of counters being reset together is what makes `reset()` a single seam rather than per-field handlers
- semantics: not surfaced through [`health()`](#health) — there is no `last_reopen_at` on [`StoreHealth`](#field-storehealth); the field is private bookkeeping for the cooldown gate, not an operator metric, and a viewer can derive its currency from `reopens == 1 and last_error_ts > 0` instead
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited` — the only test that injects a controlled `monotonic` clock (`iter([0.0, 1.0, 2.0, 3.0])`) and exercises the gate; does not observe `_last_reopen_at` directly, but proves the cooldown behavior that depends on it by re-raising the second `recycle()` inside the 5 s window
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- concurrency: lock-protected — read at the gate and written at the assignment, both inside `_Store.lock` inside [`recycle()`](#recycle), so the cooldown comparison and the timestamp write serialize on the same RLock as the rest of the writer state
- verify: json_path(path="$._last_reopen_at", matches="^[0-9]+(\\.[0-9]+)?$")
- verify: json_path(path="$._last_reopen_at", equals=0)

### _last_ok_ts, _last_write_ts, _last_prune_ts

The trio of wall-clock timestamps [`health()`](#health) reads into the matching `StoreHealth` fields — `last_ok_ts`, `last_write_ts`, and `last_prune_ts` — and clears together with the rest of the writer state in [`reset()`](#reset). Each is stamped by exactly one operation: [`note_ok()`](#note_ok) on a successful wrapped call, [`writing()`](#writing) on a successful `COMMIT`, and [`note_prune()`](#note_prune) on a prune cycle. All three share `time.time()`'s wall-clock-units typing and the `0.0` "no observation yet" sentinel, so each is documented as its own nested field below.

#### _last_ok_ts

- type: `float` — wall-clock seconds since the epoch, from `time.time()`
- default: `0.0`
- required: false — `0.0` is the "no successful statement yet" sentinel; [`health()`](#health)'s `ok = _last_error_ts <= _last_ok_ts` is True when both timestamps are zero, which is the boot state
- semantics: stamped by [`note_ok()`](#note_ok) from both the `_resilient` wrapper's success branch and the `_reading` wrapper's success branch — every wrapped call that ran to completion, not just writes, leaves a fresh timestamp
- semantics: stamped unconditionally (not inside `_Store.lock`) because each call replaces the value rather than mutating it, and the timestamp feeds a health display, not a correctness check
- semantics: read by [`health()`](#health) as the upper bound against which `ok = _last_error_ts <= _last_ok_ts` is computed — a failure older than the last successful call has been healed; one newer has not
- semantics: surfaced through `StoreHealth.last_ok_ts` so the operator dashboard can show how long ago the store last answered
- semantics: cleared to `0.0` by [`reset()`](#reset) along with the other failure timestamps, so a test that switches `$GROOM_DB` between cases cannot let a previous case's success time leak into the next
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- code: `groom/groom/store.py::_Store._last_ok_ts`
- verify: json_path(path="$.last_ok_ts", matches="^[0-9]+(\\.[0-9]+)?$") — a non-zero wall-clock float after [`note_ok()`](#note_ok) has run
- verify: json_path(path="$.last_ok_ts", equals=0) — the boot-state sentinel on a fresh `_Store`

#### _last_write_ts

- type: `float` — wall-clock seconds since the epoch, from `time.time()`
- default: `0.0`
- required: false — `0.0` is the "no successful commit yet" sentinel; in a fresh process or after [`reset()`](#reset), the field has held no write
- semantics: stamped by [`writing()`](#writing) only after `conn.commit()` succeeds — an exception inside the `with` block triggers `ROLLBACK` and the assignment is skipped, so a write that the wrapper raised on never leaves a `_last_write_ts`
- semantics: stamped inside `_Store.lock` at the end of the transaction's `with` block, so concurrent writers serialize through the RLock before the assignment
- semantics: read by [`health()`](#health) as `StoreHealth.last_write_ts` for the operator dashboard so a viewer can see how stale the last successful commit is
- semantics: cleared to `0.0` by [`reset()`](#reset) along with the other failure timestamps
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- code: `groom/groom/store.py::_Store._last_write_ts`
- verify: json_path(path="$.last_write_ts", matches="^[0-9]+(\\.[0-9]+)?$") — a non-zero wall-clock float after a successful [`writing()`](#writing) call
- verify: json_path(path="$.last_write_ts", equals=0) — the boot-state sentinel before any [`writing()`](#writing) has committed

#### _last_prune_ts

- type: `float` — wall-clock seconds since the epoch, from `time.time()`
- default: `0.0`
- required: false — `0.0` is the "no prune yet" sentinel; a process that has never called [`note_prune()`](#note_prune) reports the default
- semantics: stamped by [`note_prune()`](#note_prune) to the explicit `ts` argument when one is given, otherwise to the current wall time — the optional argument exists so a recurring job can stamp the time the prune *completed* without the rounding that calling `time.time()` at the call site would add
- semantics: stamped unconditionally (not inside `_Store.lock`) because each call replaces the value rather than mutating it
- semantics: read by [`health()`](#health) as `StoreHealth.last_prune_ts` for the operator dashboard so a viewer can see how stale the last prune cycle is
- semantics: cleared to `0.0` by [`reset()`](#reset) along with the other failure timestamps
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- code: `groom/groom/store.py::_Store._last_prune_ts`
- verify: json_path(path="$.last_prune_ts", matches="^[0-9]+(\\.[0-9]+)?$") — a non-zero wall-clock float after [`note_prune()`](#note_prune) has run
- verify: json_path(path="$.last_prune_ts", equals=0) — the boot-state sentinel before any [`note_prune()`](#note_prune) has run

### _last_checkpoint_busy

The single bit the WAL-checkpoint tick records so a dashboard reader can see whether the recurring checkpoint is keeping up. SQLite's `PRAGMA wal_checkpoint(TRUNCATE)` returns one result row `(busy, log_frames, checkpointed)` — `busy == 1` is the only signal that the file was left alone, the one row that gets thrown away when the loop only logs and the failure mode by which a 293 MB database can carry a 376 MB WAL beside it. The field carries nothing else.

- type: `int` — the `busy` column from the `PRAGMA wal_checkpoint(TRUNCATE)` result row (0 or 1)
- default: `0` — the "no checkpoint yet" sentinel; a fresh `_Store` or one that has just called [`reset()`](#reset) reports this until the first [`note_checkpoint()`](#note_checkpoint) call
- required: false — surfaced as `StoreHealth.last_checkpoint_busy` for operator visibility, not asserted on by any caller
- semantics: stamped by [`note_checkpoint()`](#note_checkpoint) to the `busy` value SQLite returned from the most recent `PRAGMA wal_checkpoint(TRUNCATE)` — `1` when a reader was holding a snapshot and the WAL was left alone, `0` when the checkpoint actually truncated the file
- semantics: surfaced through `StoreHealth.last_checkpoint_busy` so the operator dashboard can see whether the recurring checkpoint is keeping up — a steady `1` across many checkpoints means a reader is pinning the WAL indefinitely, which is the failure mode the field exists to make visible
- semantics: cleared to `0` by [`reset()`](#reset) along with the rest of the writer state — the test harness calls `reset()` between cases to switch `$GROOM_DB`, and a previous case's `busy` value would leak into the next case's first `health()` call otherwise
- code: `groom/groom/store.py::_Store._last_checkpoint_busy`
- tests: `groom/tests/test_telemetry.py::test_a_blocked_checkpoint_is_reported_and_never_poisons`
- persistence: instance-only — held in `_Store` memory only, never persisted to disk, lost on process restart
- verify: json_path(path="$.last_checkpoint_busy", equals=1) — observed after a checkpoint runs while a reader holds a long-lived snapshot open in a transaction
- verify: json_path(path="$.last_checkpoint_busy", equals=0) — the boot-state sentinel on a fresh `_Store`, and again after [`reset()`](#reset)

## Methods

### init

- sig: `__init__(self, monotonic: Callable[[], float] = time.monotonic) -> None`
- does: initialize the singleton with process-wide writer state, per-thread reader handles, and failure tracking
- verify: json_path(path="$._generation", equals=0)
- does: inject `monotonic` clock so reopen cooldown is testable without real sleep
- raises: none
- code: `groom/groom/store.py::_Store.__init__`

### connect

- sig: `connect(self) -> sqlite3.Connection`
- does: return the open write connection, opening or reopening it if there isn't one
- verify: json_path(path="$.result_type", equals="sqlite3.Connection")
- does: close the previous connection via [`_close_quietly()`](#_close_quietly) and reopen if `db_path()` has changed (tests switch $GROOM_DB between cases)
- verify: created(subject="connection to new database path")
- raises: sqlite3.Error if [`_open()`](#_open) fails (caught and retried by caller's @_resilient wrapper)
- verify: json_path(path="$.exception_type", equals="sqlite3.Error")
- returns: the write connection, opened at the path stored in [`_path`](#_path) in autocommit mode
- verify: json_path(path="$.isolation_level", absent=true)
- code: `groom/groom/store.py::_Store.connect`
- concurrency: write-connection — `connect()` takes `self.lock` (the process-wide `RLock`) before opening or returning the connection, so concurrent callers are serialized rather than racing to open two handles
- idempotency: connection — idempotent once the file exists — multiple calls return the same open handle (until recycled)
- verify: persists(subject="connection")

### _open

- sig: `_open(self, path: Path) -> sqlite3.Connection`
- does: create the database file and its parent directories if needed
- verify: created(subject="database file at path")
- does: open with `check_same_thread=False` (explicit locking via RLock) and `isolation_level=None` (autocommit)
- does: set row factory to `sqlite3.Row` (dict-like column access — `row["column"]`)
- does: enable WAL mode (`PRAGMA journal_mode=WAL`) for reader/writer isolation
- verify: json_path(path="journal_mode", equals="wal")
- does: set `PRAGMA synchronous=NORMAL` (one fsync per checkpoint, not per commit, since SQLite is not the record of truth)
- verify: json_path(path="synchronous", equals=2)
- does: set `PRAGMA busy_timeout=5000` (wait 5s for lock contention from concurrent processes)
- verify: json_path(path="busy_timeout", equals=5000)
- does: apply schema (`CREATE TABLE IF NOT EXISTS` for spans, metrics, logs, turns, attend_sessions and their indexes) via `conn.executescript(_SCHEMA)`
- verify: created(subject="spans table")
- does: run column migrations via `_migrate(conn)` — `ALTER TABLE ADD COLUMN` for backfilled columns in `_ADDED_SPAN_COLUMNS`, `_ADDED_LOG_COLUMNS`, `_ADDED_ATTEND_COLUMNS` (currently a no-op since the three tuples are empty, but the call is what makes adding a column a one-line change)
- raises: sqlite3.Error if CREATE/ALTER fails
- verify: json_path(path="exception_type", equals="sqlite3.Error")
- returns: the opened and initialized connection
- verify: json_path(path="type", equals="sqlite3.Connection")
- code: `groom/groom/store.py::_Store._open`

### writing

- sig: `writing(self) -> Iterator[sqlite3.Connection]`
- abstract: context manager for one atomic write transaction
- does: take the RLock before entering (all writes are serialized)
- verify: conflict_on_stale(subject="concurrent writing() attempt", token="writing() context open")
- does: call `BEGIN IMMEDIATE` to take the write lock upfront — if a transaction would fail half-way through on a snapshot conflict, detecting it before the conflict is the point
- verify: conflict_on_stale(subject="concurrent writing() attempt", token="writing() context open") — concurrent `writing()` blocks on the writer lock from the first `BEGIN IMMEDIATE`, not from the first statement, so the snapshot the transaction would otherwise upgrade against is already taken
- does: yield the connection (caller executes statements)
- verify: json_path(path="$.yielded_type", equals="sqlite3.Connection")
- does: `ROLLBACK` on any exception (including KeyboardInterrupt or task cancellation)
- verify: absent(subject="the metrics row inserted inside writing() before the exception, observed from a fresh sqlite3 connection to the database file")
- does: `commit()` on success
- verify: persists(subject="the metrics row inserted inside writing(), observed from a fresh sqlite3 connection after the context exits")
- does: stamp [_last_write_ts](#_last_write_ts) on successful exit
- verify: json_path(path="$._last_write_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- raises: any exception from the called statements (wrapped by @_resilient caller)
- verify: json_path(path="$.exception_type", equals="RuntimeError")
- returns: the connection yielded to the caller for statement execution
- verify: json_path(path="$.yielded_type", equals="sqlite3.Connection")
- code: `groom/groom/store.py::_Store.writing`
- tests: `groom/tests/test_telemetry.py::test_a_failed_write_leaves_no_open_transaction` — the one test that drives `_STORE.writing()` directly, asserting the connection is no longer `in_transaction` after a raised `RuntimeError` and that the row the doomed call inserted is not in a fresh connection afterwards
- consistency: writes — all writes to the store go through this one context, so every write is serialized and atomic
- verify: conflict_on_stale(subject="concurrent writing() attempt", token="writing() context open")
- consistency: transaction — caller executes all statements within the same transaction
- verify: unchanged(subject="database state outside the rows writing() inserted", except_fields=["the metrics rows inserted by writing()"])

### recycle

- sig: `recycle(self, exc: BaseException, where: str) -> None`
- abstract: close the write connection due to a transient or permanent failure, enforcing a cooldown to prevent retry storms when the file itself is the problem. The RLock is reentrant; callers via @_resilient that already hold the lock will not deadlock.
- does: close the connection via [`_close_quietly()`](#_close_quietly) and mark it for reopening the next time connect() is called
- verify: absent(subject="_conn")
- does: increment `_reopens` and update failure tracking
- verify: count(subject="_reopens", equals=1)
- does: raise the original exception on a second close within REOPEN_COOLDOWN_S (5s), because retrying twice that soon means the file itself is the problem
- verify: emitted(event="store.recycled.fast_reopen")
- does: log the recycling for operator diagnostics
- verify: emitted(event="store.recycled")
- raises: the original exception if reopens too fast (meaning: give up, the file is broken)
- verify: exit_status(code=1)
- code: `groom/groom/store.py::_Store.recycle`
- concurrency: lock — takes the lock so close is safe while another thread may be mid-statement
- verify: conflict_on_stale(subject="connection", token="_last_reopen_at")

### reset

- sig: `reset(self) -> None`
- abstract: clear all connection state and failure counters (used between tests to switch $GROOM_DB without residual state)
- does: call [`_close_quietly()`](#_close_quietly) to close the write connection
- verify: absent(subject="_conn")
- does: call [`retire_reader`](#retire_reader) to close this thread's read handle
- verify: removed(subject="read connection from thread-local cache")
- does: clear [`_path`](#_path), _reopens, _failures, _last_error, _last_error_ts, _last_reopen_at, [_last_ok_ts, _last_write_ts, _last_prune_ts](#_last_ok_ts-_last_write_ts-_last_prune_ts), _last_checkpoint_busy
- verify: json_path(path="$._reopens", equals=0)
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.reset`
- tests: `groom/tests/test_store_reads.py::test_reset_retires_the_calling_threads_handle` — asserts that a thread's read handle opened under one $GROOM_DB is not the handle the next case sees (it is retired by `reset()`)
- concurrency: lock — takes the RLock so the close inside [`_close_quietly()`](#_close_quietly) is safe while another thread may be mid-statement on the writer
- verify: conflict_on_stale(subject="concurrent reset() attempt", token="_reopens")

### _close_quietly

- sig: `_close_quietly(self) -> None`
- abstract: close the write connection safely, suppressing errors (called from both cleanup and recycle paths)
- does: suppress sqlite3.Error when calling rollback() (connection may be mid-transaction)
- verify: json_path(path="$.exception_from_rollback", absent=true)
- does: suppress sqlite3.Error when calling close() (connection may be already closed or broken)
- verify: json_path(path="$.exception_from_close", absent=true)
- does: set _conn to None so the next connect() opens a fresh handle
- verify: json_path(path="$._conn", absent=true)
- does: increment _generation so every thread's read handle sees the writer has recycled
- verify: json_path(path="$.generation_delta", equals=1)
- raises: none — all errors are suppressed
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store._close_quietly`
- consistency: readers — readers are not closed from here (another thread may be mid-statement on one)
- consistency: reader-retirement — readers retire themselves when they see _generation has incremented

### read_connection

- sig: `read_connection(self) -> sqlite3.Connection`
- abstract: return a read-only connection belonging to the calling thread
- does: check thread-local cache fast-path: if a _Reader exists with matching generation and path, return its connection (no lock)
- verify: persists(subject="cached read connection")
- does: if cache miss, retire the old one and take the lock once to ensure the writer exists (only init step that needs lock)
- verify: removed(subject="old reader from thread-local storage")
- does: open a `query_only` connection at the writer's path, not at lock time (so the slow open happens without the lock)
- verify: json_path(path="$.query_only", equals=1)
- does: cache the connection in thread-local storage with its generation and path
- verify: persists(subject="read connection in thread-local cache")
- returns: a per-thread read-only connection ready to use
- verify: json_path(path="$.type", equals="sqlite3.Connection")
- code: `groom/groom/store.py::_Store.read_connection`
- concurrency: lock-free-path — fast path takes no lock at all — both checks are plain attribute reads
- concurrency: first-query-sync — only the first query per thread takes the lock once to sync with the writer
- verify: count(subject="lock acquisitions per thread", equals=1)
- concurrency: unserialized-reads — after sync, reads are fully unserialized

### retire_reader

- sig: `retire_reader(self) -> None`
- abstract: close this thread's read handle and clear the cache
- does: read the cached `_Reader` from `self._readers.handle` into a local `cached` (None when nothing was cached yet)
- does: clear `self._readers.handle` to None — the assignment runs unconditionally, even when no handle was cached
- verify: absent(subject="thread-local reader handle")
- does: close `cached.conn` only when a cached reader existed, suppressing any `sqlite3.Error` the close raises
- verify: removed(subject="read connection from thread-local cache")
- raises: none — `sqlite3.Error` from `close()` is suppressed
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.retire_reader`
- tests: `groom/tests/test_store_reads.py::test_reset_retires_the_calling_threads_handle`
- concurrency: thread-local — operates only on `self._readers` and takes no `_Store.lock`, because closing another thread's connection while it is mid-statement is a crash rather than a cleanup
- idempotency: self-clearing — calling twice in a row is equivalent to calling once, because the first call sets `_readers.handle` to None and the second call sees `cached is None`, skipping the conditional close
- consistency: reader-retirement — readers retire themselves the next time `read_connection()` sees `_generation` has moved; `retire_reader()` is the explicit form of that retirement, called when a read fails or the writer is being torn down

### recycle_reader

- sig: `recycle_reader(self, exc: BaseException, where: str) -> None`
- abstract: a read failed; retire that handle and leave the writer alone. Deliberately not the same as [`recycle()`](#recycle) — a reader's broken handle says nothing about the writer's state, and closing the writer here would abort whatever transaction another thread has open. The body is a fixed sequence: stamp the three failure fields, log the failure at `ERROR` level for operator diagnostics, and call [`retire_reader()`](#retire_reader) on this thread
- does: increment `_failures` by one — the read path's contribution to the same health counter [`recycle()`](#recycle) increments on the writer path
- verify: json_path(path="$.failures", equals=1) — observed on `health()` after one `recycle_reader()` call on a fresh `_Store`
- does: write `_last_error` to `f"{type(exc).__name__}: {exc}"` — the same formatted exception message [`recycle()`](#recycle) writes, so a viewer reading `health().last_error` cannot tell which path captured it
- verify: json_path(path="$.last_error", matches="^.*:.*$") — the formatted exception on `health()` after `recycle_reader()` captured a `sqlite3.OperationalError`
- does: write `_last_error_ts` to `time.time()` — the wall-clock seconds, on the same timeline [`_last_ok_ts`](#_last_ok_ts) and [`_last_write_ts`](#_last_write_ts) sit on
- verify: json_path(path="$.last_error_ts", matches="^[0-9]+(\\.[0-9]+)?$") — the wall-clock timestamp on `health()` after `recycle_reader()`
- does: call [`retire_reader()`](#retire_reader) so the calling thread's next query opens a fresh handle — the only state this method mutates beyond the three failure fields
- verify: absent(subject="read connection from thread-local cache") — the calling thread's cached `_Reader` is gone after `recycle_reader()` runs against a thread that had one cached
- raises: none — the body never raises; any `sqlite3.Error` from closing the retired handle is suppressed inside [`retire_reader()`](#retire_reader)
- verify: json_path(path="$.exception", absent=true) — `recycle_reader()` does not raise on its own
- code: `groom/groom/store.py::_Store.recycle_reader`
- tests: `groom/tests/test_store_reads.py::test_a_broken_read_handle_is_retired_without_disturbing_the_writer` — closes the cached read handle so the next query raises, exercises the [`_reading`](#_reading) wrapper's catch path that calls `recycle_reader()`, and asserts the writer handle is the same object afterwards
- concurrency: reader-path-unlocked — none of the writes happen under `_Store.lock`, because the writer lock is what a read exists to avoid and taking it to record a number is exactly the wait this path was built to avoid
- concurrency: increment-may-race-with-recycle — `self._failures += 1` is a read-modify-write that can lose increments when a [`recycle()`](#recycle) and a `recycle_reader()` interleave on the same `_Store`; a lost increment under a race is the cheaper of the two waits

### note_ok

- sig: `note_ok(self) -> None`
- abstract: stamp a successful statement (used by @_resilient and @_reading)
- does: update [_last_ok_ts](#_last_ok_ts) to current wall time
- verify: json_path(path="$._last_ok_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.note_ok`
- tests: `groom/tests/test_telemetry.py::test_store_health_rides_the_state_payload` — drives an `insert_spans` through the `_resilient` wrapper (so [`_resilient`](#_resilient)'s post-success branch calls `_STORE.note_ok()`), breaks the handle, drives a second call that fails and is recycled (so [`_last_error_ts`](#_last_error_ts) is stamped), then drives a third call that succeeds and is again stamped by `note_ok()`; asserts `health["ok"] is True`, which only holds when the final `note_ok()` left [`_last_ok_ts`](#_last_ok_ts) newer than [`_last_error_ts`](#_last_error_ts)

`_last_ok_ts` is the upper bound against which [`health()`](#health) compares `_last_error_ts`: a failure older than the last good call has been healed; one newer has not.

### note_prune

- sig: `note_prune(self, ts: float | None = None) -> None`
- abstract: stamp when the prune operation completed
- does: set [_last_prune_ts](#_last_prune_ts) to the explicit `ts` argument when one is given
- verify: json_path(path="$._last_prune_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- does: set [_last_prune_ts](#_last_prune_ts) to current wall time when `ts is None`
- verify: json_path(path="$._last_prune_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.note_prune`
- concurrency: lock-free — the assignment runs outside `_Store.lock` (the writer lock never enters this method), trading the read-modify-write race the unlock allows against the wait a lock-protected stamp would cost in a path that runs on every prune tick

### note_checkpoint

- sig: `note_checkpoint(self, busy: int) -> None`
- abstract: record whether the WAL checkpoint found a reader in the way
- does: set _last_checkpoint_busy to the busy value (0 or 1)
- verify: json_path(path="$._last_checkpoint_busy", equals=1)
- raises: none
- code: `groom/groom/store.py::_Store.note_checkpoint`

`busy=1` means a reader was holding a snapshot and the file was left alone; `_last_checkpoint_busy` is then surfaced in [`health()`](#health) for operator visibility.

### health

- sig: `health(self) -> StoreHealth`
- does: snapshot the connection and error state into a StoreHealth dataclass, reporting `path` as `str(db_path())` — the database this call resolves, not the one a connection was opened against earlier
- verify: json_path(path="$.path", matches="^.*/telemetry\\.db$")
- does: compute WAL file size as current (read from disk each time)
- verify: json_path(path="$.wal_bytes", matches="^[0-9]+$")
- does: return ok flag as `_last_error_ts <= _last_ok_ts` (failure older than last success has been healed)
- does: read [`_last_ok_ts`](#_last_ok_ts) as the upper bound in the comparison above
- verify: json_path(path="$.ok", equals=false)
- returns: StoreHealth with path, ok, reopens, failures, last_error, last_error_ts, last_write_ts, last_prune_ts, last_checkpoint_busy, wal_bytes
- verify: json_path(path="$.failures", matches="^[0-9]+$")
- code: `groom/groom/store.py::_Store.health`

The `path` observation is scenario-owned: the scenario points `$GROOM_DB` at
`<sandbox>/telemetry.db`, calls `health()`, and captures the returned dataclass as a mapping. A
filename that is not the platform default's `groom.db` is what makes the check discriminating — the
near-miss defects are reporting the platform data dir instead of the configured `$GROOM_DB`, and
reporting the `-wal` sibling `health()` stats alongside it, both of which a presence-only read on
`$.path` passes.

## Supporting types

### _Reader

- sig: `_Reader(conn: sqlite3.Connection, generation: int, path: Path)`
- abstract: one thread's read handle, tagged with what it was opened against (for cache validation)
- semantics: cached in thread-local storage; the generation and path let read_connection() detect stale snapshots and reconnect silently
- code: `groom/groom/store.py::_Reader`

### field: StoreHealth

The frozen dataclass returned by [`_Store.health()`](#health) on every call — a complete
snapshot of the connection and resilience state at that moment. Eleven attributes, all
positional, all required; the class holds no defaults. Constructed fresh per call and never
mutated afterwards; consumed verbatim by [`_STORE.health()`](#health)'s sibling
[`health_dict()`](groom-store.md#health-and-health_dict), which `asdict`s the same fields
into the JSON shape under the `store` key of [dashboard state payload](../dashboard-state-payload.md#field-store),
so a viewer of `/api/state` reads this object as one mapping of the same eleven fields.

The snapshot is named `StoreHealth` (not `status` or `store_state`) because the snapshot
intentionally carries two viewpoints at once: `wal_bytes` and `last_checkpoint_busy` are
real-time readings at the moment of the call, while `ok`, `reopens`, `failures`,
`last_error`, and `last_error_ts` aggregate since the last [`reset()`](#reset). The
dashboard reads both in one dict rather than asking the same store twice and reconciling,
which would risk observing the failure of the first ask from the second.

The eleven attributes are documented as nested fields below, ordered as the dataclass
declares them: boolean `ok`, the database `path` string, then the wall-clock timestamps
`last_ok_ts` / `last_error_ts` / `last_write_ts` / `last_prune_ts`, then the integer
counters `reopens` / `failures`, the most recent exception text `last_error`, and finally
`wal_bytes` and `last_checkpoint_busy` from the checkpoint tick.

- type: frozen dataclass with eleven positional attributes
- semantics: a snapshot, never mutating — the runner must call [health()](#health) again to see new state
- semantics: shaped for the dashboard, not for in-process use — same fields surface through [`health_dict()`](groom-store.md#health-and-health_dict) as JSON
- semantics: `_resilient`-decorated callers do not read this type — `_Store.health()` runs on the operator dashboard path, not on the ingest path
- code: `groom/groom/store.py::StoreHealth`
- code: `groom/groom/store.py::_Store.health`
- detail: [_store-class](_store-class.md)
- tests: `groom/tests/test_telemetry.py::test_store_health_rides_the_state_payload` — closes the writer mid-test, retries through `_resilient`, and reads `state_message([])["store"]["ok"] is True` against the snapshot the next [health()](#health) returns

#### field: ok

- type: `bool`
- default: `True` — computed at construction when [`_Store.health()`](#health) builds the snapshot
- required: true
- semantics: "no failure is outstanding right now" — `_last_error_ts <= _last_ok_ts`, the comparison evaluated once per call
- semantics: distinct from "the last call succeeded": after one wedged-and-reopened call, `_last_error_ts` and the new `_last_ok_ts` are roughly equal, so `ok` flips to `True` even though a recycle really happened
- code: `groom/groom/store.py::StoreHealth.ok`
- verify: json_path(path="$.ok", equals=false)
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited` — recycles twice; the second recycle raises inside the cooldown without stamping `_last_ok_ts`, so `_last_error_ts > _last_ok_ts` and `holder.health().ok is False`

#### field: path

- type: `str`
- default: none — set on every [`_Store.health()`](#health) call to `str(db_path())`
- required: true
- semantics: the database file this call resolves, not the path a connection was opened against earlier — re-read from `db_path()` on every snapshot so a `$GROOM_DB` change between calls is reflected immediately rather than held over from a previous open
- code: `groom/groom/store.py::StoreHealth.path`
- verify: json_path(path="$.path", matches="^.*telemetry\\.db$")
- tests: `groom/tests/test_telemetry.py::test_store_health_rides_the_state_payload` — overrides `$GROOM_DB` to a per-test path and asserts `state_message([])["store"]["path"] == str(store.db_path())`

#### field: last_ok_ts

- type: `float` (epoch seconds, `time.time()` units — wall-clock so it is comparable to `last_write_ts` and `last_prune_ts`)
- default: `0.0` — the "no successful statement has run" sentinel on a fresh `_Store` and after [`reset()`](#reset)
- required: true
- semantics: wall-clock instant of the most recent successful wrapped statement, stamped by [`note_ok()`](#note_ok) inside `_resilient` after the wrapped function returns
- semantics: used as the upper bound in the `ok` comparison, so `ok = last_ok_ts >= last_error_ts`
- code: `groom/groom/store.py::StoreHealth.last_ok_ts`
- code: `groom/groom/store.py::_Store.note_ok`
- verify: json_path(path="$.last_ok_ts", matches="^[0-9]+(\\.[0-9]+)?$")

#### field: reopens

- type: `int`
- default: `0` — incremented inside [`recycle()`](#recycle) after `_close_quietly()` has returned
- required: true
- semantics: count of writer connection recyclings completed since the last [`reset()`](#reset)
- semantics: a recycle suppressed by the cooldown gate raises instead of closing and leaves the count where it was — the counter measures success, not attempts
- code: `groom/groom/store.py::StoreHealth.reopens`
- verify: count(subject="_reopens", equals=1)
- tests: `groom/tests/test_telemetry.py::test_a_closed_connection_heals_on_the_next_write` — closes the writer mid-test, retries through `_resilient`, asserts `store.health().reopens == 1`

#### field: failures

- type: `int`
- default: `0` — incremented on every failure stamped by [`recycle()`](#recycle) or [`recycle_reader()`](#recycle_reader)
- required: true
- semantics: count of connection errors observed since the last [`reset()`](#reset)
- semantics: the increment from `recycle()` happens before the cooldown gate, so a recycle that raises inside the cooldown still bumps the count
- code: `groom/groom/store.py::StoreHealth.failures`
- verify: count(subject="_failures", equals=2)
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited` — recycles twice against a `_Store` with an injected clock; first stamp succeeds and bumps to 1, second recycle raises inside the cooldown but still bumps to 2

#### field: last_error

- type: `str`
- default: `""` — the "no failure observed" sentinel on a fresh `_Store` and after [`reset()`](#reset)
- required: true
- semantics: formatted as `f"{type(exc).__name__}: {exc}"` so the exception class name prefixes the message after `: `
- semantics: one example format is `OperationalError: database is locked` — the class and message joined with `": "`, with no escaping
- semantics: surfaced raw to the operator dashboard as the string itself
- semantics: the dashboard does not parse it into the exception class — it escapes and renders text only
- code: `groom/groom/store.py::StoreHealth.last_error`
- verify: json_path(path="$.last_error", matches=".*:.*")
- tests: `groom/tests/test_telemetry.py::test_reopen_is_rate_limited` — the recycle stamps an `OperationalError`-prefixed message, asserted via `holder.health().last_error`

#### field: last_error_ts

- type: `float` (epoch seconds, `time.time()` units)
- default: `0.0` — the "no failure observed" sentinel
- required: true
- semantics: wall-clock instant of the most recent failure, stamped by [`recycle()`](#recycle) and [`recycle_reader()`](#recycle_reader) at the same site as [`last_error`](#field-last_error)
- semantics: read as the lower bound in the `ok` comparison — `ok = last_error_ts <= last_ok_ts`
- code: `groom/groom/store.py::StoreHealth.last_error_ts`
- verify: json_path(path="$.last_error_ts", matches="^[0-9]+(\\.[0-9]+)?$")

#### field: last_write_ts

- type: `float` (epoch seconds, `time.time()` units)
- default: `0.0` — the "no successful commit yet" sentinel on a fresh `_Store` and after [`reset()`](#reset)
- required: true
- semantics: wall-clock instant of the most recent successful `COMMIT`, stamped by [`writing()`](#writing) on its successful path inside the `_Store.lock`
- semantics: surfaced to the dashboard so a viewer can see how stale the last durable write is
- code: `groom/groom/store.py::StoreHealth.last_write_ts`
- code: `groom/groom/store.py::_Store.writing`
- verify: json_path(path="$.last_write_ts", matches="^[0-9]+(\\.[0-9]+)?$")

#### field: last_prune_ts

- type: `float` (epoch seconds, `time.time()` units)
- default: `0.0` — the "no prune cycle yet" sentinel on a fresh `_Store` and after [`reset()`](#reset)
- required: true
- semantics: wall-clock instant of the most recent prune cycle, stamped by [`note_prune()`](#note_prune) when the prune loop has finished (optionally with an explicit timestamp argument)
- semantics: surfaced to the dashboard so a viewer can see how stale the last prune is
- code: `groom/groom/store.py::StoreHealth.last_prune_ts`
- code: `groom/groom/store.py::_Store.note_prune`
- verify: json_path(path="$.last_prune_ts", matches="^[0-9]+(\\.[0-9]+)?$")

#### field: wal_bytes

- type: `int`
- default: `0` — the size of the `-wal` sibling when no `-wal` file exists on disk at the moment of the call
- required: true
- semantics: byte size of the `-wal` sibling of the database file, read from disk on every [`_Store.health()`](#health) call as `wal.stat().st_size if wal.exists() else 0`
- semantics: goes to `0` when the WAL has been truncated (checkpoint succeeded) or when the database has never been opened in WAL mode
- code: `groom/groom/store.py::StoreHealth.wal_bytes`
- verify: json_path(path="$.wal_bytes", matches="^[0-9]+$")

#### field: last_checkpoint_busy

- type: `int`
- default: `0` — the "no checkpoint has run yet" sentinel on a fresh `_Store` and after [`reset()`](#reset)
- default: `0` — also the value reported when the most recent `PRAGMA wal_checkpoint(TRUNCATE)` was unobstructed (a busy count of `1` is the failure signal, not `0`)
- required: true
- semantics: SQLite's `wal_checkpoint(TRUNCATE)` `busy` flag (0 or 1) from the most recent [`checkpoint()`](groom-store.md#checkpoint) call, recorded by [`note_checkpoint()`](#note_checkpoint)
- semantics: a steady `1` across many checkpoints means a reader is pinning the WAL indefinitely — the failure mode this field exists to make visible (a 293 MB database carrying a 376 MB WAL)
- code: `groom/groom/store.py::StoreHealth.last_checkpoint_busy`
- code: `groom/groom/store.py::_Store.note_checkpoint`
- verify: json_path(path="$.last_checkpoint_busy", equals=1)
- tests: `groom/tests/test_telemetry.py::test_a_blocked_checkpoint_is_reported_and_never_poisons` — opens a reader transaction holding `BEGIN`, calls `checkpoint()`, asserts `store.health().last_checkpoint_busy == 1`

## Decorators

The module-level wrappers that wrap store calls in retry-and-heal semantics. They are decorators of the same name in `groom/groom/store.py` (defined adjacent to the `_Store` class they wrap); the wrappers are what `_Store`-decorated methods call before touching the connection, and the contract here is the one those wrapped methods inherit.

### method: _resilient

The decorator used by every write-side store call (`insert_spans`, `_write_metrics`, `insert_logs`, `apply_estimates`, `_delete_chunk`, `purge_test_runs`, `insert_turns`, `attend_*`, `_write_metrics`, `checkpoint`, `recycle`-backed writers). Decorate leaf functions only: a decorated function that calls another decorated one multiplies attempts.

- sig: `_resilient(fn: Callable[_P, _T]) -> Callable[_P, _T]`
- abstract: serialize a store call under the lock, and heal the connection under it exactly once
- concurrency: write-connection — takes `_STORE.lock` for the duration of the wrapped call, so a second call blocks until the first releases it rather than interleaving statements on the same connection
- verify: conflict_on_stale(subject="concurrent _resilient call", token="_STORE.lock held by first call")
- consistency rule: write-connection — on `sqlite3.Error`, calls `_STORE.recycle()` and retries the undecorated function body exactly once, so a wedged connection is healed within the one call instead of propagating to the caller
- verify: count(subject="function body invocations through _resilient wrapper after a sqlite3.Error", equals=2)
- consistency rule: store-health — on eventual success, calls `_STORE.note_ok()` before returning, clearing the failure state that `health().ok` reads
- verify: count(subject="_STORE.note_ok() calls after a successful _resilient call", equals=1)
- raises: the original sqlite3.Error when `_STORE.recycle()` raises (file is the problem — the wrapper does not wrap or replace it)
- verify: json_path(path="$.exception_type", equals="sqlite3.OperationalError")
- raises: any non-sqlite3 exception from the wrapped function unchanged (the wrapper's `except` only catches `sqlite3.Error`)
- verify: json_path(path="$.exception_type", equals="ValueError")
- code: `groom/groom/store.py::_resilient`
- tests: `groom/tests/test_telemetry.py::test_a_closed_connection_heals_on_the_next_write` — closes the writer handle mid-test, drives `insert_spans` (decorated with `_resilient`) through `_STORE.connect()`, and asserts both the row lands and `reopens == 1`, which only holds if the wrapper retried the undecorated body once after `recycle()` reopened
- tests: `groom/tests/test_telemetry.py::test_store_health_rides_the_state_payload` — drives an `insert_spans` through the `_resilient` wrapper, breaks the handle, drives a second call that fails and is recycled, then drives a third call that succeeds; asserts `health["ok"] is True`, which only holds when the final successful call left `_last_ok_ts` newer than `_last_error_ts` via `_STORE.note_ok()`
- semantics: retry calls the *undecorated* body so depth is bounded at two by construction; the wrapper's return value is whatever the wrapped function returned

### method: _reading

The decorator used by every read-side store call (`query_logs`, `unpriced_models`, `reprice`, `_estimable_turns`, `unpriceable_turns`, `node_costs`, `run_profile`, `query_spans`, `run_summaries`, `archive_page`, `_test_run_ids`, `_expired_run_ids`, `_profile_turn_summary` collaborators, `unarchived_row_counts`, `query_turns`, `run_directories`, `run_bounds`, `test_run_ids`). It is `_resilient` without the lock: same one-retry contract, but readers already serialize through the per-thread `_Reader` handle and do not contend with the writer. Decorate leaf functions only.

- sig: `_reading(fn: Callable[_P, _T]) -> Callable[_P, _T]`
- abstract: heal the connection once on a read failure, and take no lock doing it
- does: call the wrapped function without acquiring `_STORE.lock`, so concurrent reads do not serialize on a writer behind a held lock
- verify: persists(subject="query result through _reading wrapper while another thread holds _STORE.lock")
- does: on `sqlite3.Error`, call `_STORE.recycle_reader(exc, name)` and retry the undecorated function body exactly once
- verify: count(subject="function body invocations through _reading wrapper after a sqlite3.Error", equals=2)
- does: on success, call `_STORE.note_ok()` and return the wrapped function's result
- verify: count(subject="_STORE.note_ok() calls after a successful _reading call", equals=1)
- raises: any non-sqlite3 exception from the wrapped function unchanged (the wrapper's `except` only catches `sqlite3.Error`)
- verify: json_path(path="$.exception_type", equals="ValueError")
- code: `groom/groom/store.py::_reading`
- consistency: recycle-reader-suppresses-close-error — the error closing the retired handle is suppressed inside [`_STORE.retire_reader()`](#retire_reader), so a `sqlite3.Error` from `close()` does not surface through `_STORE.recycle_reader()` and the wrapper's retry path is reached
- verify: json_path(path="$.exception_type", absent=true)
- tests: `groom/tests/test_store_reads.py::test_the_dashboard_queries_answer_while_the_write_lock_is_held` — warms each thread's read handle outside the measurement, holds `_STORE.lock` from another thread for two seconds, then asserts every dashboard read (`query_spans`, `run_summaries`, `query_logs`, `query_turns`, `run_profile`) returned inside a 250 ms budget; the reads answer because the wrapper does not acquire the writer's lock
- tests: `groom/tests/test_store_reads.py::test_a_broken_read_handle_is_retired_without_disturbing_the_writer` — closes the cached read handle so the next query raises, exercises the `_reading` wrapper's catch path that calls `recycle_reader()`, and asserts the writer handle is the same object afterwards, which only holds if `recycle_reader()` retired the read handle without recycling the writer
- semantics: same one-retry contract as `_resilient` because a read hits the same disposable handle; decorate leaf functions only

## concept: Design rationale

The five load-bearing design choices behind `_Store`, the process's one SQLite handle. Each was learned from a serve that silently stopped storing; the rationale lives in source comments at the cited symbol.

- code: `groom/groom/store.py::_Store`
- code: `groom/groom/store.py::_Store.__init__`
- code: `groom/groom/store.py::_Store._open`
- code: `groom/groom/store.py::_Store.recycle`
- code: `groom/groom/store.py::_Store.read_connection`
- code: `groom/groom/store.py::_resilient`
- code: `groom/groom/store.py::_reading`

**Autocommit mode** (`isolation_level=None`) removes the failure mode where an exception between an implicit BEGIN and commit leaves the connection inside a transaction. Every later SELECT would re-pin the read snapshot, and every later write would die of SQLITE_BUSY_SNAPSHOT forever because nothing reopened.

**One RLock** means SQLite serialized mode plus the transaction-level discipline that one connection carries exactly one transaction, so without the lock a worker thread's write and the event loop's inline read become the same transaction.

**Connection recycling** makes the handle disposable: the file is not. When a statement fails, the next call opens a fresh handle. A wedged connection heals on the first reopen; a broken file (disk full, corruption) would trash on every request without the `REOPEN_COOLDOWN_S` cooldown.

**Per-thread readers** exist because a sqlite3 connection carries one transaction and one snapshot, so handing the same one to two pool threads interleaves their statements. The pools are small and long-lived, so this is a handful of handles for the life of the process, not one per request.

**WAL mode** gives a reader a consistent snapshot alongside the writer without blocking it, which is why readers need no lock at all.

