# Docker harness (unattended, isolated runs)

> This harness is **not** part of the `workhorse-agent` PyPI package. It lives in
> the source repo (`Dockerfile`, `compose.yaml`, `entrypoint.sh`) and is meant for
> running a workflow in a fully isolated container — the design target is a
> week-long unattended run that survives reboots without touching your host
> environment. For the plain `workhorse` CLI, see the [README](../README.md).

The bundled image runs `workhorse` with credential seeding, persistent volumes,
and isolation: the agent works against its own clone (never a host working tree)
and all state lives in named volumes.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- A logged-in Claude **subscription** on the host (`~/.claude/.credentials.json`
  present — i.e. you have run `claude` and authenticated). This is the default
  auth path and matches what your interactive Claude CLI uses.

No Python, `uv`, or Claude CLI installation is required on the host — everything
runs inside the container.

## Authentication

By default the worker uses your **Claude subscription**. At startup
`entrypoint.sh` seeds `~/.claude/.credentials.json` from the host (mounted
read-only) into the persistent `claude-state` volume **once**; the CLI then
refreshes/rotates the token in-volume across runs and reboots. A minimal
`~/.claude.json` onboarding stub is written so headless runs don't prompt.

Alternatives:

- **Long-lived OAuth token** — run `claude setup-token` on the host and export
  `CLAUDE_CODE_OAUTH_TOKEN` before `docker compose up` (or put it in a `.env`
  beside `compose.yaml`). This skips the credentials-file seed.
- **Bedrock** — uncomment the `CLAUDE_CODE_USE_BEDROCK`/`AWS_PROFILE` env and the
  `~/.aws` mount in `compose.yaml`.

To re-seed credentials after re-authenticating on the host, clear the
`claude-state` volume (`docker volume rm <project>_claude-state`; see
[Resetting state](#resetting-state) for the project-name prefix).

## Running a workflow

The base `compose.yaml` defines the worker service, named volumes, and auth
seeding. You select the workflow and the target repo through environment variables
and a **layered override compose file** — this is how `workhorse` is meant to be
embedded in a project:

```bash
WORKFLOW_DIR=/abs/path/to/workflow-dir \
docker compose -f compose.yaml -f your-override.compose.yaml up --abort-on-container-exit

# Force a full image rebuild (after controller or pyproject.toml changes)
... docker compose -f compose.yaml -f your-override.compose.yaml up --build --abort-on-container-exit
```

`WORKFLOW_DIR` must point at a directory containing a `workflow.yaml`; its
`prompts/` and `scripts/` subdirectories are mounted alongside it inside the
container.

> The controller `.py` is `COPY`d into the image, not bind-mounted, so controller
> edits take effect only after an image rebuild (`--build`).

### Override compose file (clone from your working tree)

The typical embedding bind-mounts your working tree **read-only** and has the
workflow's `setup.sh` clone from that mount instead of from GitHub — so no SSH
key, token, or network is needed, and your host tree is never mutated (the clone
lives in the `workspace` volume, using your latest *committed* state):

```yaml
# your-override.compose.yaml — layered on top of compose.yaml
services:
  agent:
    environment:
      REPO_URL: /mnt/src        # setup.sh prefers this over its GitHub default
      REPO_BRANCH: ${REPO_BRANCH:-main}
      REPO_NAME: ${REPO_NAME:-myrepo}   # cloned to /workspace/$REPO_NAME
    volumes:
      - type: bind
        source: ${REPO_SRC:-.}  # your host working tree
        target: /mnt/src
        read_only: true
```

A project usually wraps these commands in a `make` target (e.g. `make agent-run`)
so contributors don't type the compose invocation by hand. For a quick auth/image
smoke test, run the bundled `hello-world` workflow (which needs no repo clone) by
pointing `WORKFLOW_DIR` at it.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WORKFLOW_DIR` | _(required)_ | Absolute path to the workflow directory (mounted at `/workflow`) |
| `CLAUDE_CODE_OAUTH_TOKEN` | _(unset)_ | Optional long-lived OAuth token (`claude setup-token`); skips the credentials-file seed |
| `AGENT_RUNS_DIR` | `/runs` | Where to write run artifacts (set to the persistent `runs` volume by `compose.yaml`) |
| `AGENT_CLI` | `claude` | Which agent CLI drives the run: `claude`, `codex`, `copilot`, `aider`, or `opencode` |
| `AGENT_MODEL` | _(unset)_ | Overrides every node's model for the run (a node's own `model:` still wins) |
| `OPENROUTER_API_KEY` | _(unset)_ | Upstream key for OpenRouter models on the `aider` / `opencode` backends (no proxy). Pass it into the container |
| `CODEX_PROFILE` | _(unset)_ | Run-level default codex config profile (e.g. `openrouter`, `local`). Codex only |
| `AWS_PROFILE` | `default` | AWS profile — only when using the Bedrock alternative |

(The controller's resilience/timeout knobs are also env vars — see
[GUARDRAILS.md](GUARDRAILS.md).)

## Mounts and volumes

| Source | Target | Type | Purpose |
|---|---|---|---|
| `~/.claude/.credentials.json` | `/mnt/claude-credentials.json` | bind, read-only | Subscription auth — seeded into `claude-state` once at startup |
| `~/.claude/settings.json` | `/mnt/claude-settings.json` | bind, read-only | Optional host Claude config (commented out by default) |
| `$WORKFLOW_DIR` | `/workflow` | bind | Workflow definition (yaml, prompts, scripts) |
| `workspace` volume | `/workspace` | named volume | **Agent working tree** — repo clones, branches, and commits; persists across reboots |
| `claude-state` volume | `/claude-state` | named volume | Claude sessions + seeded credentials + onboarding stub; persists across reboots |
| `runs` volume | `/runs` | named volume | Run artifacts; persists across reboots |

### Persistence across reboots

All three named volumes (`workspace`, `claude-state`, `runs`) persist across
container restarts and host reboots, so the agent's work is never lost when the
container stops:

- **`workspace`** holds the cloned repo and the agent's committed branch (e.g.
  `<project>/auto`). Even if a push out of the container fails, committed work
  survives here. (A workflow's `setup.sh` typically `reset --hard`s the base
  branch on re-run, so commit work to a side branch — as the workflows do.)
- **`claude-state`** keeps Claude session history and the refreshed auth token,
  isolated from your host installation. (Each node runs with a *clean context*, so
  this is not one growing cross-node conversation.)
- **`runs`** keeps all run artifacts. Pull them out with `docker cp` /
  `docker compose cp` from the volume.

## Resetting state

Volume names are prefixed with the **compose project name** (defaults to the
directory you launch from, or `COMPOSE_PROJECT_NAME` if set) — `local-worker` in
the examples below; substitute your own:

```bash
# Wipe Claude session history + seeded credentials (re-seed auth on next run)
docker volume rm local-worker_claude-state

# Wipe all run artifacts in the volume
docker volume rm local-worker_runs

# Wipe the agent's working tree (clones/commits) — only if you want a clean clone
docker volume rm local-worker_workspace

# Wipe everything (run with the same -f files you launched with)
docker compose -f compose.yaml -f your-override.compose.yaml down -v
```
