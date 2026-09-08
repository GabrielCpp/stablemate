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
- verify: json_path(path="$.source", matches="^(store|export|tee)$")
- semantics: identifies whether the persisted capture came from a backend store, public export, or redacted stream
- verify: json_path(path="$.source", equals="store")
- code: `workhorse/workhorse/runner/transcript.py::capture`

### max_bytes
- type: integer
- default: `33554432`
- verify: json_path(path="$.max_bytes", equals=33554432)
- required: false
- verify: json_path(path="$.bind_without_max_bytes", equals=true)
- semantics: applies the configured byte ceiling independently to each turn's capture
- verify: json_path(path="$.truncated", equals=true)
- semantics: truncated captures append a JSON marker with the bytes written
- verify: json_path(path="$.truncated_marker.bytes", equals=32)
- code: `workhorse/workhorse/runner/transcript.py::bind`

## Methods

### bind
- sig: `bind(run_dir: Path, *, enabled: bool = True, max_bytes: int = DEFAULT_MAX_BYTES) -> None`
- does: enables capture for a run directory
- verify: created(subject="pending transcript tee")
- does: clamps the byte ceiling at zero or above
- verify: json_path(path="$.truncated", equals=true)
- returns: `None`
- code: `workhorse/workhorse/runner/transcript.py::bind`

### tee_begin
- sig: `tee_begin(node_id: str) -> Tee | None`
- does: opens a visit-keyed pending stream tee when capture is enabled and no store has yet been proven
- verify: created(subject="visit-keyed pending transcript tee")
- returns: a live `Tee`, or `None` when there is no valid visit or capture is disabled
- verify: json_path(path="$.result", matches="^(Tee|None)$")
- code: `workhorse/workhorse/runner/transcript.py::tee_begin`

### capture
- sig: `capture(backend: str, node_id: str, session_id: str, tee: Tee | None = None) -> Path | None`
- does: records metadata and copies the backend store when available
- verify: created(subject="store-backed transcript capture")
- does: otherwise stores a public export, then promotes the pending redacted tee
- verify: created(subject="export-backed or tee-backed transcript capture")
- does: discards the poorer tee after a richer store or export succeeds
- verify: removed(subject="pending tee after richer transcript capture")
- returns: the capture stem, or `None` when no capture can be safely filed
- code: `workhorse/workhorse/runner/transcript.py::capture`

### store_files
- sig: `store_files(backend: str, session_id: str) -> list[Path]`
- does: resolves known backend session files
- verify: count(subject="files resolved for a known backend session", equals=1)
- does: converts resolver errors to an empty result
- verify: count(subject="files returned after a resolver error", equals=0)
- returns: matching files or an empty list
- verify: count(subject="files returned for an unknown backend session", equals=0)
- code: `workhorse/workhorse/runner/transcript.py::store_files`

### probe_stores
- sig: `probe_stores(session_id: str) -> tuple[str, list[Path]]`
- does: checks registered stores until one contains the opaque session id
- verify: json_path(path="$.backend", equals="claude")
- returns: backend and files, or `("", [])`
- verify: count(subject="files returned for an unknown session", equals=0)
- code: `workhorse/workhorse/runner/transcript.py::probe_stores`

### export_session
- sig: `export_session(backend: str, session_id: str) -> bytes | None`
- does: invokes the registered public exporter and suppresses exporter OS failures
- verify: exit_status(code=0)
- returns: exported bytes or `None`
- verify: json_path(path="$", matches="^\\{.*\\}$")
- code: `workhorse/workhorse/runner/transcript.py::export_session`

### unbind
- sig: `unbind() -> None`
- does: disables capture
- verify: json_path(path="$.bound", equals=false)
- does: clears the active run settings so no transcript directory resolves
- verify: json_path(path="$.transcripts_dir", absent=true)
- returns: `None`
- verify: json_path(path="$.result", absent=true)
- code: `workhorse/workhorse/runner/transcript.py::unbind`

### bound
- sig: `bound() -> bool`
- does: checks whether capture is enabled with a bound run directory
- verify: json_path(path="$.bound", equals=true)
- returns: the active capture state
- verify: json_path(path="$.result", equals=true)
- code: `workhorse/workhorse/runner/transcript.py::bound`

### transcripts_dir
- sig: `transcripts_dir() -> Path | None`
- does: resolves the configured run's transcript directory
- verify: json_path(path="$.result", matches="^.+/transcripts$")
- returns: `<run_dir>/transcripts`, or `None` when no run directory is bound
- verify: json_path(path="$.result", absent=true)
- code: `workhorse/workhorse/runner/transcript.py::transcripts_dir`

### probe_exporters
- sig: `probe_exporters(session_id: str) -> tuple[str, bytes | None]`
- does: tries registered public exporters until one returns a complete export
- verify: json_path(path="$.backend", equals="opencode")
- returns: backend and bytes, or `("", None)` when no exporter recognizes the session
- verify: json_path(path="$.bytes", matches="^\\{.*\\}$")
- code: `workhorse/workhorse/runner/transcript.py::probe_exporters`

### Tee.write
- sig: `Tee.write(line: str) -> None`
- does: writes the supplied stream line while the tee is open and has remaining byte budget
- verify: created(subject="tee stream transcript")
- does: when the line crosses the byte ceiling, writes the available fragment and a JSON truncation marker
- verify: json_path(path="$.truncated", equals=true)
- does: ignores writes after the tee is closed or after truncation
- verify: unchanged(subject="tee transcript after ignored write")
- returns: `None`
- verify: json_path(path="$.result", equals="None")
- code: `workhorse/workhorse/runner/transcript.py::Tee.write`

### Tee.__init__
- sig: `Tee(path: Path, max_bytes: int) -> Tee`
- does: creates or replaces the destination file as a UTF-8 text transcript
- verify: created(subject="tee destination file")
- returns: an open tee with zero bytes written and no truncation state
- verify: json_path(path="$.truncated", equals=false)
- code: `workhorse/workhorse/runner/transcript.py::Tee.__init__`

### Tee.path
- sig: `Tee.path -> Path`
- returns: the destination path supplied when the tee was created
- verify: json_path(path="$.path", matches=".+")
- code: `workhorse/workhorse/runner/transcript.py::Tee.path`

### Tee.truncated
- sig: `Tee.truncated -> bool`
- returns: `true` after the byte ceiling is reached, otherwise `false`
- verify: json_path(path="$.truncated", equals=true)
- code: `workhorse/workhorse/runner/transcript.py::Tee.truncated`

### Tee.close
- sig: `Tee.close() -> None`
- does: closes the live tee handle so later writes leave the transcript unchanged
- verify: unchanged(subject="tee transcript after close")
- does: tolerates close errors without raising them
- verify: json_path(path="$.close_exception", absent=true)
- returns: `None`
- verify: json_path(path="$.result", equals="None")
- code: `workhorse/workhorse/runner/transcript.py::Tee.close`
