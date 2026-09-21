"""GitHub access for workflow scripts: PyGithub, never the ``gh`` CLI."""
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
    """Derive a github.com ``owner/repo`` slug from an origin URL (SSH or HTTPS)."""
    for prefix in _GITHUB_URL_PREFIXES:
        if url.startswith(prefix):
            path = url[len(prefix):]
            return path[:-4] if path.endswith(".git") else path
    return None


def github_client(token: str | None = None):
    """Return an authenticated PyGithub ``Github`` client."""
    tok = token or credentials.api_token()
    if tok:
        return Github(auth=Auth.Token(tok))
    return Github()


def resolve_github_token(root: str | Path) -> str:
    """Resolve the GitHub token for the coder PR/CI steps, given the repo ``root``."""
    return credentials.github_token(root)


def resolve_repo(path: str | Path, token: str | None = None):
    """Resolve the GitHub repository for the ``origin`` at ``path``."""
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


_PUSH_CRED_HELPER = '!f() { echo username=x-access-token; echo "password=${GH_TOKEN}"; }; f'


def push_branch(
    path: str | Path, token: str, branch: str, *, verify: bool = True, slug: str | None = None
) -> bool:
    """Push ``branch`` to a github.com repo over HTTPS with a transient token."""
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
    """Fetch ``base`` from the github.com ``origin`` over HTTPS and hard-set the local ``base`` to it (``git checkout -B <base> FETCH_HEAD``)."""
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
