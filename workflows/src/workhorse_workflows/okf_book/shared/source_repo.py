"""The repository that holds a surface's product source, resolved once and handed down.

Outside a workspace it is the run's own repository. Under a workspace it is one member of it,
while the book itself is written to the docs home.
"""
from __future__ import annotations

from pathlib import Path

from ostler.provenance import checkout_for, effective_checkouts
from pydantic import BaseModel, ConfigDict
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow import WorkflowFailed


class SourceRepo(BaseModel):
    """A repository's workspace name, empty outside a workspace, and the folder its files are read from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = ""
    path: Path

    def cite(self, repo_path: str) -> str:
        """How a `code:` bullet names `repo_path` of this repository."""
        return f"repo://{self.name}/{repo_path}" if self.name else repo_path


def source_repo(root: Path, service: str, repo: str) -> SourceRepo:
    """The repository the surface of `service` reads its source from, or a refusal naming what the surface got wrong."""
    if core_config.docs_home(root) is None:
        if repo:
            raise WorkflowFailed(f"the surface `{service}` names the repo `{repo}`, and the run is in no workspace: drop `repo`")
        return SourceRepo(path=root)
    members = effective_checkouts(None)
    if repo not in members:
        said = f"names the repo `{repo}`, which is no member" if repo else "names no repo"
        raise WorkflowFailed(f"the surface `{service}` {said} of the workspace: set `repo` to one of {', '.join(sorted(members)) or '(none)'}")
    return SourceRepo(name=repo, path=members[repo])


def repository_root(root: Path, repository: str) -> Path | None:
    """The tree a `code:` target of `repository` is read from: the book's own for an unqualified one, else the workspace member's checkout, or nothing when the workspace has no such member."""
    return checkout_for(repository, effective_checkouts(None)) if repository else root
