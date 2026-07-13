---
type: format
slug: sidecar-run-checkpoint-data
title: Sidecar run checkpoint data
---
# Sidecar run checkpoint data

Sidecar run checkpoint data is the latest workflow run's `checkpoint.json` object
stored under a workflow container's `/runs` mount. Groom consumes it as
current-node evidence in three host-visible paths: the [sidecar snapshot](concepts/sidecar-snapshot.md)
current-node reader maps its `current_id` field into [sidecar snapshot data](sidecar-snapshot-data.md)
for query and `hello` frames, the live runs-event classifier maps the same field
into `progress` [sidecar websocket frames](sidecar-websocket-frame.md#field-current-node),
and the [workflow discovery scan](concepts/workflow-discovery-scan.md#method-current-run-state)
volume fallback maps it into the
[volume reconstruction workflow-state transition](concepts/workflow-state.md#transition-volume-reconstruction).
The file is current-node evidence only; missing runs, missing files, unreadable
or malformed JSON, and absent `current_id` values all mean no current node is
available from this source.

- file: `/runs/<latest-run-directory>/checkpoint.json`
- code: groom/groom/sidecar.py::_current_node
- code: groom/groom/discovery.py::_current_run_state
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_sidecar_session.py::test_classify_event_runs_write_is_progress
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run

## Contract

- media: JSON object read from the container's mounted runs volume; this format
  has no HTTP or websocket serialization of its own.
- producer: workhorse writes the file for a workflow run; Groom treats the writer
  as an external producer and only reads the file.
- consumer: sidecar snapshot reads this format to produce the snapshot
  `current_node` value, live runs-event classification reads it to produce
  `progress.current_node`, and discovery volume reconstruction reads it to
  produce the first element of its `(current_node, terminal)` tuple.
- reader paths: the in-container sidecar reads from the local runs mount selected
  by its configured runs directory, while discovery reads from the Docker named
  runs volume through Groom's read-only [workspace volume file content
  reader](concepts/workspace-volume-file-content-reader.md).
- path rule: the file is named exactly `checkpoint.json` inside the selected
  latest run directory.
- directory selection: Groom consults only the latest run directory reported by
  the caller's runs-directory selector: the sidecar selects the final path after
  sorting direct child directories of `/runs`, and discovery uses the final entry
  from the [Docker run-directory reader](concepts/docker-run-directory-reader.md).
- scope: only the selected latest run directory can contribute current-node
  evidence; older run directories, files directly under `/runs`, and
  non-directory entries are ignored by this format's documented Groom readers.
- root shape: the readable content must parse to a JSON object for Groom's
  documented readers to treat it as checkpoint data.
- local file rule: the sidecar reader first requires the selected
  `checkpoint.json` path to be a file, then reads the entire file text and parses
  it as JSON.
- Docker volume file rule: the discovery fallback asks the volume reader for the
  selected `<latest>/checkpoint.json` text; a failed `cat` is represented as no
  file text for this format consumer, while a path-safety rejection follows the
  discovery scan's helper-failure contract.
- member naming: the current-node member is the exact, case-sensitive JSON key
  `current_id`; alternate spellings such as `currentId`, `current-id`, or `node`
  are ignored by Groom's documented readers.
- required keys: no object key is required for the file to be accepted as
  parseable checkpoint data; an object without `current_id` is treated as no
  current-node evidence.
- ignored keys: fields other than `current_id` may be present and are preserved
  on disk but ignored by Groom's documented readers for this format.
- read result: a present `current_id` value is returned unchanged by the sidecar
  current-node reader and returned unchanged as the discovery current-node tuple
  element by the volume fallback reader; only an absent key is normalized to
  `""` at this format boundary.
- empty-state rule: absent `/runs`, no selected run directory, absent
  `checkpoint.json`, unreadable local file content, failed Docker volume reads,
  empty file content in the discovery fallback, malformed JSON, and absent
  `current_id` all produce `""` as Groom's current-node value for that read path.
- error handling: sidecar current-node reads absorb `OSError` and JSON decode
  errors; discovery volume reconstruction absorbs JSON decode errors for this
  file and treats volume file-read failure as no text for this file, but lets
  Docker volume listing and path-safety helper failures follow the discovery scan
  contract. Parseable non-object JSON is outside the accepted source shape and can
  escape as the reader's ordinary key-lookup failure rather than being
  normalized.
- state effect: this format can update a workflow container's current node but
  does not by itself mark a workflow running, blocked, idle, or finished; those
  lifecycle decisions come from sidecar snapshot, live progress-frame handling,
  discovery, terminal metadata, and gate evidence consumers.
- persistence: Groom never writes, edits, deletes, repairs, or creates this file;
  it derives transient state evidence and leaves the runs volume unchanged.

## Fields

### field-current-id

- type: `Any`
- default: `""`
- required: false
- meaning: workhorse graph-node id that represents the latest checkpointed node
  for the selected run.
- wire key: `current_id`
- accepted producer values: any JSON value may appear, but Groom's documented
  callers expect the useful value to be a non-empty string node id.
- emitted value: present values are returned unchanged by the current Groom
  readers, including falsey present values; an absent value is normalized to
  `""`.
- lookup rule: readers perform an exact object-member lookup for `current_id`
  after parsing the root value; they do not coerce alternate key names, inspect
  nested objects, or derive the node id from sibling metadata.
- state effect: a truthy emitted value replaces the workflow container's current
  node in snapshot, progress-frame, and volume-reconstruction consumers without
  changing the workflow lifecycle state by itself.
- empty-state sources: missing field, unreadable checkpoint, malformed
  checkpoint, missing selected run directory, or missing checkpoint file all
  produce the same unavailable `""` result.
- non-contract fields: this field does not carry terminal state, exit code, gate
  paths, repository identity, timestamps, or run-directory id for Groom; those
  values come from other formats or discovery metadata.
