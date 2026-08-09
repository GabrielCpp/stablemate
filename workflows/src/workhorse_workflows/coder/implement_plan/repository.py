"""Fail-closed Git and command mechanics for the plan implementation flow."""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from git.exc import GitCommandError, GitError
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.implement_plan.inventory import (
    assert_plan_unchanged,
    git_control_digest,
    origin_digest,
    other_refs_digest,
    task_key,
)
from workhorse_workflows.coder.implement_plan.schemas import (
    PlanRunContext,
    PlanTask,
    VerificationCommand,
    VerificationResult,
)
from workhorse_workflows.kit import open_repo

_OUTPUT_LIMIT = 24_000


def open_context(context: PlanRunContext):
    try:
        return open_repo(context.repo_root)
    except GitError as exc:
        raise WorkflowFailed(f"cannot open repository {context.repo_root}: {exc}") from exc


def raw_git(context: PlanRunContext):
    git = open_context(context).git
    git.update_environment(GIT_NO_REPLACE_OBJECTS="1")
    return git


def head(context: PlanRunContext) -> str:
    try:
        return raw_git(context).rev_parse("HEAD").strip()
    except (GitError, ValueError) as exc:
        raise WorkflowFailed(f"cannot inspect HEAD at {context.repo_root}: {exc}") from exc


def changed_paths(root: Path) -> list[str]:
    try:
        output = open_repo(root).git.status("--porcelain=v1", "-z", "--untracked-files=all")
    except GitError as exc:
        raise WorkflowFailed(f"cannot inspect worktree changes at {root}: {exc}") from exc
    changed: list[str] = []
    records = output.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        paths = [record[3:]]
        if any(kind in record[:2] for kind in "RC") and index < len(records):
            paths.append(records[index])
            index += 1
        changed.extend(path.replace("\\", "/") for path in paths)
    return sorted(set(changed))


def owned(path: str, scopes: list[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(
        candidate == PurePosixPath(scope) or PurePosixPath(scope) in candidate.parents
        for scope in scopes
    )


def assert_owned(root: Path, task: PlanTask, *, require_changes: bool = False) -> list[str]:
    changed = changed_paths(root)
    outside = [path for path in changed if not owned(path, task.paths)]
    if outside:
        raise WorkflowFailed(f"task {task.id} changed paths it does not own: {', '.join(outside)}")
    if require_changes and not changed:
        raise WorkflowFailed(f"task {task.id} produced no changes")
    return changed


def remote_head(context: PlanRunContext) -> str:
    try:
        output = raw_git(context).ls_remote("origin", f"refs/heads/{context.branch}")
    except GitError:
        return ""
    return output.split()[0] if output.split() else ""


def assert_repository_identity(context: PlanRunContext) -> None:
    assert_plan_unchanged(context)
    try:
        branch = open_context(context).active_branch.name
    except (GitError, TypeError) as exc:
        raise WorkflowFailed(f"cannot inspect active branch: {exc}") from exc
    if branch != context.branch:
        raise WorkflowFailed(f"repository left checkpointed branch {context.branch}")
    if origin_digest(Path(context.repo_root)) != context.origin_digest:
        raise WorkflowFailed("origin configuration changed during implement-plan")
    if git_control_digest(Path(context.repo_root)) != context.git_control_digest:
        raise WorkflowFailed("Git configuration, hooks, or info controls changed during implement-plan")
    if raw_git(context).for_each_ref("--format=%(refname)", "refs/replace").strip():
        raise WorkflowFailed("replacement refs appeared during implement-plan")
    if other_refs_digest(Path(context.repo_root), context.branch) != context.other_refs_digest:
        raise WorkflowFailed("a non-current Git ref changed during implement-plan")


def assert_remote(context: PlanRunContext, expected: str) -> None:
    actual = remote_head(context)
    if actual != expected:
        raise WorkflowFailed(
            f"origin/{context.branch} moved from {expected[:12]} to {actual[:12] or '(missing)'}"
        )


def assert_clean_at(context: PlanRunContext, expected_head: str, expected_remote: str) -> None:
    assert_repository_identity(context)
    actual = head(context)
    if actual != expected_head:
        raise WorkflowFailed(
            f"HEAD moved from checkpointed commit {expected_head[:12]} to {actual[:12]}"
        )
    changed = changed_paths(Path(context.repo_root))
    if changed:
        raise WorkflowFailed(f"expected a clean worktree, found: {', '.join(changed)}")
    assert_remote(context, expected_remote)


def commit_message(context: PlanRunContext, task: PlanTask) -> str:
    subject = task.commit_type + (f"({task.commit_scope})" if task.commit_scope else "")
    return f"{subject}: implement planned change\n\nPlan-Task: {task_key(context, task.id)}"


def commit_paths(context: PlanRunContext, parent: str, commit: str) -> list[str]:
    try:
        output = raw_git(context).diff(
            "--name-only", "--no-renames", "-z", parent, commit, "--"
        )
    except GitError as exc:
        raise WorkflowFailed(f"cannot inspect recovered commit {commit[:12]}: {exc}") from exc
    return sorted(path.replace("\\", "/") for path in output.split("\0") if path)


def validate_task_commit(
    context: PlanRunContext, task: PlanTask, expected_parent: str, commit_sha: str
) -> None:
    try:
        raw = raw_git(context)
        parents = raw.show("-s", "--format=%P", commit_sha).strip().split()
        message = raw.show("-s", "--format=%B", commit_sha).strip()
    except (GitError, ValueError) as exc:
        raise WorkflowFailed(f"cannot inspect task commit {commit_sha[:12]}: {exc}") from exc
    if parents != [expected_parent]:
        raise WorkflowFailed(f"task {task.id} commit does not descend directly from expected HEAD")
    if message != commit_message(context, task):
        raise WorkflowFailed(f"task {task.id} commit message does not match its packet")
    paths = commit_paths(context, expected_parent, commit_sha)
    if not paths or any(not owned(path, task.paths) for path in paths):
        raise WorkflowFailed(f"task {task.id} commit contains missing or out-of-scope paths")


def assert_tree_matches_worktree(
    context: PlanRunContext, task: PlanTask, commit_sha: str
) -> None:
    """Compare the complete raw committed tree to bytes verification commands read."""
    raw = raw_git(context)
    root = Path(context.repo_root)
    try:
        listing = raw.ls_tree("-r", "-z", commit_sha)
    except GitError as exc:
        raise WorkflowFailed(f"cannot inspect committed tree {commit_sha[:12]}: {exc}") from exc
    for entry in listing.split("\0"):
        if not entry:
            continue
        metadata, _, relative = entry.partition("\t")
        parts = metadata.split()
        if len(parts) != 3 or parts[1] != "blob":
            raise WorkflowFailed(f"task {task.id} committed unsupported object at {relative}")
        mode = parts[0]
        worktree_path = root / relative
        try:
            blob_sha = raw.rev_parse(f"{commit_sha}:{relative}").strip()
            repo = open_context(context)
            committed = repo.odb.stream(bytes.fromhex(blob_sha)).read()
            worktree = (
                os.readlink(worktree_path).encode()
                if worktree_path.is_symlink()
                else worktree_path.read_bytes()
            )
        except (GitError, OSError) as exc:
            raise WorkflowFailed(f"cannot compare committed path {relative}: {exc}") from exc
        if committed != worktree:
            raise WorkflowFailed(
                f"task {task.id} committed bytes differ from verified worktree at {relative}"
            )
        worktree_mode = "120000" if worktree_path.is_symlink() else (
            "100755" if worktree_path.stat().st_mode & 0o111 else "100644"
        )
        if mode != worktree_mode:
            raise WorkflowFailed(
                f"task {task.id} committed mode differs from verified worktree at {relative}"
            )


def run_commands(root: Path, commands: list[VerificationCommand]) -> VerificationResult:
    logs: list[str] = []
    for command in commands:
        cwd = (root / command.cwd).resolve()
        try:
            cwd.relative_to(root.resolve())
        except ValueError as exc:
            raise WorkflowFailed(f"verification cwd escapes the repository: {command.cwd}") from exc
        if not cwd.is_dir():
            raise WorkflowFailed(f"verification cwd does not exist: {command.cwd}")
        rendered = " ".join(command.argv)
        try:
            result = subprocess.run(
                command.argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=command.timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logs.append(f"$ {rendered}\n{exc}")
            return VerificationResult(passed=False, findings="\n\n".join(logs)[-_OUTPUT_LIMIT:])
        output = (result.stdout + result.stderr)[-_OUTPUT_LIMIT:]
        logs.append(f"$ {rendered}\nexit {result.returncode}\n{output}")
        if result.returncode != 0:
            return VerificationResult(passed=False, findings="\n\n".join(logs)[-_OUTPUT_LIMIT:])
    return VerificationResult(passed=True, findings="\n\n".join(logs)[-_OUTPUT_LIMIT:])


@contextmanager
def committed_tree(root: Path, commit_sha: str) -> Iterator[Path]:
    """Materialize exactly one commit for verification, then remove the worktree.

    Takes the repository root rather than a `PlanRunContext` because the parent
    `stage-plan` flow runs the same isolated aggregate gate without owning one: its
    per-phase child holds the checkpointed repository identity, and a half-filled
    context passed here purely to reach `repo_root` would be a fail-open lookalike.
    """
    parent = Path(tempfile.mkdtemp(prefix="workhorse-verify-"))
    checkout = parent / "tree"
    hooks = parent / "empty-hooks"
    hooks.mkdir()
    try:
        repo = open_repo(root)
    except GitError as exc:
        raise WorkflowFailed(f"cannot open repository {root}: {exc}") from exc
    try:
        repo.git(c=f"core.hooksPath={hooks}").worktree(
            "add", "--detach", "--quiet", str(checkout), commit_sha
        )
        yield checkout
    except GitError as exc:
        raise WorkflowFailed(f"cannot materialize committed tree {commit_sha[:12]}: {exc}") from exc
    finally:
        try:
            repo.git.worktree("remove", "--force", str(checkout))
        except GitError:
            pass
        shutil.rmtree(parent, ignore_errors=True)


def worktree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    try:
        repo = open_repo(root)
        digest.update(repo.git.status("--porcelain=v1", "-z", "--untracked-files=all").encode())
        digest.update(repo.git.diff("--binary", "HEAD", "--").encode())
        untracked = sorted(repo.untracked_files)
    except GitError as exc:
        raise WorkflowFailed(f"cannot fingerprint worktree at {root}: {exc}") from exc
    for relative in untracked:
        path = root / relative
        digest.update(relative.encode())
        try:
            digest.update(os.readlink(path).encode() if path.is_symlink() else path.read_bytes())
        except OSError as exc:
            raise WorkflowFailed(f"cannot fingerprint {relative}: {exc}") from exc
    return digest.hexdigest()


def create_task_commit(context: PlanRunContext, task: PlanTask) -> str:
    filtered_hooks = Path(context.worklist_path).with_name("commit-hooks")
    shutil.rmtree(filtered_hooks, ignore_errors=True)
    filtered_hooks.mkdir(parents=True)
    try:
        repo = open_context(context)
        hooks_root = Path(
            repo.git.rev_parse("--path-format=absolute", "--git-path", "hooks").strip()
        )
        for name in ("pre-commit", "prepare-commit-msg", "commit-msg"):
            hook = hooks_root / name
            if not hook.is_file() or not os.access(hook, os.X_OK):
                continue
            wrapper = filtered_hooks / name
            wrapper.write_text(
                f"#!/bin/sh\nexec {shlex.quote(str(hook))} \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o700)
        repo.git.add(*task.paths)
        scope = ["--", *task.paths]
        try:
            repo.git.diff("--cached", "--quiet", *scope)
            raise WorkflowFailed(f"task {task.id} produced no staged changes")
        except GitCommandError:
            pass
        repo.git(c=f"core.hooksPath={filtered_hooks}").commit(
            "-m", commit_message(context, task), *scope
        )
    except GitError as exc:
        raise WorkflowFailed(f"could not commit task {task.id}: {exc}") from exc
    return head(context)


__all__ = [
    "assert_clean_at",
    "assert_owned",
    "assert_remote",
    "assert_repository_identity",
    "assert_tree_matches_worktree",
    "changed_paths",
    "committed_tree",
    "create_task_commit",
    "head",
    "remote_head",
    "run_commands",
    "validate_task_commit",
    "worktree_fingerprint",
]