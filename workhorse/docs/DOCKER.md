# Docker harness (unattended, isolated runs)

> This harness is **not** part of the `workhorse-agent` PyPI package. It lives in
> the source repo (`Dockerfile`, `compose.yaml`, `supervisor.py`) and is meant for
> running a workflow in a fully isolated container — the design target is a
> week-long unattended run that survives reboots without touching your host
> environment. For the plain `workhorse` CLI, see the [README](../README.md).

The bundled image runs `workhorse` as nobody's uid with **your** group, with
credential seeding and persistent per-run volumes. Several runs of the same workflow
can be in flight at once: each gets its own container, its own volume set, its own
run id, and its own `git worktree` of one repo.

**The agent works in a worktree of a repo on your disk**, not in a clone inside a
volume. That is a deliberate inversion of how this harness used to work, and it is
what makes concurrency cheap — N runs share one object store and one ref namespace
instead of paying for N clones. It also means a run's commits are *in your repo* when
it finishes, on a branch, rather than stranded in a volume you have to `docker cp`
out of. Each worktree is created detached; the branch is cut later, by a workflow
node.

## Running several at once

The generated launcher is the supported way in — it mints the run id, cuts the
worktree, stages credentials and names the compose project, none of which you want
to type:

```bash
make agent-workflows          # what this machine can run (from pipx)
make agent-run-coder          # one run, streaming its logs
make agent-run-coder DETACH=1 # …in the background; run this again for a second
make agent-runs               # what is live
make agent-logs  RUN=coder-<run-id>
make agent-stop  RUN=coder-<run-id>   # resumable: docker restart re-enters it
make agent-clean RUN=coder-<run-id>   # remove it AND its volumes
```

`make agent-run-*` targets exist for whatever workflows `farrier workflows` finds
installed here, resolved when you type `make` rather than baked into the file.

Each launch mints a UUID that becomes the run id, the compose project name, and
therefore the prefix of every named volume the run owns. That is what keeps two runs
apart: without it every container derives the same run id from a digest of its
params — identical in every container — and the second would resume or delete the
first's run directory.

## How the workflow is selected

A workflow is an **installed distribution**, not a directory: the image installs
`workhorse-workflows` and each workflow in it declares its own console script. So
`$WORKFLOW` names the workflow and `supervisor.py` spawns that name's command
(`workhorse-coder run …`). Nothing is bind-mounted at `/workflow`, and there is no
`WORKFLOW_DIR` or `WORKFLOW_PATH` — a wheel not installed in the image is a workflow the
container cannot run, and an unset or misspelled `$WORKFLOW` fails at spawn rather than
part-way into a run.

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

Driving `docker compose` yourself is still supported, and is what the launcher does
under the covers. Every variable the container reads has to be **declared** in
`compose.yaml` — compose passes on nothing from your shell that the service does not
name — so the set below is the whole interface:

```bash
WORKFLOW=coder AGENT_RUN_ID=$(cat /proc/sys/kernel/random/uuid) \
AGENT_UID=65534 AGENT_GID=$(id -g) \
AGENT_REPO_HOST_DIR=/path/to/repo AGENT_SOURCE_MODE=worktree \
AGENT_WORKTREE_ROOT=/path/to/repo/.agents/worktrees/myrun \
AGENT_REPO_DIR=/path/to/repo/.agents/worktrees/myrun/repo \
REPO_URL=/path/to/repo REPO_NAME=repo REPO_BRANCH=main \
docker compose -p coder-myrun up --abort-on-container-exit

# Force a full image rebuild (after engine or pyproject.toml changes)
... docker compose -p coder-myrun up --build --abort-on-container-exit
```

Use `-p <project>` rather than the default, or two runs share one volume set.

> The engine's `.py` is `COPY`d into the image, not bind-mounted, so engine edits
> take effect only after an image rebuild (`--build`).

### The repo bind, and why source == target

In worktree mode the repo is bound **at its own host path** — the `source:` and
`target:` of that mount are the same string, and the bind is read-write.

That is not a stylistic choice. `git worktree add` records the worktree's absolute
path in the source repo's `.git`, *and* the source's absolute path in the worktree.
If the container saw the repo somewhere else, it would write paths into your `.git`
that do not exist on your machine — `git worktree list` would show them and you
could neither use nor prune them. Read-write for the same reason: the source repo is
written to.

Worktrees default to `<repo>/.agents/worktrees/<run-id>/`, inside the repo, so that
single bind covers the source and every run's tree at paths both sides agree on.
farrier's gitignore block excludes `.agents/worktrees/`, so none of it is committable.

Leave `AGENT_SOURCE_MODE` unset (or `clone`) for the older model: a disposable clone
of `REPO_URL` inside the `workspace` volume, reset to the remote on each restart.

For an auth/image smoke test, `WORKFLOW=hello-world` runs the shipped quick start in the
container. On the host, `workhorse-hello-world run --dry-run` covers the same ground and
needs no agent CLI at all — see the [README](../README.md#quick-start).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WORKFLOW` | `coder` | Name of an installed workflow; the container spawns its `workhorse-<name> run` command |
| `AGENT_RUN_ID` | _(unset)_ | This run's identity, passed on as `--run-id`. **Set one per launch.** Unset, every container derives the same id from a digest of its params and they collide on one run directory. Baked in at container-create time, so `docker restart` resumes the same run |
| `AGENT_SOURCE_MODE` | `clone` | `worktree` gives this run its own `git worktree` of the bound host repo; `clone` makes a disposable copy in the `workspace` volume |
| `AGENT_WORKTREE_ROOT` | _(= workspace root)_ | Where this run's worktree is created. Must be the same path on the host — see the repo-bind note above |
| `AGENT_REPO_HOST_DIR` | _(unset)_ | Host path of the repo to bind, mounted at this same path. Unset, nothing is bound and `clone` is the only usable mode |
| `AGENT_REPO_DIR` | _(cwd)_ | `repo_dir`, the run's one universal input — in worktree mode, **this run's tree**, not the shared source |
| `AGENT_PARAM_<NAME>` | _(unset)_ | Becomes run parameter `<name>` (`AGENT_PARAM_DOCS_PATH=/docs` → `{"docs_path": "/docs"}`). The generic replacement for the old per-workflow spellings — see the note below |
| `AGENT_CREDENTIALS_FILE` | `~/.claude/.credentials.json` | Which file is bound as the credentials seed. The launcher points this at a per-run group-readable copy, because the real one is mode 600 and the container is not you |
| `AGENT_UID` / `AGENT_GID` | `65534` / `65534` | The container's uid:gid. The launcher uses `65534:$(id -g)` — nobody's uid, your group |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://host.docker.internal:8787` | Where telemetry ships. **Must** be set for a container: workhorse's own default is `127.0.0.1`, which in a container is its own loopback with nothing on it |
| `GROOM_HOST` / `GROOM_PORT` | `host.docker.internal` / `8787` | Where the groom-sidecar dials for the gate/progress socket |
| `CLAUDE_CODE_OAUTH_TOKEN` | _(unset)_ | Optional long-lived OAuth token (`claude setup-token`); skips the credentials-file seed |
| `AGENT_RUNS_DIR` | `/runs` | Where to write run artifacts (set to the persistent `runs` volume by `compose.yaml`) |
| `AGENT_CLI` | `claude` | Which agent CLI drives the run: `claude`, `codex`, `copilot`, `cline`, or `opencode` |
| `AGENT_MODEL` | _(unset)_ | Fallback model override when the node's `power` mapping does not provide one |
| `STABLEMATE_CONFIG` | `~/.config/stablemate/config.toml` | Unified user-wide config mapping `power` tiers to backend model/effort settings. `WORKHORSE_CONFIG` is still honored as the pre-unification spelling |
| `OPENROUTER_API_KEY` | _(unset)_ | Upstream key for OpenRouter models on the `cline` / `opencode` backends (no proxy). Pass it into the container |
| `CODEX_PROFILE` | _(unset)_ | Run-level default codex config profile (e.g. `openrouter`, `local`). Codex only |
| `AWS_PROFILE` | `default` | AWS profile — only when using the Bedrock alternative |

(The engine's resilience/timeout knobs are also env vars — see
[GUARDRAILS.md](GUARDRAILS.md).)

> **Breaking change: `CODER_WORKSPACE` and `CODER_DOCS_PATH` are gone.** Use
> `AGENT_PARAM_WORKSPACE_FILE` and `AGENT_PARAM_DOCS_PATH`. The old names were one
> workflow's vocabulary living in the shared harness, which workhorse must never
> learn; the prefix expresses any workflow's parameters without the harness knowing
> that workflow exists. A leftover `CODER_*` variable is now simply ignored, so
> check for one if a run starts with a parameter you thought you had set.

## Mounts and volumes

| Source | Target | Type | Purpose |
|---|---|---|---|
| `$AGENT_CREDENTIALS_FILE` | `/mnt/claude-credentials.json` | bind, read-only | Subscription auth — seeded into `claude-state` once at startup |
| `~/.claude/settings.json` | `/mnt/claude-settings.json` | bind, read-only | Optional host Claude config (commented out by default) |
| `$AGENT_REPO_HOST_DIR` | *the same path* | bind, read-write | The repo this run works on. Source and target must match — see the repo-bind note above |
| `../groom` | `/mnt/groom-src` | bind, read-only | Optional groom sidecar source. Copied to `/opt/live/groom/<gen>` and installed from the copy, so nothing ever imports the bind |
| `workspace` volume | `/workspace` | named volume | Clone-mode working tree. In worktree mode the run works in the bind above instead |
| `claude-state` volume | `/claude-state` | named volume | `HOME`: Claude sessions, seeded credentials, onboarding stub |
| `runs` volume | `/runs` | named volume | Run artifacts |

**The volumes are per run, not per repo.** They are named after the compose project,
so `-p coder-<run-id>` gives each run its own set. `claude-state` in particular must
not be shared: it is `HOME`, and two Claude CLIs there would rotate one
`.credentials.json` and last-writer-win each other's `.gitconfig`.

### uid, and getting your files back

The container runs as **`65534:<your gid>`** — nobody's uid, your group. The uid is
not yours; the access is. Three things make that work, and all three are already
done for you by the launcher and the supervisor:

- `umask 002` before anything is spawned, so new files are `664` and directories `775`
- `git config core.sharedRepository=group` on the **source** repo, because that is
  where a worktree's objects and refs land, and git otherwise writes into `.git`
  with no group write at all
- setgid on the worktree root, so directories created beneath it inherit your group

Result: a run's output is `nobody:<yourgroup>`, and you can read, write and commit
into it from the host without `sudo`. (Loose objects stay `0444` — that is correct
and not a problem: an object is immutable and content-addressed, so nothing ever
rewrites one. What has to be group-writable is the directories and the refs.)

Your `~/.claude/.credentials.json` is mode `600`, which no other uid can read, so the
launcher stages a `640` copy per run and binds that. **Your own file is never
modified** — chmod-ing it would be undone the next time the CLI rotates the token.

Fresh named volumes inherit the image's world-writable mountpoints and work under any
uid. A volume created by an *older* image still carries `nobody` ownership and will
fail the supervisor's writability check (exit 13) under a different uid — remove it,
or repair it:

```bash
docker run --rm -v <project>_claude-state:/claude-state ubuntu:24.04 \
  sh -c 'chmod -R a+rwX /claude-state'
```

### Persistence across reboots

A run's volumes persist across container restarts and host reboots, so its work is
never lost when the container stops:

- **the worktree** (worktree mode) holds the agent's commits, and it is on *your*
  disk in *your* repo — so committed work is already where you can see it, even if a
  push out of the container fails. It is **never reset on restart**: unlike a clone
  in a disposable volume, it may hold work in progress.
- **`claude-state`** keeps Claude session history and the refreshed auth token,
  isolated from your host installation. (Each node runs with a *clean context*, so
  this is not one growing cross-node conversation.)
- **`runs`** keeps all run artifacts. Pull them out with `docker cp` /
  `docker compose cp` from the volume.

`docker restart` re-enters a stopped container with the **same run id** — the id was
baked into its config at create time — so it resumes from its checkpoint. A fresh
`make agent-run-*` mints a new id and starts clean. That is the whole difference
between resuming a run and starting one.

## Resetting state

Volume names are prefixed with the **compose project name**, which for a launched run
is `<workflow>-<run-id>` — the handle `make agent-runs` prints. Everything a run owns
goes away with it:

```bash
make agent-clean RUN=coder-<run-id>       # container + all three of its volumes
docker compose -p coder-<run-id> down -v  # the same thing by hand
```

Individual volumes, when you want to keep the rest of a run:

```bash
# Re-seed auth on the next start (wipes Claude session history too)
docker volume rm coder-<run-id>_claude-state

# Drop run artifacts
docker volume rm coder-<run-id>_runs
```

The worktree is **not** in a volume — it is a directory in your repo, and
`agent-clean` does not touch it, because it is where the run's commits are. Remove
one deliberately when you are done with it:

```bash
git worktree remove .agents/worktrees/<run-id>/<repo>
```

A worktree whose directory you delete by hand leaves a registration behind; the next
run prunes it, and `git worktree prune` does it now.
