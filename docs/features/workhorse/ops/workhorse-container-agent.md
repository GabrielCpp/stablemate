---
type: runbook
slug: workhorse-container-agent
title: workhorse container agent
---
# workhorse container agent

This runbook operates the `agent` Compose job in the
[workhorse container environment](workhorse-container.md). It runs the installed
[workhorse CLI surface](../workhorse.md) through the container supervisor at
`workhorse/supervisor.py::main`; the environment node owns the Compose and image definitions.
The job is intentionally one-shot rather than an HTTP service: its workflow exit status and the
supervisor log are its completion signal.
The supervisor exit-code behavior is covered by
`workhorse/tests/test_supervisor.py::test_run_exit_code_is_the_containers_with_no_observer`.

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

The image is built from the workspace root, where its `pyproject.toml` and `uv.lock` are available.
Before starting a workflow, the supervisor validates writable persistent mounts, prepares Claude
authentication and Git configuration, materializes the requested checkout, writes environment-derived
workflow parameters, and then starts the selected `workhorse-<name> run` command. Its final exit code
is the container exit code; an unavailable or failed optional groom observer never changes that result.
The `agent` service is therefore ready when the workflow completes successfully, not while a network
listener is accepting connections.

Select an installed workflow with `WORKFLOW` (default `coder`). Supply a distinct `AGENT_RUN_ID` for
each concurrent fresh launch so their run directories do not collide; Docker restart preserves the
container's configured id and resumes its checkpoint. `AGENT_SOURCE_MODE=worktree` uses the read-write
repository bind at the identical host and container path; the default `clone` mode materializes a
checkout below `/workspace`. Authentication comes from the read-only `AGENT_CREDENTIALS_FILE` bind or
`CLAUDE_CODE_OAUTH_TOKEN`; existing persistent Claude credentials take precedence over a new file seed.

The container has no HTTP health endpoint. Completion is observable through the
`[supervisor] workflow exited with 0` log line and a zero container exit status; run artifacts persist
under `/runs`. Rebuild the image after changes to copied engine code or image dependencies. When the
optional groom source mount exists, the supervisor stages it into a complete generation before starting
the observer; reload requests refresh that generation, while a failed refresh leaves the prior installed
generation available. `docker compose ... down` stops the one-shot service while retaining its named
`workspace`, `claude-state`, and `runs` volumes; use Compose teardown with `-v` only when deliberately
discarding that run's persistent state.

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
- run: `WORKFLOW=hello-world docker compose -f workhorse/compose.yaml up --abort-on-container-exit agent`
- working-directory: .
- timeout: 120
- health: `log:[supervisor] workflow exited with 0` confirms successful observable completion for this non-network job
- produces: the `hello-world` workflow's run artifacts in the `runs` volume and its container exit status
- verify: [supervisor](../../../../workhorse/supervisor.py)
- provenance: derived

### stop

- kind: verify
- run: `docker compose -f workhorse/compose.yaml down`
- working-directory: .
- timeout: 30
- verify: [Compose stack](../../../../workhorse/compose.yaml)
- provenance: derived
