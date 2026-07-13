---
type: format
slug: sidecar-run-metadata
title: Sidecar run metadata
---
# Sidecar run metadata

Sidecar run metadata is the latest workflow run's `run.json` object stored under
a workflow container's `/runs` mount. Groom consumes it in two places: the
[sidecar snapshot](concepts/sidecar-snapshot.md) terminal reader maps its
`terminal` field into [sidecar snapshot data](sidecar-snapshot-data.md), and the
[workflow discovery scan](concepts/workflow-discovery-scan.md#method-current-run-state)
volume fallback maps the same field into the [volume reconstruction workflow-state
transition](concepts/workflow-state.md#transition-volume-reconstruction). A
truthy terminal value is terminal evidence for the [workflow state](concepts/workflow-state.md);
missing runs, missing files, unreadable or malformed JSON, absent `terminal`, and
falsey `terminal` values all mean no terminal marker is available.

- file: `/runs/<latest-run-directory>/run.json`
- code: groom/groom/sidecar.py::_terminal
- code: groom/groom/discovery.py::_current_run_state
- verify: groom/tests/test_sidecar.py::test_terminal_reads_latest_run_json
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes

## Contract

- media: JSON object read from the container's mounted runs volume; this format
  has no HTTP or websocket serialization of its own.
- top-level shape: object members are optional from Groom's perspective; the
  documented Groom readers inspect only the `terminal` member and ignore the
  object's size, member order, and any extra members.
- producer: workhorse writes the file for a workflow run; Groom treats the writer
  as an external producer and only reads the file.
- consumer: sidecar snapshot reads this format to produce the snapshot `terminal`
  value, while discovery volume reconstruction reads it to produce the second
  element of its `(current_node, terminal)` tuple.
- path rule: the file is named exactly `run.json` inside the selected latest run
  directory.
- directory selection: Groom consults only the latest run directory reported by
  the caller's runs-directory selector: the sidecar selects the final path after
  sorting direct child directories of `/runs`, and discovery uses the final entry
  from the [Docker run-directory reader](concepts/docker-run-directory-reader.md).
- ordering assumption: latest means lexicographically last after the reader has
  collected only direct child directories; the run-directory naming scheme is
  expected to make that order match run recency.
- scope: only the selected latest run directory can contribute terminal evidence;
  older run directories, files directly under `/runs`, and non-directory entries
  are ignored by this format's documented Groom readers.
- parse rule: the file content must parse as a JSON object before a terminal
  marker can be observed; parseable arrays, strings, numbers, booleans, or null
  are outside this format's accepted shape for Groom's current readers and can
  escape as ordinary reader exceptions rather than normalized empty terminal
  evidence.
- required keys: no key is required for the file to be accepted as parseable
  metadata; an object without `terminal` is treated as non-terminal evidence.
- ignored keys: fields other than `terminal` may be present and are preserved on
  disk but ignored by Groom's documented readers for this format.
- read result: a usable, truthy `terminal` value is returned unchanged by the
  sidecar terminal reader and returned as the discovery terminal tuple element by
  the volume fallback reader.
- empty-state rule: absent `/runs`, no selected run directory, absent `run.json`,
  unreadable file content, empty file content in the discovery fallback,
  malformed JSON, absent `terminal`, and falsey `terminal` values all produce
  `""` as Groom's terminal value for that read path.
- error handling: sidecar terminal reads absorb missing files, `OSError`, and
  JSON decode errors; discovery volume reconstruction absorbs absent/empty file
  content and JSON decode errors for this file but lets Docker volume listing,
  file-read helper failures, and parseable non-object JSON follow the discovery
  scan contract.
- state precedence: when this format yields a truthy terminal value, host-side
  resolution marks the workflow finished before applying gate evidence, so stale
  or simultaneous awaiting gate files do not become actionable for that resolver
  pass.
- persistence: Groom never writes, edits, deletes, repairs, or creates this file;
  it derives transient state evidence and leaves the runs volume unchanged.

## Fields

### field-terminal

- type: `Any`
- default: `""`
- required: false
- meaning: workflow terminal-state marker for the latest run.
- accepted producer values: any JSON value may appear, but Groom treats only
  truthy values as terminal evidence and treats absent or falsey values as no
  terminal marker.
- emitted value: truthy values are returned unchanged by the current Groom
  readers, including non-string JSON values; absent or falsey values are
  normalized to `""`.
- state effect: a truthy emitted value marks snapshot and volume-reconstruction
  consumers as terminal, which leads host-side handlers to set the workflow state
  to `finished` and skip or clear actionable gates according to their own
  transition contracts.
- empty-state sources: missing field, JSON `null`, `false`, `0`, `""`, empty
  collections, unreadable metadata, malformed metadata, missing selected run
  directory, or missing metadata file all produce the same non-terminal `""`
  result.
- accepted-shape boundary: falsey values are normalized only after the containing
  file has parsed to an object; a parseable non-object JSON document is outside
  this field contract and is not treated as an empty `terminal` field.
- non-contract fields: this field does not carry the current graph node, exit
  code, gate paths, repository identity, timestamps, or run-directory id for
  Groom; those values come from other formats or discovery metadata.
