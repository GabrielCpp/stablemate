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

### 1. Launcher: farrier-generated run targets — **done**
`render_agents_mk()` takes no arguments and emits only `agent-install`/`agent-check`
(`launcher.py:32`) — run targets were deleted when workflows left farrier's scope.
They return, driven by pipx discovery (item 4).

Each launch mints a UUID (`/proc/sys/kernel/random/uuid` — no new dependency),
names the container `<workflow>-<runid>`, creates per-run volumes/worktree/run dir,
and exports `AGENT_UID=65534`, `AGENT_GID=$(shell id -g)`.

Depends on item 4 for *what* to generate targets for; the target *shape* is
testable first against a fixed list.

**As built.** `render_agents_mk(workflows: Sequence[str] = ())`. Item 4 will pass the
discovered names; the empty default renders the adapter-only launcher, which is
also exactly what "discovery found nothing" must render as — so the no-workflow case
is not a placeholder, it is the real behavior §8.2 asks for. Kept the plan's
ordering: a list of names was all item 1 needed, and widening it to richer
discovery records later is mechanical.

Four decisions worth the next reader's time:

- **Per-run volumes come from the compose *project name*, not from compose.yaml.**
  `docker compose -p <workflow>-<runid>` namespaces every named volume by project,
  so `workspace`/`claude-state`/`runs` become per-run with *no* change to
  compose.yaml's `volumes:` block. §4.7's table asked for per-run volumes without
  saying how; this is how, and it costs nothing.
- **The operating handle is the project, not the container name.** §4.7's table says
  container `<workflow>-<runid>`; compose actually names it
  `<workflow>-<runid>-agent-1`. Setting `container_name:` to force the shorter form
  was rejected — the project name already keys the volumes *and* the container, so
  one handle addresses everything a run owns. `RUN=<workflow>-<runid>` is that
  handle.
- **Worktree creation moved to item 5.** §5.1 lists it here, but nothing consumes a
  worktree until `kit/workspace.py` learns `--source-mode worktree`. A `mkdir` and a
  bind mount that no process reads is churn, and would have had to be re-shaped
  once item 5 settled the flag names. Item 1 owns UUID + project + uid/gid + run id.
- **§3.1's fix landed here rather than waiting for the supervisor.** `compose.yaml`
  gained `AGENT_RUN_ID: ${AGENT_RUN_ID:-}` and `entrypoint.sh` forwards it as
  `--run-id`. Item 2 re-homes that line into the supervisor; doing it now is what
  makes item 1 verifiable end-to-end instead of a rendered string. Compose
  interpolates at container-*create* time, so the id is baked into the container
  config and `docker restart` resumes the same run — the restart semantics §3.1
  wanted, for free.

**Added beyond §5.1:** `agent-runs` / `agent-logs` / `agent-stop` / `agent-clean`,
each addressing one run by `RUN=`. With N runs in flight there is otherwise no way
to find, follow or stop one; `agent-stop` deliberately leaves the volumes so
`docker restart` resumes, and `agent-clean` is the destructive `down -v`.

### 2. Supervisor (`workhorse/supervisor.py`), replacing entrypoint.sh — **done**
Add `init: true` first — that is the whole reaping/signal story. Then port the 17
responsibilities from §2.1 as ~150 lines of asyncio: two children with distinct
restart policies, exit-code propagation, SIGTERM forwarding. Preflight calls
`kit.workspace` **in-process**, not via subprocess.

**Write the observer-absent test first** — the workflow must run correctly with the
observer child missing or crashed. That test is what keeps groom optional (§4.4).
Delete the dead hook branch (§2.1 #9) rather than porting it.

**As built.** `workhorse/supervisor.py` + `workhorse/tests/test_supervisor.py`;
`entrypoint.sh` deleted, `ENTRYPOINT` is now the venv's interpreter on the
supervisor, `init: true` is on the service. All 17 responsibilities are re-homed;
#9's dead hook branch was deleted, not ported.

**Verified in the real container, not by asserting on a string.** `ps -ef` inside a
running container shows `/sbin/docker-init` at pid 1 with the supervisor as its
child, so `init: true` does what §4.3 said it would. Better still, the run that
verified this had its **observer crash on startup** for an unrelated reason
(below) — so the guarantee item 2 exists for was demonstrated rather than mocked:
the supervisor logged `observer exited with 1; not restarting it`, the workflow ran
to completion, and exit 0 propagated. The run landed in `/runs/coder-v3` from
`--run-id v3`, which is §3.1 closed end to end.

Three corrections to §4, each found by running it:

- **§4.2's "net deletion" does not hold — the one-shot exit push stays.** The claim
  was that `--exit-code` exists only because the sidecar is not the parent, and
  collapses into `await proc.wait()`. Being the parent tells the *supervisor* the
  exit code; it does not tell *groom*, and the sidecar's only channel to groom is
  the WebSocket the sidecar itself holds. Removing the one-shot would mean inventing
  a supervisor→observer channel: more code, not less. It is ported as-is, as a
  best-effort spawn under a timeout that can never change the container's exit
  status.
- **The workflow script is addressed by path, not by name.** The image never put
  `/app/.venv/bin` on `$PATH`; `entrypoint.sh` hid that behind `uv run`, which
  resolves it at the cost of a step on every start. A bare `workhorse-coder`
  therefore resolved to nothing. The supervisor uses the sibling of its own
  interpreter — it already knows which environment it imported the workflow package
  from — and refuses with `no such workflow: <name> (looked for <path>)` when the
  image does not carry it.
- **`CODER_WORKSPACE` / `CODER_DOCS_PATH` are gone, replaced by `AGENT_PARAM_<NAME>`.**
  §7 forbids a workflow's field names anywhere in `workhorse/**`, and the supervisor
  lives there — porting that `printf` verbatim would have written `coder`'s
  vocabulary into the harness. The prefix is the parameterised primitive §7 asks
  for: `AGENT_PARAM_DOCS_PATH=/docs` becomes `{"docs_path": "/docs"}`, and any
  workflow's params are expressible without this file knowing that workflow exists.
  The checkout's workspace file now comes from the same resolved params rather than
  a second variable, so a run and its own checkout cannot disagree about the
  manifest. **This is a breaking change for an operator with `CODER_WORKSPACE` set**
  — item 9 owns saying so in DOCKER.md.

**Added beyond §5.2:** `faulthandler.register(SIGUSR1)`. A wedged supervisor in an
unattended container was otherwise undiagnosable — no debugger is installed and `ps`
only says the process exists. `docker kill --signal=SIGUSR1 <container>` now dumps
its stack to the container log. (Written while diagnosing exactly that.)

**Two defects found, neither in scope here:**

1. **The uid decision (§4.1/§4.8) cannot read the credentials mount.**
   `~/.claude/.credentials.json` is mode `600`, owned by the operator. A container
   running as `65534:<host gid>` cannot read it — group access does not help at
   `600` — so the first real run died on `PermissionError`. The supervisor now warns
   with an actionable message instead of a traceback, but **the uid choice itself is
   unresolved**: either the operator relaxes that file's mode, or the container runs
   as the operator's uid after all (which is what compose did before §4.1 changed
   it), or the launcher pre-stages a group-readable copy. **Item 8 must decide**;
   §4.8 only ever considered writes.
2. **groom's sidecar cannot import under `--no-sources`.** `groom/gates.py` does
   `from workhorse import gates`, but the isolated tool venv resolves
   `workhorse-agent` from **PyPI**, and the released 0.8.0 has no `gates` module —
   only this tree does. So the sidecar has been dying on startup in every container,
   silently, because the old shell discarded its stdout. Pre-existing and unrelated
   to this plan; item 3 rebuilds this install path and is where it gets fixed.

### 3. Generation-copy install + reload — **done**
The `/mnt/<pkg>-src` → `/opt/live/<pkg>/<gen>` mechanism (§4.5), shared by groom and
local pipx workflows. Reload restarts only the observer.

**As built.** `workhorse/livesource.py` + `workhorse/tests/test_livesource.py`.
`LiveSource(name, mount, root, with_editable)` and `refresh()` = stage → install →
prune. The supervisor calls it once at start and again on every reload, *between*
the observer's exit and its restart, so the process that comes back is importing a
directory that was written once and completed.

Decisions:

- **Generations are numeric and zero-padded** (`0001`, `0002`), so chronological
  order is lexical order and `generations()` is a plain sort rather than a stat of
  every entry.
- **Two generations are kept, not one.** The obvious `keep=1` deletes the directory
  the *currently running* process is importing from — precisely the failure this
  module exists to prevent. The previous generation stays until the one after it
  lands.
- **A failed install deletes its own staged copy** and returns None, leaving the
  previous generation installed. So a broken edit costs a restart, not the observer.
  The copy is removed rather than kept so the next generation number does not skip.
- **`.git`/`.venv`/`node_modules`/`__pycache__` are not copied.** The first can dwarf
  the source, the middle two are rebuilt by the install anyway, and foreign bytecode
  is worse than useless.
- `/opt/live` is **container-local, not a volume**. A copy of the host source belongs
  to this container's life; a fresh container should re-stage rather than inherit a
  generation staged from some earlier edit. The Dockerfile makes it world-writable
  alongside the other runtime dirs.

**The groom import defect (item 2's finding #2) is fixed here**, and the fix is a
correctness argument rather than a build workaround. The sidecar reads the gate files
the *engine* writes, so it must be built against the same engine: the install now
passes `--with-editable /app/workhorse` instead of letting the isolated tool venv
resolve `workhorse-agent` from PyPI. A released engine in the observer's venv and an
in-tree one in the run's is a disagreement waiting to happen — and it had already
happened, since `groom/gates.py` imports `workhorse.gates`, which the release does
not carry.

**Verified in the real container, at the level that matters.** Reading the tool
venv's `.pth` shows it resolving to `/opt/live/groom/0001` and **not**
`/mnt/groom-src` — which is §4.5's entire claim, checked rather than assumed. In the
same run the sidecar started cleanly and survived to teardown (`observer exited with
-15`, i.e. the supervisor's own SIGTERM), where the previous build had it dying on
`ImportError` before the workflow began.

**Not verified end-to-end:** a `reload` driven by a real groom dashboard over the
socket. The supervisor's half is tested (restage-then-restart, and a raising refresh
still restarting on the old generation); groom's half is unchanged by this item.

### 4. pipx discovery in farrier — **done**
Read `pipx list --json`; classify PyPI vs local; emit what the launcher must mount
and install. Flag an editable local install whose path no longer exists.

Per §8.2 the discovered set is authoritative — there is no selection list to
reconcile against. `agents.yml` supplies only per-workflow settings, so a workflow
with no entry there is still runnable on defaults.

**As built.** `farrier/farrier/pipx.py` + a `farrier workflows [--names]` subcommand,
`farrier/tests/test_pipx.py`, and `farrier/tests/test_launcher_make.py` (real `make`
against the rendered launcher).

#### The reversal: discovery happens at *make* time, not at render time

**Item 1 assumed farrier would bake the discovered list into `.agents/agents.mk`.
That is wrong, and item 1's `render_agents_mk(workflows)` parameter is gone.**

`.agents/agents.mk` is **tracked** — farrier's gitignore block (`outputs.py:313`)
deliberately excludes it while ignoring the context manifests. The installed pipx set
is a property of the *machine*. Baking one into the other gives you a tracked file
that differs per developer, churns on every `pipx install`/`uninstall`, fails
`make agent-check` on any machine whose set differs — and, for a workflow installed
from a local path, commits somebody's home directory into a **public** repo.

So the rendered file is byte-identical everywhere and asks at parse time:

```make
ifneq ($(filter agent-run-%,$(MAKECMDGOALS)),)
AGENT_WORKFLOWS := $(shell $(FARRIER) workflows --names)
$(foreach wf,$(AGENT_WORKFLOWS),$(eval $(call agent_run_target,$(wf))))
endif
```

Three things this buys, each deliberate:

- **Real targets, not a pattern rule.** `$(eval)` generates `agent-run-coder` as an
  actual target, so `make agent-run-typo` gets make's own *No rule to make target*.
  An `agent-run-%` pattern rule matches anything and would launch a container for a
  workflow that does not exist. §8.2 asked for "a target per discovered workflow";
  this is that, without writing the names down.
- **Gated on the goal.** `farrier workflows` shells out to pipx (~0.4s measured, plus
  interpreter start). This file is `include`d by the repo's root Makefile, so an
  unconditional `$(shell …)` would tax every `make <anything>`. A test asserts `make
  help` succeeds with `FARRIER=/nonexistent-binary`.
- **`agent-workflows`** is the human surface, since the run targets no longer show up
  in `make help` (which greps the file). It prints each distribution, its version,
  and where it was installed from.

Other decisions:

- **Classification is by shape, not by existence.** A local install whose directory
  was deleted still classifies as local and reports `missing`, rather than falling
  through to "looks like a PyPI name" — which would have the container try to
  `pip install /home/dev/gone`. `farrier workflows` exits 1 when any install is
  stale, because nothing else reports it until a container fails on the mount.
- **`workhorse-agent` and `workhorse-workflows` match the script prefix but are not
  workflows**, so they are excluded by name. `stablemate-library` needs no exclusion —
  it exposes no apps at all.
- **Every failure path returns an empty list.** No pipx, a non-zero exit, unparseable
  JSON, a renamed key after a pipx upgrade: the honest answer from inside a Makefile
  is "no workflows are discoverable", never a traceback in the middle of `make`.

**Verified with real `make`,** not by asserting on the rendered string: the file
parses, a discovered name becomes a target that reaches `docker compose` with the
right `WORKFLOW`, a hyphenated name (`okf-builder`) survives `$(eval)`'s re-parse, an
undiscovered name fails, and an unrelated target never invokes discovery. The
`--names` output was also checked against this machine's actual `pipx list --json`.

**Still open — the mount/install half.** Discovery reports `local_path`, but nothing
consumes it yet: for a workflow installed from a host directory the launcher must
bind that directory and the container must install from a copy (livesource, item 3,
is already the mechanism — `LiveSource` is generic over the package for exactly this
reason). Sequenced with item 5, which is when the launcher grows bind mounts anyway.

**Tech debt found, out of scope:** `workhorse-workflows` pins `workhorse-agent>=1,<2`
but the newest release is `0.8.0`, so `pipx install workhorse-workflows` cannot
resolve — from PyPI or from a local checkout. Nothing in this plan depends on it
(the image installs from the workspace), but it means the *documented* install path
is broken today.

### 5. Worktree checkout — **done**
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

**Done.** `kit/workspace.py` gained `source_mode` + `worktree_root` (arguments, with
`--source-mode`/`--worktree-root` on its `__main__`), the supervisor translates
`AGENT_SOURCE_MODE`/`AGENT_WORKTREE_ROOT` into them, compose.yaml binds the host repo
at its own path, and the launcher cuts a per-run worktree.
`workflows/tests/test_kit_worktree.py` covers it against real git repos — worktree
registration is written by absolute path on both sides, so a fake would only assert
on itself.

**One bind covers both sides.** The worktree root defaults *inside* the repo
(`$(AGENT_REPO)/.agents/worktrees/<runid>`), and the repo is bound source==target.
That single mount therefore puts the source repo *and* every run's tree at paths the
container and the host agree on — which is the whole requirement, without a second
mount to keep in sync. §4.7's table put the worktree root outside the repo; inside is
strictly better and costs nothing.

**A compose bind cannot be conditional**, so the repo bind is declared once with
`source: ${AGENT_REPO_HOST_DIR:-.}` / `target: ${AGENT_REPO_HOST_DIR:-/mnt/unused-host-repo}`.
Set (worktree mode) it binds the repo at its own path; unset (clone mode) it binds
the compose file's own directory somewhere nothing reads. Verified with
`docker compose config` in both states. The alternative — the launcher generating a
per-run override file — was rejected as reintroducing generated compose fragments for
one mount.

**`AGENT_REPO_DIR` points at the run's own tree, not the shared source.** It is
`repo_dir`, workhorse's one universal input; leaving it at the host repo would put N
agents in one working directory, which is exactly what the worktrees exist to stop.

**Bug found and fixed on the way:** `REPO_URL`/`REPO_NAME`/`REPO_BRANCH` were read by
the entrypoint but **never declared in `compose.yaml`**, and compose does not pass
host environment through unless a service declares it. So the single-repo checkout
path could not be reached from compose at all — every container logged "no workspace
file and no repo url given". Now declared alongside the new variables.

#### Verified end to end, twice over

A container cut a `git worktree` of a real host repo, and on the **host** side
`git worktree list` shows it at a host-valid absolute path, detached at `main`'s
commit, with `.git` a file pointing back into the source repo. That is §4.5's
both-sides-absolute requirement checked from the side that would have been broken.

Then the actual premise of the plan: **two containers of the same workflow, launched
concurrently against one host repo, both exited 0** — each with its own detached
worktree (both registered host-side), its own volume set
(`hello-alpha_*` / `hello-beta_*`), and its own run directory
(`hello-world-alpha` / `hello-world-beta`, i.e. the launcher's UUID reaching all the
way through with no digest collision).

**Unrelated failure seen and discounted:** with the host repo under `/tmp/claude-1000`,
the Claude CLI refuses to run (`Temp directory … is owned by uid 0`). It is a property
of that path, not of worktree mode; the re-run under `$HOME` was clean.

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
