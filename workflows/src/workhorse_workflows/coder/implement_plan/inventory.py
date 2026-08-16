"""Snapshot a prose plan and validate its checkpoint-authoritative packet DAG."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import stat
import textwrap
from collections import deque
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from git.exc import GitError
from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_repo_root

from workhorse_workflows.coder.implement_plan.schemas import (
    PlanDecomposition,
    PlanRunContext,
    PlanTask,
    PreparedPlan,
    VerificationCommand,
)
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.kit import open_repo

_SCOPE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_COMMIT_TYPES = frozenset(
    {"feat", "fix", "perf", "refactor", "docs", "test", "build", "ci", "chore", "revert"}
)
_DOC_SUFFIXES = frozenset({".md", ".rst", ".txt", ".adoc"})


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


#: `branch.<name>.<setting>`, as `git config --list` spells it.
_BRANCH_SETTING = re.compile(r"^branch\.(?P<name>.+)\.[^.]+$")


def _config_records(raw: str) -> list[tuple[str, str]]:
    """`git config --list --show-origin -z` as (origin, `key\\nvalue`) pairs.

    The `-z` form emits each entry as two NUL-terminated fields, so a value that
    itself contains a newline — the reason `-z` is asked for — cannot be mistaken
    for the start of the next entry.
    """
    fields = raw.split("\0")
    return [(fields[i], fields[i + 1]) for i in range(0, len(fields) - 1, 2)]


def _foreign_branch_setting(entry: str, active: str) -> bool:
    """Whether an entry is another branch's bookkeeping in the shared config file.

    A linked worktree gets no config file of its own: `branch.<name>.remote` and
    `.merge` for *every* branch in the repository live in the one `.git/config`
    that all worktrees share. So a `git push -u`, `git branch --track` or
    `git checkout -b` run in a sibling worktree — by a person, by another agent —
    rewrites this run's fingerprint without touching this run, and the identity
    assertion kills it mid-packet.

    Those keys cannot change what this run does. It commits on the branch it has
    already asserted separately, and pushes to `origin` by name, whose URL carries
    its own digest. The *active* branch's settings stay in the fingerprint; only
    the other branches' drop out. It is the same trade the ref fingerprint makes
    in `assert_repository_identity`: refusing sibling churn breaks precisely the
    dedicated-worktree isolation the check exists to protect.
    """
    setting = _BRANCH_SETTING.match(entry.split("\n", 1)[0])
    return setting is not None and setting.group("name") != active


def git_control_digest(root: Path) -> str:
    """Identity of Git controls that can change add/commit/push behavior invisibly."""
    digest = hashlib.sha256()
    try:
        repo = open_repo(root)
        try:
            active = repo.active_branch.name
        except (GitError, TypeError):
            active = ""
        for origin, entry in _config_records(repo.git.config("--list", "--show-origin", "-z")):
            if _foreign_branch_setting(entry, active):
                continue
            digest.update(origin.encode())
            digest.update(b"\0")
            digest.update(entry.encode())
            digest.update(b"\0")
        controls: list[Path] = []
        for name in (
            "hooks",
            "info/exclude",
            "info/attributes",
            "info/grafts",
            "objects/info/alternates",
            "refs/replace",
        ):
            resolved = Path(repo.git.rev_parse("--git-path", name).strip())
            controls.append(resolved if resolved.is_absolute() else root / resolved)
    except (GitError, OSError) as exc:
        raise WorkflowFailed(f"cannot fingerprint Git controls at {root}: {exc}") from exc
    files: list[Path] = []
    for control in controls:
        if control.is_dir():
            files.extend(path for path in control.rglob("*") if path.is_file())
        else:
            files.append(control)
    for path in sorted(files, key=lambda value: str(value)):
        digest.update(str(path).encode())
        try:
            mode = path.lstat().st_mode if path.exists() or path.is_symlink() else 0
            digest.update(str(stat.S_IFMT(mode)).encode())
            digest.update(str(stat.S_IMODE(mode)).encode())
            digest.update(path.read_bytes() if path.is_file() else b"(missing)")
        except OSError as exc:
            raise WorkflowFailed(f"cannot fingerprint Git control {path}: {exc}") from exc
    return digest.hexdigest()


def origin_endpoint(root: Path) -> str:
    """Credential-free identity shared by every origin fetch and push target."""
    try:
        git = open_repo(root).git
        fetch = git.remote("get-url", "--all", "origin").splitlines()
        push = git.remote("get-url", "--all", "--push", "origin").splitlines()
    except GitError as exc:
        raise WorkflowFailed(f"cannot resolve origin endpoints: {exc}") from exc
    endpoints = {_safe_endpoint(url) for url in [*fetch, *push] if url.strip()}
    if len(endpoints) != 1:
        raise WorkflowFailed("implement-plan requires every origin fetch/push URL to be one endpoint")
    return endpoints.pop()


def origin_digest(root: Path) -> str:
    """Opaque checkpoint identity for the credential-free origin endpoint."""
    return hashlib.sha256(origin_endpoint(root).encode()).hexdigest()


def _safe_endpoint(value: str) -> str:
    """Remove URL userinfo before an origin identity reaches a checkpoint."""
    endpoint = value.strip()
    parsed = urlsplit(endpoint)
    if not parsed.scheme or not parsed.netloc:
        if ":" in endpoint:
            authority, path = endpoint.split(":", 1)
            if "@" in authority:
                return f"{authority.rsplit('@', 1)[1]}:{path}"
        return endpoint
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host + (f":{parsed.port}" if parsed.port is not None else "")
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _clean_repo_relative(value: str, *, label: str, allow_dot: bool = False) -> str:
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise WorkflowFailed(f"{label} must be a safe repository-relative path, got {value!r}")
    normalized = path.as_posix().rstrip("/") or "."
    if normalized == "." and not allow_dot:
        raise WorkflowFailed(f"{label} may not own the whole repository")
    return normalized


def commit_subject(task: PlanTask) -> str:
    """The task's Conventional Commit subject, derived from its own title.

    Derived rather than fixed because the subject is the durable output: a reader
    six months out has the log and nothing else, and a run of commits all reading
    "implement planned change" tells them only that a machine was here. It stays a
    pure function of the packet so `validate_task_commit` can still assert the
    committed message byte-for-byte.
    """
    head = task.commit_type + (f"({task.commit_scope})" if task.commit_scope else "")
    description = " ".join(task.title.split()).rstrip(".")
    description = description[:1].lower() + description[1:]
    return f"{head}: {description}"


def commit_body(task: PlanTask) -> str:
    """The task's objective, wrapped at 72 columns; empty when it has none."""
    paragraphs = [" ".join(block.split()) for block in task.objective.strip().split("\n\n")]
    return "\n\n".join(textwrap.fill(block, width=72) for block in paragraphs if block)


def validate_command(command: VerificationCommand, *, owner: str) -> VerificationCommand:
    if not command.argv or any(not part for part in command.argv):
        raise WorkflowFailed(f"{owner} has a verification command with an empty argv")
    executable = command.argv[0]
    executable_name = PurePosixPath(executable.replace("\\", "/")).name.lower()
    forbidden = {"git", "git.exe", "sh", "bash", "cmd", "cmd.exe", "powershell", "pwsh"}
    if executable_name in forbidden:
        raise WorkflowFailed(f"{owner} verification executable {executable!r} is not allowed")
    if not 1 <= command.timeout_s <= 7200:
        raise WorkflowFailed(f"{owner} verification timeout must be between 1 and 7200 seconds")
    command.cwd = _clean_repo_relative(
        command.cwd or ".", label=f"{owner} command cwd", allow_dot=True
    )
    return command


def _path_owned(path: str, scopes: list[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(
        candidate == PurePosixPath(scope) or PurePosixPath(scope) in candidate.parents
        for scope in scopes
    )


def _documentation(path: str) -> bool:
    candidate = PurePosixPath(path)
    return candidate.suffix.lower() in _DOC_SUFFIXES or "docs" in candidate.parts


def _valid_commit_scopes(root: Path) -> set[str]:
    try:
        tracked = open_repo(root).git.ls_files("-z").split("\0")
        return {
            path.split("/", 1)[0]
            for path in tracked
            if "/" in path and not path.startswith(".")
        } | {"deps", "release", "ci", "lint", "hooks"}
    except (GitError, OSError) as exc:
        raise WorkflowFailed(f"cannot inspect repository scopes at {root}: {exc}") from exc


def _validate_task(task: PlanTask, context: PlanRunContext) -> PlanTask:
    if not task.id.strip():
        raise WorkflowFailed("plan task needs an id to be addressable in the packet DAG")
    if not task.title.strip() or not task.objective.strip() or not task.acceptance:
        raise WorkflowFailed(f"task {task.id} needs a title, objective, and acceptance criteria")
    if not task.paths:
        raise WorkflowFailed(f"task {task.id} must own at least one explicit path")
    task.paths = list(
        dict.fromkeys(
            _clean_repo_relative(path, label=f"task {task.id} path") for path in task.paths
        )
    )
    if any(PurePosixPath(path).parts[0] == ".agents" for path in task.paths):
        raise WorkflowFailed(f"task {task.id} may not own Workhorse's .agents run storage")
    try:
        source = Path(context.source_path).relative_to(Path(context.repo_root)).as_posix()
    except ValueError:
        source = ""
    if source and _path_owned(source, task.paths):
        raise WorkflowFailed(f"task {task.id} ownership covers the private source plan {source}")
    if not task.verification:
        raise WorkflowFailed(f"task {task.id} must declare deterministic verification")
    task.verification = [
        validate_command(command, owner=f"task {task.id}") for command in task.verification
    ]
    if task.commit_type not in _COMMIT_TYPES:
        raise WorkflowFailed(f"task {task.id} has unsupported commit type {task.commit_type!r}")
    valid_scopes = _valid_commit_scopes(Path(context.repo_root))
    if task.commit_scope and (
        not _SCOPE.fullmatch(task.commit_scope) or task.commit_scope not in valid_scopes
    ):
        raise WorkflowFailed(f"task {task.id} has invalid commit scope {task.commit_scope!r}")
    # Vocabulary is not choice. `docs` is the type most often applied to a packet that
    # is nothing of the kind — the release tooling reads it and ships the work to
    # nobody, and the omission only surfaces weeks later as a bug report against a
    # version that never contained the change. A packet touching no documentation at
    # all is the one case where that is mechanically provable; a packet that does
    # touch some is left alone, because a documentation change may legitimately reach
    # into a source file for a docstring.
    if task.commit_type == "docs" and not any(_documentation(path) for path in task.paths):
        raise WorkflowFailed(
            f"task {task.id} is typed docs but owns no documentation: {', '.join(task.paths)}"
        )
    if len(commit_subject(task)) > 72:
        raise WorkflowFailed(f"task {task.id} commit subject exceeds 72 characters")
    task.depends_on = list(dict.fromkeys(task.depends_on))
    return task


def _topological(logger, tasks: list[PlanTask]) -> list[PlanTask]:
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise WorkflowFailed("plan decomposition contains duplicate task ids")
    position = {task.id: index for index, task in enumerate(tasks)}
    dependants: dict[str, list[str]] = {task.id: [] for task in tasks}
    indegree: dict[str, int] = {}
    for task in tasks:
        missing = [dependency for dependency in task.depends_on if dependency not in by_id]
        if missing:
            raise WorkflowFailed(f"task {task.id} depends on unknown tasks: {', '.join(missing)}")
        if task.id in task.depends_on:
            raise WorkflowFailed(f"task {task.id} depends on itself")
        indegree[task.id] = len(task.depends_on)
        for dependency in task.depends_on:
            dependants[dependency].append(task.id)
    ready = deque(task.id for task in tasks if indegree[task.id] == 0)
    ordered: list[PlanTask] = []
    while ready:
        task_id = ready.popleft()
        ordered.append(by_id[task_id])
        released: list[str] = []
        for dependant in dependants[task_id]:
            indegree[dependant] -= 1
            if indegree[dependant] == 0:
                released.append(dependant)
        ready.extend(sorted(released, key=position.__getitem__))
    if len(ordered) != len(tasks):
        cycle = ", ".join(task_id for task_id, degree in indegree.items() if degree)
        raise WorkflowFailed(f"plan decomposition contains a dependency cycle: {cycle}")
    ancestors: dict[str, set[str]] = {}
    for task in ordered:
        ancestors[task.id] = set(task.depends_on)
        for dependency in task.depends_on:
            ancestors[task.id].update(ancestors[dependency])
    # Two packets that own a file in common must be ordered against each other, so that
    # the later one is written against the earlier one's committed result rather than
    # against a file it is about to contradict. That order already exists: execution is
    # sequential, and the sort above is a total order the planner itself determined by
    # the sequence it emitted. What can be missing is the *statement* of it — declaring
    # every implied edge across eight packets sharing four files is a transitive closure
    # done by hand, and the one that gets forgotten is between two branches that do not
    # converge until much later. Record the implied edge instead of killing the run for
    # it: the invariant is that the pair is ordered and that the order is in the
    # checkpoint, and both hold. Every added edge runs forwards along `ordered`, so no
    # edge can create a cycle or change the sequence it was derived from.
    for index, right in enumerate(ordered):
        for left in ordered[:index]:
            if left.id in ancestors[right.id]:
                continue
            overlap = any(
                _path_owned(left_path, [right_path]) or _path_owned(right_path, [left_path])
                for left_path in left.paths
                for right_path in right.paths
            )
            if not overlap:
                continue
            right.depends_on.append(left.id)
            ancestors[right.id].update({left.id, *ancestors[left.id]})
            logger.info(
                "ordered %s after %s: shared path ownership, no declared dependency",
                right.id,
                left.id,
            )
    return ordered


@blueprint.node
def snapshot_plan(logger, plan_path: str, run_dir: str, repo_dir: str = "") -> PlanRunContext:
    """Freeze plan text and repository identity before any planning turn runs."""
    repo_root = find_repo_root(repo_dir)
    source = Path(plan_path).expanduser()
    if not source.is_absolute():
        source = repo_root / source
    source = source.resolve()
    try:
        content = source.read_bytes()
        text = content.decode("utf-8")
        repo = open_repo(repo_root)
        replacements = repo.git.for_each_ref("--format=%(refname)", "refs/replace").strip()
        if replacements:
            raise WorkflowFailed("implement-plan refuses repositories with active replacement refs")
        repo.git.update_environment(GIT_NO_REPLACE_OBJECTS="1")
        branch = repo.active_branch.name
        base_commit = repo.git.rev_parse("HEAD").strip()
    except (OSError, UnicodeDecodeError, GitError, TypeError) as exc:
        raise WorkflowFailed(f"cannot snapshot plan {source}: {exc}") from exc
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        raise WorkflowFailed(
            f"implement-plan requires a clean worktree at {repo_root}; preserve or commit existing work first"
        )
    if not branch or branch == "HEAD":
        raise WorkflowFailed("implement-plan requires a checked-out branch, not detached HEAD")
    try:
        remote = repo.git.ls_remote("origin", f"refs/heads/{branch}")
    except GitError as exc:
        raise WorkflowFailed(f"implement-plan requires a readable origin/{branch}: {exc}") from exc
    remote_head = remote.split()[0] if remote.split() else ""
    if remote_head != base_commit:
        raise WorkflowFailed(
            f"implement-plan requires origin/{branch} at local HEAD {base_commit[:12]}"
        )
    digest = hashlib.sha256(content).hexdigest()
    private_dir = Path(run_dir) / "implement-plan"
    context = PlanRunContext(
        repo_root=str(repo_root),
        source_path=str(source),
        plan_text=text,
        plan_digest=digest,
        worklist_path=str(private_dir / "worklist.json"),
        branch=branch,
        base_commit=base_commit,
        origin_digest=origin_digest(repo_root),
        git_control_digest=git_control_digest(repo_root),
        run_nonce=secrets.token_hex(16),
    )
    _atomic_json(
        private_dir / "snapshot.json",
        context.model_dump(mode="json", exclude={"plan_text"}),
    )
    logger.info("snapshotted %s as %s", source, digest[:12])
    return context


def assert_plan_unchanged(context: PlanRunContext) -> None:
    try:
        current_digest = hashlib.sha256(Path(context.source_path).read_bytes()).hexdigest()
    except OSError as exc:
        raise WorkflowFailed(f"cannot re-read source plan: {exc}") from exc
    if current_digest != context.plan_digest:
        raise WorkflowFailed("source plan changed after snapshot; start a new implement-plan run")


@blueprint.node
def prepare_plan(
    logger, decomposition: PlanDecomposition, context: PlanRunContext
) -> PreparedPlan:
    """Validate the agent proposal into immutable checkpoint authority."""
    return _prepared_plan(logger, decomposition, context)


@blueprint.node
def audit_plan_decomposition(
    logger, decomposition: PlanDecomposition, context: PlanRunContext
) -> str:
    """Why this proposal cannot become checkpoint authority, or "" if it can.

    Decomposition is the one agent turn in this flow with no bounded rework, so any
    packet a validation rejects has cost a whole planning turn and ended the run —
    for a scope typo, a subject three characters too long, an edge the planner could
    only have found by hand-computing a transitive closure. Every other turn here
    gets its verdict back and one more attempt; this reports the same verdict without
    raising, so the caller can spend that attempt before the failure becomes terminal.
    """
    try:
        _prepared_plan(logger, decomposition, context)
    except WorkflowFailed as exc:
        logger.info("decomposition rejected: %s", exc)
        return str(exc)
    return ""


def _prepared_plan(
    logger, decomposition: PlanDecomposition, context: PlanRunContext
) -> PreparedPlan:
    assert_plan_unchanged(context)
    if decomposition.status != "ready":
        raise WorkflowFailed(
            f"plan decomposition was not ready: {decomposition.summary or decomposition.status or 'no result'}"
        )
    if not decomposition.tasks:
        raise WorkflowFailed("plan decomposition produced no implementation tasks")
    tasks = _topological(logger, [_validate_task(task, context) for task in decomposition.tasks])
    final = [
        validate_command(command, owner="final gate")
        for command in decomposition.final_verification
    ]
    if not final:
        raise WorkflowFailed("plan decomposition must declare a final repository verification gate")
    logger.info("prepared %d dependency-ordered plan tasks", len(tasks))
    return PreparedPlan(tasks=tasks, final_verification=final, summary=decomposition.summary)


def task_key(context: PlanRunContext, task_id: str) -> str:
    source = f"{context.run_nonce}:{task_id}".encode()
    return hashlib.sha256(source).hexdigest()[:16]


def write_worklist(
    context: PlanRunContext,
    plan: PreparedPlan,
    *,
    current_index: int,
    completed_commits: list[str],
    blocked: str = "",
) -> None:
    """Project checkpoint authority for operators; never read it back to schedule work."""
    items: list[wl.WorkItem] = []
    for index, task in enumerate(plan.tasks):
        if index < len(completed_commits):
            status, commit_sha = "done", completed_commits[index]
        elif index == current_index and blocked == task.id:
            status, commit_sha = "blocked", ""
        elif index == current_index:
            status, commit_sha = "active", ""
        else:
            status, commit_sha = "pending", ""
        items.append(
            wl.WorkItem(
                id=task.id,
                status=status,
                kind="plan-task",
                order=index + 1,
                payload={"task": task.model_dump(mode="json"), "commit_sha": commit_sha},
            )
        )
    payload = {
        "version": 1,
        "plan_digest": context.plan_digest,
        "branch": context.branch,
        "base_commit": context.base_commit,
        "tasks": [item.model_dump(exclude_unset=True, mode="json") for item in items],
    }
    _atomic_json(Path(context.worklist_path), payload)


__all__ = [
    "assert_plan_unchanged",
    "audit_plan_decomposition",
    "commit_body",
    "commit_subject",
    "git_control_digest",
    "origin_endpoint",
    "origin_digest",
    "prepare_plan",
    "snapshot_plan",
    "task_key",
    "validate_command",
    "write_worklist",
]