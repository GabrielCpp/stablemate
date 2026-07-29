"""The git commands workflow scripts need, wrapped so a script never shells out.

GitPython is a thin wrapper over the git CLI, so behaviour matches the subprocess
calls these replaced while the error handling routes through ``GitError``. Under test
the git CLI still runs for real against a throwaway repo
(``workhorse.testing.make_git_repo``) — there is nothing to monkeypatch here; only the
GitHub seam (:mod:`workhorse_workflows.kit.github`) is faked.

Each helper opens the repo lazily and returns a plain value / bool so callers stay
fail-soft: a bad repo or failed command yields ``None``/``False``/``-1`` rather than
raising into an unattended run.

GitPython is imported at **module scope**. It used to be imported inside every
function because importing it runs a ``git --version`` probe that crashes when ``git``
is shadowed by a stub, and workhorse is full of git-free scripts that must import
``scriptutil`` without a real git on PATH. That is no longer a concern here: this
module *is* the git half, nothing imports it except code that is about to run git, and
the engine no longer imports it at all.
"""
from __future__ import annotations

from pathlib import Path

from git import Git, Repo
from git.exc import GitCommandError, GitError


def open_repo(path: str | Path) -> Repo:
    """The GitPython ``Repo`` at ``path`` — the single seam every helper here opens."""
    return Repo(str(path))


def origin_url(path: str | Path) -> str | None:
    """The ``origin`` remote URL of the repo at ``path``, or None when absent."""
    try:
        repo = open_repo(path)
        return next((r.url for r in repo.remotes if r.name == "origin"), None)
    except GitError:
        return None


def local_branch_exists(path: str | Path, branch: str) -> bool:
    """True if ``branch`` exists as a local branch (mirrors GitPython's repo.heads)."""
    try:
        return branch in [h.name for h in open_repo(path).heads]
    except GitError:
        return False


def branch_exists(path: str | Path, ref: str) -> bool:
    """True if ``ref`` resolves in the repo (mirrors ``git rev-parse --verify``)."""
    try:
        open_repo(path).git.rev_parse("--verify", "--quiet", ref)
        return True
    except GitError:
        return False


def current_branch(path: str | Path) -> str:
    """The current branch name, or ``"main"`` if detached/unresolvable."""
    try:
        name = open_repo(path).active_branch.name
        return name if name and name != "HEAD" else "main"
    except (GitError, TypeError):
        return "main"


def active_branch(path: str | Path) -> str | None:
    """The current branch name, or None when HEAD is detached/unresolvable.

    Unlike :func:`current_branch` (which defaults to ``"main"``), this preserves the
    'no branch' signal callers use to fall back to a trunk."""
    try:
        name = open_repo(path).active_branch.name
    except (GitError, TypeError):
        return None
    return name or None


def checkout(path: str | Path, branch: str, *, create: bool = False, reset: bool = False) -> bool:
    """Check out ``branch``. ``create`` cuts it with ``-b``; ``reset`` create-or-resets
    it to the current HEAD with ``-B`` (and wins over ``create``). Returns success; a
    failure is reported as False rather than raised (best-effort)."""
    if reset:
        args = ["-B", branch]
    elif create:
        args = ["-b", branch]
    else:
        args = [branch]
    try:
        open_repo(path).git.checkout(*args)
        return True
    except GitError:
        return False


def commits_ahead(path: str | Path, branch: str, base: str) -> int:
    """Commits reachable from ``branch`` but not ``origin/<base>``. Returns -1 when
    the range is unresolvable (e.g. no ``origin/<base>`` yet)."""
    try:
        out = open_repo(path).git.rev_list("--count", f"origin/{base}..{branch}")
        return int(out.strip())
    except (GitError, ValueError):
        return -1


def commit_paths(path: str | Path, message: str, *pathspecs: str) -> bool:
    """Stage ``pathspecs`` (everything, via ``-A``, when none are given) and commit.

    Returns False when nothing was staged (or the commit failed), True when a
    commit was made. The staged-change check is scoped to the same pathspecs, so a
    scoped commit lands only when those paths actually changed."""
    scope = ["--", *pathspecs] if pathspecs else []
    try:
        repo = open_repo(path)
        repo.git.add(*(pathspecs or ("-A",)))
        try:
            repo.git.diff("--cached", "--quiet", *scope)
            return False  # nothing staged
        except GitCommandError:
            pass  # staged changes present
        repo.git.commit("-m", message, *scope)
        return True
    except GitError:
        return False


def commit_all(path: str | Path, message: str) -> bool:
    """Stage every change (``git add -A``) and commit it. Returns False when there
    was nothing to commit (or the commit failed)."""
    return commit_paths(path, message)


def short_sha(path: str | Path, ref: str = "HEAD") -> str:
    """The abbreviated commit sha for ``ref`` (``git rev-parse --short``), or "" when
    it can't be resolved."""
    try:
        return open_repo(path).git.rev_parse("--short", ref).strip()
    except GitError:
        return ""


def rename_branch(path: str | Path, old: str, new: str) -> bool:
    """Rename branch ``old`` to ``new`` (``git branch -m``). Returns success."""
    try:
        open_repo(path).git.branch("-m", old, new)
        return True
    except GitError:
        return False


def restore_paths(path: str | Path, *pathspecs: str) -> bool:
    """Discard working-tree changes to ``pathspecs`` (``git checkout -- <paths>``).
    Returns success; a no-pathspec call is a no-op that returns False."""
    if not pathspecs:
        return False
    try:
        open_repo(path).git.checkout("--", *pathspecs)
        return True
    except GitError:
        return False


def default_branch(path: str | Path) -> str | None:
    """The remote's default branch (``origin/HEAD`` → e.g. ``main``), or None when
    ``origin/HEAD`` is not set / unresolvable."""
    try:
        ref = open_repo(path).git.symbolic_ref("--short", "refs/remotes/origin/HEAD").strip()
    except GitError:
        return None
    if ref.startswith("origin/"):
        ref = ref[len("origin/"):]
    return ref or None


def merge_base(path: str | Path, *refs: str) -> str | None:
    """The best common ancestor of ``refs`` (``git merge-base``), or None."""
    try:
        out = open_repo(path).git.merge_base(*refs).strip()
    except GitError:
        return None
    return out or None


def show_file(path: str | Path, ref: str, relpath: str) -> str | None:
    """The contents of ``relpath`` at ``ref`` (``git show <ref>:<relpath>``), or None
    when it didn't exist there (or git is unavailable)."""
    try:
        return open_repo(path).git.show(f"{ref}:{relpath}")
    except GitError:
        return None


def diff_text(path: str | Path, *args: str) -> str:
    """Raw ``git diff <args>`` output ("" on error). The caller passes the diff
    arguments, e.g. ``diff_text(root, "--unified=0", base, "HEAD", "--")``."""
    try:
        return open_repo(path).git.diff(*args)
    except GitError:
        return ""


def list_tracked_files(path: str | Path, *pathspecs: str) -> list[str]:
    """Repo-relative paths git tracks (``git ls-files``), optionally limited to
    ``pathspecs``. Empty list when git is unavailable."""
    try:
        out = open_repo(path).git.ls_files(*pathspecs)
    except GitError:
        return []
    return [line for line in out.splitlines() if line]


def remote_urls(path: str | Path, name: str = "origin") -> list[str]:
    """The configured URLs for remote ``name`` — its push URL then its fetch URL,
    de-duplicated in order. Empty when the remote or repo is absent.

    Uses a bare ``git`` bound to ``path`` (not :func:`open_repo`) plus a per-call
    ``safe.directory`` trust, so it can read a repo whose working tree is owned by
    another user — e.g. a host-owned bind mount inside a container, which git would
    otherwise refuse to touch with a "dubious ownership" error."""
    repo_path = str(Path(path).resolve())
    git = Git(repo_path)
    urls: list[str] = []
    for extra in (["--push", name], [name]):
        try:
            url = git(c=f"safe.directory={repo_path}").remote("get-url", *extra).strip()
        except GitError:
            url = ""
        if url and url not in urls:
            urls.append(url)
    return urls


def set_identity(path: str | Path, name: str, email: str) -> bool:
    """Set the repo-local ``user.name`` / ``user.email`` (``git config``). Returns
    success. Used by unattended committers (e.g. a container agent) that have no
    ambient git identity."""
    try:
        repo = open_repo(path)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", name)
            cw.set_value("user", "email", email)
        return True
    except GitError:
        return False


def allow_all_directories() -> None:
    """Add ``*`` to the GLOBAL ``safe.directory`` list (``git config --global``), so
    git operates on repos owned by another user — a host-owned bind mount inside a
    disposable, isolated container. Best-effort: a failure is swallowed."""
    try:
        Git().config("--global", "--add", "safe.directory", "*")
    except GitError:
        pass


def clone(url: str, dest: str | Path, *, branch: str | None = None, single_branch: bool = True) -> bool:
    """Clone ``url`` into ``dest`` (``git clone``). Returns success. Honors the ambient
    ``GIT_SSH_COMMAND`` for SSH remotes (git inherits it from the environment)."""
    kwargs: dict = {}
    if branch:
        kwargs["branch"] = branch
    if single_branch:
        kwargs["single_branch"] = True
    try:
        Repo.clone_from(url, str(dest), **kwargs)
        return True
    except GitError:
        return False


def fetch_reset(path: str | Path, branch: str, *, remote: str = "origin") -> bool:
    """Fetch ``remote`` and hard-reset the local ``branch`` to ``<remote>/<branch>``
    (``git fetch`` → ``checkout`` → ``reset --hard``). Returns success."""
    try:
        git = open_repo(path).git
        git.fetch("--quiet", remote)
        git.checkout("--quiet", branch)
        git.reset("--quiet", "--hard", f"{remote}/{branch}")
        return True
    except GitError:
        return False


def push_to_origin(
    path: str | Path, branch: str, *, remote: str = "origin", force_with_lease: bool = False
) -> bool:
    """Push ``branch`` to ``remote`` using the checkout's AMBIENT credentials (SSH key
    or a cached helper) — not a token (see
    :func:`workhorse_workflows.kit.github.push_branch` for token pushes).
    ``force_with_lease`` adds ``--force-with-lease``. Returns success."""
    args = ["--quiet"]
    if force_with_lease:
        args.append("--force-with-lease")
    try:
        open_repo(path).git.push(*args, remote, branch)
        return True
    except GitError:
        return False
