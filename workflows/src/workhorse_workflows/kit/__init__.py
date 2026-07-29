"""The domain half of what used to be ``workhorse.scriptutil``: git, GitHub, workspaces.

The engine kept the seams a *runner* needs — ``load_jsonc``, ``die``, ``find_repo_root``,
``find_docs_root``, ``fresh_import``, ``run_tool`` — and nothing that knows what a repo
is. Everything that drives git or github.com lives here, which is why ``gitpython`` and
``PyGithub`` are this package's dependencies and no longer workhorse-agent's.

Scripts import the flat surface, exactly as they imported ``scriptutil``::

    from workhorse_workflows.kit import commit_all, github_client, resolve_workspace

**Patch the defining submodule** — :mod:`~workhorse_workflows.kit.git`,
:mod:`~workhorse_workflows.kit.github`, :mod:`~workhorse_workflows.kit.workspace` — and
the flat surface follows, because this module resolves a name through ``__getattr__``
rather than binding it at import time. That is what keeps the seam contract the same one
``scriptutil`` had: a script node is re-imported on every run, so its
``from … import github_client`` re-reads the attribute and picks up the fake. A plain
re-export would have frozen those bindings at *package* import, one process-lifetime
earlier, and every existing patch would have silently stopped reaching the script.

One rule follows from having three modules where there was one: a helper here calls
another through its module (``git_kit.origin_url(...)``), never a direct import, so a
test that fakes ``kit.git.origin_url`` also redirects :mod:`~workhorse_workflows.kit.github`'s
internal use of it — which is what monkeypatching a single module used to give for free.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

_NAMES: dict[str, str] = {
    name: "workhorse_workflows.kit.git"
    for name in (
        "active_branch",
        "allow_all_directories",
        "branch_exists",
        "checkout",
        "clone",
        "commit_all",
        "commit_paths",
        "commits_ahead",
        "current_branch",
        "default_branch",
        "diff_text",
        "fetch_reset",
        "list_tracked_files",
        "local_branch_exists",
        "merge_base",
        "open_repo",
        "origin_url",
        "push_to_origin",
        "remote_urls",
        "rename_branch",
        "restore_paths",
        "set_identity",
        "short_sha",
        "show_file",
    )
} | {
    name: "workhorse_workflows.kit.github"
    for name in (
        "find_open_pr",
        "github_client",
        "push_branch",
        "repo_full_name_from_url",
        "resolve_github_token",
        "resolve_repo",
        "sync_to_origin",
    )
} | {
    name: "workhorse_workflows.kit.workspace"
    for name in (
        "build_dispatch_list",
        "checkout_workspace",
        "get_affected_repos",
        "get_repo_config",
        "resolve_workspace",
    )
}

__all__ = sorted(_NAMES)


def __getattr__(name: str):
    """Resolve a flat name against the submodule that defines it, on every access."""
    module = _NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    return __all__


if TYPE_CHECKING:  # the names above, for a reader and a type checker
    from workhorse_workflows.kit.git import (  # noqa: F401
        active_branch,
        allow_all_directories,
        branch_exists,
        checkout,
        clone,
        commit_all,
        commit_paths,
        commits_ahead,
        current_branch,
        default_branch,
        diff_text,
        fetch_reset,
        list_tracked_files,
        local_branch_exists,
        merge_base,
        open_repo,
        origin_url,
        push_to_origin,
        remote_urls,
        rename_branch,
        restore_paths,
        set_identity,
        short_sha,
        show_file,
    )
    from workhorse_workflows.kit.github import (  # noqa: F401
        find_open_pr,
        github_client,
        push_branch,
        repo_full_name_from_url,
        resolve_github_token,
        resolve_repo,
        sync_to_origin,
    )
    from workhorse_workflows.kit.workspace import (  # noqa: F401
        build_dispatch_list,
        checkout_workspace,
        get_affected_repos,
        get_repo_config,
        resolve_workspace,
    )
