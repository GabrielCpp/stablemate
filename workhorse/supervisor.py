#!/usr/bin/env python3
"""Container supervision: preflight, then two children with different lifecycles.

This replaces `entrypoint.sh`. Like the Dockerfile and compose.yaml beside it, it is
**not** part of the `workhorse-agent` distribution — it lives in the repo and is
COPY'd into the image, and nothing outside a container imports it.

It is not PID 1. `init: true` on the compose service puts Docker's bundled tini
there, which is where zombie reaping and signal delivery belong — a battle-tested C
binary, one line of yaml, nothing to maintain. What is left is *policy*, and policy
is why no off-the-shelf supervisor fits: supervisord, s6 and circus are all
**service** supervisors that keep processes up, and this container's main child is a
**job that completes whose exit code has to become the container's**.

    PID 1: tini
      └── supervisor.py            (this file)
            ├── preflight          auth seed, git identity, workspace checkout
            ├── observer           optional; restarted on the reload exit code
            └── run                the workflow; its exit code is the container's

The two children differ in every way that matters, which is the whole reason this
is code rather than configuration:

* The **run** is the point. Its exit code is the container's, a SIGTERM must reach
  it so `docker stop` stays graceful, and when it ends the container ends.
* The **observer** is optional and never fatal. It is groom's sidecar, which
  requests a reload by *exiting* with a reserved code (a process cannot cleanly
  re-exec from its own imported source), so "restart it" is the supervisor's job.
  Absent, crashed or crash-looping, the run must be unaffected — that is what keeps
  groom optional rather than load-bearing for every container.

**The environment stops here.** Nothing inside a run may read `os.environ`: a value
read from the environment is in no checkpoint, so a resume silently takes a
different one, and `--params` cannot set it. This process is the boundary that
translates the operator's environment into arguments, once, on the way in.
"""
from __future__ import annotations

import asyncio
import contextlib
import faulthandler
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import livesource
from workhorse_workflows.kit import workspace

log = logging.getLogger("supervisor")

# groom's sidecar signals "restart me, my source changed" by exiting with this code,
# chosen to sit outside the normal 0/1/2, 126/127 and 128+signal ranges. Any other
# exit means stop, so a reload that lands on unimportable code fails safe instead of
# storming (groom/groom/sidecar.py::RELOAD_EXIT_CODE).
RELOAD_EXIT_CODE = 3

# A volume this container cannot write is not a workflow error to be recovered from
# deep in a node — it is a misconfigured mount. Its own exit code, so an operator can
# tell it apart from a run that failed.
NOT_WRITABLE_EXIT_CODE = 13

# How long the best-effort "the workflow exited" notice, and the observer's own
# shutdown, may take before teardown stops waiting for them.
TEARDOWN_TIMEOUT_S = 10.0

# Prefix for operator-supplied run parameters: AGENT_PARAM_DOCS_PATH=/docs becomes
# `{"docs_path": "/docs"}` in the params file. Deliberately workflow-agnostic — the
# harness must never learn one workflow's vocabulary, and this file lives under
# workhorse/, where that rule applies.
PARAM_ENV_PREFIX = "AGENT_PARAM_"


@dataclass(frozen=True)
class Layout:
    """Where this container keeps things. Injected rather than hardcoded so the
    preflight steps below are exercisable against a tmpdir."""

    # HOME. A named volume, so Claude's session history, the seeded credentials and
    # the onboarding flag survive a restart or a reboot.
    claude_home: Path = Path("/claude-state")
    workspace: Path = Path("/workspace")
    runs: Path = Path("/runs")
    # Read-only host mounts, absent unless the operator provided them.
    settings_src: Path = Path("/mnt/claude-settings.json")
    credentials_src: Path = Path("/mnt/claude-credentials.json")
    observer_src: Path = Path("/mnt/groom-src")
    # Where a bind's per-generation copies are staged. Container-local rather than a
    # volume: a copy of the host source belongs to this container's life, and a fresh
    # one should re-stage rather than inherit some earlier edit.
    live_root: Path = Path("/opt/live")
    # The image's own workhorse checkout, for packages that must be built against
    # the same engine the run uses rather than a released one.
    image_workhorse: Path = Path("/app/workhorse")

    @property
    def claude_dir(self) -> Path:
        return self.claude_home / ".claude"

    @property
    def credentials(self) -> Path:
        return self.claude_dir / ".credentials.json"

    @property
    def onboarding_stub(self) -> Path:
        return self.claude_home / ".claude.json"

    @property
    def boundary_params(self) -> Path:
        return self.claude_home / "boundary-params.json"

    @property
    def tool_bin(self) -> Path:
        return self.claude_home / ".local" / "bin"

    @property
    def observer(self) -> Path:
        return self.tool_bin / "groom-sidecar"


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #


def require_writable(paths: Sequence[Path]) -> None:
    """Fail loudly, here, when a mount is not writable by this uid.

    This container never runs as root and never repairs volume ownership itself.
    The uid is not fixed either — compose passes nobody's uid with the operator's
    gid — so the image makes these mountpoints world-writable and a *fresh* volume
    inherits that mode. A volume created by an older image still carries `nobody`
    ownership and trips this under any other uid; remove it or chown it to migrate.
    """
    for path in paths:
        if not path.is_dir() or not os.access(path, os.W_OK):
            log.error(
                "%s must be writable by uid %d:%d. Prepare the volume's ownership "
                "before starting this non-root container.",
                path, os.getuid(), os.getgid(),
            )
            raise SystemExit(NOT_WRITABLE_EXIT_CODE)


def seed_claude_home(layout: Layout, env: Mapping[str, str]) -> None:
    """Prepare HOME so a headless Claude CLI starts authenticated and un-prompted.

    Auth has three sources and the priority between them is the whole point: an
    explicit token wins; otherwise credentials *already in the volume* win over the
    host's copy, because the CLI refreshes and rotates that token in-volume across
    runs and overwriting it with a stale host copy would log the container out. The
    host file is therefore a one-time seed, not a sync.
    """
    layout.claude_dir.mkdir(parents=True, exist_ok=True)

    # settings.json is config, not a secret, so it refreshes every start.
    if layout.settings_src.is_file():
        shutil.copyfile(layout.settings_src, layout.claude_dir / "settings.json")

    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        log.info("auth: using CLAUDE_CODE_OAUTH_TOKEN")
    elif layout.credentials.is_file():
        log.info("auth: using credentials already in the claude-state volume")
    elif layout.credentials_src.is_file():
        # A credentials file the host keeps at mode 600 is unreadable to any uid but
        # its owner's — and this container deliberately does not run as the operator
        # (see the uid discussion in the internal container-concurrent-runs plan §4.8).
        # That is a mount the operator has to fix, so say which one and how, rather
        # than dying in a traceback that names only `shutil.copyfile`.
        try:
            shutil.copyfile(layout.credentials_src, layout.credentials)
        except OSError as exc:
            log.warning(
                "auth: cannot read %s (%s). This container runs as uid %d, which the "
                "file's mode does not admit — make it group-readable by gid %d, or "
                "export CLAUDE_CODE_OAUTH_TOKEN instead.",
                layout.credentials_src, exc.strerror, os.getuid(), os.getgid(),
            )
        else:
            log.info("auth: seeded subscription credentials into the claude-state volume")
            layout.credentials.chmod(0o600)
    else:
        log.warning(
            "no CLAUDE_CODE_OAUTH_TOKEN and no credentials mounted at %s — "
            "the Claude CLI will not be authenticated.",
            layout.credentials_src,
        )

    # Skip the interactive onboarding flow. A minimal stub is enough; the account is
    # resolved from the token or the credentials file.
    if not layout.onboarding_stub.exists():
        layout.onboarding_stub.write_text(
            '{"hasCompletedOnboarding": true}\n', encoding="utf-8"
        )


def configure_git(env: Mapping[str, str]) -> None:
    """Global git config for commits made inside the container.

    `safe.directory '*'` is required regardless of where the checkout lands: this
    uid owns none of the bind-mounted host paths a run may touch, and git refuses to
    operate in a repo it believes belongs to someone else. It has to run before
    anything touches a repo.
    """
    _git("config", "--global", "--add", "safe.directory", "*")
    _git("config", "--global", "user.email", env.get("GIT_AUTHOR_EMAIL") or "agent@example.com")
    _git("config", "--global", "user.name", env.get("GIT_AUTHOR_NAME") or "Agent")


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True)


def observer_source(layout: Layout) -> livesource.LiveSource:
    """groom's sidecar, as a package installed from its host bind.

    `with_editable` carries **this image's** workhorse rather than letting the
    isolated tool venv resolve `workhorse-agent` from PyPI. That is a correctness
    requirement, not a build convenience: the sidecar reads the gate files the engine
    writes, so a released workhorse in the sidecar's venv and an in-tree one in the
    run's means the two can disagree about the format. They did — `groom/gates.py`
    imports `workhorse.gates`, which the released distribution does not yet have, so
    the sidecar died on startup in every container and the old shell threw the
    traceback away.
    """
    return livesource.LiveSource(
        name="groom",
        mount=layout.observer_src,
        root=layout.live_root / "groom",
        with_editable=(layout.image_workhorse,),
    )


def install_observer(layout: Layout) -> list[str] | None:
    """Stage and install the observer, and return how to run it.

    Failure is swallowed on purpose at every step — no bind, a copy that failed, a
    broken install, no network for its dependencies — because a container with no
    observer is a supported configuration, not a degraded one. `livesource.refresh`
    already reports None rather than raising for each of those.
    """
    livesource.refresh(observer_source(layout), layout.tool_bin)
    return [str(layout.observer)] if os.access(layout.observer, os.X_OK) else None


def run_params(env: Mapping[str, str]) -> dict[str, str]:
    """The operator's environment, as run parameters.

    `AGENT_PARAM_DOCS_PATH=/docs` becomes `{"docs_path": "/docs"}`. The prefix
    convention exists so this file needs no table of any particular workflow's
    variable names: workhorse is shared by every workflow and must never learn the
    shape of one. Empty values are dropped rather than passed as `""`, which a
    workflow would read as "explicitly blank" rather than "unset".
    """
    return {
        key[len(PARAM_ENV_PREFIX):].lower(): value
        for key, value in sorted(env.items())
        if key.startswith(PARAM_ENV_PREFIX) and value
    }


def write_boundary_params(path: Path, params: Mapping[str, str]) -> Path:
    """Write the params file the run is launched with.

    A file rather than inline `--params`, so an explicit `--params` among the
    operator's own trailing arguments still wins — the CLI merges the file first,
    then inline.
    """
    path.write_text(json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def checkout(env: Mapping[str, str], params: Mapping[str, str]) -> None:
    """Materialise the working trees the run needs, before the engine starts.

    Called **in-process** rather than as a subprocess: it is ordinary Python from a
    package this image already installs, and a subprocess bought nothing here but a
    second interpreter start and a traceback thrown away. The workspace manifest
    comes from the resolved run params rather than a second environment variable, so
    the run and its own checkout cannot disagree about which one they are using.

    This call is the whole reason the environment stops at this process. Nothing
    under the run may read `os.environ` — a value read there is in no checkpoint, so
    a resume days later silently takes a different one — so each of these crosses as
    an argument, once, here.
    """
    workspace.checkout_workspace(
        params.get("workspace_file", ""),
        env.get("WORKSPACE_ROOT") or "/workspace",
        repo_url=env.get("REPO_URL", ""),
        repo_name=env.get("REPO_NAME") or "repo",
        repo_branch=env.get("REPO_BRANCH") or "main",
        source_mode=env.get("AGENT_SOURCE_MODE") or "clone",
        worktree_root=env.get("AGENT_WORKTREE_ROOT") or "",
    )


def run_command(
    env: Mapping[str, str],
    params_file: Path,
    extra: Sequence[str],
    *,
    bin_dir: Path | None = None,
) -> list[str]:
    """The workflow's own console script, and its arguments.

    There is no generic `workhorse run <name>`: each workflow in the installed
    distribution binds its own command, so an unset or misspelled `$WORKFLOW` fails
    at spawn rather than as a resolution error part-way into a run.

    The script is addressed by path, as a sibling of the interpreter running this
    file, rather than by name through `$PATH`. The image does not put the venv's
    `bin/` on `$PATH` — the shell this replaced papered over that with `uv run`, at
    the cost of a resolution step on every start — and the supervisor already knows
    exactly which environment it imported the workflow package from.
    """
    name = env.get("WORKFLOW", "")
    if not name:
        raise SystemExit("set WORKFLOW to the workflow to run, e.g. coder")
    script = (bin_dir or Path(sys.executable).parent) / f"workhorse-{name}"
    if not os.access(script, os.X_OK):
        raise SystemExit(f"no such workflow: {name} (looked for {script})")
    cmd = [str(script), "run"]
    if env.get("AGENT_RUNS_DIR"):
        cmd += ["--runs-dir", env["AGENT_RUNS_DIR"]]
    # Explicit, because workhorse's fallback digests the run params and every
    # container's are identical — without it N concurrent containers all resolve to
    # one run dir, and the second resumes or deletes the first.
    if env.get("AGENT_RUN_ID"):
        cmd += ["--run-id", env["AGENT_RUN_ID"]]
    cmd += ["--params-file", str(params_file)]
    return cmd + list(extra)


# --------------------------------------------------------------------------- #
# Supervision
# --------------------------------------------------------------------------- #


@dataclass
class Child:
    """One supervised process, plus the two facts a signal handler needs.

    `stopping` is set by the handler and re-read after the spawn returns, so a
    SIGTERM arriving *during* a spawn is honoured rather than lost in the window
    between "decided to start" and "have a pid to signal".
    """

    cmd: Sequence[str]
    env: Mapping[str, str] = field(default_factory=dict)
    proc: asyncio.subprocess.Process | None = None
    stopping: bool = False

    async def start(self) -> asyncio.subprocess.Process:
        self.proc = await asyncio.create_subprocess_exec(*self.cmd, env=dict(self.env))
        if self.stopping:
            self.signal(signal.SIGTERM)
        return self.proc

    def signal(self, sig: int) -> None:
        self.stopping = True
        proc = self.proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.send_signal(sig)


async def supervise_observer(
    child: Child,
    *,
    reload_code: int = RELOAD_EXIT_CODE,
    on_reload: Callable[[], object] | None = None,
) -> None:
    """Keep restarting the observer for as long as it asks to be reloaded.

    Only the reserved reload code restarts it. Anything else — a clean exit, a
    crash, an unimportable module after a bad edit — ends the loop for good, which
    is what makes a broken reload fail safe rather than spin. Every outcome here is
    non-fatal by construction: this coroutine returns, it never raises into the
    run's exit code.

    `on_reload` is what actually picks up the operator's edit: it re-stages the host
    bind into a new generation and installs that (see livesource). It runs *between*
    the exit and the restart, so the process that comes back is importing a directory
    written once and complete, never the bind the operator is still editing.
    """
    while not child.stopping:
        proc = await child.start()
        rc = await proc.wait()
        if rc != reload_code:
            if rc:
                log.warning("observer exited with %d; not restarting it", rc)
            return
        log.info("observer requested a reload")
        if on_reload is not None:
            # A refresh that fails leaves the previous generation installed, so the
            # restart below still has something to run. Never fatal.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(on_reload)


async def supervise(
    run: Child,
    observer: Child | None = None,
    *,
    exit_notice: Callable[[int], Sequence[str]] | None = None,
    on_reload: Callable[[], object] | None = None,
    timeout_s: float = TEARDOWN_TIMEOUT_S,
) -> int:
    """Run both children and return the run's exit code as the container's.

    The observer starts first, so it is watching before the run produces anything,
    but it is never waited *on*: the run finishing is what ends the container, and
    an observer that is missing, crashed or looping must not change that. It is torn
    down afterwards, so it is still alive while the exit notice goes out.
    """
    loop = asyncio.get_running_loop()
    observer_task = (
        asyncio.create_task(supervise_observer(observer, on_reload=on_reload))
        if observer is not None
        else None
    )

    # Installed before the spawn, so a `docker stop` during startup still reaches the
    # run rather than being dropped. Only the run is signalled here; the observer is
    # torn down in order below, after the notice.
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, run.signal, sig)

    proc = await run.start()
    rc = await proc.wait()
    log.info("workflow exited with %d", rc)

    # Best-effort "the workflow exited" push. It must never change the container's
    # own exit status, and never delay teardown indefinitely.
    if exit_notice is not None:
        with contextlib.suppress(Exception):
            async with asyncio.timeout(timeout_s):
                notice = await asyncio.create_subprocess_exec(
                    *exit_notice(rc), env=dict(run.env),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                await notice.wait()

    if observer is not None and observer_task is not None:
        observer.signal(signal.SIGTERM)
        with contextlib.suppress(Exception):
            async with asyncio.timeout(timeout_s):
                await observer_task
        observer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await observer_task

    return rc


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    """Preflight, then supervise. `argv` is appended to the workflow's `run` command.

    There are no flags of this process's own: everything it needs is environment,
    and everything it passes on is an argument. Adding a flag here would create a
    second way to configure a container, reachable only by editing the image.
    """
    extra = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.INFO, format="[supervisor] %(message)s", stream=sys.stderr
    )
    # A wedged supervisor in an unattended container is otherwise undiagnosable: no
    # debugger is installed and `ps` only says the process exists. `docker kill
    # --signal=SIGUSR1 <container>` dumps its stack to the container log instead.
    faulthandler.register(signal.SIGUSR1)

    # Everything this container writes into a bind-mounted host path has to stay
    # usable from the host afterwards, and the container's uid is deliberately not
    # the operator's. Group access is what bridges that, so nothing may drop the
    # group write bit: 002 leaves new files 664 and new directories 775. Set before
    # the first child is spawned, because a umask is inherited, not applied.
    os.umask(0o002)

    layout = Layout()
    # HOME is pinned before anything reads it: the Claude CLI, uv's tool dir and
    # git's global config all resolve through it, and all three have to land on the
    # persistent volume rather than in the image's read-only layer.
    os.environ["HOME"] = str(layout.claude_home)
    env = dict(os.environ)

    require_writable([layout.workspace, layout.runs, layout.claude_home])
    seed_claude_home(layout, env)
    configure_git(env)

    params = run_params(env)
    checkout(env, params)
    params_file = write_boundary_params(layout.boundary_params, params)

    observer_cmd = install_observer(layout)
    observer = (
        # PYTHONDONTWRITEBYTECODE because a generation dir is written once and never
        # touched again; .pyc files scattered through it are pure noise the prune
        # then has to delete.
        Child(observer_cmd, env={**env, "PYTHONDONTWRITEBYTECODE": "1"})
        if observer_cmd
        else None
    )
    # The exit push stays a one-shot process even though this supervisor IS the
    # sidecar's parent now. Being the parent tells *us* the exit code; it does not
    # tell groom, and the sidecar's only channel to groom is the WebSocket the
    # sidecar itself holds. Collapsing this into `await proc.wait()` would mean
    # inventing a supervisor→observer channel — more code, not less.
    notice = (lambda rc: [*observer_cmd, "--exit-code", str(rc)]) if observer_cmd else None

    return asyncio.run(
        supervise(
            Child(run_command(env, params_file, extra), env=env),
            observer,
            exit_notice=notice,
            on_reload=lambda: livesource.refresh(observer_source(layout), layout.tool_bin),
        )
    )


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
