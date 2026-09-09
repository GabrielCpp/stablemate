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

## Attributes

### init

- sig: `__init__(self, monotonic: Callable[[], float] = time.monotonic) -> None`
- does: initialize the singleton with process-wide writer state, per-thread reader handles, and failure tracking
- does: inject `monotonic` clock so reopen cooldown is testable without real sleep
- raises: none
- code: `groom/groom/store.py::_Store.__init__`

### _conn

- semantics: the open write connection, or None; protected by `lock`
- required: false — None until first connect() call, and None again after _close_quietly()

### _path

- semantics: Path the connection is open against (used to detect when db_path() env var changes)
- required: false — None if no connection yet

### lock

- semantics: `threading.RLock()` serializing every write and connection state mutation
- required: true — every write goes through `@_resilient` which takes this lock
- idempotency: write-nesting — reentrant so write operations can nest without deadlock

### _readers

- semantics: `threading.local()` holding per-thread read connections in `.handle: _Reader`
- required: true — readers are isolated per thread so concurrent readers do not share snapshots
- concurrency: isolation — thread-local storage means no lock needed
- concurrency: ownership — each thread owns its handle

### _generation

- semantics: monotonic counter incremented each time the write connection is closed, so read handles can detect stale snapshots
- required: true — incremented in _close_quietly() so read_connection() sees when writer has recycled

### _reopens, _failures

- semantics: count of connection recyclings and errors encountered
- required: false — used only for health reporting

### _last_error, _last_error_ts

- semantics: the most recent exception message and when it occurred
- required: false — used for health reporting and recovery decision (is this fresh or healing?)

### _last_reopen_at

- semantics: when the last reopen was attempted
- required: true — used by recycle() to enforce REOPEN_COOLDOWN_S (5s) between reopens when the file is the problem

### _last_ok_ts, _last_write_ts, _last_prune_ts

- semantics: wall-clock timestamps of the last successful operation, write, and prune
- required: false — used for health reporting

### _last_checkpoint_busy

- semantics: whether the most recent checkpoint found a reader in the way (busy=1)
- required: false — surfaced in health for operator visibility

## Methods

### connect

- sig: `connect(self) -> sqlite3.Connection`
- does: return the open write connection, opening or reopening it if there isn't one
- verify: json_path(path="$.result_type", equals="sqlite3.Connection")
- does: close and reopen if `db_path()` has changed (tests switch $GROOM_DB between cases)
- verify: created(subject="connection to new database path")
- raises: sqlite3.Error if _open() fails (caught and retried by caller's @_resilient wrapper)
- verify: json_path(path="$.exception_type", equals="sqlite3.Error")
- returns: the write connection, opened at `self._path` in autocommit mode
- verify: json_path(path="$.isolation_level", equals=null)
- code: `groom/groom/store.py::_Store.connect`
- concurrency: `connect()` takes `self.lock` (the process-wide `RLock`) before opening or returning the connection, so concurrent callers are serialized rather than racing to open two handles
- idempotency: connection — idempotent once the file exists — multiple calls return the same open handle (until recycled)
- verify: persists(subject="connection")

### _open

- sig: `_open(self, path: Path) -> sqlite3.Connection`
- does: create the database file and its parent directories if needed
- verify: created(subject="database file at path")
- does: open with `check_same_thread=False` (explicit locking via RLock) and `isolation_level=None` (autocommit)
- does: enable WAL mode (`PRAGMA journal_mode=WAL`) for reader/writer isolation
- verify: json_path(path="journal_mode", equals="wal")
- does: set `PRAGMA synchronous=NORMAL` (one fsync per checkpoint, not per commit, since SQLite is not the record of truth)
- verify: json_path(path="synchronous", equals=2)
- does: set `PRAGMA busy_timeout=5000` (wait 5s for lock contention from concurrent processes)
- verify: json_path(path="busy_timeout", equals=5000)
- does: apply schema (CREATE TABLE IF NOT EXISTS) and run migrations (ALTER TABLE ADD COLUMN for backfilled columns)
- verify: created(subject="spans table")
- raises: sqlite3.Error if CREATE/ALTER fails
- verify: json_path(path="exception_type", equals="sqlite3.Error")
- returns: the opened and initialized connection
- verify: json_path(path="type", equals="sqlite3.Connection")
- code: `groom/groom/store.py::_Store._open`

### writing

- sig: `writing(self) -> Iterator[sqlite3.Connection]`
- abstract: context manager for one atomic write transaction
- does: take the RLock before entering (all writes are serialized)
- does: call `BEGIN IMMEDIATE` to take the write lock upfront — if a transaction would fail half-way through on a snapshot conflict, detecting it before the conflict is the point
- does: yield the connection (caller executes statements)
- does: `ROLLBACK` on any exception (including KeyboardInterrupt or task cancellation)
- does: `commit()` on success
- does: stamp `_last_write_ts` on successful exit
- raises: any exception from the called statements (wrapped by @_resilient caller)
- returns: the connection yielded to the caller for statement execution
- code: `groom/groom/store.py::_Store.writing`
- consistency: writes — all writes to the store go through this one context, so every write is serialized and atomic
- consistency: transaction — caller executes all statements within the same transaction

### recycle

- sig: `recycle(self, exc: BaseException, where: str) -> None`
- abstract: close the write connection due to a transient or permanent failure, enforcing a cooldown to prevent retry storms when the file itself is the problem. The RLock is reentrant; callers via @_resilient that already hold the lock will not deadlock.
- does: close the connection and mark it for reopening the next time connect() is called
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
- does: call _close_quietly() to close the write connection
- verify: absent(subject="_conn")
- does: call retire_reader() to close this thread's read handle
- verify: removed(subject="read connection from thread-local cache")
- does: clear _path, _reopens, _failures, _last_error, _last_error_ts, _last_reopen_at, _last_ok_ts, _last_write_ts, _last_prune_ts, _last_checkpoint_busy
- verify: json_path(path="$._reopens", equals=0)
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.reset`
- semantics: called by tests (via module-level reset()) and by reset-like paths

### _close_quietly

- sig: `_close_quietly(self) -> None`
- abstract: close the write connection safely, suppressing errors (called from both cleanup and recycle paths)
- does: suppress sqlite3.Error when calling rollback() (connection may be mid-transaction)
- verify: json_path(path="$.exception_from_rollback", equals=null)
- does: suppress sqlite3.Error when calling close() (connection may be already closed or broken)
- verify: json_path(path="$.exception_from_close", equals=null)
- does: set _conn to None so the next connect() opens a fresh handle
- verify: json_path(path="$._conn", equals=null)
- does: increment _generation so every thread's read handle sees the writer has recycled
- verify: json_path(path="$.generation_delta", equals=1)
- raises: none — all errors are suppressed
- verify: json_path(path="$.exception", equals=null)
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
- does: get the cached _Reader from thread-local storage and close it, suppressing sqlite3.Error
- verify: removed(subject="read connection from thread-local cache")
- does: clear the thread-local handle reference
- verify: absent(subject="thread-local reader handle")
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.retire_reader`

### recycle_reader

- sig: `recycle_reader(self, exc: BaseException, where: str) -> None`
- abstract: a read failed; retire that handle and leave the writer alone
- does: increment _failures (without taking the lock — the counters feed a health display and lock contention costs more than a lost increment)
- verify: count(subject="_failures", equals=1)
- does: record _last_error (also without the lock)
- verify: json_path(path="$.last_error", matches="^.*:.*$")
- does: record _last_error_ts (also without the lock)
- verify: json_path(path="$.last_error_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- does: log the error
- verify: emitted(event="store.reader.recycled")
- does: call retire_reader()
- verify: removed(subject="read connection from thread-local cache")
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.recycle_reader`
- semantics: deliberately not the same as recycle(); a reader's broken handle says nothing about the writer's state, and closing the writer would abort whatever transaction another thread has open

### note_ok

- sig: `note_ok(self) -> None`
- abstract: stamp a successful statement (used by @_resilient and @_reading)
- does: update _last_ok_ts to current wall time
- verify: json_path(path="$._last_ok_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.note_ok`
- semantics: what health().ok is measured against — a failure older than the last good call has been healed; one newer has not

### note_prune

- sig: `note_prune(self, ts: float | None = None) -> None`
- abstract: stamp when the prune operation completed
- does: set _last_prune_ts to the provided timestamp or current time
- verify: json_path(path="$._last_prune_ts", matches="^[0-9]+(\\.[0-9]+)?$")
- raises: none
- verify: json_path(path="$.exception", absent=true)
- code: `groom/groom/store.py::_Store.note_prune`

### note_checkpoint

- sig: `note_checkpoint(self, busy: int) -> None`
- abstract: record whether the WAL checkpoint found a reader in the way
- does: set _last_checkpoint_busy to the busy value (0 or 1)
- verify: json_path(path="$._last_checkpoint_busy", equals=1)
- raises: none
- code: `groom/groom/store.py::_Store.note_checkpoint`
- semantics: busy=1 means a reader was holding a snapshot and the file was left alone; surfaced in health for operator visibility

### health

- sig: `health(self) -> StoreHealth`
- does: snapshot the connection and error state into a StoreHealth dataclass
- verify: json_path(path="$.path")
- does: compute WAL file size as current (read from disk each time)
- verify: json_path(path="$.wal_bytes", matches="^[0-9]+$")
- does: return ok flag as `_last_error_ts <= _last_ok_ts` (failure older than last success has been healed)
- verify: json_path(path="$.ok", equals=false)
- returns: StoreHealth with path, ok, reopens, failures, last_error, last_error_ts, last_write_ts, last_prune_ts, last_checkpoint_busy, wal_bytes
- verify: json_path(path="$.failures", matches="^[0-9]+$")
- code: `groom/groom/store.py::_Store.health`

## Supporting types

### _Reader

- sig: `_Reader(conn: sqlite3.Connection, generation: int, path: Path)`
- abstract: one thread's read handle, tagged with what it was opened against (for cache validation)
- semantics: cached in thread-local storage; the generation and path let read_connection() detect stale snapshots and reconnect silently
- code: `groom/groom/store.py::_Reader`

### StoreHealth

- sig: `StoreHealth(ok: bool, path: str, last_ok_ts: float, reopens: int, failures: int, last_error: str, last_error_ts: float, last_write_ts: float, last_prune_ts: float, wal_bytes: int, last_checkpoint_busy: int)`
- abstract: snapshot of store connection and resilience state
- does: ok flag is not "the last call succeeded" but "nothing has failed since the last successful reopen" — the distinction that matters after a two-week serve
- code: `groom/groom/store.py::StoreHealth`
- tests: `groom/tests/test_store_resilience.py::test_health_ok_flag_requires_newer_success_than_failure`

## Decorators

### _resilient

- sig: `_resilient(fn: Callable[_P, _T]) -> Callable[_P, _T]`
- abstract: serialize a store call under the lock, and heal the connection under it exactly once
- concurrency: takes `_STORE.lock` for the duration of the wrapped call, so a second call blocks until the first releases it rather than interleaving statements on the same connection
- consistency rule: on `sqlite3.Error`, calls `_STORE.recycle()` and retries the undecorated function body exactly once, so a wedged connection is healed within the one call instead of propagating to the caller
- consistency rule: on eventual success, calls `_STORE.note_ok()` before returning, clearing the failure state that `health().ok` reads
- raises: the original sqlite3.Error if recycle() raises (meaning: file is the problem); any other exception from the function
- code: `groom/groom/store.py::_resilient`
- semantics: retry calls the *undecorated* body so depth is bounded at two by construction; decorate leaf functions only; the wrapper's return value is whatever the wrapped function returned

### _reading

- sig: `_reading(fn: Callable[_P, _T]) -> Callable[_P, _T]`
- abstract: serialize a query, heal the connection once, and take no lock (readers already serialize through the thread-local handle)
- does: call the wrapped function without holding _STORE.lock
- does: on sqlite3.Error: call _STORE.recycle_reader(), then retry the undecorated function body exactly once
- does: on success: call _STORE.note_ok() and return the result
- raises: any exception from the function
- code: `groom/groom/store.py::_reading`
- consistency: recycle-reader-never-raises — `_STORE.recycle_reader()` never raises (it suppresses the error closing the retired handle internally), so the retry after it always executes; a `recycle_reader()` that could raise would leave the original error unretried instead
- semantics: same one-retry contract as _resilient because a read hits the same disposable handle; decorate leaf functions only

## Design rationale

**Autocommit mode** (`isolation_level=None`) removes the failure mode where an exception between an implicit BEGIN and commit leaves the connection inside a transaction. Every later SELECT would re-pin the read snapshot, and every later write would die of SQLITE_BUSY_SNAPSHOT forever because nothing reopened.

**One RLock** means SQLite serialized mode plus the transaction-level discipline that one connection carries exactly one transaction, so without the lock a worker thread's write and the event loop's inline read become the same transaction.

**Connection recycling** makes the handle disposable: the file is not. When a statement fails, the next call opens a fresh handle. A wedged connection heals on the first reopen; a broken file (disk full, corruption) would trash on every request without the `REOPEN_COOLDOWN_S` cooldown.

**Per-thread readers** exist because a sqlite3 connection carries one transaction and one snapshot, so handing the same one to two pool threads interleaves their statements. The pools are small and long-lived, so this is a handful of handles for the life of the process, not one per request.

**WAL mode** gives a reader a consistent snapshot alongside the writer without blocking it, which is why readers need no lock at all.

