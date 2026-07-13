---
type: concept
slug: sidecar-recursive-watch-installer
title: Sidecar recursive watch installer
---
# Sidecar recursive watch installer

Sidecar recursive watch installer is the delegated filesystem-watch setup used by the [sidecar connected session](sidecar-connected-session.md) and the [residual sidecar push and query fallback](../flows/residual-sidecar-push-and-query-fallback.md). For one root directory it recursively subscribes an existing inotify handle to every directory not pruned by the [sidecar skip directory names](groom-sidecar-module.md#field-skip-dir-names), using the [sidecar watch flags](groom-sidecar-module.md#field-watch-flags), and records each returned watch descriptor in the caller-owned descriptor-to-path map so later filesystem events can be resolved to absolute parent paths.

- code: groom/groom/sidecar.py::_add_watches

## Contract

- sig: `_add_watches(inotify: INotify, root: Path, wd_to_path: dict[int, str]) -> None`
- input: `inotify` is an already-open inotify handle that accepts directory watch registrations and remains owned by the caller.
- input: `root` is the directory tree to subscribe, including the root directory itself when it exists; missing files and non-directory paths are treated as empty watch trees.
- input: `wd_to_path` is the caller-owned watch-descriptor map updated in place with integer watch descriptors as keys and observed directory path strings as values; existing entries are preserved unless a newly returned descriptor reuses the same integer key.
- output: returns `None`; all useful result data is the in-place extension of `wd_to_path`.
- effects: recursively inspects directory names beneath `root`, calls the inotify handle once for each watchable non-pruned directory including `root`, and mutates `wd_to_path` for successful watch registrations only.
- non-effects: does not create directories, read file contents, classify events, send websocket frames, send residual HTTP pushes, allocate an inotify handle, close the handle, or remove existing watch descriptors from `wd_to_path`.
- root rule: when `root` is not a directory, the installer returns immediately and leaves `wd_to_path` unchanged.
- prune rule: child directory names equal to `.git`, `node_modules`, `__pycache__`, or `.venv` are removed from traversal at every visited level; the matching directory and all descendants inside it are never watched.
- watch mask: each subscribed directory receives the [sidecar watch flags](groom-sidecar-module.md#field-watch-flags) for file modification, close-after-write, creation, and move-into events.
- registration rule: the map entry is recorded only after the inotify watch call succeeds; failed directories do not receive placeholder entries.
- error handling: an `OSError` while adding a watch for one directory skips that directory's map entry and continues with the remaining traversal; directory-scanning errors ignored by the underlying walk produce no watch attempt for that subtree and are not surfaced by this layer.
- ordering: watch attempts follow the underlying recursive directory-walk order; the map is not sorted, cleared, or de-duplicated by this layer.
- lifecycle: callers invoke this installer at session startup for the configured workspace and runs mounts and again when an already-watched directory reports a created or moved-in child directory.

## Algorithm

1. Return immediately when the requested root is not a directory.
2. Recursively walk the root directory tree starting at the root itself.
3. At each visited directory, prune child names listed in [field-skip-dir-names](groom-sidecar-module.md#field-skip-dir-names) from further descent.
4. Attempt to add one inotify watch for the visited directory using [field-watch-flags](groom-sidecar-module.md#field-watch-flags).
5. If the watch registration raises `OSError`, skip only that directory's map entry and continue walking any remaining reachable directories.
6. Store each successful watch descriptor in `wd_to_path` with the visited directory path string as its value.

## Methods

### method-_add_watches

- sig: `_add_watches(inotify: INotify, root: Path, wd_to_path: dict[int, str]) -> None`
- abstract: false
- raises: no intentional exception for missing roots, default directory-scanning errors ignored by the underlying walk, or per-directory watch-registration `OSError`; root path checks and unexpected runtime failures are not otherwise normalized by this layer.
- code: groom/groom/sidecar.py::_add_watches
- input: `inotify` is an open inotify handle; `root` is a path-like root to inspect; `wd_to_path` is the mutable descriptor-to-path dictionary owned by the caller.
- output: `None`, with successful watch registrations represented by new or overwritten `wd_to_path` entries.
- effects: installs recursive directory watches below the root, excluding [field-skip-dir-names](groom-sidecar-module.md#field-skip-dir-names), with [field-watch-flags](groom-sidecar-module.md#field-watch-flags), and records descriptor-to-path mappings for later event classification.
- calls: standard-library directory traversal and third-party inotify registration only; it does not call another groom service symbol.
- algorithm:
  1. Reject absent or non-directory roots as empty inputs.
  2. Walk every reachable directory under the root.
  3. Remove skipped child names before the walk descends further.
  4. Register the current directory with the sidecar watch mask.
  5. Continue after per-directory `OSError` without adding a descriptor entry for that directory.
  6. Record each successful descriptor-to-directory mapping in the caller's map.
