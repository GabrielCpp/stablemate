"""Shared utilities for workhorse workflow scripts.

Workflow scripts import from here rather than maintaining a local ``lib/`` directory:

    from workhorse.scriptutil import load_json, find_repo_root, run_tool

Because workhorse is installed editable (``pip install -e``), this module is
available to any script invoked via ``sys.executable``.

What is left here is what a *runner* needs and nothing that knows what a repo is:
JSON/JSONC parsing, root resolution, and one seam — :func:`run_tool`, which runs an
external CLI (e.g. ``ostler``) as a subprocess so an in-process test can intercept it
by monkeypatching this module.

Git, GitHub and multi-repo workspace resolution moved to
:mod:`workhorse_workflows.kit`, which is where ``gitpython`` and ``PyGithub`` are
dependencies. They are workflow domain, not engine: the engine gained nothing from
knowing how to open a PR, and every install of it paid for two libraries it never
called. Scripts import the same names from ``workhorse_workflows.kit`` and patch the
defining submodule (``kit.git``, ``kit.github``, ``kit.workspace``).
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import json5


def load_jsonc(text: str) -> dict:
    """Parse JSON with Comments (trailing commas, // comments) as used by VSCode.

    A real JSON5 parse, not a strip-then-`json.loads`. The stripping version deleted from
    `//` to end of line without knowing what a string literal is, so any workspace file
    holding a URL — `{"url": "https://example.com"}` — was truncated mid-string and then
    reported as invalid JSON. `.code-workspace` files routinely hold URLs and `//` paths.
    """
    return json5.loads(text)


def load_json(path: Path, label: str, logger: logging.Logger) -> dict:
    """Load a JSON file; logs warnings via caller's logger. Returns {} on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s not found at %s", label, path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s unreadable at %s: %s", label, path, exc)
    return {}


def find_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo: ``repo_dir`` when given, else walk up from the CWD.

    ``repo_dir`` is the run's own input — :attr:`workhorse.pyflow.Workflow.repo_dir`,
    which the CLI defaults to the launch directory — and a node receives it as an
    argument. This function reads no environment variable of its own: a node whose root
    depends on the ambient environment is a node whose behavior no caller can see or
    override, which is why `workflows/README.md` prohibits it.
    """
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def find_docs_root(docs_path: str = "", repo_dir: str | Path = "") -> Path:
    """Resolve the docs repo root: ``docs_path`` when given, else the repo root.

    A relative ``docs_path`` is joined onto ``find_repo_root(repo_dir)``, so the two
    inputs travel together — both are workflow inputs, and neither is read from the
    environment here.
    """
    if docs_path:
        p = Path(docs_path)
        if p.is_absolute():
            return p.resolve()
        return (find_repo_root(repo_dir) / p).resolve()
    return find_repo_root(repo_dir)


def run_tool(
    argv: list[str],
    cwd: str | Path | None = None,
    *,
    check: bool = False,
    logger: logging.Logger | None = None,
) -> subprocess.CompletedProcess:
    """Run an external CLI tool (e.g. ``ostler``) as a subprocess and return the
    completed process.

    The single seam workflow scripts route external-CLI calls through, so an
    in-process test can monkeypatch ``run_tool`` to return a canned result — no PATH
    shim. In production it runs the real binary (the "real passthrough" contract). Set
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
