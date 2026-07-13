---
type: concept
slug: workflow-discovery-scan
title: Workflow discovery scan
---
# Workflow discovery scan

Workflow discovery scan is the importable Groom discovery module used by the [workflow registry](workflow-registry.md) reconciliation path to recover [workflow container](workflow-container.md) records that existed before the Groom server started or before an operator requested a refresh. The module exposes the top-level [scan](#method-scan), [present-container-id lookup](#method-present-container-ids), [workhorse-container classifier](#method-classify-workhorse-container), and Docker-inspect-to-workflow conversion folded into the [initial workflow-state transition](workflow-state.md#transition-discovery-initial) and [Docker inspect workflow-container consumer](../docker-inspect-container-object.md#consumer-workflow-container-conversion). It also owns the private helpers that index mounts, derive workflow type, normalize environment entries, resolve one candidate container, apply sidecar query snapshots through the [sidecar query snapshot transition](workflow-state.md#transition-sidecar-query-or-discovery-snapshot), and reconstruct fallback state through the [volume reconstruction transition](workflow-state.md#transition-volume-reconstruction).

As a one-shot Docker fleet reader, the module enumerates Docker containers through the [Docker all-container listing reader](docker-all-container-listing-reader.md), resolves each candidate through the [per-container discovery resolver](#method-resolve-container), classifies inspected containers through the [workhorse-container classifier](#method-classify-workhorse-container), uses the [mount destination index](#method-index-mounts-by-destination) to recognize workhorse mount contracts and read volume metadata from the [Docker inspect container object](../docker-inspect-container-object.md), creates baseline records through the [initial workflow-state transition](workflow-state.md#transition-discovery-initial), names the workflow kind from the `/workflow` mount or compose service label, applies running-container [sidecar snapshot data](../sidecar-snapshot-data.md), reconstructs fallback state from [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md), [sidecar run metadata](../sidecar-run-metadata.md), and [operator gate context files](../operator-gate-context-file.md), returns only workhorse-backed containers in Docker's reported order, and exposes the live-container-id lookup that reconciliation uses to decide whether stale registry entries may be pruned safely.

For stopped or legacy containers, the scan's current-run-state method selects the latest run through the [Docker run-directory reader](docker-run-directory-reader.md) before reading checkpoint and terminal metadata from that run directory.

- code: groom/groom/discovery.py
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- verify: groom/tests/test_discovery.py::test_scan_skips_containers_that_are_not_workhorse_containers
- refs: [Docker all-container listing reader](docker-all-container-listing-reader.md), [Docker inspection reader](docker-inspection-reader.md), [host-to-container sidecar query](host-to-container-sidecar-query.md), [Docker run-directory reader](docker-run-directory-reader.md), [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md), [workspace volume file-content reader](workspace-volume-file-content-reader.md), [Docker container-id listing reader](docker-container-id-listing-reader.md)

## Contract

- role: importable discovery module for startup and manual-refresh reconciliation; it reads Docker and mounted workflow volumes but does not own registry persistence, server routes, websocket queues, dashboard rendering, or gate-answer writes.
- public members: `scan`, `present_container_ids`, `is_workhorse_container`, and `container_from_inspect` are the module's supported call surface.
- folded members: `container_from_inspect` is grounded by the [initial workflow-state transition](workflow-state.md#transition-discovery-initial) and [Docker inspect workflow-container consumer](../docker-inspect-container-object.md#consumer-workflow-container-conversion); `_apply_snapshot` is grounded by the [sidecar query snapshot transition](workflow-state.md#transition-sidecar-query-or-discovery-snapshot); `_resolve_via_volumes` is grounded by the [volume reconstruction transition](workflow-state.md#transition-volume-reconstruction).
- import behavior: defining the module imports Docker I/O, gate parsing, and workflow model collaborators and initializes only literal constants; it does not list Docker containers, inspect containers, query sidecars, read volumes, mutate workflow records, or start background work at import time.
- collaborator boundary: calls stay inside Groom's Docker I/O, gate parsing, and model layers, plus Python standard-library JSON, POSIX path, and worker-pool facilities; third-party packages and external services are reached only through the first-party Docker I/O helpers documented separately.
- purpose: produce one best-effort snapshot of discoverable workhorse workflow containers for startup and manual refresh reconciliation.
- input: no caller-supplied arguments; the scan reads the current Docker container list from the local Docker CLI environment available to the Groom process.
- output: `list[WorkflowContainer]`, containing one resolved [workflow container](workflow-container.md) per discoverable workhorse container whose per-container resolver returns a record.
- ordering: preserves the `docker ps -a` entry order for every returned workflow container; unresolved and non-workhorse candidates are removed without re-sorting the remaining records.
- concurrency: resolves multiple candidate containers concurrently, capped at eight workers and never exceeding the number of candidate container ids in the current Docker listing.
- empty fleet: returns an empty list when Docker reports no container entries with an `ID` field or the Docker listing helper reports no entries.
- filtering: ignores Docker entries without an `ID` and omits any candidate whose per-container resolver returns `None`, including unrelated containers and failed inspections.
- state source: delegates all per-container state decisions to the [per-container discovery resolver](#method-resolve-container), which prefers a running container sidecar snapshot and falls back to volume reconstruction when needed.
- persistence: does not mutate the [workflow registry](workflow-registry.md), write files, broadcast dashboard fragments, start or stop containers, answer gates, or persist any scan result outside the returned list.

## Fields

### field-scan-worker-cap

- type: `int`
- default: `8`
- required: true
- code: groom/groom/discovery.py::_SCAN_WORKERS
- meaning: upper bound on concurrent per-container resolver calls during one scan.
- constraints: the actual worker count is the smaller of this cap and the number of candidate Docker container ids, so an empty candidate list creates no worker pool and a fleet smaller than eight creates no unused resolver workers.

### field-workflow-mount-destination

- type: `str`
- default: `/workflow`
- required: true
- code: groom/groom/discovery.py::WORKFLOW_MOUNT
- meaning: Docker inspect mount destination that identifies the mounted workhorse workflow definition and supplies the primary workflow-type source path.
- constraints: the destination must be present in the mount destination index for a candidate to be workhorse-backed; its source basename may still be generic, in which case workflow-type derivation falls back to the compose service label.

### field-runs-mount-destination

- type: `str`
- default: `/runs`
- required: true
- code: groom/groom/discovery.py::RUNS_MOUNT
- meaning: Docker inspect mount destination for the named volume containing run directories, checkpoint data, and terminal run metadata.
- constraints: the destination must be present in the mount destination index for a candidate to be workhorse-backed; its mount `Name` becomes the workflow container's runs-volume field for fallback reconstruction.

### field-workspace-mount-destination

- type: `str`
- default: `/workspace`
- required: true
- code: groom/groom/discovery.py::WORKSPACE_MOUNT
- meaning: Docker inspect mount destination for the named workspace volume containing repository files and operator gate context files.
- constraints: the destination must be present in the mount destination index for a candidate to be workhorse-backed; its mount `Name` becomes the workflow container's workspace-volume field for fallback gate discovery.

## Effects

- Reads: Docker's all-container listing through the [Docker all-container listing reader](docker-all-container-listing-reader.md), which returns parseable Docker `ps` rows from `groom/groom/docker_io.py::docker_ps_all`.
- Derives: a candidate id list by keeping each listing entry's non-empty `ID` value.
- Short-circuits: returns `[]` without creating a worker pool when the candidate id list is empty.
- Calls: [method-resolve-container](#method-resolve-container) once for each candidate id.
- Emits: a list containing every non-null [workflow container](workflow-container.md) emitted by the resolver, in the same relative order as the candidate id list.
- Omits: `None` resolver results, so callers receive no placeholder for unrelated containers, failed inspection, or unresolvable workflow state.

## Failure behavior

- Docker listing failure: represented by the Docker listing helper as an empty listing, so the scan emits `[]` rather than raising a scan-specific error.
- Per-container failure: exceptions raised while resolving an individual candidate are not converted by `scan`; they propagate to the caller because the scan only filters explicit `None` results.
- Worker-pool failure: exceptions from the concurrent mapping layer are not converted and surface to the caller.

## Boundaries

- Does not decide whether a discovered container is workhorse-backed; the resolver owns that classification.
- Does not parse Docker inspect payloads, sidecar snapshots, run artifacts, or gate files; those belong to deeper discovery helpers.
- Does not prune stale registry entries; the caller compares the scan result with the live container-id set during registry reconciliation.

## Algorithms

### algorithm-scan-order

- step: Read every Docker container listing row through the all-container listing reader.
- step: Build the candidate id sequence from rows whose `ID` field is present and non-empty, preserving the listing order.
- step: Return an empty list immediately when the candidate sequence is empty.
- step: Create a bounded resolver pool sized to the smaller of the candidate count and the scan worker cap.
- step: Resolve each candidate id through [method-resolve-container](#method-resolve-container), preserving candidate order in the resolved sequence.
- step: Drop explicit `None` resolver results from the resolved sequence.
- step: Return the remaining workflow containers in the same relative order as their Docker listing candidates.

### algorithm-per-container-resolution

- step: Inspect the candidate container id through the Docker inspection reader.
- step: Return `None` when the inspect payload is absent or fails the workhorse mount-contract classifier.
- step: Convert eligible inspect metadata into a baseline workflow container through the [initial workflow-state transition](workflow-state.md#transition-discovery-initial).
- step: If the inspected container is running, request a sidecar query snapshot using the normalized baseline container id.
- step: If the sidecar query returns a dictionary snapshot, apply [sidecar snapshot data](../sidecar-snapshot-data.md) through the [sidecar query snapshot transition](workflow-state.md#transition-sidecar-query-or-discovery-snapshot) and skip volume reconstruction.
- step: If the container is stopped or the sidecar query does not return a dictionary snapshot, reconstruct state from run and workspace volumes through the [volume reconstruction transition](workflow-state.md#transition-volume-reconstruction).
- step: Return the resolved workflow container to the top-level scan.

## Methods

### method-scan

- sig: `scan() -> list[WorkflowContainer]`
- abstract: false
- raises: propagates Docker listing, Docker inspect, sidecar query, volume listing, volume file-read, and worker-pool exceptions that the underlying discovery helpers do not convert.
- code: groom/groom/discovery.py::scan
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- verify: groom/tests/test_discovery.py::test_scan_skips_containers_that_are_not_workhorse_containers

Runs one bounded discovery pass and returns the ordered workflow-container records that can be resolved from the local Docker fleet. The method is the module's public snapshot entry point: it reads all Docker rows, keeps rows with non-empty ids, resolves each candidate through [method-resolve-container](#method-resolve-container), and returns only non-null workflow records.

#### Contract

- input: no caller-supplied arguments; all evidence comes from the local Docker container listing and the per-container resolver's Docker, sidecar, run-volume, and workspace-volume reads.
- output: `list[WorkflowContainer]`, preserving Docker listing order after non-workhorse and unresolved candidates are removed.
- worker limit: uses at most eight concurrent candidate resolvers and no more workers than there are candidate ids.
- empty-listing behavior: returns `[]` without creating a worker pool when no Docker listing entry supplies a non-empty `ID`.
- side effects: does not mutate registry state, prune stale containers, broadcast dashboard updates, answer gates, start containers, stop containers, or write files.

#### Effects

- Calls: the [Docker all-container listing reader](docker-all-container-listing-reader.md) once for the complete candidate fleet.
- Derives: a candidate id sequence from listing rows whose `ID` field is present and non-empty.
- Calls: [method-resolve-container](#method-resolve-container) once per candidate id through a bounded ordered worker pool.
- Filters: drops explicit `None` resolver results.
- Returns: the remaining workflow-container records in their original candidate order.

### method-container-from-inspect

- sig: `container_from_inspect(inspect: dict[str, Any]) -> WorkflowContainer`
- abstract: false
- raises: no domain-specific exception; malformed truthy inspect subtrees or mount rows may propagate ordinary mapping, sequence, or attribute errors from the helpers that read them.
- refs: [initial workflow-state transition](workflow-state.md#transition-discovery-initial)
- refs: [Docker inspect workflow-container consumer](../docker-inspect-container-object.md#consumer-workflow-container-conversion)

Converts one Docker inspect container object into a baseline workflow-container record before sidecar or volume evidence can refine runtime state. The symbol's code grounding lives on the state-transition and format-consumer nodes because those nodes are the authoritative contracts for the conversion semantics.

#### Contract

- input: one [Docker inspect container object](../docker-inspect-container-object.md) or partial inspect-shaped dictionary.
- output: one [workflow container](workflow-container.md) with normalized container id, display name, repository name, repository branch, workflow type, initial state, workspace volume, and runs volume.
- identity mapping: `Id` becomes the first twelve characters of `container_id`; `Name` loses leading slashes and falls back to the truncated id when empty.
- repository mapping: only `REPO_NAME` and `REPO_BRANCH` from the environment map are copied; unrelated environment values and secrets are not copied into the workflow record.
- workflow-type mapping: [method-derive-workflow-type](#method-derive-workflow-type) supplies the workflow kind from the `/workflow` mount source basename or compose service label fallback.
- volume mapping: the `/workspace` and `/runs` mount rows supply `workspace_volume` and `runs_volume` from their `Name` fields, defaulting to empty strings when absent.
- state mapping: truthy `State.Running` produces `WorkflowState.RUNNING`; falsey or absent running state produces `WorkflowState.IDLE` until later discovery evidence changes it.
- side effects: none; the conversion does not inspect additional containers, query sidecars, read volumes, mutate the workflow registry, or write gate files.

### method-resolve-container

- sig: `_resolve_container(container_id: str) -> WorkflowContainer | None`
- abstract: false
- raises: propagates Docker inspect launch or timeout exceptions from the [Docker inspection reader](docker-inspection-reader.md), and propagates fallback volume-read exceptions when a workhorse container cannot be resolved through a sidecar snapshot.
- code: groom/groom/discovery.py::_resolve_container
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- verify: groom/tests/test_discovery.py::test_scan_skips_containers_that_are_not_workhorse_containers

Resolves one Docker candidate id into either one [workflow container](workflow-container.md) or no result for the scan. The method reads one [Docker inspect container object](../docker-inspect-container-object.md), rejects absent metadata and containers that do not carry the workhorse mount contract, creates the baseline workflow record from inspect metadata, then chooses between a running-container [sidecar snapshot data](../sidecar-snapshot-data.md) query and the existing volume-reconstruction fallback. It owns the discovery-time choice between the [initial workflow-state transition](workflow-state.md#transition-discovery-initial), the [sidecar query snapshot transition](workflow-state.md#transition-sidecar-query-or-discovery-snapshot), and the [volume reconstruction transition](workflow-state.md#transition-volume-reconstruction).

#### Contract

- input: `container_id` is the Docker id string supplied by the scan's candidate list; the resolver passes it unchanged to Docker inspect and uses the inspected workflow record's normalized id for sidecar query.
- output: `WorkflowContainer | None`; `None` means the candidate did not yield a workhorse workflow record and must be omitted from the scan result.
- eligibility: a container is workhorse-backed only when its inspect mount list contains destinations `/workflow`, `/runs`, and `/workspace`; unrelated containers and failed inspect lookups return `None`.
- baseline record: eligible inspect metadata is converted to a [workflow container](workflow-container.md) before sidecar or volume evidence is applied, including display name, repository identity, workflow type, initial running-or-idle [workflow state](workflow-state.md), workspace volume, and runs volume.
- running branch: when `State.Running` is truthy, the resolver asks the live container for a sidecar query snapshot and uses that snapshot only when the query returns a dictionary.
- stopped branch: when `State.Running` is falsey, the resolver does not query the sidecar and immediately uses volume reconstruction.
- sidecar precedence: a returned sidecar snapshot is authoritative for current node, terminal marker, and gates for this newly resolved record; the volume fallback is skipped on this branch.
- fallback trigger: missing sidecar snapshot, sidecar query failure represented as `None`, legacy sidecar output, stopped container state, or non-running container state all route to volume reconstruction.
- terminal precedence: terminal evidence from either sidecar snapshot or run-volume metadata marks the workflow `finished` and prevents gate evidence from becoming actionable for that resolver pass.
- gate output: non-terminal gate evidence creates [gate info](gate-info.md) entries keyed by file path on the returned workflow container and marks the workflow `blocked` when at least one gate is retained.
- persistence: returns an in-memory workflow record only; registry replacement, stale pruning, dashboard broadcast, and UI rendering belong to callers.

#### Effects

- Reads: one Docker inspect payload through the [Docker inspection reader](docker-inspection-reader.md).
- Calls: [method-classify-workhorse-container](#method-classify-workhorse-container) to classify the inspect payload as workhorse-backed or unrelated by indexing mount rows by `Destination` and requiring `/workflow`, `/runs`, and `/workspace` before any workflow record is emitted.
- Emits: `None` when Docker inspect is unavailable or the mount contract does not identify a workhorse workflow container.
- Builds: one baseline [workflow container](workflow-container.md) from eligible Docker inspect metadata through the [initial workflow-state transition](workflow-state.md#transition-discovery-initial).
- Extracts: Docker `Config.Env` through [method-extract-environment-map](#method-extract-environment-map), then reads only `REPO_NAME` and `REPO_BRANCH` from that map for the baseline workflow record.
- Derives: workflow type through [method-derive-workflow-type](#method-derive-workflow-type), reading the `/workflow` mount source basename first and the compose service label only when the basename is absent or generic.
- Reads: the inspect `State.Running` value after the baseline record is built to decide whether a live sidecar query is allowed.
- Calls: the [host-to-container sidecar query](host-to-container-sidecar-query.md) only for running containers, using the normalized workflow container id.
- Applies: returned [sidecar snapshot data](../sidecar-snapshot-data.md) to update current node, terminal state, and open gates when the sidecar query succeeds.
- Falls back: to [volume reconstruction](workflow-state.md#transition-volume-reconstruction) when the sidecar query is skipped or unavailable, allowing stopped and legacy containers to recover current node, terminal state, and awaiting gates from mounted volumes.
- Returns: the resolved workflow container with sidecar or fallback state applied when the candidate is eligible.
- Preserves: Docker container lifecycle, mounted volume contents, sidecar process state, workflow registry membership, websocket queues, dashboard DOM, answer files, and gate files.

#### Failure behavior

- Missing inspect: returns `None`; the scan drops the candidate without a placeholder.
- Non-workhorse inspect: returns `None`; the scan treats the candidate as unrelated Docker state.
- Sidecar query failure: represented by the [host-to-container sidecar query](host-to-container-sidecar-query.md) as `None`, causing fallback volume reconstruction rather than a resolver-specific exception.
- Sidecar terminal snapshot: returns a finished workflow and does not retain snapshot gates as answerable work.
- Volume fallback failure: not converted by this method; exceptions from fallback volume readers propagate to the scan caller.

### method-classify-workhorse-container

- sig: `is_workhorse_container(inspect: dict[str, Any]) -> bool`
- abstract: false
- raises: no domain-specific exception; malformed truthy mount rows may propagate the mount-index helper's ordinary attribute error.
- code: groom/groom/discovery.py::is_workhorse_container
- verify: groom/tests/test_discovery.py::test_is_workhorse_container_requires_all_three_mounts
- verify: groom/tests/test_discovery.py::test_is_workhorse_container_ignores_unrelated_containers

Classifies whether one [Docker inspect container object](../docker-inspect-container-object.md) carries the workhorse mount contract required for Groom discovery. The classifier is intentionally metadata-only: it does not inspect process state, sidecar availability, run artifacts, gate files, repository identity, or workflow type.

#### Contract

- input: one Docker inspect container object or partial inspect-shaped dictionary supplied by the per-container resolver.
- required-mounts: the destination-keyed mount lookup must contain all three literal destinations `/workflow`, `/runs`, and `/workspace`.
- output: `true` only when all required destinations are present; `false` for missing, empty, or unrelated mount sets.
- source-of-truth: mount `Destination` values are authoritative for eligibility; mount type, source path, volume name, container name, labels, environment, and running state are not considered.
- persistence: returns one boolean and does not mutate the inspect object, Docker state, registry state, mounted volumes, sidecar state, dashboard state, or gate files.

#### Effects

- Calls: [method-index-mounts-by-destination](#method-index-mounts-by-destination) to normalize the inspect `Mounts` list.
- Reads: only membership of the three canonical mount destinations in that lookup.
- Emits: `false` for non-workhorse containers so [method-resolve-container](#method-resolve-container) can drop them from the discovery scan.
- Preserves: all metadata values in the inspect object and mount rows.

#### Algorithm

- step: Build the destination-keyed mount lookup through [method-index-mounts-by-destination](#method-index-mounts-by-destination), using the inspect object's top-level `Mounts` value and the helper's empty-list and duplicate-destination rules.
- step: Check membership of the literal `/workflow` destination in the lookup.
- step: Check membership of the literal `/runs` destination in the lookup.
- step: Check membership of the literal `/workspace` destination in the lookup.
- step: Return `true` only when all three membership checks are true; return `false` otherwise.

#### Failure behavior

- Missing mount list: returns `false` because the mount index is empty.
- Partial mount contract: returns `false` when any one of `/workflow`, `/runs`, or `/workspace` is absent, even if the other two are present.
- Extra mounts: ignored; a container with the three required destinations remains eligible when additional destinations exist.

### method-index-mounts-by-destination

- sig: `_mounts_by_dest(inspect: dict[str, Any]) -> dict[str, dict[str, Any]]`
- abstract: Build a destination-keyed view of Docker inspect mount rows so discovery can recognize the workhorse mount contract and read the `/workflow`, `/runs`, and `/workspace` records without depending on mount-list order.
- raises: no domain-specific exception; absent or falsey `Mounts` returns an empty mapping, while malformed non-mapping mount entries may propagate their normal attribute error.
- code: groom/groom/discovery.py::_mounts_by_dest
- verify: groom/tests/test_discovery.py::test_is_workhorse_container_requires_all_three_mounts
- verify: groom/tests/test_discovery.py::test_is_workhorse_container_ignores_unrelated_containers
- verify: groom/tests/test_discovery.py::test_container_from_inspect_reads_env_name_and_volumes
- verify: groom/tests/test_discovery.py::test_workflow_type_from_workflow_mount_basename

Produces the normalized mount lookup shared by workhorse-container eligibility, baseline workflow-container creation, workflow-type derivation, and volume-name extraction.

#### Contract

- input: one [Docker inspect container object](../docker-inspect-container-object.md) or partial inspect-shaped dictionary.
- source-field: reads only the top-level `Mounts` value.
- output: `dict[str, dict[str, Any]]` whose keys are each retained mount row's `Destination` value and whose values are the original mount-row dictionaries.
- empty-source: missing `Mounts`, `None`, or any other falsey `Mounts` value produces `{}`.
- order: input order does not matter for callers because they select mounts by destination path.
- duplicates: when more than one mount row has the same `Destination`, the later row in Docker's `Mounts` sequence is the retained value for that destination.
- destinationless-row: a row with no `Destination` key is still retained under the `None` key, but Groom's documented consumers ignore it because they look up only `/workflow`, `/runs`, and `/workspace`.
- persistence: returns an in-memory lookup only; it never mutates the inspect object, Docker state, workflow registry, mounted volumes, or dashboard state.

#### Effects

- Reads: the top-level `Mounts` list from the inspect object.
- Derives: direct destination-to-row lookups for `/workflow`, `/runs`, and `/workspace` consumers.
- Enables: workhorse eligibility checks to require the three canonical destinations regardless of list order.
- Enables: workflow-container conversion to read the `/workspace` and `/runs` mount `Name` values and the `/workflow` mount `Source` value.
- Preserves: all mount-row keys and values in the retained row dictionaries, including Docker fields Groom does not interpret.

#### Failure behavior

- Missing mount list: returns an empty mapping, causing callers to classify the container as non-workhorse or to derive empty volume metadata.
- Partial mount row: absent `Destination`, `Name`, or `Source` fields do not fail this method; destinationless rows are not selected by documented callers, and missing metadata fields fall back in the caller that reads them.
- Malformed mount row: a non-mapping item inside a truthy `Mounts` iterable is outside the accepted inspect-object shape and is not converted by this helper.

### method-derive-workflow-type

- sig: `_workflow_type(inspect: dict[str, Any], mounts: dict[str, dict[str, Any]]) -> str`
- abstract: Derive the workflow kind string stored on a baseline [workflow container](workflow-container.md) from Docker metadata in a way that is independent of container name and repository identity.
- raises: no domain-specific exception; absent mount metadata, absent configuration, absent labels, empty strings, and falsey values produce `""` when no supported source exists, while malformed truthy inspect or mount records may propagate their ordinary attribute error.
- code: groom/groom/discovery.py::_workflow_type
- verify: groom/tests/test_discovery.py::test_workflow_type_from_workflow_mount_basename
- verify: groom/tests/test_discovery.py::test_workflow_type_falls_back_to_compose_service_label

Chooses the workflow type used by the [initial workflow-state transition](workflow-state.md#transition-discovery-initial) and the [workflow container](workflow-container.md#field-workflow-type) field. The method consumes the destination-keyed mount lookup produced by [method-index-mounts-by-destination](#method-index-mounts-by-destination), reads only the `/workflow` mount `Source` and the Docker inspect `Config.Labels` fallback, and returns a display string for workflow kinds such as `coder` or `author` without reading or copying environment variables.

#### Contract

- input-inspect: one [Docker inspect container object](../docker-inspect-container-object.md) or partial inspect-shaped dictionary.
- input-mounts: destination-keyed mount lookup whose `/workflow` entry, when present, may carry a `Source` string.
- primary-source: the basename of the `/workflow` mount `Source` after removing trailing slashes.
- accepted-primary: any non-empty basename other than the literal generic value `workflow` is returned unchanged as the workflow type.
- fallback-source: `Config.Labels["com.docker.compose.service"]` from the inspect object.
- fallback-trigger: fallback is used only when the primary basename is empty or exactly `workflow`.
- missing-fallback: missing `Config`, missing `Labels`, missing compose service label, or an empty label returns `""` when fallback is needed.
- output: `str`; no validation restricts the returned value to a fixed enum because workflow kinds are defined by workhorse workflow directories and compose service names.
- privacy-boundary: environment variables, repository names, branches, gate content, run artifacts, and volume names are not read by this method.
- persistence: returns an in-memory string only; it never mutates the inspect object, mount lookup, Docker state, workflow registry, mounted volumes, sidecar state, dashboard state, or environment variables.

#### Effects

- Reads: the `/workflow` row from the destination-keyed mount lookup.
- Reads: the mount row's `Source` value, defaulting to `""` when the mount row or source key is absent.
- Derives: a candidate workflow type from the final path segment of the source after trailing slashes are ignored.
- Returns: the candidate when it is non-empty and not the generic `workflow` path segment.
- Reads: the Docker inspect `Config.Labels` map only when the candidate is empty or generic.
- Returns: the compose service label value when fallback is needed and present.
- Emits: `""` when neither source provides a non-empty workflow type.
- Preserves: the supplied inspect dictionary and mount lookup exactly as received.

#### Failure behavior

- Missing `/workflow` mount: primary derivation produces an empty candidate and falls back to the compose service label.
- Source ending in `/workflow`: primary derivation is considered generic and falls back to the compose service label.
- Source with trailing slash: trailing slashes are ignored before the basename is selected, so `/host/workflows/coder/` emits `coder`.
- Missing labels: returns `""` when fallback is required and no compose service label is present.
- Non-string source or label values: outside the documented Docker inspect shape for this method and not normalized by the workflow-type derivation layer.

### method-extract-environment-map

- sig: `_env_map(inspect: dict[str, Any]) -> dict[str, str]`
- abstract: Normalize Docker inspect `Config.Env` entries from `KEY=VALUE` strings into a string lookup so discovery can read selected repository identity fields without retaining unrelated environment variables.
- raises: no domain-specific exception; absent or falsey `Config`/`Env` returns an empty mapping, while a truthy non-mapping `Config` or non-string environment entry is outside the accepted Docker inspect shape and may propagate its ordinary attribute/type error.
- code: groom/groom/discovery.py::_env_map
- verify: groom/tests/test_discovery.py::test_container_from_inspect_reads_env_name_and_volumes

Builds the transient environment lookup used by the [initial workflow-state transition](workflow-state.md#transition-discovery-initial) and baseline [workflow container](workflow-container.md) creation. The method treats the [Docker inspect container object](../docker-inspect-container-object.md) as the source of truth, returns only parsed environment key/value pairs, and leaves the caller responsible for choosing which keys are safe to copy onto the workflow record.

#### Contract

- input: one [Docker inspect container object](../docker-inspect-container-object.md) or partial inspect-shaped dictionary.
- source-field: reads only nested `Config.Env`; missing `Config`, missing `Env`, `None`, or any other falsey value produces `{}`.
- accepted-entry: a string containing at least one `=` is parsed as an environment assignment.
- key: the substring before the first `=`; an empty key is retained as `""` if Docker supplied one.
- value: the substring after the first `=`; later `=` characters remain part of the value, and an empty value is retained as `""`.
- output: `dict[str, str]` containing every accepted assignment keyed by environment variable name.
- duplicate-key: when `Config.Env` contains more than one accepted entry with the same key, the later entry in list order is retained.
- ignored-entry: strings without `=` are skipped and do not appear in the returned mapping.
- selection-boundary: the method does not decide which variables become workflow fields; current callers read only `REPO_NAME` and `REPO_BRANCH`.
- privacy-boundary: secrets and unrelated variables may be present in the returned local mapping, but the baseline workflow-container conversion does not copy them into the public workflow record.
- persistence: returns an in-memory mapping only; it never mutates the inspect object, Docker state, workflow registry, mounted volumes, sidecar state, dashboard state, or environment variables.

#### Effects

- Reads: the nested Docker inspect `Config.Env` list.
- Derives: direct key-to-value lookups for environment entries written as `KEY=VALUE`.
- Enables: workflow-container conversion to map `REPO_NAME` to `repo_name` and `REPO_BRANCH` to `repo_branch`, defaulting each missing key to `""` in the caller.
- Omits: malformed environment strings that have no equals sign.
- Preserves: unrelated environment variables, secret values, entry order outside duplicate-key replacement, and the source inspect object.

#### Failure behavior

- Missing configuration: returns an empty mapping, causing repository identity fields to default to empty strings in the caller.
- Empty environment list: returns an empty mapping.
- Entry without equals: silently skips that entry.
- Duplicate variable: keeps the last value encountered for the same key.
- Malformed inspect shape: a truthy non-mapping `Config` value or non-string item inside `Env` is outside the documented input contract and is not converted by this helper.

### method-current-run-state

- sig: `_current_run_state(runs_volume: str) -> tuple[str, str]`
- abstract: false
- raises: propagates Docker volume listing and file-read launch or timeout exceptions from the underlying Docker I/O helpers; JSON parse errors are converted to empty values.
- code: groom/groom/discovery.py::_current_run_state
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes

Reads the latest run directory in a workflow's `/runs` volume and returns the two run-derived state fields needed by volume reconstruction: the current node from [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md) and the terminal marker from run metadata.

#### Contract

- input: `runs_volume` is a Docker named volume string previously copied from the eligible container's `/runs` mount.
- directory-selection: the latest run is the final entry from the sorted run-directory list returned by the [Docker run-directory reader](docker-run-directory-reader.md).
- checkpoint-source: reads [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md) and extracts `current_id` from the parsed JSON object when available.
- terminal-source: reads `<latest>/run.json` and extracts `terminal` from the parsed JSON object when available.
- output: `(current_node, terminal)`, where each element is a string and missing, unreadable, malformed, absent, or falsey data becomes `""` for that element.
- persistence: returns transient state evidence only; it does not mutate Docker volumes, workflow containers, the registry, sidecar sessions, gate files, or dashboard clients.

#### Effects

- Calls: the [Docker run-directory reader](docker-run-directory-reader.md) for the supplied runs volume.
- Selects: the final entry from the reader's sorted directory list as the latest run id.
- Short-circuits: returns `("", "")` when the run-directory list is empty.
- Reads: at most two files from the selected latest run directory: `<latest>/checkpoint.json` and `<latest>/run.json`.
- Parses: each non-empty file as JSON independently, so a malformed checkpoint does not prevent terminal metadata from being read and malformed run metadata does not discard a current-node value already parsed.
- Emits: the parsed checkpoint `current_id` string or `""`, and the parsed run metadata `terminal` string or `""`.
- Preserves: all other run artifacts and metadata fields.

#### Failure behavior

- No runs: returns `("", "")`.
- Missing file content: leaves the corresponding tuple element empty.
- Malformed JSON: leaves the corresponding tuple element empty and continues with the other file when applicable.
- Missing JSON field: leaves the corresponding tuple element empty.

### method-find-awaiting-gates

- sig: `_find_gates(workspace_volume: str) -> list[GateInfo]`
- abstract: false
- raises: propagates Docker file-read launch, timeout, and path-guard exceptions from the underlying file-content reader; Docker grep failures are represented by the awaiting-file reader as an empty path list.
- code: groom/groom/discovery.py::_find_gates
- verify: groom/tests/test_discovery.py::test_find_gates_only_keeps_files_still_awaiting
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run

Reconstructs open operator gates from a workflow's `/workspace` volume during discovery fallback. It starts from the host-side awaiting-file sweep, rereads each candidate file, revalidates the current status through the shared gate parser, extracts the operator-facing question, and returns gate records whose workflow id is deliberately blank until a caller attaches the containing workflow id.

#### Contract

- input: `workspace_volume` is a Docker named volume string previously copied from the eligible container's `/workspace` mount.
- candidate-source: the [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md) supplies workspace-relative paths whose file content appeared to contain `STATUS: AWAITING_OPERATOR` during the sweep.
- reread-rule: each candidate path is read again before it becomes a gate record, because a file may have changed after the grep sweep.
- status-rule: only files whose reread content is still classified as `AWAITING_OPERATOR` by the [operator gate context file](../operator-gate-context-file.md#method-status-of) status parser are retained.
- question-rule: retained files use the [operator gate context file](../operator-gate-context-file.md#method-extract-question) extractor for the gate question text.
- output: `list[GateInfo]`, preserving the awaiting-file reader's path order for retained gates.
- workflow-id: emitted gate records have `workflow_id=""`; the volume reconstruction transition assigns the containing workflow container id before storing them on the workflow.
- persistence: returns in-memory gate records only; it never writes gate files, answers questions, mutates workflow containers, registers locks, broadcasts dashboard HTML, or persists state.

#### Effects

- Calls: the first-party [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md) once for the supplied volume.
- Calls: the first-party workspace-volume file-content reader once for each candidate path.
- Filters: drops candidates whose reread content is missing or no longer awaiting.
- Builds: one [gate info](gate-info.md) record per retained file path, with blank workflow id, the candidate path, extracted question text, and awaiting status.
- Preserves: non-awaiting gate files, consumed or answered files, unreadable files, workspace volume contents, and registry state.

#### Failure behavior

- No candidates: returns an empty list.
- Missing reread content: skips that candidate.
- Stale candidate: skips a candidate whose reread status is no longer `AWAITING_OPERATOR`.
- Awaiting-file sweep failure: returns an empty list through the underlying reader's failure contract.

### method-present-container-ids

- sig: `present_container_ids() -> set[str] | None`
- abstract: false
- raises: propagates launch and timeout exceptions from the underlying Docker container-id listing helper; Docker command failure itself is represented as `None`.
- code: groom/groom/discovery.py::present_container_ids
- verify: groom/tests/test_discovery.py::test_present_container_ids_passes_through_docker_layer

Returns the local Docker daemon's current container-id set for stale-registry pruning. The lookup is intentionally broader than workhorse discovery: it reports every present container id, not only containers that have `/workflow`, `/runs`, and `/workspace` mounts, because reconciliation only needs to know whether an already-registered workflow container still exists.

#### Contract

- input: no caller-supplied arguments; the method reads the local Docker daemon through the first-party container-id listing reader.
- output: `set[str] | None`, where a set is the complete current Docker container-id population known to the Docker helper and `None` means Docker was unreachable or the helper could not produce a reliable listing.
- id scope: includes every Docker container id reported by the helper, not only ids for workhorse-backed containers and not only ids already present in the workflow registry.
- prune safety: `None` is a negative capability signal that callers must treat differently from an empty set, because pruning on an unreachable Docker daemon would remove valid registry entries.
- persistence: returns an in-memory value only; it never mutates the [workflow registry](workflow-registry.md), [workflow container](workflow-container.md) records, Docker containers, sidecar sessions, dashboard clients, gate files, answer logs, or mounted volumes.

#### Effects

- Calls: the first-party [Docker container-id listing reader](docker-container-id-listing-reader.md) once.
- Emits: the returned `set[str]` unchanged when Docker reports container ids; each id is the short normalized id supplied by the Docker container-id listing reader.
- Emits: `None` unchanged when the Docker container-id listing reader receives a failed Docker command result, allowing callers to distinguish an unreachable Docker daemon from an empty Docker fleet.
- Preserves: workflow registry contents, discovery scan results, gate state, sidecar state, dashboard websocket clients, and Docker containers.
- Does not: filter to workhorse containers, inspect containers, resolve workflow state, prune registry entries, mutate workflow records, broadcast dashboard HTML, answer gates, start or stop containers, write files, or persist state.

#### Failure behavior

- Docker command failure: returns `None` through the Docker I/O helper rather than raising a domain-specific discovery error.
- Empty Docker fleet: returns an empty `set[str]`, which callers may use as a positive signal that no containers are currently present.
- Process launch or timeout failure: not converted by this wrapper; any exception raised by the Docker I/O helper propagates to the caller.
