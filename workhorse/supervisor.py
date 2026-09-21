#!/usr/bin/env python3
"""Container supervision: preflight, then two children with different lifecycles."""
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

RELOAD_EXIT_CODE = 3

NOT_WRITABLE_EXIT_CODE = 13

TEARDOWN_TIMEOUT_S = 10.0

PARAM_ENV_PREFIX = "AGENT_PARAM_"


@dataclass(frozen=True)
class Layout:
    """Where this container keeps things."""

    claude_home: Path = Path("/claude-state")
    workspace: Path = Path("/workspace")
    runs: Path = Path("/runs")
    settings_src: Path = Path("/mnt/claude-settings.json")
    credentials_src: Path = Path("/mnt/claude-credentials.json")
    observer_src: Path = Path("/mnt/groom-src")
    live_root: Path = Path("/opt/live")
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




def require_writable(paths: Sequence[Path]) -> None:
    """Fail loudly, here, when a mount is not writable by this uid."""
    for path in paths:
        if not path.is_dir() or not os.access(path, os.W_OK):
            log.error(
                "%s must be writable by uid %d:%d. Prepare the volume's ownership "
                "before starting this non-root container.",
                path, os.getuid(), os.getgid(),
            )
            raise SystemExit(NOT_WRITABLE_EXIT_CODE)


def seed_claude_home(layout: Layout, env: Mapping[str, str]) -> None:
    """Prepare HOME so a headless Claude CLI starts authenticated and un-prompted."""
    layout.claude_dir.mkdir(parents=True, exist_ok=True)

    if layout.settings_src.is_file():
        shutil.copyfile(layout.settings_src, layout.claude_dir / "settings.json")

    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        log.info("auth: using CLAUDE_CODE_OAUTH_TOKEN")
    elif layout.credentials.is_file():
        log.info("auth: using credentials already in the claude-state volume")
    elif layout.credentials_src.is_file():
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

    if not layout.onboarding_stub.exists():
        layout.onboarding_stub.write_text(
            '{"hasCompletedOnboarding": true}\n', encoding="utf-8"
        )


def configure_git(env: Mapping[str, str]) -> None:
    """Global git config for commits made inside the container."""
    _git("config", "--global", "--add", "safe.directory", "*")
    _git("config", "--global", "user.email", env.get("GIT_AUTHOR_EMAIL") or "agent@example.com")
    _git("config", "--global", "user.name", env.get("GIT_AUTHOR_NAME") or "Agent")


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True)


def observer_source(layout: Layout) -> livesource.LiveSource:
    """groom's sidecar, as a package installed from its host bind."""
    return livesource.LiveSource(
        name="groom",
        mount=layout.observer_src,
        root=layout.live_root / "groom",
        with_editable=(layout.image_workhorse,),
    )


def install_observer(layout: Layout) -> list[str] | None:
    """Stage and install the observer, and return how to run it."""
    livesource.refresh(observer_source(layout), layout.tool_bin)
    return [str(layout.observer)] if os.access(layout.observer, os.X_OK) else None


def run_params(env: Mapping[str, str]) -> dict[str, str]:
    """The operator's environment, as run parameters."""
    return {
        key[len(PARAM_ENV_PREFIX):].lower(): value
        for key, value in sorted(env.items())
        if key.startswith(PARAM_ENV_PREFIX) and value
    }


def write_boundary_params(path: Path, params: Mapping[str, str]) -> Path:
    """Write the params file the run is launched with."""
    path.write_text(json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def checkout(env: Mapping[str, str], params: Mapping[str, str]) -> None:
    """Materialise the working trees the run needs, before the engine starts."""
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
    """The workflow's own console script, and its arguments."""
    name = env.get("WORKFLOW", "")
    if not name:
        raise SystemExit("set WORKFLOW to the workflow to run, e.g. coder")
    script = (bin_dir or Path(sys.executable).parent) / f"workhorse-{name}"
    if not os.access(script, os.X_OK):
        raise SystemExit(f"no such workflow: {name} (looked for {script})")
    cmd = [str(script), "run"]
    if env.get("AGENT_RUNS_DIR"):
        cmd += ["--runs-dir", env["AGENT_RUNS_DIR"]]
    if env.get("AGENT_RUN_ID"):
        cmd += ["--run-id", env["AGENT_RUN_ID"]]
    if env.get("AGENT_CONFIG"):
        cmd += ["--config", env["AGENT_CONFIG"]]
    if env.get("AGENT_PROFILE"):
        cmd += ["--profile", env["AGENT_PROFILE"]]
    cmd += ["--params-file", str(params_file)]
    return cmd + list(extra)




@dataclass
class Child:
    """One supervised process, plus the two facts a signal handler needs."""

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
    """Keep restarting the observer for as long as it asks to be reloaded."""
    while not child.stopping:
        proc = await child.start()
        rc = await proc.wait()
        if rc != reload_code:
            if rc:
                log.warning("observer exited with %d; not restarting it", rc)
            return
        log.info("observer requested a reload")
        if on_reload is not None:
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
    """Run both children and return the run's exit code as the container's."""
    loop = asyncio.get_running_loop()
    observer_task = (
        asyncio.create_task(supervise_observer(observer, on_reload=on_reload))
        if observer is not None
        else None
    )

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, run.signal, sig)

    proc = await run.start()
    rc = await proc.wait()
    while rc == RELOAD_EXIT_CODE and not run.stopping:
        log.info("workflow requested a reload")
        if on_reload is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(on_reload)
        proc = await run.start()
        rc = await proc.wait()
    log.info("workflow exited with %d", rc)

    if exit_notice is not None:
        with contextlib.suppress(Exception):
            async with asyncio.timeout(timeout_s):
                notice = await asyncio.create_subprocess_exec(
                    *exit_notice(rc), env=dict(run.env),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                try:
                    await notice.wait()
                finally:
                    if notice.returncode is None:
                        with contextlib.suppress(ProcessLookupError):
                            notice.kill()
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




def main(argv: Sequence[str] | None = None) -> int:
    """Preflight, then supervise."""
    extra = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.INFO, format="[supervisor] %(message)s", stream=sys.stderr
    )
    faulthandler.register(signal.SIGUSR1)

    os.umask(0o002)

    layout = Layout()
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
        Child(observer_cmd, env={**env, "PYTHONDONTWRITEBYTECODE": "1"})
        if observer_cmd
        else None
    )
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
