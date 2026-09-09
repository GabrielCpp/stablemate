---
type: concept
slug: groom-turns-module
title: Groom turns module
---
# Groom turns module

The Groom turns module archives turn records — the transcripts, prompts, and outputs captured during workflow executions. A turn record is written first to a run directory by the capture layer (the session store), then moved to a durable archive root beside the groom database where it lives independently of whether the run directory still exists. This is the only path a transcript moves from its source in the workhorse agent to the archive that survives the deletion of the run directory.

Two archive roots structure the design: `transcripts/<run_id>/` holds records for live or recently-finished runs and is where the harvester writes; `archives/<run_id>/` holds frozen records past their retention window, moved there by the archiver when their telemetry ages out. Both roots are siblings under the database directory, making promotion a single same-filesystem `os.rename()`, atomic and fail-closed: a run is in exactly one state with no third state to reason about. The harvester only knows about `transcripts/`, so archived runs cannot be re-written. Nothing here deletes a run whose index row still exists in SQL; deletion happens only from `groom.store.prune`, after the archiver has confirmed the copy.

Records are indexed by `(generation, seq, session_id)` — the visit key — which is stamped by the runner but may be reconstructed from the session map for runs predating the visit-key innovation. A reconstructed key carries `generation = -1` and an ordinal that orders the run's turns, stable across re-harvests since the session map is append-only. A record's path is stored relative to its root in the index, so `record_path()` resolves it by checking the live root first, then the frozen one, handling the rare case of a re-run that was archived twice.

Nothing here may raise into groom's tick. A record that cannot be copied is a record that is not archived — a poorer archive, not a broken groom.

- code: groom/groom/turns.py
- refs: [groom archive module](groom-archive-module.md), [groom store](groom-store.md)

The harvesting and backfill flows are covered by `groom/tests/test_turns.py`.

## Constants

### max-record-bytes

- type: `int`
- default: `67108864` (64 MiB), from `GROOM_TRANSCRIPT_MAX_BYTES`
- required: true
- code: groom/groom/turns.py::MAX_RECORD_BYTES
- consistency: archived-record — no record is archived larger than this limit in bytes
- verify: persists(subject="archived record")
- semantics: ceiling on one archived record, by byte count. Bounds both the runner's capture layer and the backfill path, which copies out of a CLI's own store and has never been through the runner's cap. A record exceeding this limit is truncated during copying, not rejected.

### run-transcripts

- type: `str`
- default: `transcripts` (from `capture.TRANSCRIPTS_DIR`)
- required: true
- code: groom/groom/turns.py::RUN_TRANSCRIPTS
- semantics: subdirectory of a run directory holding what the capture layer wrote — JSONL files, sidechains, and export metadata.

### run-turns

- type: `str`
- default: `turns`
- required: true
- code: groom/groom/turns.py::RUN_TURNS
- semantics: subdirectory of a run directory holding each visit's rendered prompt and parsed output — `prompt.md`, `output.json`, `context_after.json`.

### session-map

- type: `str`
- default: `sessions.jsonl`
- required: true
- code: groom/groom/turns.py::SESSION_MAP
- semantics: filename of a run's per-turn session map, one JSON object per line, carrying `node`, `session_id`, and optional `generation`, `seq`, `workflow`, `backend`, `flow`, `head`, `ts` fields.

### legacy-generation

- type: `int`
- default: `-1`
- required: true
- code: groom/groom/turns.py::LEGACY_GENERATION
- semantics: generation stamped on a record whose row predates the visit key, so a reader can distinguish a reconstructed ordinal from a number the run actually counted. Negative because the engine counts from zero — `0` itself is a real generation.

### legacy-prefix

- type: `str`
- default: `legacy`
- required: true
- code: groom/groom/turns.py::LEGACY_PREFIX
- semantics: first segment of a reconstructed slug like `legacy-00003-node_name`. Non-numeric by design so it cannot collide with a real `NNN-NNNNN-node` slug.

## Archive roots

### transcripts-root

- sig: `transcripts_root() -> Path`
- abstract: false
- returns: `Path` to the `transcripts/` directory under `store.db_path().parent`, where archived records live beside `groom.db`
- code: groom/groom/turns.py::transcripts_root
- semantics: derived from `groom.store.db_path()` rather than the platform data dir directly, so a test or operator that points `$GROOM_DB` elsewhere moves the bodies with the index instead of writing them into the real archive.

### archives-root

- sig: `archives_root() -> Path`
- abstract: false
- returns: `Path` to the `archives/` directory under `store.db_path().parent`, holding frozen runs that are the sibling of `transcripts_root()`
- code: groom/groom/turns.py::archives_root
- consistency: archive-promotion — a run past its retention window is moved as a whole into this directory by `groom.archive` via a single same-filesystem rename
- verify: persists(subject="archived run directory")
- semantics: both roots are siblings so promotion is atomic and fail-closed, and the harvester — which only ever knows `transcripts_root()` — structurally cannot write into an archived run.

## Discovery

These functions read a run directory to enumerate the turns it holds and identify the source files to copy.

### session-rows

- sig: `_session_rows(run_dir: Path) -> list[dict[str, Any]]`
- abstract: false
- does: read the run's `sessions.jsonl` file, dropping unparseable lines (malformed JSON or missing `session_id` field) without raising
- returns: `list` of dicts with keys `node`, `session_id`, and optional `generation`, `seq`, `workflow`, `backend`, `flow`, `head`, `ts`; `[]` when the file does not exist or is unreadable
- code: groom/groom/turns.py::_session_rows
- consistency: read-error-handling — OSError on read is caught and returns empty list
- verify: absent(subject="exception from read")
- consistency: parse-error-handling — JSON errors are skipped per line without propagating
- verify: absent(subject="exception from JSON parse")

### visits

- sig: `_visits(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int, int, str]]`
- abstract: false
- does: pair each session-map row with the visit key it addresses — generation, seq, and a slug
- does: reconstruct a visit key for rows predating the engine's visit-key stamping, using `generation = -1` and an ordinal that counts distinct `(node, session_id)` pairs
- does: use a reconstructed slug like `legacy-00001-node_name` that cannot collide with a real `NNN-NNNNN-node` slug
- returns: `list` of tuples: `(row dict, generation int, seq int, slug str)`
- returns: the ordinal for reconstructed keys is stable across re-harvests because the session map is append-only and dedupes the pair rather than counting lines
- code: groom/groom/turns.py::_visits

### sources

- sig: `_sources(run_dir: Path, slug: str, session_id: str) -> list[tuple[str, Path]]`
- abstract: false
- does: enumerate the files this visit contributed from both `RUN_TRANSCRIPTS/` (the capture layer's output) and `RUN_TURNS/` (the turn outputs) subdirectories — transcripts, metadata, prompt, output, and sidechains
- returns: `list` of `(record-relative name, file path)` tuples, where the name is how it appears in the archive (`transcript.jsonl`, `prompt.md`, etc.) and the path is its location in the run directory; `[]` when no files are found for this visit
- code: groom/groom/turns.py::_sources

### capture-source

- sig: `_capture_source(run_dir: Path, slug: str, session_id: str) -> str`
- abstract: false
- does: read what capture reported — `store`, `export`, `tee`, or empty when the metadata is absent
- returns: the value of the `source` field from the `.meta.json` sidecar, or `""` when the file is missing, unparseable, or does not contain `source`
- code: groom/groom/turns.py::_capture_source
- semantics: read from the sidecar meta rather than inferred from filenames, because a consumer that guesses will guess wrong about the turn that matters.

## Copying

These functions materialize a record from source files into an archive directory.

### digest-of

- sig: `_digest_of(sources: list[tuple[str, Path]]) -> tuple[str, int]`
- abstract: false
- does: compute a SHA-256 digest over every source file and sum their byte counts
- does: iterate directories recursively to include every member file
- returns: `(hex digest string, byte count int)` tuple
- code: groom/groom/turns.py::_digest_of
- semantics: digests every file, not just the transcript, because a record whose prompt arrives on one tick and whose transcript grows on the next has changed both times — a digest watching only one would skip the other.

### members

- sig: `_members(name: str, path: Path) -> list[tuple[str, Path]]`
- abstract: false
- does: flatten a source into `(record-relative name, file path)` pairs, recursing for directories
- returns: `[]` for sources that are neither file nor directory
- returns: a directory yields all its members recursively as `(name/subpath, file path)` tuples
- code: groom/groom/turns.py::_members

### copy-record

- sig: `_copy_record(sources: list[tuple[str, Path]], target: Path) -> int`
- abstract: false
- does: materialize one record under the target directory, rewriting it from empty rather than merging into what is there
- does: respect the byte limit `MAX_RECORD_BYTES` — stop copying when reached and return what was written
- returns: byte count of files written
- does: not raise on individual file read failures — logs them at debug level and continues
- raises: `OSError` on directory creation or target cleanup can propagate
- code: groom/groom/turns.py::_copy_record
- consistency: record-directory — record directory is rewritten from empty on every harvest, so stale members from previous runs do not persist
- verify: unchanged(subject="record directory", except_fields=["timestamp"])
- semantics: rewriting from empty prevents a record that shrank from leaving the older, longer file beside the newer one pretending to be part of the same turn.

## Harvesting

These functions copy turn records from live run directories into the archive.

### indexed

- sig: `_indexed(run_id: str) -> dict[tuple[Any, Any, str], str]`
- abstract: false
- does: query the index for all archived records of this run and return their digests
- returns: `dict` mapping `(generation, seq, session_id)` to SHA-256 digest
- code: groom/groom/turns.py::_indexed
- persistence: archived-record-digest — archived record digests are read from persistent storage (groom.db) on every harvest
- verify: persists(subject="archived record digest")
- semantics: used to detect whether a record has changed since the last archive pass — if the digest matches, the record is skipped on the harvest tick.

### harvest-run

- sig: `harvest_run(run_dir: Path, run_id: str = "", workflow: str = "") -> int`
- abstract: false
- does: archive every turn record this run directory holds that is not already archived
- does: deduplicate records when the session map names the same session twice (a retry that kept the session) — copied once and counted once
- returns: the number of records copied (newly archived records; unchanged records are skipped and not counted)
- does: not raise on individual record copy failures — logs them at debug level and continues
- raises: `OSError` from `_session_rows` can propagate
- code: groom/groom/turns.py::harvest_run
- persistence: turn-record — turn records from the run directory are archived to persistent storage under `transcripts_root()`
- verify: persists(subject="turn record")
- semantics: returns zero on a run that has not moved since the last tick (the common case), because the digest check comes before any copying.

### known-runs

- sig: `known_runs() -> list[tuple[str, Path, str]]`
- abstract: false
- does: enumerate every run the telemetry store has seen a directory for, excluding scratch and test runs
- returns: `list` of `(run_id str, run_dir Path, workflow str)` tuples
- code: groom/groom/turns.py::known_runs
- semantics: scratch and test run directories are excluded because a suite that runs workflows under `tempfile.mkdtemp` produces real turn records that would fill the archive durably if included.

### harvest

- sig: `harvest() -> int`
- abstract: false
- does: harvest every known run directory that still exists on this host
- does: skip runs whose directories are gone — pruned, or belonging to a container whose records arrive by another path
- returns: total record count copied across all runs
- does: not raise on any per-run failure — logs at debug level and continues
- code: groom/groom/turns.py::harvest
- semantics: a run directory that is gone is not an error here; it is the normal state of most runs after their retention window.

## Backfilling

These functions archive turns whose transcript never reached the run directory but is still in the CLI's own store.

### backfill

- sig: `backfill(dry_run: bool = False) -> list[dict[str, Any]]`
- abstract: false
- does: archive turns whose transcript is still only in the CLI's store, joining on session ids in each known run's session map
- does: for each session, probe the store backends in order and fetch the transcript via export if the store files are absent
- does: reconstruct the backend name if the map predates the `backend` field by asking each backend which sessions it holds
- returns: `list` of record dicts that would be or were archived, one dict per session
- returns: the same records in both dry-run and real mode so `--dry-run` and the real thing report the same thing
- does: not raise on any per-record failure — logs at debug level and continues
- code: groom/groom/turns.py::backfill
- persistence: cli-store-turn-record — turns whose transcript is in the CLI store are archived to persistent storage
- verify: persists(subject="turn record from CLI store")
- semantics: this is what makes sessions already on disk from before capture existed addressable, and it is an exact join rather than a heuristic — the session map says which node and which visit each session belongs to.

## Model resolution

These functions recover concrete model identifiers from CLI session stores and price the turns.

### session-models

- sig: `session_models(session_id: str, backend: str = "") -> list[str]`
- abstract: false
- does: return every model id this session's store names, first seen first
- does: probe multiple store backends and exporters if the backend name is unknown
- returns: `list[str]` of model identifiers, in the order first seen
- returns: models from exported sessions are qualified with provider when available (`provider/model` format)
- code: groom/groom/turns.py::session_models
- consistency: session-model-id — model ids are read from the actual session store, not from a record whose model field is an alias
- verify: persists(subject="model identifier from session store")
- semantics: the span says what the harness was asked for (which for a CLI invoked as `--model sonnet` is an alias), but the session store says what the provider actually ran per message — recovering the concrete model rather than guessing one.

### resolved

- sig: `_resolved(alias: str, candidates: list[str]) -> str`
- abstract: false
- does: find the one model in candidates that the alias names and is in the price card
- returns: the matched model id, or `""` when zero or more than one model matches
- does: match by checking if the alias (lowercased, stripped) is contained in the candidate (lowercased), so a session that ran both opus and sonnet resolves each alias to its own model
- returns: `""` if exactly one model does not match or if the matched model has no price card entry
- code: groom/groom/turns.py::_resolved
- semantics: both conditions are load-bearing — ambiguous sessions are left unpriced because a coin flip between rates is evidence and not.

### resolve-models

- sig: `resolve_models(run: str = "", dry_run: bool = False) -> dict[str, Any]`
- abstract: false
- does: price turns whose recorded model is an alias by reading concrete ids from their session stores
- does: if dry-run, return the records that would be priced without updating the database
- returns: `dict` with keys `considered` (turn count), `sessions_read` (unique sessions), `priced` (turns successfully priced), `est_cost_usd` (total cost), `resolved` (model resolution counts), `unresolved` (unresolved model counts)
- code: groom/groom/turns.py::resolve_models
- persistence: turn-cost-estimate — estimated costs are written to the database when not in dry-run mode
- verify: persists(subject="turn cost estimate")
- semantics: a turn the price card cannot price is not always a missing rate — often the rate is there and the *name* is not. This recovers the concrete id and prices the tokens with it, stamping `priced_model` in the index.

## Reading

These functions retrieve archived records and their contents.

### visit-label

- sig: `visit_label(row: dict[str, Any]) -> str`
- abstract: false
- does: format an index row's visit key for human reading — `3-17` for a real key or `legacy-17` for a reconstructed one
- returns: string like `3-17` or `legacy-17`
- code: groom/groom/turns.py::visit_label
- semantics: a reader has to be able to tell the two apart — `legacy-17` orders the run's turns and nothing more, while a real `3-17` is the seventeenth turn of the third start.

### record-path

- sig: `record_path(row: dict[str, Any]) -> Path`
- abstract: false
- does: resolve an index row's bodies to their actual location — checking the live root first, then the frozen one
- does: handle the rare case of a run archived twice whose second archive minted a derived name like `<run_id>-<token>/` while the index still says `<run_id>/`
- returns: `Path` to the record directory, or the expected path if the record does not exist
- code: groom/groom/turns.py::record_path
- semantics: live is checked first because that is where anything still being written is; frozen is checked next because that is where a run lives once deleted from the live root; the derived-name glob is the last resort for re-runs that were archived twice.

### read-record

- sig: `read_record(row: dict[str, Any]) -> dict[str, Any]`
- abstract: false
- does: load one archived record as data — its index row, file listing, and prompt text; does not load the transcript into memory, instead providing the path for a caller to stream or grep
- returns: `dict` with all index row fields plus `dir` (path to the record directory), `files` (list of relative file paths), and `prompt` (text content or empty string if missing)
- code: groom/groom/turns.py::read_record

