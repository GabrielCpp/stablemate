---
type: concept
slug: transcript-capture
title: Agent transcript capture
---
# Agent transcript capture

Transcript capture preserves the richest available evidence for each agent visit under the run
directory. It prefers a local CLI store, then a public exporter, then the redacted live stream tee;
capture failure is deliberately best-effort and never fails the turn.

- code: `workhorse/workhorse/runner/transcript.py::capture`
- code: `workhorse/workhorse/runner/transcript.py::tee_begin`
- code: `workhorse/workhorse/runner/transcript.py::bind`
- code: `workhorse/workhorse/runner/transcript.py::export_session`
- tests: `workhorse/tests/test_transcript.py::test_the_store_is_preferred_and_the_tee_it_beats_is_dropped`, `workhorse/tests/test_transcript.py::test_a_backend_with_no_store_is_captured_from_the_tee`, `workhorse/tests/test_transcript.py::test_the_next_turn_promotes_a_provisional_tee_after_the_session_settles`, `workhorse/tests/test_transcript.py::test_the_tee_stops_at_the_cap_and_says_so`
- detail: [run artifacts](../run-artifacts.md)

## Fields

### source
- type: `store | export | tee`
- required: true
- semantics: identifies whether the persisted capture came from a backend store, public export, or redacted stream
- code: `workhorse/workhorse/runner/transcript.py::capture`

### max_bytes
- type: integer
- default: `33554432`
- required: false
- semantics: applies the configured byte ceiling independently to each turn's capture
- verify: json_path(path="$.bytes", equals=32)
- semantics: truncated captures append a JSON marker with the bytes written
- verify: json_path(path="$.truncated", equals=true)
- code: `workhorse/workhorse/runner/transcript.py::bind`

## Methods

### bind
- sig: `bind(run_dir: Path, *, enabled: bool = True, max_bytes: int = DEFAULT_MAX_BYTES) -> None`
- does: enables capture for a run directory and clamps the byte ceiling at zero or above
- returns: `None`
- code: `workhorse/workhorse/runner/transcript.py::bind`

### tee_begin
- sig: `tee_begin(node_id: str) -> Tee | None`
- does: opens a visit-keyed pending stream tee when capture is enabled and no store has yet been proven
- returns: a live `Tee`, or `None` when there is no valid visit or capture is disabled
- code: `workhorse/workhorse/runner/transcript.py::tee_begin`

### capture
- sig: `capture(backend: str, node_id: str, session_id: str, tee: Tee | None = None) -> Path | None`
- does: records metadata and copies the backend store when available
- does: otherwise stores a public export, then promotes the pending redacted tee
- does: discards the poorer tee after a richer store or export succeeds
- returns: the capture stem, or `None` when no capture can be safely filed
- code: `workhorse/workhorse/runner/transcript.py::capture`

### store_files
- sig: `store_files(backend: str, session_id: str) -> list[Path]`
- does: resolves known backend session files and converts resolver errors to an empty result
- returns: matching files or an empty list
- code: `workhorse/workhorse/runner/transcript.py::store_files`

### probe_stores
- sig: `probe_stores(session_id: str) -> tuple[str, list[Path]]`
- does: checks registered stores until one contains the opaque session id
- returns: backend and files, or `("", [])`
- code: `workhorse/workhorse/runner/transcript.py::probe_stores`

### export_session
- sig: `export_session(backend: str, session_id: str) -> bytes | None`
- does: invokes the registered public exporter and suppresses exporter OS failures
- returns: exported bytes or `None`
- code: `workhorse/workhorse/runner/transcript.py::export_session`

### unbind
- sig: `unbind() -> None`
- does: disables capture and clears the active run settings
- returns: `None`
- code: `workhorse/workhorse/runner/transcript.py::unbind`

### bound
- sig: `bound() -> bool`
- does: checks whether capture is enabled with a bound run directory
- returns: the active capture state
- code: `workhorse/workhorse/runner/transcript.py::bound`

### transcripts_dir
- sig: `transcripts_dir() -> Path | None`
- does: resolves the configured run's transcript directory
- returns: `<run_dir>/transcripts`, or `None` when no run directory is bound
- code: `workhorse/workhorse/runner/transcript.py::transcripts_dir`

### probe_exporters
- sig: `probe_exporters(session_id: str) -> tuple[str, bytes | None]`
- does: tries registered public exporters until one returns a complete export
- returns: backend and bytes, or `("", None)` when no exporter recognizes the session
- code: `workhorse/workhorse/runner/transcript.py::probe_exporters`

### Tee.write
- sig: `Tee.write(line: str) -> None`
- does: writes stream lines until the byte ceiling and appends a truncation marker at the boundary
- returns: `None`
- code: `workhorse/workhorse/runner/transcript.py::Tee.write`

### Tee.close
- sig: `Tee.close() -> None`
- does: closes the live tee handle and tolerates close errors
- returns: `None`
- code: `workhorse/workhorse/runner/transcript.py::Tee.close`
