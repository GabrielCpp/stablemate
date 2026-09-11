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
- tests: `workhorse/tests/test_transcript.py::test_the_store_is_preferred_and_the_tee_it_beats_is_dropped`, `workhorse/tests/test_transcript.py::test_a_backend_with_no_store_is_captured_from_the_tee`, `workhorse/tests/test_transcript.py::test_a_backend_export_is_preferred_over_the_stream_tee`, `workhorse/tests/test_transcript.py::test_a_failed_backend_export_preserves_the_stream_tee`, `workhorse/tests/test_transcript.py::test_the_next_turn_promotes_a_provisional_tee_after_the_session_settles`, `workhorse/tests/test_transcript.py::test_opencode_export_uses_the_public_full_session_command`, `workhorse/tests/test_transcript.py::test_opencode_export_rereads_a_partial_successful_snapshot`, `workhorse/tests/test_transcript.py::test_the_tee_stops_at_the_cap_and_says_so`, `workhorse/tests/test_transcript.py::test_the_store_capture_is_also_capped`, `workhorse/tests/test_transcript.py::test_capture_is_off_when_the_run_asked_for_it_to_be`, `workhorse/tests/test_transcript.py::test_a_turn_outside_a_visit_is_not_filed_under_somebody_elses`, `workhorse/tests/test_transcript.py::test_each_lap_of_a_looping_node_is_captured_separately`, `workhorse/tests/test_transcript.py::test_capture_never_faults_the_turn`, `workhorse/tests/test_transcript.py::test_a_session_with_no_recorded_backend_is_found_by_probing_the_stores`
- detail: [run artifacts](../run-artifacts.md)
- detail: [agent visit key](visit-key.md)

## Fields

### source
- type: `store | export | tee`
- required: true
- verify: json_path(path="$.source", matches="^(store|export|tee)$")
- semantics: identifies whether the persisted capture came from a backend store, public export, or redacted stream
- verify: json_path(path="$.source", equals="store")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [transcript-capture](transcript-capture.md)

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

## Constants

Module-level names that the run record cites directly and that the binding step defaults to.
Each is fixed at import time — `bind` does not let an operator override the directory names,
only the byte ceiling.

### field: TRANSCRIPTS_DIR
- type: string
- default: `"transcripts"`
- required: true
- semantics: the run-dir-relative directory under which every captured turn lands
- verify: json_path(path="$.capture_path", matches="^.+/transcripts/.+$")
- semantics: named for what it holds (transcripts, not captures) so the same shell-visible path does not have to be re-invented for every backend the registry grows
- verify: json_path(path="$.capture_path_basename", equals="transcripts")
- code: `workhorse/workhorse/runner/transcript.py::TRANSCRIPTS_DIR`

### field: PENDING_DIR
- type: string
- default: `".pending"`
- required: true
- semantics: the transcripts-dir-relative subdirectory that holds an in-flight tee — a tee whose
  visit key is known but whose session id is not — at the moment the stream callback writes its
  first line. The leading dot keeps it out of a casual `ls` while a turn is still running.
  `capture` renames its single file out of `.pending/` once the CLI names the session id.
- code: `workhorse/workhorse/runner/transcript.py::PENDING_DIR`
- verify: json_path(path="$.pending_path_basename", equals=".pending")

### field: DEFAULT_MAX_BYTES
- type: integer
- default: `33554432`
- verify: json_path(path="$.default_max_bytes", equals=33554432)
- required: true
- semantics: per-turn byte ceiling applied to every capture when `bind` is called without an
  override (32 MiB — sized for the pathological turn so a normal one never notices it)
- verify: json_path(path="$.bind_default_max_bytes", equals=33554432)
- semantics: a turn that hits the cap is truncated with a JSON marker rather than dropped, so the
  evidence that does fit is still usable
- verify: json_path(path="$.truncated", equals=true)
- code: `workhorse/workhorse/runner/transcript.py::DEFAULT_MAX_BYTES`

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

## Backends

The `_STORES` and `_EXPORTERS` dicts (in `workhorse/workhorse/runner/transcript.py`) are the
registry the rest of the module walks by backend name. Each entry is keyed by the same string
`sessions.jsonl` records on the line that names the session — the one `store_files(backend,
session_id)` and `export_session(backend, session_id)` look up by, and the one
`probe_stores(session_id)` / `probe_exporters(session_id)` walk declaration-order to find when the
caller does not know. A backend absent from both registries is not a defect; it means **the tee
is the source** for every turn it ran.

- **claude** — store. `_claude_store(session_id)` reads
  `~/.claude/projects/*/<session_id>.jsonl` and, when present, the sibling
  `<session_id>/` directory of subagent sidechains and tool results. Project slugs are globbed
  rather than derived from cwd: a tree change between visits would otherwise invalidate a
  derivation in a way a glob is not, and the CLI's own slug encoding is the thing the resolver
  has to match.
  `workhorse/workhorse/runner/transcript.py::_claude_store`

- **codex** — store. `_codex_store(session_id)` reads
  `~/.codex/sessions/<y>/<m>/<d>/rollout-*-<session_id>.jsonl`, looked up by the date-bucketed
  pattern the CLI itself uses. No sibling tree: codex's session model is a single rollout file
  per session.
  `workhorse/workhorse/runner/transcript.py::_codex_store`

- **opencode** — exporter. `_opencode_export(session_id)` shells out to
  `opencode export <session_id>`, retries once on a partial valid-JSON response (a completed
  `opencode run` can briefly expose a partial export while its session is being finalized; the
  retry is the readiness check, because there is no separate session-settled signal to wait on),
  and returns the captured JSON bytes. The corresponding store resolver is **deliberately not
  registered** — OpenCode's internal database is not a stable filesystem contract, so the export
  is the only contract the module treats as authoritative.
  `workhorse/workhorse/runner/transcript.py::_opencode_export`

