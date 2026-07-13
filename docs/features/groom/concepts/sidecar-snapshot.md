---
type: concept
slug: sidecar-snapshot
title: Sidecar snapshot
---
# Sidecar snapshot

Sidecar snapshot is the sidecar's local read of the workflow container state,
returned as [sidecar snapshot data](../sidecar-snapshot-data.md) for
[`groom-sidecar --query`](../groom-sidecar.md#groom-sidecar-root) and embedded in
the `hello` [sidecar websocket frame](../sidecar-websocket-frame.md). It reads the
current node from [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md),
the terminal marker from [sidecar run metadata](../sidecar-run-metadata.md), and
open gates from the container's mounted `/workspace` tree by sweeping for
awaiting gate context files; it does not open network connections, install
inotify watches, mutate files, or decide the workflow's state on the host.

- code: groom/groom/sidecar.py::snapshot
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates

## Contract

- input: no call arguments; the reader uses the sidecar process environment's
  workspace and runs mount paths, which default to `/workspace` and `/runs` when
  `GROOM_WORKSPACE_DIR` and `GROOM_RUNS_DIR` are unset.
- output: one [sidecar snapshot data](../sidecar-snapshot-data.md) object with
  `current_node`, `terminal`, and `gates` keys present on every successful call.
- effects: performs local file reads only; emits no HTTP request, websocket frame,
  stdout text, inotify watch, process exit, or filesystem write.
- current node: reads [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md)
  from the latest available run directory and maps a present `current_id` value
  unchanged to snapshot `current_node`; missing run directories, missing
  checkpoints, unreadable checkpoints, malformed JSON, and absent `current_id`
  values all become `""`.
- source shape: the run checkpoint and run metadata readers expect parsed JSON
  objects; JSON arrays, strings, numbers, booleans, or null are outside the
  accepted source shape and can escape as ordinary attribute errors from those
  helpers rather than being normalized.
- ordering: reads current node first, terminal state second, and open gates third;
  each value reflects the filesystem state observed by its own read path rather
  than a transactionally consistent snapshot across both mounts.
- gate source: open gates are detected by scanning the workspace mount and
  retaining only files whose initial status text is `AWAITING_OPERATOR`; files in
  `.git`, `node_modules`, `__pycache__`, and `.venv` directories are excluded
  from the sweep.
- gate entry shape: each retained gate contributes one `gates` item with a
  workspace-relative `file_path` when possible and a `question` extracted from the
  full file text.
- freshness: intended for reconnect/one-shot reconciliation; the returned object
  is current at read time and carries no subscription, cursor, timestamp, or
  durable identity.
- error handling: read and JSON errors inside the delegated readers are absorbed
  by those readers and represented as empty fields; the aggregator itself adds no
  additional exception handling.

## Algorithm

1. Read the current workflow graph node from the latest run checkpoint.
2. Read the terminal workflow state from the latest run metadata.
3. Sweep the workspace for every currently awaiting operator gate.
4. Return a dictionary containing those three results under the fixed keys
   `current_node`, `terminal`, and `gates`.

## Deeper Calls

- `_latest_run_dir() -> Path | None` selects the lexicographically last
  directory in the configured runs mount, or `None` when the mount is absent or
  empty.
- `_current_node() -> str` returns the latest run checkpoint's raw `current_id`
  value, normally a graph-node string, or `""` when no checkpoint can supply one.
- `_terminal() -> str` returns the latest run's truthy terminal-state value, or
  `""` when the run has not finished or no readable [sidecar run
  metadata](../sidecar-run-metadata.md) exists.
- `scan_gates() -> list[dict]` returns every currently awaiting gate as snapshot
  gate entries.

## Methods

### method-snapshot

- sig: `snapshot() -> dict`
- abstract: false
- raises: none intentionally raised by the aggregator itself; exceptions from
  delegated readers that are outside their normalization contracts can propagate.
- code: groom/groom/sidecar.py::snapshot
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- input: no call arguments; uses the sidecar's configured runs mount and
  workspace mount.
- output: one [sidecar snapshot data](../sidecar-snapshot-data.md) dictionary with
  `current_node`, `terminal`, and `gates` keys in every successful return value.
- effects: performs the delegated local file reads needed to collect the three
  fields; performs no network I/O, websocket send, stdout write, inotify
  subscription, process exit, or filesystem mutation.
- calls: [method-_current_node](#method-_current_node),
  [method-_terminal](#method-_terminal), and
  [method-scan_gates](#method-scan_gates), in that order.
- algorithm:
  1. Read the latest current graph-node id with [method-_current_node](#method-_current_node).
  2. Read the latest terminal-state marker with [method-_terminal](#method-_terminal).
  3. Sweep for awaiting gate entries with [method-scan_gates](#method-scan_gates).
  4. Return the three values under exactly the `current_node`, `terminal`, and
     `gates` keys.

### method-_latest_run_dir

- sig: `_latest_run_dir() -> Path | None`
- abstract: false
- raises: none for a missing runs mount; that case returns `None`. Directory
  iteration errors from an existing runs mount are not absorbed.
- code: groom/groom/sidecar.py::_latest_run_dir
- verify: groom/tests/test_sidecar.py::test_terminal_reads_latest_run_json
- input: no call arguments; uses the sidecar's configured runs mount path.
- output: the latest run directory path, or `None` when the configured runs mount
  is not a directory or contains no child directories.
- effects: reads the runs mount directory entries and tests child paths for
  directory status; performs no workspace scan, file content read, network I/O,
  inotify subscription, stdout write, process exit, or filesystem mutation.
- selection rule: only direct children of the runs mount that are directories are
  eligible; files and non-directory entries are ignored.
- ordering rule: eligible directories are sorted by path order, and the final
  sorted entry is treated as the latest run.
- empty rule: when no eligible run directories remain after filtering, the result
  is `None`.
- algorithm:
  1. Return `None` when the configured runs mount is not a directory.
  2. List direct children of the runs mount and retain only child directories.
  3. Sort the retained directory paths.
  4. Return the final sorted directory when at least one directory remains.
  5. Return `None` when the retained directory list is empty.

### method-_current_node

- sig: `_current_node() -> str`
- abstract: false
- raises: none for missing runs, missing checkpoints, unreadable checkpoints, or
  malformed checkpoint JSON; those cases return `""`. A parseable non-object
  JSON value is outside the accepted checkpoint shape and can raise instead of
  normalizing.
- code: groom/groom/sidecar.py::_current_node
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- input: no call arguments; uses `method-_latest_run_dir` to find the latest run
  directory from the sidecar's configured runs mount.
- output: current workhorse graph-node id from the latest [sidecar run checkpoint
  data](../sidecar-run-checkpoint-data.md) `current_id` value, normally a string;
  a present value is returned unchanged, while no usable value returns `""`.
- effects: reads at most one `checkpoint.json` file from the latest run
  directory; performs no workspace scan, network I/O, inotify subscription,
  stdout write, process exit, or filesystem mutation.
- algorithm:
  1. Resolve the latest run directory with `method-_latest_run_dir`.
  2. Return `""` when no latest run directory exists.
  3. Select `checkpoint.json` inside that latest run directory.
  4. Return `""` when the checkpoint file is absent.
  5. Read and parse the checkpoint as JSON.
  6. Return the parsed JSON object's `current_id` value unchanged when the key is
     present, including falsey or non-string JSON values.
  7. Return `""` when the checkpoint cannot be read, cannot be parsed, or lacks
     a `current_id` key.

### method-_terminal

- sig: `_terminal() -> str`
- abstract: false
- raises: none for missing runs, missing run metadata, unreadable metadata, or
  malformed metadata JSON; those cases return `""`. A parseable non-object JSON
  value is outside the accepted metadata shape and can raise instead of
  normalizing.
- code: groom/groom/sidecar.py::_terminal
- verify: groom/tests/test_sidecar.py::test_terminal_reads_latest_run_json
- input: no call arguments; uses `method-_latest_run_dir` to find the latest run
  directory from the sidecar's configured runs mount.
- output: truthy terminal-state value from the latest run's [sidecar run
  metadata](../sidecar-run-metadata.md) `terminal` field, returned unchanged, or
  `""` when no usable terminal marker is available.
- effects: reads at most one `run.json` file from the latest run directory;
  performs no workspace scan, network I/O, inotify subscription, stdout write,
  process exit, or filesystem mutation.
- algorithm:
  1. Resolve the latest run directory with `method-_latest_run_dir`.
  2. Return `""` when no latest run directory exists.
  3. Select `run.json` inside that latest run directory.
  4. Return `""` when the metadata file is absent.
  5. Read and parse the metadata as JSON.
  6. Return the parsed JSON object's `terminal` value unchanged when it is truthy.
  7. Return `""` when the metadata cannot be read, cannot be parsed, has no
     `terminal` field, or has a falsey `terminal` value.

### method-scan_gates

- sig: `scan_gates() -> list[dict]`
- abstract: false
- raises: none for a missing workspace mount or per-file read failures; those
  cases return an empty list or skip the unreadable file.
- code: groom/groom/sidecar.py::scan_gates
- verify: groom/tests/test_sidecar.py::test_scan_gates_finds_awaiting_and_skips_git_and_non_awaiting
- input: no call arguments; uses the sidecar's configured workspace mount as the
  scan root.
- output: a list of [sidecar snapshot data](../sidecar-snapshot-data.md) gate
  entries, one per currently awaiting gate file encountered by the workspace
  sweep.
- effects: recursively reads the workspace directory tree, reads a small prefix
  of each candidate file to classify its status, and reads the full text only for
  awaiting files so the returned question can be extracted; performs no network
  I/O, inotify subscription, stdout write, process exit, or filesystem mutation.
- skip dirs: `.git`, `node_modules`, `__pycache__`, and `.venv` directories are
  pruned at every visited level before files are inspected.
- status rule: the first 512 characters of each file are decoded with replacement
  for invalid characters and retained only when [operator gate context file
  status parser](../operator-gate-context-file.md#method-status-of) returns
  exactly `AWAITING_OPERATOR`.
- file path rule: the retained `file_path` is workspace-relative when the file can
  be relativized to the workspace mount; otherwise it falls back to the observed
  path string.
- question rule: the retained `question` is produced by [operator gate context
  file](../operator-gate-context-file.md#method-extract-question) extraction
  from the full gate-file content after the status check succeeds.
- error handling: an `OSError` while opening, prefix-reading, or full-reading a
  file skips that file and does not abort the scan.
- ordering: returned gate entries follow the underlying workspace traversal order;
  no additional sorting, de-duplication, or stable ordering is applied.
- algorithm:
  1. Start with an empty gate-entry list.
  2. Return the empty list immediately when the configured workspace mount is not
     a directory.
  3. Walk the workspace tree recursively while pruning skipped directory names
     from each directory's children.
  4. For each file, read only the initial status prefix; skip the file when that
     read fails.
  5. Classify the status prefix with [operator gate context file status
     parser](../operator-gate-context-file.md#method-status-of); skip the file
     unless the result is exactly `AWAITING_OPERATOR`.
  6. Read the full file text; skip the file when that read fails.
  7. Extract the operator-facing question with [operator gate context
     file](../operator-gate-context-file.md#method-extract-question) rules, build
     a gate entry from the relative file path and extracted question, then append
     it to the result list.
  8. Return the accumulated gate-entry list.
