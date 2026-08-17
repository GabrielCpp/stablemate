"""Fail-closed Git and command mechanics for the plan implementation flow."""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from git.exc import GitCommandError, GitError
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.implement_plan.inventory import (
    assert_plan_unchanged,
    commit_body,
    commit_subject,
    git_control_digest,
    origin_digest,
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


def worktree_changes(root: Path) -> list[tuple[str, str]]:
    """Every differing path with its porcelain status code, renames as both names."""
    try:
        output = open_repo(root).git.status("--porcelain=v1", "-z", "--untracked-files=all")
    except GitError as exc:
        raise WorkflowFailed(f"cannot inspect worktree changes at {root}: {exc}") from exc
    changes: list[tuple[str, str]] = []
    records = output.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        code = record[:2]
        paths = [record[3:]]
        if any(kind in code for kind in "RC") and index < len(records):
            paths.append(records[index])
            index += 1
        changes.extend((code, path.replace("\\", "/")) for path in paths)
    return changes


def changed_paths(root: Path) -> list[str]:
    return sorted({path for _, path in worktree_changes(root)})


def owned(path: str, scopes: Sequence[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(
        candidate == PurePosixPath(scope) or PurePosixPath(scope) in candidate.parents
        for scope in scopes
    )


def task_scopes(tasks: Sequence[PlanTask], task: PlanTask) -> list[str]:
    """Everything a packet may change: its own declared paths, plus its dependencies'.

    A packet that declares `depends_on` is stating that it builds on that packet's
    work, and a change routinely has to travel along that edge — this packet alters a
    signature, and the call site belongs to the packet underneath it. The planner
    declares `paths` before a line of the work exists, so it cannot see those call
    sites; refusing the propagation ends the run over an edit that is not only correct
    but required, since the packet's own verification runs the dependency's tests.

    Following a declared edge is not the collision this check exists to catch. That is
    a packet reaching into work it never said it depended on — an unordered sibling,
    where two turns really can overwrite each other — and it stays refused. The edge is
    only ever followed one step: the plan orders dependants after dependencies, so the
    dependency is already committed and verified at its own commit, and a later packet
    building on it is what the ordering is *for*.
    """
    by_id = {other.id: other for other in tasks}
    scopes = {*task.paths}
    for dependency in task.depends_on:
        upstream = by_id.get(dependency)
        if upstream is not None:
            scopes.update(upstream.paths)
    return sorted(scopes)


def plan_snapshot_path(context: PlanRunContext) -> str:
    """The plan's own repository-relative path, or "" when it lives outside the repo."""
    try:
        return Path(context.source_path).relative_to(Path(context.repo_root)).as_posix()
    except ValueError:
        return ""


def adoptable(code: str, path: str, snapshot: str) -> bool:
    """Whether a change is a brand-new file the packet may take ownership of.

    A packet declares its paths in the planning turn, before a line of the work
    exists, so it routinely misses one file the work genuinely needs — most often
    the test file the tests-first turn has to create, whose home follows the
    repository's layout rather than the planner's guess. Killing the run there is
    the wrong trade: a file that did not exist belongs to nobody, so adopting it
    keeps everything the ownership check is *for* — no packet quietly edits
    another packet's files, and each commit holds one packet's work — while the
    run continues. A change to a file that already existed is still a violation:
    that is the case where two packets can collide, and it stays refused.
    """
    if not (code == "??" or code.startswith("A")):
        return False
    if PurePosixPath(path).parts[0] in {".agents", ".git"}:
        return False
    return path != snapshot


def adopted_paths(
    context: PlanRunContext, task: PlanTask, scopes: Sequence[str] | None = None
) -> list[str]:
    """New, undeclared files the turn created, which this task now also owns."""
    snapshot = plan_snapshot_path(context)
    reach = list(scopes) if scopes is not None else task.paths
    return sorted(
        {
            path
            for code, path in worktree_changes(Path(context.repo_root))
            if not owned(path, reach) and adoptable(code, path, snapshot)
        }
    )


def assert_owned(
    context: PlanRunContext,
    task: PlanTask,
    *,
    scopes: Sequence[str] | None = None,
    require_changes: bool = False,
) -> list[str]:
    root = Path(context.repo_root)
    reach = list(scopes) if scopes is not None else task.paths
    changed = changed_paths(root)
    adopted = set(adopted_paths(context, task, reach))
    outside = [path for path in changed if not owned(path, reach) and path not in adopted]
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
    # Deliberately no fingerprint over the repository's *other* refs. The run reads and
    # writes exactly two — its branch and origin/<branch> — and those are asserted
    # directly (HEAD unmoved, remote unmoved). A sibling branch, a tag, a note or a
    # remote-tracking ref moving cannot change this run's parent chain or its content,
    # so failing on it only breaks the case the isolation is *for*: a dedicated worktree
    # sharing one repository with other work. `refs/replace` is the one ref class that
    # does rewrite object content, and it is refused above.


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


def reset_soft(context: PlanRunContext, target: str) -> None:
    """Move the branch back to `target`, keeping every file the commit contained."""
    try:
        raw_git(context).reset("--soft", target)
    except (GitError, ValueError) as exc:
        raise WorkflowFailed(f"cannot move HEAD back to {target[:12]}: {exc}") from exc


def commit_message(context: PlanRunContext, task: PlanTask) -> str:
    blocks = [commit_subject(task)]
    body = commit_body(task)
    if body:
        blocks.append(body)
    blocks.append(f"Plan-Task: {task_key(context, task.id)}")
    return "\n\n".join(blocks)


def commit_changes(context: PlanRunContext, parent: str, commit: str) -> list[tuple[str, str]]:
    """Each path the commit touched, with its diff status code against ``parent``."""
    try:
        output = raw_git(context).diff(
            "--name-status", "--no-renames", "-z", parent, commit, "--"
        )
    except GitError as exc:
        raise WorkflowFailed(f"cannot inspect recovered commit {commit[:12]}: {exc}") from exc
    fields = [field for field in output.split("\0") if field]
    return [
        (fields[index], fields[index + 1].replace("\\", "/"))
        for index in range(0, len(fields) - 1, 2)
    ]


def commit_paths(context: PlanRunContext, parent: str, commit: str) -> list[str]:
    return sorted(path for _, path in commit_changes(context, parent, commit))


def validate_task_commit(
    context: PlanRunContext,
    task: PlanTask,
    expected_parent: str,
    commit_sha: str,
    scopes: Sequence[str],
) -> None:
    """Assert the commit is the packet's own: right parent, right message, right paths.

    `scopes` is the packet's reach — `task_scopes`, its declared paths plus its
    dependencies' — and not `task.paths`. The two must be the same set the turn was held
    to, or the run rejects at commit an edit it authorised while the turn was running:
    `assert_owned` admits the reach, `create_task_commit` stages the reach, and judging the
    result by the narrower set failed a packet for following a dependency edge it declared.
    Observed in the wild, on a packet whose dependency had published a `nothing consumes
    this yet` guard that the packet existed to make untrue.
    """
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
    changes = commit_changes(context, expected_parent, commit_sha)
    snapshot = plan_snapshot_path(context)
    outside = [
        path
        for code, path in changes
        if not owned(path, scopes) and not adoptable(code, path, snapshot)
    ]
    if not changes or outside:
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


def create_task_commit(
    context: PlanRunContext, task: PlanTask, scopes: Sequence[str] | None = None
) -> str:
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
        reach = list(scopes) if scopes is not None else task.paths
        committed_paths = [*reach, *adopted_paths(context, task, reach)]
        repo.git.add(*committed_paths)
        scope = ["--", *committed_paths]
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
    "task_scopes",
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