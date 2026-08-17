"""The one seam a node routes a genuine external CLI through.

Git, GitHub and ostler each have a richer in-process facade of their own
(:mod:`~workhorse_workflows.kit.git`, :mod:`~workhorse_workflows.kit.github`,
``ostler.Ostler``); this is for the CLI that has none.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path


def run_tool(
    argv: list[str],
    cwd: str | Path | None = None,
    *,
    check: bool = False,
    logger: logging.Logger | None = None,
) -> subprocess.CompletedProcess:
    """Run an external CLI tool as a subprocess and return the completed process.

    The single seam nodes route external-CLI calls through, so an in-process test can
    monkeypatch ``run_tool`` on this module to return a canned result — no PATH shim. In
    production it runs the real binary (the "real passthrough" contract). Set
    ``check=True`` to raise ``RuntimeError`` on a non-zero exit."""
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )
    if result.returncode != 0 and check:
        if logger is not None:
            logger.error(
                "%s failed (exit %d): %s",
                " ".join(argv), result.returncode, result.stderr.strip(),
            )
        raise RuntimeError(f"{argv[0]} failed: {result.stderr.strip()}")
    return result
