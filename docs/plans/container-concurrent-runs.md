# Concurrent containerized runs: supervisor-owned, pipx-sourced

> **Status:** proposed; nothing implemented. This document records the design for
> running **N concurrent containerized workflow runs of the same kind** (three
> `coder` runs at once), replacing `entrypoint.sh` with a small Python supervisor,
> sourcing workflows from pipx rather than the base library, and giving each run
> its own `git worktree` of a bind-mounted host repo.
>
> Written against `main` @ `173cbd8`. Every file:line below was verified against
> that tree — treat them as facts to build on, not claims to re-derive.

## 1. Problem

The container harness runs exactly one workflow, once. Everything about it is a
singleton: one service, three shared named volumes, one run directory, one `HOME`.
Running a second `coder` against it does not interleave — it destroys the first
(§3.2).

Four things need to change together, because each blocks the others:

1. **Concurrency.** N runs of the same workflow, isolated from each other.
2. **The entrypoint.** `entrypoint.sh` carries 17 responsibilities in shell
   (§2.1). Shell supervision is fragile and untestable; it should be Python.
3. **Workflow source.** Farrier stopped installing workflows when they became
   Python distributions. It should install them again — discovered from **pipx**,
   which makes a local uv project as installable as a PyPI release.
4. **Working trees.** N concurrent runs need N working trees of one repo.

## 2. What exists today

### 2.1 `entrypoint.sh` — 17 responsibilities

Inventoried in full because the supervisor must re-home every one of them.
**(a)** one-time setup · **(b)** supervision · **(c)** env translation

| # | Responsibility | Lines | Kind |
|---|---|---|---|
| 1 | `set -euo pipefail` | `:1-2` | b |
| 2 | Pin `HOME=/claude-state` | `:8-9` | c |
| 3 | Assert `/workspace`, `/runs`, `$CLAUDE_HOME` writable; **exit 13** otherwise. Never repairs ownership | `:11-33` | a |
| 4 | `mkdir -p $CLAUDE_HOME/.claude` | `:35` | a |
| 5 | Copy `/mnt/claude-settings.json` → `~/.claude/settings.json` each start | `:39-41` | a |
| 6 | Auth, 3-way priority: `CLAUDE_CODE_OAUTH_TOKEN` > in-volume creds > one-time seed + `chmod 600` | `:49-60` | a |
| 7 | Onboarding stub `~/.claude.json` | `:64-66` | a |
| 8 | Git identity: `safe.directory '*'`, `user.email`/`user.name` | `:74-76` | a,c |
| 9 | Workspace checkout via `python3 -m workhorse_workflows.kit.workspace`, env→argv | `:88-97` | a,c |
| 10 | `uv tool install --editable /mnt/groom-src` (failure-tolerant) | `:117-121` | a |
| 11 | Sidecar restart loop keyed on **exit code 3** | `:130-137` | b |
| 12 | Hand-printf `boundary-params.json` | `:151-162` | c |
| 13 | Assert `$WORKFLOW`, spawn `uv run workhorse-$WORKFLOW run …` **backgrounded** | `:164-172` | b,c |
| 14 | `trap 'kill -TERM $wf_pid' TERM INT` | `:176` | b |
| 15 | `wait`, capture exit code | `:180-181` | b |
| 16 | One-shot `groom-sidecar --exit-code "$rc"` | `:186` | b |
| 17 | `exit "$rc"` | `:188` | b |

**#9's hook branch is dead.** It tests for `/workflow/scripts/checkout-workspace.py`;
no such file exists anywhere in the repo, and `compose.yaml:71-74` deliberately
never mounts `/workflow`. Delete rather than port.

### 2.2 Container

`compose.yaml` — one service `agent` (`:2`), build context `..`
(`:7-8`). `user: "${AGENT_UID:-65534}:${AGENT_GID:-65534}"` (`:16`). Env: `WORKFLOW`
default `coder` (`:43`), `AGENT_RUNS_DIR=/runs` (`:45`). Named volumes `workspace`,
`claude-state`, `runs` (`:99-119`) — **all shared, none per-run**. No
`container_name`, no `ports`, no `init`.

`Dockerfile` — `ubuntu:24.04`. COPYs `workhorse/`, `ostler/`, `workflows/`,
`core/` (`:94-104`); **`groom/` deliberately not copied** (`:80-87`) — it arrives at
runtime from a read-only bind. `chmod -R a+rwX /app /workspace /runs /claude-state`
(`:127`) so a fresh volume is writable under any uid. `USER nobody` (`:133`),
`ENTRYPOINT ["/entrypoint.sh"]` (`:151`).

### 2.3 groom

The sidecar is **read-only and non-authoritative** (`sidecar.py:15-16`): it watches
`/workspace` + `/runs` with inotify and dials one WebSocket **out** to
`ws://host.docker.internal:8787/sidecar` (`sidecar.py:45-46,460`).

**It supervises nothing.** No `Popen`, `fork`, `waitpid`, `add_signal_handler` or
`create_subprocess_exec` anywhere in `groom/` — only one-shot `subprocess.run`
captures.

**Reload is exit code 3.** `POST /reload` (`app.py:847-866`) → `send_reload()`
(`sidecar_hub.py:105-109`) → `ReloadRequested` (`sidecar.py:444`) →
`RELOAD_EXIT_CODE = 3` (`sidecar.py:49-52,464-467`) → the shell loop restarts it
(`entrypoint.sh:130-137`).

**Telemetry is standard OTLP/HTTP**: groom serves `/v1/traces`, `/v1/metrics`,
`/v1/logs` on the dashboard port (`app.py:575-627`). Identity rides the OTLP
Resource — `run_id`, `workflow`, `repo`, `branch`, `run_dir` (`otel.py:419-443`).

**groom's telemetry half is already multi-run** (`store` keyed by `run_id`,
`store.py:45-85`; `state.RUNS`, `alerts.py:100-105`). Its **sidecar half is not**:
`_identity()` carries no `run_id` at all (`sidecar.py:58-64`), and
`_latest_run_dir()` hardcodes "the newest run dir is the run" (`sidecar.py:103-107`).
`app.py:283-284` states it outright: "There is always one workflow per container."

### 2.4 Workflows and pipx

All five workflows ship in **one** distribution, `workhorse-workflows`, exposing
five console scripts (`workflows/pyproject.toml:70-75`). There is deliberately no
`workhorse run <name>` and no entry-point group — a script carries its own
`Registry` (`cli/__init__.py:92-95`).

`pipx list --json` carries the provenance needed, under
`venvs.<n>.metadata.main_package`:

| Field | Use |
|---|---|
| `package_or_url` | PyPI name, git URL, **or a local host path** |
| `pip_args` | contains `--editable` for a local editable install |
| `app_paths` | the console scripts the venv exposes |
| `package_version` | pin for the PyPI case |

Verified: `stablemate-library` reports
`package_or_url = '/mnt/data/workspace/stablemate/base-library'` with `--editable`.

## 3. Blocking defects

Existing bugs the design walks into. Not invented work.

### 3.1 Every container derives the same run id — resolved by decision

`cli/run.py:181` defaults params to `{"repo_dir": "/app"}` (cwd is `/app`,
`Dockerfile:77`), and `derive_run_id` hashes that identically every time
(`rundir.py:46-47`).

**Fixed at the launcher, not in workhorse.** The generated Makefile mints a UUID
per launch and passes `--run-id`; an explicit id always wins (`rundir.py:44-45`),
so the digest path is never taken in a container. `derive_run_id` is unchanged —
the digest remains correct for interactive local runs, where re-running the same
command *should* resume.

The UUID is baked into the container config at create time, which gives the right
restart semantics free: `docker restart` re-enters with the same id and resumes; a
fresh `make` launch mints a new one and starts clean.

### 3.2 A second run deletes the first's live run directory

`ArtifactWriter.__init__` (`artifacts.py:76-77`) calls `_clear_stale_run`, which
`shutil.rmtree`s. If the first had checkpointed, `auto_resolve` (`rundir.py:50-75`)
instead *resumes* it and two processes write one `checkpoint.json`.

**Downgraded to hardening** by §3.1 — distinct ids no longer collide. Still
reachable via a hand-passed duplicate `--run-id`. Worth a cheap guard (refuse the
rmtree when the target holds a live pid/lock); not a blocker.

### 3.3 Telemetry is silently off in every container

`otel.py:146-147` defaults the OTLP endpoint to `http://127.0.0.1:8787` — the
*container's own* loopback. Workhorse probes it (`otel.py:324-343`), the probe
fails, telemetry disables itself with no error. Nothing in `compose.yaml` or
`entrypoint.sh` sets `OTEL_EXPORTER_OTLP_ENDPOINT`.

So "groom collects telemetry" is native-only today. `extra_hosts`
(`compose.yaml:17-27`) already publishes `host.docker.internal` and is the target.

### 3.4 groom cannot join a container to its telemetry

`WorkflowContainer.run_id` (`models.py:41`) is set only in `_sync_native_row`
(`app.py:222`), native rows only. `projection.run_id_of` falls back to
`container_id` (`projection.py:117-120`), so `_run_facts` (`app.py:374-391`) looks
up `state.RUNS[container_id]` — never a hit for a container.

### 3.5 Docker discovery matches nothing

`discovery.is_workhorse_container` (`discovery.py:46-48`) requires a `/workflow`
mount that `compose.yaml:71-74` deliberately never creates. Containers reach the
dashboard only via the sidecar's `hello`.

## 4. Design

### 4.1 Decisions

| Question | Decision |
|---|---|
| Isolation unit | **One container per run** |
| Process identity | **`65534:<host gid>`** — nobody's uid, operator's group |
| Working trees | **`git worktree` of a bind-mounted host repo** |
| Workflow source | **pipx-discovered**, PyPI or local uv project |
| PID 1 | **tini via `init: true`**; a Python supervisor as its child |
| Live update | **Read-only mount → separate writable generation copy** |
| Run id | **UUID minted by the launcher**, passed as `--run-id` |
| Launcher | **The farrier-generated Makefile** |

### 4.2 Why the sidecar cannot simply become PID 1

Reload **is** exit code 3. That costs nothing today because the sidecar owns no
state and no children. **If the sidecar were PID 1 owning the workhorse child,
exiting on reload would kill the run.** groom's own docs give the underlying
reason (`sidecar-live-sessions.md:161-166`): a process cannot cleanly re-exec from
its own imported source.

So PID 1 is not the sidecar. It is tini, with a small Python supervisor beneath it
owning two children:

```
PID 1: tini                        (init: true — bought, not built)
  └── supervisor.py                (Python, tested)
        ├── preflight              auth seed, git identity, worktree checkout
        ├── child A: observer      restart on exit 3 — reload restarts ONLY this
        └── child B: workhorse     the run; its exit code is the container's
```

This still deletes the shell script — the objection was to *shell*, not to
supervision — and makes reload work without touching the run.

**It is a net deletion in one place:** the `--exit-code` one-shot push
(`cli.py:284-286`, `entrypoint.sh:186`) exists *only* because the sidecar is not
the parent. It collapses into `await proc.wait()`.

### 4.3 Build vs buy

**Buy the OS hygiene.** `init: true` on the compose service injects Docker's
bundled tini as PID 1 — verified: `docker run --init` shows `docker-init` at pid 1,
and `docker compose config` accepts `init: true`. That is zombie reaping and signal
delivery from a battle-tested C binary, one line, nothing to maintain. Reaping is
the fiddly part of being PID 1; there is no reason to own it.

**Write the policy.** No package fits, because they all invert the core
requirement — they are *service* supervisors that keep things up, and the workhorse
child is a **job that completes whose exit code must become the container's**.

| Candidate | Why not |
|---|---|
| supervisord | Does not exit when a child finishes; extracting the exit code needs an event-listener shim that kills the supervisor. INI config, not code. |
| s6-overlay | Same service model; config-as-a-directory-of-files is the shell fragility being removed, in another notation. Not Python. |
| circus | Service model, plus ZeroMQ for a two-process problem. |
| honcho / foreman | Procfile, dev-oriented. No per-child policy, no exit-code propagation. |
| tini / dumb-init | One child only. Complementary (above), not a replacement. |

With tini underneath, what remains is ~150 lines of asyncio, all of it policy that
would otherwise be configuration in someone else's format.

### 4.4 Where the supervisor lives

**In the harness, not in a published package.** `DOCKER.md:1-7` already establishes
that `Dockerfile`/`compose.yaml`/`entrypoint.sh` are *not* part of the
`workhorse-agent` distribution — they live in the repo and are COPY'd in.
`workhorse/supervisor.py` replaces `entrypoint.sh` in that slot.

If the supervisor lived in groom, groom would have to be baked into the image and
become load-bearing for every container. Today it is optional — no bind, no
sidecar, never fatal (`entrypoint.sh:119`). Keeping the supervisor in the harness
preserves that: **the supervisor always exists; the observer child stays optional.**

### 4.5 Reload against a read-only mount

Today `uv tool install --editable /mnt/groom-src` means the running process imports
**live** from the bind, so a host edit mutates what a running process imports.

```
/mnt/<pkg>-src         ro bind of host source     (never imported)
/opt/live/<pkg>/<gen>  writable copy, installed   (imported)
```

Reload = copy the mount to a **new generation dir**, install from it, restart the
observer child. The run never sees a torn import, and a failed reload leaves the
previous generation to fall back to. The same mechanism serves local pipx
workflows (§4.6) — one implementation, two callers.

### 4.6 pipx as the workflow source

- **PyPI** → `pip install <name>==<version>`. Nothing to mount.
- **local path** (`package_or_url` is a directory) → bind read-only, copy into
  `/opt/live`, install from the copy.

Discovery is per-distribution; `app_paths` enumerates the workflows it provides.

### 4.7 Per-run isolation

One-container-per-run keeps "one workflow per container" (`app.py:283-284`) **true**,
which is fortunate given §2.3. The remaining work is narrow: thread `run_id` into
the sidecar identity so two containers of the same workflow+repo are
distinguishable.

| Resource | Today | Per-run |
|---|---|---|
| container | `<project>-agent-1` | `<workflow>-<runid>` |
| volumes | shared `workspace`/`claude-state`/`runs` | per-run |
| worktree | n/a | `<WORKTREE_ROOT>/<runid>/<repo>` |
| run dir | `/runs/<workflow>-<digest>` | `/runs/<workflow>-<runid>` |

**`claude-state` must be per-run.** It is `HOME`: sharing it means two Claude CLIs
rotating one `.credentials.json`, one `.gitconfig` last-writer-wins, and a single
fixed `boundary-params.json` (`entrypoint.sh:151`) each container truncates and
rewrites. Seed credentials into each from the host mount.

### 4.8 uid/gid

`65534:<host gid>`. The image already does `chmod -R a+rwX` on runtime dirs
(`Dockerfile:127`), so container-internal paths work under any uid. The host side
needs, so run output is usable:

- `git config core.sharedRepository=group` on the bind-mounted repo
- `umask 002` in the supervisor before spawning
- setgid on the worktree root, so new dirs inherit the group

Result: files are `nobody:<yourgroup>`, mode 664/775 — writable from the host by
anyone in that group. The uid is not yours; the access is.

**Verify, do not assume.** Git writes loose objects `0444` by default;
`core.sharedRepository` is what relaxes that. This needs a real container writing
to a real host repo, not an assertion.

## 5. Work items, in order

### 1. Launcher: farrier-generated run targets
`render_agents_mk()` takes no arguments and emits only `agent-install`/`agent-check`
(`launcher.py:32`) — run targets were deleted when workflows left farrier's scope.
They return, driven by pipx discovery (item 4).

Each launch mints a UUID (`/proc/sys/kernel/random/uuid` — no new dependency),
names the container `<workflow>-<runid>`, creates per-run volumes/worktree/run dir,
and exports `AGENT_UID=65534`, `AGENT_GID=$(shell id -g)`.

Depends on item 4 for *what* to generate targets for; the target *shape* is
testable first against a fixed list.

### 2. Supervisor (`workhorse/supervisor.py`), replacing entrypoint.sh
Add `init: true` first — that is the whole reaping/signal story. Then port the 17
responsibilities from §2.1 as ~150 lines of asyncio: two children with distinct
restart policies, exit-code propagation, SIGTERM forwarding. Preflight calls
`kit.workspace` **in-process**, not via subprocess.

**Write the observer-absent test first** — the workflow must run correctly with the
observer child missing or crashed. That test is what keeps groom optional (§4.4).
Delete the dead hook branch (§2.1 #9) rather than porting it.

### 3. Generation-copy install + reload
The `/mnt/<pkg>-src` → `/opt/live/<pkg>/<gen>` mechanism (§4.5), shared by groom and
local pipx workflows. Reload restarts only the observer.

### 4. pipx discovery in farrier
Read `pipx list --json`; classify PyPI vs local; emit what the launcher must mount
and install. Flag an editable local install whose path no longer exists.

Per §8.2 the discovered set is authoritative — there is no selection list to
reconcile against. `agents.yml` supplies only per-workflow settings, so a workflow
with no entry there is still runnable on defaults.

### 5. Worktree checkout
Reinstate in `kit/workspace.py` — as **CLI arguments, not env vars**.
`workflows/README.md:53` prohibits `os.environ` under `src/workhorse_workflows/`
because a value read from the environment is in no checkpoint, so a resume silently
takes a different one. The supervisor is the process boundary and passes
`--source-mode worktree --worktree-root <path>`. This is strictly better than an
env-var design: the value lands in the checkpoint and is reachable from `--params`.

Worktree metadata is **absolute and written on both sides** — the source repo
records the worktree's path and vice versa — so the repo must be bound at its own
host path, and the bind cannot be read-only (`git worktree add` writes into the
source `.git`). Create worktrees **detached**: no workflow knows its branch at
checkout time; the branch is cut later at a workflow node. Never reset a worktree on
resume — unlike a clone in a disposable volume, it holds the operator's real work.

### 6. Branch ownership guard
`checkout()` is at `kit/git.py:80`. N concurrent runs sharing one ref namespace
makes this load-bearing rather than defensive. Git already refuses to check out a
branch another worktree holds — that half is free. `kit/git.py` has three raw
`git.checkout(...)` sites (`:91`, `:183`, `:332`) and `sync_to_origin` moved to
`kit/github.py:150`, so a guard in `checkout()` alone is not airtight; the durable
layer is a per-worktree `reference-transaction` hook via `extensions.worktreeConfig`
+ `core.hooksPath`.

### 6b. Drop epic-branch archival (§8.3)
Replace `_archive_stale_branch` with the four-state rule. Needs a new
`branch_merged(path, branch, base)` helper. Touches `coder/shared/queue.py:237,260`,
the schema docstring at `schemas/queue.py:80`, and the assertion at
`test_workflow.py:596`. **Sequenced here, after item 5**, because the justification
is the worktree model — done earlier it is an unmotivated behavior change.

### 7. Telemetry endpoint (§3.3) and run/telemetry join (§3.4)
Point `OTEL_EXPORTER_OTLP_ENDPOINT` at `host.docker.internal:8787`. Carry `run_id`
on the container row so `_run_facts` can join. Optionally fix `/workflow` discovery
(§3.5) or drop the requirement.

### 8. uid/gid host-usability
`core.sharedRepository`, umask, setgid — verified against a real container writing
to a real host repo (§4.8).

### 9. Docs
`DOCKER.md:11` asserts the agent "works against its own clone (never a host working
tree)" — deliberately inverted by item 5. Also `workhorse/docs/DEVELOPMENT.md` if
the entrypoint is described there.

## 6. Verification gate

Every item ends green:

```bash
ruff check .          # from the repo root
make check-public
```

Test suites **must run separately** — they collide when combined (13 collection
errors, each subproject has its own pytest config):

```bash
uv run pytest workhorse/tests -q
uv run pytest farrier/tests -q
uv run pytest ostler/tests -q
uv run pytest workflows/tests -q
```

Operational notes learned the hard way:

- In a fresh git worktree, `uv sync` alone leaves the tree broken
  (`ModuleNotFoundError: stablemate_core`). Use **`uv sync --all-packages`**.
- Docker is reachable and the operator is uid 1000 — **exercise the real container**
  where a change has runtime surface. Rendering a compose file is not verification.
- `make check-public` resolves private names via `--git-common-dir`, so it works
  from a linked worktree.

## 7. Constraints from the repo's own docs

- **Root `CLAUDE.md`** — ruff clean from the repo root, zero findings; fix rather
  than silence. Public repo: neutral placeholders only (`acme`, `example.com`).
- **`workhorse/CLAUDE.md`** — fail soft for unattended runs. Stay
  repository-agnostic *and* workflow-agnostic: no workflow field names in
  `workhorse/**`. If the engine needs a capability, add a **parameterised
  primitive** (`stack.py`'s `ensure_stack` taking a manifest dict is the model).
- **`workflows/README.md:53`** — no `os.environ` under `src/workhorse_workflows/`.
  The process boundary translates env → arguments. One exception:
  `kit/credentials.py`, because a secret must never become a checkpointed param.
- **`stablemate-repo-docs` skill** — `docs/features/**` is ostler's OKF graph; plans
  live here in `docs/plans/`.
- Comments explain **why**, at the density of the surrounding code.

## 8. Resolved questions

Recorded with rationale, because each was a real fork and the reasoning is the
part worth keeping.

### 8.1 Checkpoints — keep them; drop only digest resolution

"Container runs need checkpoints less" is true of *auto-resume by params digest* —
an interactive nicety (re-run the same command, continue where you stopped) that a
UUID launch deliberately bypasses. It is **not** true of *checkpointing itself*.

The design target is a week-long unattended run, and the checkpoint is what carries
it across a host reboot or an OOM kill. Those runs are the least able to afford
starting over, and nobody is watching to notice that they did.

**Decision: containers keep writing checkpoints every transition. A `docker
restart` resumes the same UUID run. What the UUID kills is digest resolution, not
durability.** No change to `derive_run_id` (§3.1).

### 8.2 `agents.yml` — configuration only; discovery decides what exists

`agents.yml` today has **no** `workflow:` key, and farrier reads none — the
selection concern was fully removed when workflows became distributions. It is not
being restored.

**Decision: the installed pipx set is the single source of truth for which
workflows are runnable.** Farrier generates a target per discovered workflow.
`agents.yml` carries only per-workflow *settings* for those that need them (branch,
worktree root, env passthrough) — never a selection list.

The reason is drift: a selection list is a second source of truth that goes stale
the moment someone `pipx install`s or uninstalls, and a stale list fails at
generation time with a confusing "workflow not found" rather than at the moment the
set actually changed. Discovery cannot drift from itself.

### 8.3 Epic-branch archival — drop it, use the four-state rule

`_archive_stale_branch` (`coder/shared/queue.py:260`) renames a leftover
`feat/<epic>` aside to `archive/<epic>-<sha>`, with collision suffixing
(`_archive_name`, `:237`). It is documented in a typed schema
(`schemas/queue.py:80`) and asserted by a test (`test_workflow.py:596`).

Its premise is that refs it creates are disposable — true when they land in a
container-local clone that `down -v` destroys. **Under worktrees they land in the
operator's real repo**, so every re-run leaves a permanent `archive/*` ref in
`git branch`. The step was designed under an assumption the worktree model
invalidates.

**Decision: replace it with an explicit four-state rule.**

| State of existing `feat/<epic>` | Action |
|---|---|
| Held by another worktree | **Hard error** — git refuses anyway; surface it clearly |
| Exists, already merged into base | Safe to reset to base and reuse |
| Exists, unmerged, not ours | **Hard error** — real work; a human decides |
| Exists, this run resuming | Check out, no reset |

This is more precise than archival was: archival renamed *every* existing branch,
merged or not, to defend against one case (a squash-merged branch that has since
diverged). The table handles that case directly and refuses the genuinely dangerous
one instead of silently renaming past it.

Needs a `branch_merged(path, branch, base)` helper — none exists; `commits_ahead`
answers a different question. `rename_branch` and `short_sha` stay in the kit, just
uncalled from here. **Sequence after item 5**, since the justification is the
worktree model; doing it earlier is a behavior change with no motivating context.
Removing it also converges coder onto author's resume semantics, which already
check out an existing branch without resetting.
