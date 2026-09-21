"""Everything a node reuses: git, GitHub, workspaces, paths, JSON, external CLIs."""
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
        "GitError",
        "head_sha",
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
        "trunk_base",
    )
} | {
    name: "workhorse_workflows.kit.worklist"
    for name in (
        "build_worklist",
        "BuildWorklist",
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
    "poll_run_inbox": "workhorse_workflows.kit.inbox",
} | {
    "run_tool": "workhorse_workflows.kit.tools",
}

__all__ = sorted(_NAMES)  # pyright: ignore[reportUnsupportedDunderAll]


def __getattr__(name: str):
    """Resolve a flat name against the submodule that defines it, on every access."""
    module = _NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    return __all__


if TYPE_CHECKING:
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
        head_sha,
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
        trunk_base,
    )
    from workhorse_workflows.kit.worklist import (  # noqa: F401
        BuildWorklist,
        build_worklist,
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
    from workhorse_workflows.kit.inbox import poll_run_inbox  # noqa: F401
    from workhorse_workflows.kit.tools import run_tool  # noqa: F401
    from workhorse_workflows.kit.workspace import (  # noqa: F401
        build_dispatch_list,
        checkout_workspace,
        get_affected_repos,
        get_repo_config,
        resolve_workspace,
    )
