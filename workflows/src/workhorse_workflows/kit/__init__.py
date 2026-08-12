"""Everything a node reuses: git, GitHub, workspaces, paths, JSON, external CLIs.

All of it used to be ``workhorse.scriptutil``, in the engine distribution. It is here
instead because a helper a *node* calls is workflow domain, not engine: the engine gained
nothing from knowing how to open a PR or where a repo's docs live, and every install of it
paid for ``gitpython``, ``PyGithub`` and ``json5`` — three libraries it never called. What
stayed behind in workhorse is what the driver itself runs on, and nothing else.

Nodes import the flat surface, exactly as they imported ``scriptutil``::

    from workhorse_workflows.kit import commit_all, github_client, resolve_workspace

**Patch the defining submodule** — :mod:`~workhorse_workflows.kit.git`,
:mod:`~workhorse_workflows.kit.github`, :mod:`~workhorse_workflows.kit.workspace`,
:mod:`~workhorse_workflows.kit.paths`, :mod:`~workhorse_workflows.kit.jsonio`,
:mod:`~workhorse_workflows.kit.tools` — and
the flat surface follows, because this module resolves a name through ``__getattr__``
rather than binding it at import time. That is what keeps the seam contract the same one
``scriptutil`` had: a script node is re-imported on every run, so its
``from … import github_client`` re-reads the attribute and picks up the fake. A plain
re-export would have frozen those bindings at *package* import, one process-lifetime
earlier, and every existing patch would have silently stopped reaching the script.

One rule follows from having several modules where there was one: a helper here calls
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
        "branch_merged",
        "branch_owner",
        "checkout",
        "clone",
        "commit_all",
        "commit_paths",
        "commits_ahead",
        "current_branch",
        "default_branch",
        "diff_text",
        "fetch_reset",
        # The exception the two commit helpers raise when git refuses. Re-exported so a
        # node that must tell "nothing to commit" from "git said no" still imports only
        # from the kit, rather than reaching past it into gitpython.
        "GitError",
        "is_ancestor",
        "list_tracked_files",
        "local_branch_exists",
        "merge_base",
        "merge_ref",
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
} | {
    name: "workhorse_workflows.kit.paths"
    for name in (
        "find_docs_root",
        "find_repo_root",
    )
} | {
    name: "workhorse_workflows.kit.jsonio"
    for name in (
        "load_json",
        "load_jsonc",
    )
} | {
    "run_tool": "workhorse_workflows.kit.tools",
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
        branch_merged,
        branch_owner,
        checkout,
        clone,
        commit_all,
        commit_paths,
        commits_ahead,
        current_branch,
        default_branch,
        diff_text,
        fetch_reset,
        GitError,
        is_ancestor,
        list_tracked_files,
        local_branch_exists,
        merge_base,
        merge_ref,
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
    from workhorse_workflows.kit.jsonio import (  # noqa: F401
        load_json,
        load_jsonc,
    )
    from workhorse_workflows.kit.paths import (  # noqa: F401
        find_docs_root,
        find_repo_root,
    )
    from workhorse_workflows.kit.tools import run_tool  # noqa: F401
    from workhorse_workflows.kit.workspace import (  # noqa: F401
        build_dispatch_list,
        checkout_workspace,
        get_affected_repos,
        get_repo_config,
        resolve_workspace,
    )
