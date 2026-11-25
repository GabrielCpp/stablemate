"""The one seam a node routes a genuine external CLI through."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from workhorse_workflows.kit import leased_env


def run_tool(
    argv: list[str],
    cwd: str | Path | None = None,
    *,
    check: bool = False,
    logger: logging.Logger | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external CLI tool as a subprocess and return the completed process. With a `timeout`, a tool still running at the limit is killed with every process it started before `subprocess.TimeoutExpired` is raised. The tool and everything it starts run in a process group of their own."""
    if timeout is None:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            env=leased_env.child_env(env),
        )
    else:
        result = _run_limited(argv, cwd, env, timeout)
    if result.returncode != 0 and check:
        if logger is not None:
            logger.error(
                "%s failed (exit %d): %s",
                " ".join(argv), result.returncode, result.stderr.strip(),
            )
        raise RuntimeError(f"{argv[0]} failed: {result.stderr.strip()}")
    return result


def _run_limited(
    argv: list[str], cwd: str | Path | None, env: dict[str, str] | None, timeout: float
) -> subprocess.CompletedProcess[str]:
    with spawn_grouped(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        env=leased_env.child_env(env),
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(process)
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr) from None
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def spawn_grouped(argv: str | list[str], **options: Any) -> subprocess.Popen[Any]:
    """Start *argv* as the leader of a process group of its own, so `kill_group` reaches all it starts."""
    if sys.platform == "win32":
        return subprocess.Popen(argv, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, **options)
    return subprocess.Popen(argv, start_new_session=True, **options)


def kill_group(process: subprocess.Popen[Any]) -> None:
    """Kill the group `spawn_grouped` started, or the process alone where Windows has no group kill."""
    if sys.platform == "win32":
        process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
