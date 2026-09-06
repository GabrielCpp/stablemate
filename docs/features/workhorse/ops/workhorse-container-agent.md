---
type: runbook
slug: workhorse-container-agent
title: workhorse container agent
---
# workhorse container agent

- driver: cli
- environment: [workhorse container environment](workhorse-container.md)
- cli: [workhorse](../workhorse.md)
- surfaces: [workhorse](../workhorse.md)
- code: `workhorse/supervisor.py::main`
- reuse: never
- fresh: `docker compose -f workhorse/compose.yaml build agent`
- boot-timeout: 120
- stop: `docker compose -f workhorse/compose.yaml down`
- working-directory: .

This runbook operates the repository's isolated `agent` Compose job. The image is built from the
workspace root so its `pyproject.toml` and `uv.lock` are available; the Dockerfile copies the
workhorse, workflows, core, and ostler workspace members into the image. The supervisor performs
credential and git setup, materializes the requested checkout, runs the selected workflow's
`workhorse-<name> run` command, and returns that command's exit status as the container status.

The workflow is selected by `WORKFLOW` (default `coder`). `AGENT_RUN_ID` must be unique per fresh
launch so concurrent containers do not share a run directory; restarting the same container keeps
the baked-in id and resumes its checkpoint. `AGENT_SOURCE_MODE=worktree` uses the read-write repo
bind at its identical host/container path, while the default `clone` mode uses `/workspace`.
Credential input is either the read-only `AGENT_CREDENTIALS_FILE` bind or
`CLAUDE_CODE_OAUTH_TOKEN`; the supervisor seeds the persistent Claude state only when the volume
does not already contain credentials.

The container has no HTTP health endpoint. Completion is observable through the supervisor log and
the container exit status; run artifacts are written under `/runs`. Engine or image dependency
changes require `--build`. A mounted groom source is optional: its observer is staged into a
generation directory and a reload request restarts only the observer; a core reload re-stages the
engine before the workflow is re-entered, while a failed refresh leaves the prior generation in
place.

## Steps

### build

- kind: prepare
- run: `docker compose -f workhorse/compose.yaml build agent`
- working-directory: .
- timeout: 120
- produces: the `agent` image containing the workspace members and installed workflow commands
- verify: [workhorse Dockerfile](../../../../workhorse/Dockerfile)
- provenance: derived

### serve

- kind: service
- run: `docker compose -f workhorse/compose.yaml up --abort-on-container-exit agent`
- working-directory: .
- timeout: 120
- health: `log:[supervisor] workflow exited with 0` confirms successful observable completion for this non-network job
- produces: the selected workflow's run artifacts in the `runs` volume and its exit status
- verify: [supervisor](../../../../workhorse/supervisor.py)
- provenance: derived

### stop

- kind: verify
- run: `docker compose -f workhorse/compose.yaml down`
- working-directory: .
- timeout: 30
- verify: [Compose stack](../../../../workhorse/compose.yaml)
- provenance: derived
