"""The git commands workflow scripts need, wrapped so a script never shells out."""
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
    """The current branch name, or None when HEAD is detached/unresolvable."""
    try:
        name = open_repo(path).active_branch.name
    except (GitError, TypeError):
        return None
    return name or None


def checkout(path: str | Path, branch: str, *, create: bool = False, reset: bool = False) -> bool:
    """Check out ``branch``."""
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


def branch_owner(path: str | Path, branch: str) -> str | None:
    """The working tree that currently has ``branch`` checked out, or None."""
    try:
        listing = open_repo(path).git.worktree("list", "--porcelain")
    except GitError:
        return None
    wanted = branch if branch.startswith("refs/") else f"refs/heads/{branch}"
    tree: str | None = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            tree = line[len("worktree "):].strip()
        elif line.startswith("branch ") and tree and line[len("branch "):].strip() == wanted:
            return tree
    return None


def branch_merged(path: str | Path, branch: str, base: str) -> bool:
    """True when ``branch`` carries nothing ``base`` does not already have."""
    for ref in (base, f"origin/{base}") if base and "/" not in base else (base,):
        if not ref or not branch_exists(path, ref):
            continue
        if is_ancestor(path, branch, ref):
            return True
        try:
            open_repo(path).git.diff("--quiet", ref, branch)
            return True
        except GitError:
            continue
    return False


def commits_ahead(path: str | Path, branch: str, base: str) -> int:
    """Commits reachable from ``branch`` but not ``origin/<base>``."""
    try:
        out = open_repo(path).git.rev_list("--count", f"origin/{base}..{branch}")
        return int(out.strip())
    except (GitError, ValueError):
        return -1


def commit_paths(path: str | Path, message: str, *pathspecs: str, verify: bool = True) -> bool:
    """Stage exactly ``pathspecs`` and commit them."""
    if not pathspecs:
        return False
    scope = ["--", *pathspecs]
    try:
        repo = open_repo(path)
    except GitError:
        return False
    if not repo.git.status("--porcelain", *scope).strip():
        return False
    repo.git.add(*pathspecs)
    try:
        repo.git.diff("--cached", "--quiet", *scope)
        return False
    except GitCommandError:
        pass
    repo.git.commit("-m", message, *(() if verify else ("--no-verify",)), *scope)
    return True


def commit_all(path: str | Path, message: str) -> bool:
    """Stage EVERY change in the working tree (``git add -A``) and commit it."""
    try:
        repo = open_repo(path)
    except GitError:
        return False
    repo.git.add("-A")
    try:
        repo.git.diff("--cached", "--quiet")
        return False
    except GitCommandError:
        pass
    repo.git.commit("-m", message)
    return True


def head_sha(path: str | Path, ref: str = "HEAD") -> str:
    """The full commit sha for ``ref``, or "" when it can't be resolved."""
    try:
        return open_repo(path).git.rev_parse(ref).strip()
    except GitError:
        return ""


def short_sha(path: str | Path, ref: str = "HEAD") -> str:
    """The abbreviated commit sha for ``ref`` (``git rev-parse --short``), or "" when it can't be resolved."""
    try:
        return open_repo(path).git.rev_parse("--short", ref).strip()
    except GitError:
        return ""


def rename_branch(path: str | Path, old: str, new: str) -> bool:
    """Rename branch ``old`` to ``new`` (``git branch -m``)."""
    try:
        open_repo(path).git.branch("-m", old, new)
        return True
    except GitError:
        return False


def restore_paths(path: str | Path, *pathspecs: str) -> bool:
    """Discard working-tree changes to ``pathspecs`` (``git checkout -- <paths>``)."""
    if not pathspecs:
        return False
    try:
        open_repo(path).git.checkout("--", *pathspecs)
        return True
    except GitError:
        return False


def default_branch(path: str | Path) -> str | None:
    """The remote's default branch (``origin/HEAD`` → e.g."""
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


TRUNK_CANDIDATES = ("origin/master", "origin/main", "master", "main")


def trunk_base(path: str | Path) -> str:
    """The ref a branch's own work starts after: its merge base with trunk, else ``HEAD~1``."""
    for branch in TRUNK_CANDIDATES:
        base = merge_base(path, "HEAD", branch)
        if base:
            return base
    return "HEAD~1"


def merge_ref(path: str | Path, ref: str) -> bool:
    """Merge ``ref`` into the current branch."""
    try:
        open_repo(path).git.merge(ref, "--no-edit")
        return True
    except GitError:
        try:
            open_repo(path).git.merge("--abort")
        except GitError:
            pass
        return False


def is_ancestor(path: str | Path, ancestor: str, descendant: str) -> bool:
    """True if ``ancestor`` is reachable from ``descendant`` (``git merge-base --is-ancestor``)."""
    try:
        open_repo(path).git.merge_base("--is-ancestor", ancestor, descendant)
        return True
    except GitError:
        return False


def show_file(path: str | Path, ref: str, relpath: str) -> str | None:
    """The contents of ``relpath`` at ``ref`` (``git show <ref>:<relpath>``), or None when it didn't exist there (or git is unavailable)."""
    try:
        return open_repo(path).git.show(f"{ref}:{relpath}")
    except GitError:
        return None


def diff_text(path: str | Path, *args: str) -> str:
    """Raw ``git diff <args>`` output ("" on error)."""
    try:
        return open_repo(path).git.diff(*args)
    except GitError:
        return ""


def list_tracked_files(path: str | Path, *pathspecs: str) -> list[str]:
    """Repo-relative paths git tracks (``git ls-files``), optionally limited to ``pathspecs``."""
    try:
        out = open_repo(path).git.ls_files(*pathspecs)
    except GitError:
        return []
    return [line for line in out.splitlines() if line]


def remote_urls(path: str | Path, name: str = "origin") -> list[str]:
    """The configured URLs for remote ``name`` — its push URL then its fetch URL, de-duplicated in order."""
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
    """Set the repo-local ``user.name`` / ``user.email`` (``git config``)."""
    try:
        repo = open_repo(path)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", name)
            cw.set_value("user", "email", email)
        return True
    except GitError:
        return False


def allow_all_directories() -> None:
    """Add ``*`` to the GLOBAL ``safe.directory`` list (``git config --global``), so git operates on repos owned by another user — a host-owned bind mount inside a disposable, isolated container."""
    try:
        Git().config("--global", "--add", "safe.directory", "*")
    except GitError:
        pass


def clone(
    url: str,
    dest: str | Path,
    *,
    branch: str | None = None,
    single_branch: bool = True,
    ssh_command: str = "",
) -> bool:
    """Clone ``url`` into ``dest`` (``git clone``)."""
    kwargs: dict = {}
    if branch:
        kwargs["branch"] = branch
    if single_branch:
        kwargs["single_branch"] = True
    if ssh_command:
        kwargs["env"] = {"GIT_SSH_COMMAND": ssh_command}
    try:
        Repo.clone_from(url, str(dest), **kwargs)
        return True
    except GitError:
        return False


def fetch_reset(path: str | Path, branch: str, *, remote: str = "origin") -> bool:
    """Fetch ``remote`` and hard-reset the local ``branch`` to ``<remote>/<branch>`` (``git fetch`` → ``checkout`` → ``reset --hard``)."""
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
    """Push ``branch`` to ``remote`` using the checkout's AMBIENT credentials (SSH key or a cached helper) — not a token (see :func:`workhorse_workflows.kit.github.push_branch` for token pushes)."""
    args = ["--quiet"]
    if force_with_lease:
        args.append("--force-with-lease")
    try:
        open_repo(path).git.push(*args, remote, branch)
        return True
    except GitError:
        return False
