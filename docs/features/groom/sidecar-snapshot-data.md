---
type: format
slug: sidecar-snapshot-data
title: Sidecar snapshot data
---
# Sidecar snapshot data

Sidecar snapshot data is the JSON-compatible object returned by the
[sidecar snapshot](concepts/sidecar-snapshot.md) reader. It is printed by
[`groom-sidecar --query`](groom-sidecar.md#groom-sidecar-root), embedded in a
`hello` [sidecar websocket frame](sidecar-websocket-frame.md), and consumed by
the [run sidecar websocket session](http/groom.md#run-sidecar-websocket-session)
and Docker discovery paths to rebuild a [workflow container](concepts/workflow-container.md)'s
current node, finished/running/blocked state, and open [gate info](concepts/gate-info.md)
records from local run metadata and [operator gate context files](operator-gate-context-file.md).

- code: groom/groom/sidecar.py::snapshot
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_running_when_no_gates
- verify: groom/tests/test_app.py::test_apply_hello_finished_when_terminal
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively
- file: not an on-disk artifact; this is an in-memory object serialized as JSON
  for sidecar query stdout and websocket `hello` frames.

## Contract

- media: JSON object when serialized; all top-level keys are present in the
  producer's return value.
- top-level keys: the first-party producer emits exactly `current_node`,
  `terminal`, and `gates`; query and websocket delivery wrap or serialize that
  object but do not add snapshot-local keys.
- producer: the sidecar snapshot reader builds the object from the sidecar
  process's configured `/runs` and `/workspace` mounts using local reads only.
- delivery: query mode writes exactly this object as compact JSON to stdout;
  websocket connect embeds it under `hello.snapshot` without adding or removing
  fields inside the snapshot object.
- consumers: host-side discovery and sidecar websocket hello handling treat this
  object as authoritative for the connected or queried container's current node,
  terminal state, and open gates at the time it was read.
- empty-state rule: missing, unreadable, or malformed source files, including the
  latest [sidecar run checkpoint data](sidecar-run-checkpoint-data.md), become
  empty strings or an empty gate list rather than a partial object.
- terminal rule: a truthy `terminal` value means the workflow has reached a
  finished terminal state and host consumers do not retain snapshot gates as
  answerable work for that container.
- non-terminal state rule: when `terminal` is falsey, any retained gate entry
  makes the host workflow blocked; no retained gates makes a websocket hello mark
  the workflow running, while discovery leaves a previously running/idle state
  unchanged unless gates are present.
- identity rule: this format carries no container id, repository name, branch,
  workflow type, run id, timestamp, exit code, sequence number, or cursor; those
  values come from sidecar identity, Docker inspect, residual push payloads, or
  the existing workflow record.
- consistency rule: each field reflects its own read path; the format is not a
  transactionally locked view across the runs and workspace mounts.
- serialization rule: query mode and websocket hello delivery use ordinary JSON
  serialization with no custom encoder; values inside this object must therefore
  be JSON-serializable as produced by the local file readers and gate scanner.
- validation boundary: the producer normalizes read failures into empty values,
  but host consumers still tolerate absent, falsey, or empty `snapshot` objects
  from decoded frames.

## Fields

### field-current-node

- type: any JSON value; normally `str`
- default: `""`
- required: true
- meaning: latest workhorse graph-node id read from the newest [sidecar run
  checkpoint data](sidecar-run-checkpoint-data.md) `current_id` value; empty
  means no current node is available or the checkpoint could not be read.
- producer rule: the sidecar selects the lexicographically latest directory under
  its configured runs mount, reads `checkpoint.json`, parses JSON, and returns
  the parsed object's `current_id` value unchanged when the key is present; the
  normal workhorse value is a string node id.
- empty rule: missing runs mount, no run directories, missing checkpoint,
  unreadable checkpoint, malformed JSON, or absent `current_id` all produce `""`.
- consumer rule: discovery and websocket hello replace the workflow container's
  current node only when this value is truthy; a falsey value preserves the
  existing current node.

### field-terminal

- type: JSON value; normally `str`, falsey values normalized to `""`
- default: `""`
- required: true
- meaning: latest run terminal-state label read from the newest run metadata;
  empty means the workflow is not known to be terminal.
- producer rule: the sidecar selects the lexicographically latest directory under
  its configured runs mount, reads `run.json`, parses JSON, and returns a truthy
  `terminal` value as supplied by the metadata object.
- empty rule: missing runs mount, no run directories, missing run metadata,
  unreadable metadata, malformed JSON, absent `terminal`, or falsey `terminal`
  all produce `""`.
- consumer rule: discovery and websocket hello treat any truthy value as terminal
  and mark the workflow container finished; this terminal decision wins over any
  gate entries present in the same snapshot.

### field-gates

- type: `list[object]`
- default: `[]`
- required: true
- meaning: every workspace file whose gate status is currently awaiting operator
  input, represented as one gate entry per file.
- item shape: each entry is an object with `file_path` and `question` keys.
- item validation: the first-party producer emits only objects in this list;
  host consumers expect object-like entries and do not retain malformed entries
  whose `file_path` is absent or empty.
- producer rule: sidecar snapshots include only files whose status prefix is
  classified as `AWAITING_OPERATOR`; skipped workspace directories, unreadable
  files, and non-awaiting statuses do not produce entries.
- source scan: the sidecar recursively walks its configured workspace mount,
  prunes `.git`, `node_modules`, `__pycache__`, and `.venv` directories at every
  level, reads only the initial status prefix before deciding whether a full file
  read is needed, and extracts questions only from retained files.
- symlink rule: directory symlinks are not followed by the workspace walk; file
  symlinks encountered as files are read through the normal file-read path.
- ordering: producer traversal order; callers must not rely on sorted gate
  entries from the sidecar snapshot itself.
- consumer rule: when `terminal` is falsey, host consumers iterate this list,
  ignore entries with an empty normalized `file_path`, and create or replace one
  gate info record per retained path.
- replacement rule: websocket hello clears the workflow's existing gate map before
  applying these entries; discovery applies entries to a newly inspected workflow
  record rather than merging into an existing registry record.

### field-gates-file-path

- type: `str`
- default: none for retained entries
- required: true for each gate entry
- meaning: workspace-relative path to the awaiting gate file when it can be
  relativized to the workspace mount, otherwise the observed absolute/path text.
- producer rule: the sidecar scan attempts workspace-relative paths first and
  falls back to the observed path string only when relativization fails.
- consumer rule: websocket hello string-normalizes this value and drops the entry
  when the result is empty; discovery query handling drops falsey values without
  additional string normalization.
- constraints: the producer does not de-duplicate paths or validate that the path
  is safe for later answering; answer-time code owns gate-file mutation safety.

### field-gates-question

- type: `str`
- default: `""`
- required: true for each gate entry
- meaning: operator-facing question text extracted from the awaiting gate file.
- producer rule: extracted from the full gate-file content after the file has
  already passed the awaiting-status prefix check.
- consumer rule: websocket hello stores `str(question)` on the gate info record;
  discovery query handling stores the supplied value directly.
- constraints: the format carries the extracted prompt only, not the full gate
  context file, answer options, status line, or answer destination.
