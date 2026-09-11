---
type: format
slug: transcript-capture-meta
title: Transcript capture meta
---
# Transcript capture meta

The per-turn `<stem>.meta.json` written by [`capture`](concepts/transcript-capture.md#capture) through
[`_write_meta`](concepts/transcript-capture.md#capture) for every transcript it lands. It is the
sidecar that names which of the three capture tiers (the backend store, the backend's public
export, or the redacted stream tee) the matching `<stem>.jsonl`, `<stem>.d/`, `<stem>.export.json`
or `<stem>.tee.jsonl` came from, how many bytes that tier wrote, whether the per-turn byte
ceiling was hit, and the visit key plus head observation that join the capture to the rest of the
run record. A consumer reading a capture without it cannot tell the store capture (rich, with
attachments and sidechains) from the tee (redacted by construction) — the meta is the contract
that fixes that. The deferred-export path may re-write this file on a later turn: when a tee
sourced from a backend that has an exporter gets promoted to a real export, this file's `source`
group (`source`, `bytes`, `truncated`) is replaced with the export's, while the per-visit fields
(`backend`, `session_id`, `node`, `generation`, `seq`, `ts`, `head`) are preserved.

- file: `<run_dir>/transcripts/<gen>-<seq>-<node>__<session-id>.meta.json`
- code: `workhorse/workhorse/runner/transcript.py::_write_meta`
- detail: [agent transcript capture](concepts/transcript-capture.md)
- tests: `workhorse/tests/test_transcript.py::test_the_store_is_preferred_and_the_tee_it_beats_is_dropped`, `workhorse/tests/test_transcript.py::test_a_backend_with_no_store_is_captured_from_the_tee`, `workhorse/tests/test_transcript.py::test_a_backend_export_is_preferred_over_the_stream_tee`, `workhorse/tests/test_transcript.py::test_a_failed_backend_export_preserves_the_stream_tee`, `workhorse/tests/test_transcript.py::test_the_next_turn_promotes_a_provisional_tee_after_the_session_settles`, `workhorse/tests/test_transcript.py::test_the_tee_stops_at_the_cap_and_says_so`, `workhorse/tests/test_transcript.py::test_the_store_capture_is_also_capped`

## Fields

### backend

- type: string
- default: absent
- required: true
- semantics: the CLI backend name whose vocabulary the matching `session_id` is in
- semantics: the same key the `_STORES` and `_EXPORTERS` registries in
  [agent transcript capture](concepts/transcript-capture.md#backends) are addressed by
- verify: json_path(path="$.backend", matches=".+")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### session_id

- type: string
- default: absent
- required: true
- semantics: the backend's opaque session id, copied verbatim from the backend's session record
- verify: json_path(path="$.session_id", matches=".+")
- semantics: identical to the `session_id` line in [`sessions.jsonl`](run-artifacts.md#sessionsjsonl) for the
  same visit, so the meta and the manifest agree on which session the capture is from
- verify: unchanged(subject="session_id across meta and sessions.jsonl for the same visit")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### node

- type: string
- default: absent
- required: true
- semantics: the engine node id this turn belonged to
- verify: json_path(path="$.node", matches=".+")
- semantics: identical to the `<node>` segment of the
  [visit key](concepts/visit-key.md) naming the capture's stem, so a reader can recover the visit
  from the meta alone
- verify: unchanged(subject="node across meta and visit key for the same capture")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### generation

- type: integer
- default: absent
- required: true
- semantics: the visit key's `generation` — how many times this run directory had been started
  when the turn was recorded (the same `resume_generation` `run.json` reads)
- verify: json_path(path="$.generation", matches="^[0-9]+$")
- semantics: the value is captured from the active visit key at record time rather than
  re-derived from `run.json`, so the meta's `generation` is the count at the time of capture and
  survives an in-place rewrite of the same meta unchanged
- verify: unchanged(subject="the meta on a deferred-export rewrite", except_fields=["source", "bytes", "truncated"])
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### seq

- type: integer
- default: absent
- required: true
- semantics: the visit key's `seq` — the run's monotone agent-node visit counter (`turn_seq`)
- verify: json_path(path="$.seq", matches="^[0-9]+$")
- semantics: together with `generation` and `node`, this is the visit key naming the capture's stem
- verify: unchanged(subject="seq across meta and visit key for the same capture")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### ts

- type: integer
- default: absent
- required: true
- semantics: positive epoch seconds when the capture was written, taken at the moment the meta
  dict is assembled so a meta's `ts` is the capture's clock, not the underlying turn's
- verify: json_path(path="$.ts", matches="^[1-9][0-9]*$")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### head

- type: string
- default: absent — recorded only when `workhorse.gitstate.current_head()` returned a non-empty
  value at capture time
- required: false
- semantics: the commit the run's tree was on when the turn was recorded, observed through
  [`workhorse.gitstate`](concepts/run-agent.md) rather than read from the backend
- verify: json_path(path="$.head", matches="^[0-9a-f]+$")
- semantics: identical to the `head` line in [`sessions.jsonl`](run-artifacts.md#sessionsjsonl) for
  the same visit, so the meta and the manifest agree on which commit the capture is from
- verify: unchanged(subject="head across meta and sessions.jsonl for the same visit")
- semantics: absent means *not observed* — a non-repository working tree, a missing `git`, or a hung
  filesystem — never *clean*
- verify: absent(subject="the head field on a meta captured without a bound repo")
- semantics: a consumer that needs the run's HEAD must look at [`sessions.jsonl`](run-artifacts.md#sessionsjsonl),
  not infer absence from the meta
- verify: unchanged(subject="head across meta and sessions.jsonl for the same visit")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### source

- type: `store | export | tee`
- default: absent
- required: true
- semantics: the capture tier the matching file came from — `store` for a copy out of the
  backend's session store (richest, retains attachments and sidechains), `export` for a backend's
  public full-session export, `tee` for the redacted stream tee (fallback)
- verify: json_path(path="$.source", matches="^(store|export|tee)$")
- semantics: mutated in place by the deferred-export path — a `tee` sourced from a backend
  that has an exporter is replaced with `export` once the same session is re-exported
  successfully, and `bytes`/`truncated` are replaced with the export's
- verify: json_path(path="$.source", equals="export")
- semantics: the per-visit fields (`backend`, `session_id`, `node`, `generation`, `seq`, `ts`,
  `head`) are preserved on a deferred-export rewrite
- verify: unchanged(subject="the meta on a deferred-export rewrite", except_fields=["source", "bytes", "truncated"])
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### bytes

- type: integer
- default: absent
- required: true
- semantics: bytes written into the matching capture file — the cumulative store copy for
  `source=store`, the body length for `source=export`, the renamed tee's on-disk size for
  `source=tee`. Independent of the `max_bytes` cap on the surrounding turn: a capture that hit
  the cap records the bytes it managed to write before the truncation marker
- verify: json_path(path="$.bytes", matches="^[0-9]+$")
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)

### truncated

- type: boolean
- default: absent
- required: true
- semantics: `true` iff the matching capture file was closed by the per-turn byte ceiling rather than by exhausting its stream
- verify: json_path(path="$.truncated", equals=true)
- semantics: `false` when the capture ran to the end of its source without hitting the cap
- verify: json_path(path="$.truncated", equals=false)
- semantics: a `true` meta is paired with a final `{"truncated": true, "bytes": N}` line in the
  capture file so the file announces where it stopped instead of looking like a turn that died
- verify: omits(subject="the matching capture file when meta.truncated is false", matches='"truncated":true')
- semantics: for `source=store` or `source=export`, the meta's truncation flag is the OR across
  each store file in a directory tree or across the single export body — any one of them hitting
  the cap marks the meta truncated
- verify: json_path(path="$.truncated", equals=true)
- semantics: for `source=tee`, the meta's truncation flag is copied verbatim from the tee's own
  truncation state — when the tee's `_truncated` flag is set the meta records `true`, and `false`
  otherwise
- verify: json_path(path="$.truncated", equals=true)
- verify: json_path(path="$.truncated", equals=false)
- code: `workhorse/workhorse/runner/transcript.py::capture`
- detail: [agent transcript capture](concepts/transcript-capture.md)