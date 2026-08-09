"""Where the repo is, and where its docs are — from the run's own inputs, not the ambient
environment.

Both functions take ``repo_dir`` as an argument for the same reason
:func:`~workhorse_workflows.kit.workspace.resolve_workspace` does: a run's cwd is not
necessarily the consuming repo, and a node whose root depends on the environment is a node
whose behavior no caller can see, override or checkpoint.
"""
from __future__ import annotations

from pathlib import Path


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
