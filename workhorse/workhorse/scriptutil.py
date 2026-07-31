"""Shared utilities for workhorse workflow scripts.

Workflow scripts import from here rather than maintaining a local ``lib/`` directory:

    from workhorse.scriptutil import load_json, find_repo_root, run_tool

Because workhorse is installed editable (``pip install -e``), this module is
available to any script invoked via ``sys.executable``.

What is left here is what a *runner* needs and nothing that knows what a repo is:
JSON/JSONC parsing, the hard-fail idiom, root resolution, the mid-run reimport, and
one seam — :func:`run_tool`, which runs an external CLI (e.g. ``ostler``) as a
subprocess so an in-process test can intercept it by monkeypatching this module.

Git, GitHub and multi-repo workspace resolution moved to
:mod:`workhorse_workflows.kit`, which is where ``gitpython`` and ``PyGithub`` are
dependencies. They are workflow domain, not engine: the engine gained nothing from
knowing how to open a PR, and every install of it paid for two libraries it never
called. Scripts import the same names from ``workhorse_workflows.kit`` and patch the
defining submodule (``kit.git``, ``kit.github``, ``kit.workspace``).
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NoReturn


def load_jsonc(text: str) -> dict:
    """Parse JSON with Comments (trailing commas, // comments) as used by VSCode."""
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def load_json(path: Path, label: str, logger: logging.Logger) -> dict:
    """Load a JSON file; logs warnings via caller's logger. Returns {} on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s not found at %s", label, path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s unreadable at %s: %s", label, path, exc)
    return {}


def die(message: str, *, code: int = 1) -> NoReturn:
    """Print ``message`` to stderr and exit with ``code`` — the hard-fail idiom
    for workflow scripts, defined once here instead of re-implemented per script.

    Unlike ``sys.exit(message)``, which always exits with code 1, this pairs an
    actionable message with any exit ``code`` (scripts use ``2`` to distinguish a
    bad/missing invocation target from an ordinary failure — a distinction the
    workhorse script runner propagates). Typed ``NoReturn`` so a caller's control
    flow narrows: statements after ``die(...)`` are unreachable, and a thin
    per-script wrapper that always ends in ``die`` is itself ``NoReturn``.
    """
    print(message, file=sys.stderr)
    raise SystemExit(code)

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


def fresh_import(name: str, *, also_purge: tuple[str, ...] = ()) -> ModuleType:
    """Re-import ``name`` straight from disk instead of whatever ``sys.modules`` holds.

    The in-process script runner (``workhorse/runner/script.py``) reuses one Python
    interpreter for an entire graph run. A script node re-executes fresh on every
    call, but anything it merely ``import``s stays cached in ``sys.modules`` for the
    rest of the run — so a fix landed on disk mid-run (e.g. an environment-fix loop
    editing a QA-tool package while QA nodes are still ahead in the graph) stays
    invisible to every later node unless that node forces a real reimport. Pass any
    package ``name`` transitively imports and might change mid-run via
    ``also_purge`` — e.g. ``fresh_import("qa_cli", also_purge=("ostler",))`` — so its
    own stale submodules don't leak back in through the reimported caller.

    ``WORKHORSE_FRESH_IMPORT=0`` disables the purge and returns the cached module.
    Reimporting builds a *new module object*, so every ``monkeypatch.setattr`` a test
    applied to the old one is silently discarded — the mock stays in place, just no
    longer on the thing the caller reaches. A test that patches a seam this function
    would re-import should set the variable for the duration of the run; nothing edits
    a package on disk under test, so the behavior it exists for cannot occur there.
    """
    if (os.environ.get("WORKHORSE_FRESH_IMPORT") or "1").strip().lower() in (
        "0", "false", "no", "off",
    ):
        return sys.modules.get(name) or importlib.import_module(name)
    for root in (name, *also_purge):
        for mod in [m for m in sys.modules if m == root or m.startswith(root + ".")]:
            del sys.modules[mod]
    return importlib.import_module(name)

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
