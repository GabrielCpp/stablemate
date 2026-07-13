---
type: format
slug: docker-inspect-container-object
title: Docker inspect container object
---
# Docker inspect container object

Docker inspect container object is the raw JSON object Groom accepts from the [Docker inspection reader](concepts/docker-inspection-reader.md). Discovery, the [push-first volume metadata resolver](concepts/push-first-volume-metadata-resolver.md), and the [container running-state check](concepts/container-running-state-check.md) consume only the identity, display-name, running-state, configuration, and mount fields needed to recognize a workhorse workflow container and populate a [workflow container](concepts/workflow-container.md); additional Docker keys may be present and are ignored by Groom's documented readers.

- file: not an on-disk Groom artifact; this is one object from the Docker CLI `docker inspect` JSON array.
- code: groom/groom/docker_io.py::docker_inspect
- code: groom/groom/discovery.py::container_from_inspect
- code: groom/groom/discovery.py::_resolve_container
- code: groom/groom/discovery.py::is_workhorse_container
- code: groom/groom/app.py::_ensure_volumes
- code: groom/groom/docker_io.py::is_running
- verify: groom/tests/test_discovery.py::test_is_workhorse_container_requires_all_three_mounts, groom/tests/test_discovery.py::test_is_workhorse_container_ignores_unrelated_containers, groom/tests/test_discovery.py::test_container_from_inspect_reads_env_name_and_volumes, groom/tests/test_discovery.py::test_workflow_type_from_workflow_mount_basename, groom/tests/test_discovery.py::test_workflow_type_falls_back_to_compose_service_label, groom/tests/test_discovery.py::test_container_from_inspect_marks_stopped_container_idle, groom/tests/test_discovery.py::test_container_from_inspect_falls_back_to_id_when_unnamed, groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container, groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes

## Contract

- producer: Docker CLI `docker inspect <container_id>` emits a JSON array of container objects; Groom's inspection reader returns the first array item when the command succeeds and the JSON parses.
- accepted top-level type: `dict[str, Any]` for every documented consumer; absent inspection metadata is represented before this format as `None`, not as a special object field.
- consumers: discovery classifies workhorse containers, converts this object into a workflow-container record, and uses `State.Running` to choose live sidecar query versus volume reconstruction; the push-first resolver uses the conversion to fill volume and workflow-type metadata; running-state checks read only the nested `State.Running` value.
- object identity: `Id` is the only Docker identity field Groom reads; all stored workflow-container ids derived from this object are the first twelve characters of `Id`.
- eligibility: discovery treats the object as a workhorse workflow container only when the `Mounts` rows include destinations `/workflow`, `/runs`, and `/workspace`; the mount `Type` field is not checked.
- state mapping: discovery converts truthy `State.Running` to the initial `running` workflow state and falsey or absent `State.Running` to the initial `idle` workflow state before sidecar or volume evidence may refine it.
- resolver routing: the per-container discovery resolver also reads `State.Running` after baseline conversion; truthy running state attempts a live sidecar query first, while falsey or absent running state skips sidecar query and reconstructs state from Docker volumes.
- repository identity: discovery copies only `REPO_NAME` and `REPO_BRANCH` values parsed from `Config.Env`; unrelated environment variables, including secrets, do not become workflow-container fields.
- workflow type: discovery reads the basename of the `/workflow` mount `Source` first and falls back to `Config.Labels.com.docker.compose.service` when that basename is empty or exactly `workflow`.
- volume identity: discovery reads the `/workspace` and `/runs` mount `Name` values into `workspace_volume` and `runs_volume`; it does not read host files or Docker volumes as part of parsing this object.
- extra fields: fields outside this contract may be present and are ignored by the documented Groom consumers, including Docker `State.ExitCode`, network settings, image metadata, and mount fields other than `Destination`, `Name`, and `Source`.
- missing fields: absent or falsey documented fields fall back to empty strings, false running state, empty dictionaries, empty lists, or non-eligibility as described per field; the format itself does not reject partial objects.
- malformed fields: truthy documented containers that do not support the mapping/list/string operations used by consumers are outside Groom's accepted shape and may raise ordinary Python type/attribute errors in the consuming layer.

## Fields

### field-id

- type: `str`
- default: `""`
- required: false
- meaning: full Docker container id; discovery truncates it to the first 12 characters for the workflow-container identity.
- consumers: [workflow discovery scan](concepts/workflow-discovery-scan.md#method-resolve-container) and the [initial workflow-state transition](concepts/workflow-state.md#transition-discovery-initial) use this field through workflow-container conversion; running-state checks ignore it because their input id is supplied by the caller.
- missing-or-empty: produces an empty workflow-container id, and an empty name fallback when `Name` is also empty.

### field-name

- type: `str`
- default: `""`
- required: false
- meaning: Docker container name, often prefixed with `/`; discovery strips the leading slash and falls back to the truncated container id when the resulting name is empty.
- transform: removes all leading `/` characters and leaves any other name characters unchanged.
- missing-or-empty: workflow-container display name becomes the normalized `Id` prefix.

### field-state

- type: `dict[str, Any]`
- default: `{}`
- required: false
- meaning: Docker lifecycle metadata; Groom reads `Running` as a boolean source for initial workflow state and for the running-state probe.
- consumers: discovery and the running-state check read only `Running`; this format does not give `ExitCode` any Groom semantics.
- missing-or-falsey: treated as an empty mapping by documented consumers.

### field-state-running

- type: `bool`
- default: `False`
- required: false
- meaning: nested `State.Running` value; true maps discovery state to running and false maps it to idle before sidecar or volume state resolution.
- path: `State.Running`
- conversion: consumers apply Python truthiness, so any truthy value behaves as running and any falsey or absent value behaves as not running.
- consumers: [container running-state check](concepts/container-running-state-check.md) returns this booleanized value, the [initial workflow-state transition](concepts/workflow-state.md#transition-discovery-initial) converts it into `WorkflowState.RUNNING` or `WorkflowState.IDLE`, and the [per-container discovery resolver](concepts/workflow-discovery-scan.md#method-resolve-container) uses it to choose sidecar query versus volume reconstruction.

### field-config

- type: `dict[str, Any]`
- default: `{}`
- required: false
- meaning: Docker configuration metadata; Groom reads `Env` for repository identity and `Labels` as a fallback source for workflow type.
- missing-or-falsey: treated as an empty mapping by discovery's environment and label readers.

### field-config-env

- type: `list[str]`
- default: `[]`
- required: false
- meaning: environment entries in `KEY=VALUE` form; Groom recognizes `REPO_NAME` and `REPO_BRANCH`, ignores entries without `=`, and ignores unrelated variables.
- path: `Config.Env`
- consumer: [workflow discovery scan](concepts/workflow-discovery-scan.md#method-extract-environment-map) parses this list into a transient lookup before baseline workflow-container creation.
- encoding: each accepted entry is split only at the first `=`, so values may themselves contain `=` and empty values are retained.
- duplicate-key: if Docker supplies the same variable more than once, the later accepted entry wins in Groom's lookup.
- privacy: unrelated entries, including secret-bearing variables, are not copied into the [workflow container](concepts/workflow-container.md); current discovery copies only `REPO_NAME` and `REPO_BRANCH`.
- malformed-entry: strings without `=` are skipped by Groom's environment-map extractor.
- recognized-key: `REPO_NAME` becomes the workflow container's repository name.
- recognized-key: `REPO_BRANCH` becomes the workflow container's repository branch.

### field-config-env-entry

- type: `str`
- default: absent
- required: false
- meaning: one Docker environment entry inside `Config.Env`; entries containing `=` are accepted as key/value assignments, and entries without `=` are ignored.
- path: `Config.Env[]`
- parsing: split at the first `=` only; the substring before it is the key and the substring after it is the value, including any later `=` characters.
- empty-value: retained as an empty string when Docker supplies `KEY=`.
- duplicate-key: later accepted entries replace earlier accepted entries for the same key in Groom's transient lookup.
- malformed-entry: a string without `=` is skipped and has no workflow-container effect.

### field-config-env-repo-name

- type: `str`
- default: `""`
- required: false
- meaning: optional `REPO_NAME` assignment inside `Config.Env`; Groom copies its parsed value into the workflow container repository-name field during Docker discovery conversion.
- path: `Config.Env[].REPO_NAME`
- consumer: [workflow-container conversion](#consumer-workflow-container-conversion) through the [environment-map extractor](concepts/workflow-discovery-scan.md#method-extract-environment-map).
- missing-or-empty: produces an empty workflow-container repository name.
- duplicate-key: the later `REPO_NAME=` entry wins if Docker supplies more than one.

### field-config-env-repo-branch

- type: `str`
- default: `""`
- required: false
- meaning: optional `REPO_BRANCH` assignment inside `Config.Env`; Groom copies its parsed value into the workflow container repository-branch field during Docker discovery conversion.
- path: `Config.Env[].REPO_BRANCH`
- consumer: [workflow-container conversion](#consumer-workflow-container-conversion) through the [environment-map extractor](concepts/workflow-discovery-scan.md#method-extract-environment-map).
- missing-or-empty: produces an empty workflow-container repository branch.
- duplicate-key: the later `REPO_BRANCH=` entry wins if Docker supplies more than one.

### field-config-labels

- type: `dict[str, str]`
- default: `{}`
- required: false
- meaning: Docker label map; Groom reads `com.docker.compose.service` only when the `/workflow` mount source basename is empty or generic.
- path: `Config.Labels`
- consumer: [workflow-type derivation](concepts/workflow-discovery-scan.md#method-derive-workflow-type) reads this map as the fallback workflow-kind source.

### field-config-labels-compose-service

- type: `str`
- default: `""`
- required: false
- meaning: nested `Config.Labels["com.docker.compose.service"]` value used as workflow type only when the `/workflow` mount source basename is empty or exactly `workflow`.
- path: `Config.Labels.com.docker.compose.service`
- priority: lower than `/workflow` mount `Source` basename.

### field-mounts

- type: `list[dict[str, Any]]`
- default: `[]`
- required: false
- meaning: Docker mount list; Groom indexes entries by `Destination` to find `/workflow`, `/runs`, and `/workspace` mounts.
- path: `Mounts`
- ordering: insignificant to Groom's documented consumers because discovery selects retained mount rows by destination path.
- duplicate-destination: if duplicate destination rows are supplied, the destination index retains the later row for that destination.
- eligibility: the object is discoverable as a workhorse workflow container only when the destination index contains `/workflow`, `/runs`, and `/workspace`.

### field-mount-destination

- type: `str`
- default: missing
- required: false
- meaning: mount target path inside the container; `/workflow`, `/runs`, and `/workspace` identify a workhorse workflow container and select the records used for workflow type and volume names.
- path: `Mounts[].Destination`
- index-key: discovery stores the whole mount row under this value in a transient destination lookup.
- missing-destination: mount rows without a destination are indexed under `None` and do not satisfy any workhorse mount requirement.

### field-mount-destination-workflow

- type: literal `/workflow`
- default: missing
- required: true for discovery eligibility
- meaning: identifies the mount row whose `Source` basename supplies the preferred workflow type.
- path: `Mounts[].Destination`

### field-mount-destination-runs

- type: literal `/runs`
- default: missing
- required: true for discovery eligibility
- meaning: identifies the mount row whose `Name` becomes the workflow container's runs-volume identifier.
- path: `Mounts[].Destination`

### field-mount-destination-workspace

- type: literal `/workspace`
- default: missing
- required: true for discovery eligibility
- meaning: identifies the mount row whose `Name` becomes the workflow container's workspace-volume identifier.
- path: `Mounts[].Destination`

### field-mount-name

- type: `str`
- default: `""`
- required: false
- meaning: Docker named-volume value for a mount; Groom stores the `/workspace` mount name as `workspace_volume` and the `/runs` mount name as `runs_volume`.
- path: `Mounts[].Name`
- ignored-for: the `/workflow` mount row, where workflow type comes from `Source` rather than `Name`.

### field-mount-source

- type: `str`
- default: `""`
- required: false
- meaning: host or volume source for a mount; Groom reads the basename of the `/workflow` source as the workflow type when it is non-empty and not the generic value `workflow`.
- path: `Mounts[].Source`
- transform: discovery strips trailing `/` characters, reads the POSIX basename, and accepts that basename as workflow type when it is neither empty nor `workflow`.
- fallback: when the transformed `/workflow` source basename is empty or `workflow`, discovery reads `Config.Labels.com.docker.compose.service` instead.

## Consumer Semantics

### producer-docker-inspection-reader

- code: groom/groom/docker_io.py::docker_inspect
- output: one Docker inspect container object, selected as the first element from a successful parsed `docker inspect <container_id>` response.
- absent-output: no object is produced when Docker exits non-zero, stdout is not valid JSON, or the parsed JSON value is falsey.
- shape-boundary: the reader does not verify that the selected first element is a mapping or a workhorse container before returning it; every field-level contract in this format is therefore owned by the downstream consumer that reads that field.
- no interpretation: does not classify mounts, parse environment variables, derive workflow state, normalize ids, read volumes, query sidecars, or mutate registry state.
- side effects: performs only the host Docker metadata read through the shared Docker subprocess runner.

### consumer-workhorse-container-classifier

- code: groom/groom/discovery.py::is_workhorse_container
- input: one Docker inspect container object or partial inspect-shaped dictionary.
- reads: `Mounts[].Destination` only.
- returns: `True` only when destination-indexed mounts include `/workflow`, `/runs`, and `/workspace`.
- returns: `False` for absent mounts, empty mounts, or any object missing at least one of those three destinations.
- side effects: none; the classifier does not inspect process state, read volumes, parse environment variables, or mutate registry state.

### consumer-workflow-container-conversion

- code: groom/groom/discovery.py::container_from_inspect
- input: one Docker inspect container object or partial inspect-shaped dictionary.
- reads: `Id`, `Name`, `State.Running`, `Config.Env`, `Config.Labels`, `Mounts[].Destination`, `Mounts[].Name`, and `Mounts[].Source`.
- emits: one [workflow container](concepts/workflow-container.md) value with normalized id, display name, repository identity, workflow type, initial workflow state, workspace volume, and runs volume.
- defaulting: missing fields become empty strings, empty mappings, empty lists, or `idle` initial state rather than a format-level rejection.
- side effects: none; conversion does not update the registry, broadcast, query sidecars, read Docker volumes, or answer gates.

### consumer-discovery-resolution-path-selection

- code: groom/groom/discovery.py::_resolve_container
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- input: one Docker inspect container object returned for a candidate id during workflow discovery.
- reads: `State.Running` after the object has passed workhorse-container classification and baseline workflow-container conversion.
- emits: a control-flow choice only; running containers are queried through the [host-to-container sidecar query](concepts/host-to-container-sidecar-query.md) path, and stopped or non-running containers skip sidecar query and use [volume reconstruction](concepts/workflow-state.md#transition-volume-reconstruction).
- running-path: truthy `State.Running` calls the [host-to-container sidecar query](concepts/host-to-container-sidecar-query.md) with the normalized workflow container id produced from the same inspect object.
- stopped-path: falsey or absent `State.Running` does not call the sidecar query and falls directly back to [volume reconstruction](concepts/workflow-state.md#transition-volume-reconstruction).
- fallback: a running-path sidecar query that returns no snapshot also falls back to [volume reconstruction](concepts/workflow-state.md#transition-volume-reconstruction).
- side effects: this consumer does not mutate the inspect object; any workflow-container mutation happens through sidecar snapshot application or volume reconstruction after the path choice.

### consumer-push-first-volume-hydration

- code: groom/groom/app.py::_ensure_volumes
- input: one Docker inspect container object returned for the caller-supplied workflow id after a push or sidecar path sees a container before discovery has supplied Docker volume metadata.
- reads: the [workflow-container conversion](#consumer-workflow-container-conversion) output derived from `Mounts[].Destination`, `Mounts[].Name`, `Mounts[].Source`, and `Config.Labels.com.docker.compose.service`.
- emits: registry metadata for the caller's id containing only `workspace_volume`, `runs_volume`, and `workflow_type` from the converted object.
- classification: does not run the workhorse-container classifier before conversion; an inspect object missing the workhorse mount contract can therefore produce empty volume or workflow-type fields for the registry upsert.
- skipped-before-read: if the existing registry entry already has a non-empty workspace volume, this consumer performs no Docker inspection and reads no Docker inspect container object.
- absent-metadata: when the Docker inspection reader returns no object, this consumer performs no conversion and emits no registry update.
- side effects: mutates only the in-memory workflow registry through the normal upsert rule; it does not broadcast dashboard HTML, change lifecycle state, answer gates, query sidecars, read Docker volumes, or persist data.

### consumer-running-state-check

- code: groom/groom/docker_io.py::is_running
- input: one Docker inspect container object returned by the [Docker inspection reader](concepts/docker-inspection-reader.md), or no metadata.
- reads: `State.Running` only.
- emits: `True` only when inspection metadata exists and `State.Running` is truthy; otherwise emits `False` for absent metadata or absent/falsey running state.
- side effects: performs the Docker inspection read through the reader but does not mutate the workflow registry or container.
