"""GitHub access for workflow scripts: PyGithub, never the ``gh`` CLI.

:func:`github_client` is the one seam every script goes through. Because it is a plain
Python call, an in-process test monkeypatches it — no PATH shim, no CLI, no network.
The helpers below inherit that seam.

**Patch the defining module.** A test fakes ``workhorse_workflows.kit.github.github_client``
and both paths follow: the global lookups made inside *this* module, and the scripts that
imported the name flat, since :mod:`workhorse_workflows.kit` forwards through
``__getattr__`` rather than binding a copy. For the same reason the git calls here go
through the module object (``git_kit.origin_url``) instead of a direct import — a test
that fakes ``kit.git.origin_url`` must reach these callers too.

The token pushes live here rather than in :mod:`workhorse_workflows.kit.git` because
they are github.com operations that happen to use git — they resolve an ``owner/repo``
slug and push over ``https://github.com/…`` with a transient credential.
"""
from __future__ import annotations

from pathlib import Path

from git.exc import GitError
from github import Auth, Github, GithubException

from workhorse_workflows.kit import credentials
from workhorse_workflows.kit import git as git_kit

_GITHUB_URL_PREFIXES = (
    "git@github.com:",
    "ssh://git@github.com/",
    "https://github.com/",
)


def repo_full_name_from_url(url: str) -> str | None:
    """Derive a github.com ``owner/repo`` slug from an origin URL (SSH or HTTPS).
    Returns None when the origin is not a github.com remote."""
    for prefix in _GITHUB_URL_PREFIXES:
        if url.startswith(prefix):
            path = url[len(prefix):]
            return path[:-4] if path.endswith(".git") else path
    return None


def github_client(token: str | None = None):
    """Return an authenticated PyGithub ``Github`` client.

    The one seam every workflow script goes through for GitHub API access (opening
    PRs, checking checks, merging) instead of shelling out to the ``gh`` CLI.
    ``token`` defaults to whatever :mod:`workhorse_workflows.kit.credentials` finds —
    the only module in this package allowed to read the environment, and only because
    a secret must never become a checkpointed parameter.
    """
    tok = token or credentials.api_token()
    if tok:
        return Github(auth=Auth.Token(tok))
    return Github()


def resolve_github_token(root: str | Path) -> str:
    """Resolve the GitHub token for the coder PR/CI steps, given the repo ``root``.

    Order: the env var named by agents.yml ``workflow.githubTokenEnv`` (repo-
    configurable, not hardcoded), then the conventional ``GH_TOKEN``, then
    ``GITHUB_TOKEN``. Returns ``""`` when none is set — callers treat empty as
    "no token" and skip (best-effort).

    ``root`` is required rather than defaulted: it is the caller's ``repo_dir``, and a
    node that let this resolve itself from the ambient environment would be reading a
    run input the run's parameters never recorded.
    """
    return credentials.github_token(root)


def resolve_repo(path: str | Path, token: str | None = None):
    """Resolve the GitHub repository for the ``origin`` at ``path``.

    Returns ``(repo, slug)`` where ``repo`` is a PyGithub ``Repository`` (via the
    :func:`github_client` seam) or None when there is no origin, the origin is not a
    github.com remote, or the API can't be reached; ``slug`` is the ``owner/repo``
    string (or None when it can't be derived) for logging."""
    url = git_kit.origin_url(path)
    if not url:
        return None, None
    slug = repo_full_name_from_url(url)
    if not slug:
        return None, None
    try:
        return github_client(token).get_repo(slug), slug
    except GithubException:
        return None, slug


def find_open_pr(gh_repo, branch: str):
    """The first OPEN pull request on ``gh_repo`` whose head is ``branch``, or None."""
    try:
        owner = gh_repo.owner.login
        for pr in gh_repo.get_pulls(state="open", head=f"{owner}:{branch}"):
            return pr
    except GithubException:
        return None
    return None


# The token is read from GH_TOKEN by this inline credential helper at git-exec
# time, so it is never written into a remote URL, git config, or the process
# arguments (which would leak it into logs / `ps`).
_PUSH_CRED_HELPER = '!f() { echo username=x-access-token; echo "password=${GH_TOKEN}"; }; f'


def push_branch(
    path: str | Path, token: str, branch: str, *, verify: bool = True, slug: str | None = None
) -> bool:
    """Push ``branch`` to a github.com repo over HTTPS with a transient token.

    The target repo is the ``origin`` slug by default; pass ``slug`` to override it
    (for a bind-mount clone whose ``origin`` is a local path but that pushes to a
    known ``owner/repo``). With ``verify`` (the default) returns True only after
    confirming the remote branch head advanced to the local head — a push can
    report success while leaving the ref unmoved, which is exactly what let a fix
    loop spin against a stale PR head. Returns False on any failure (no github
    target, push rejected, or unverified head)."""
    if slug is None:
        url = git_kit.origin_url(path)
        slug = repo_full_name_from_url(url) if url else None
    if not slug:
        return False
    push_url = f"https://github.com/{slug}.git"
    try:
        git = git_kit.open_repo(path).git
    except GitError:
        return False
    git.update_environment(GH_TOKEN=token)
    cred = f"credential.helper={_PUSH_CRED_HELPER}"
    try:
        git(c=cred).push(push_url, f"{branch}:{branch}")
    except GitError:
        return False
    if not verify:
        return True
    try:
        local_head = git.rev_parse(branch).strip()
        ls_remote = git(c=cred).ls_remote(push_url, f"refs/heads/{branch}")
    except GitError:
        return False
    remote_head = ls_remote.split()[0] if ls_remote.split() else ""
    return bool(remote_head) and remote_head == local_head


def sync_to_origin(path: str | Path, token: str, base: str) -> str | None:
    """Fetch ``base`` from the github.com ``origin`` over HTTPS and hard-set the local
    ``base`` to it (``git checkout -B <base> FETCH_HEAD``).

    Returns the new short HEAD sha on success, or None on any failure. Used after a
    merge lands to move the local checkout to the merged tip, so the next branch is
    cut from it. The token rides the same inline credential helper as
    :func:`push_branch` — never written into a URL, git config, or the logs."""
    url = git_kit.origin_url(path)
    slug = repo_full_name_from_url(url) if url else None
    if not slug:
        return None
    fetch_url = f"https://github.com/{slug}.git"
    try:
        git = git_kit.open_repo(path).git
    except GitError:
        return None
    git.update_environment(GH_TOKEN=token)
    try:
        git(c=f"credential.helper={_PUSH_CRED_HELPER}").fetch(fetch_url, base)
        git.checkout("-B", base, "FETCH_HEAD")
        return git.rev_parse("--short", "HEAD").strip()
    except GitError:
        return None
