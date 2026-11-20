"""The one seam a node routes a genuine external CLI through."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path


def run_tool(
    argv: list[str],
    cwd: str | Path | None = None,
    *,
    check: bool = False,
    logger: logging.Logger | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external CLI tool as a subprocess and return the completed process. With a `timeout`, a tool still running at the limit is killed with every process it started before `subprocess.TimeoutExpired` is raised. The tool stays in the caller's process group, so a stop of the run still reaches it."""
    if timeout is None:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            env={**os.environ, **env} if env else None,
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
    with subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        env={**os.environ, **env} if env else None,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            for pid in [*_started_by(process.pid), process.pid]:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    continue
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr) from None
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _started_by(pid: int) -> list[int]:
    """Every live process below `pid`, deepest first."""
    listed = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False).stdout.split()
    found: list[int] = []
    for child in map(int, listed):
        found += [*_started_by(child), child]
    return found
