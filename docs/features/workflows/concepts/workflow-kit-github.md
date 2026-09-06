---
type: concept
slug: workflow-kit-github
title: Workflow kit GitHub
---
# Workflow kit GitHub

The GitHub kit is the workflow package's boundary for GitHub repository discovery, pull-request
lookup, authenticated API access, HTTPS branch pushes, and synchronization after a merge. It uses
the [credentials kit](workflow-kit-credentials.md) for token resolution and the [Git kit](workflow-kit-git.md)
for repository and remote operations. GitHub and Git failures are represented as empty or false
results so callers can treat unavailable remote integration as a best-effort outcome.

- code: `workflows/src/workhorse_workflows/kit/github.py`

## Methods

### repo_full_name_from_url

- sig: `repo_full_name_from_url(url: str) -> str | None`
- does: recognizes GitHub origins with `git@github.com:`, `ssh://git@github.com/`, or `https://github.com/` prefixes
- does: removes a trailing `.git` suffix from the recognized repository path
- returns: the remaining `owner/repo` path for a recognized prefix
- returns: `None` when the URL does not use one of the recognized GitHub prefixes
- code: `workflows/src/workhorse_workflows/kit/github.py::repo_full_name_from_url`

### github_client

- sig: `github_client(token: str | None = None)`
- does: uses the supplied token when it is truthy
- does: resolves an absent or empty token through `credentials.api_token()`
- returns: an authenticated PyGithub client when a token is available
- returns: an unauthenticated PyGithub client when no token is available
- code: `workflows/src/workhorse_workflows/kit/github.py::github_client`

### resolve_github_token

- sig: `resolve_github_token(root: str | Path) -> str`
- does: resolves the repository-specific GitHub token variable and its configured fallback variables through the credentials kit
- returns: the resolved token string, or an empty string when no candidate is set
- code: `workflows/src/workhorse_workflows/kit/github.py::resolve_github_token`

### resolve_repo

- sig: `resolve_repo(path: str | Path, token: str | None = None)`
- does: reads the `origin` URL for the repository at `path`
- does: derives a GitHub `owner/repo` slug from the origin URL
- does: requests the repository through the GitHub client seam using the optional token
- returns: `(repository, slug)` when the origin is a recognized GitHub URL and the API lookup succeeds
- returns: `(None, None)` when there is no origin or the origin is not a recognized GitHub URL
- returns: `(None, slug)` when the recognized repository cannot be reached through the API
- code: `workflows/src/workhorse_workflows/kit/github.py::resolve_repo`

### find_open_pr

- sig: `find_open_pr(gh_repo, branch: str)`
- does: lists open pull requests whose head selector is the repository owner's login and the supplied branch
- returns: the first matching open pull request
- returns: `None` when no matching pull request exists
- returns: `None` when GitHub rejects the owner or pull-request query
- code: `workflows/src/workhorse_workflows/kit/github.py::find_open_pr`

### push_branch

- sig: `push_branch(path: str | Path, token: str, branch: str, *, verify: bool = True, slug: str | None = None) -> bool`
- does: derives the target GitHub slug from the repository origin unless `slug` is supplied
- does: pushes the local `branch` to the same-named remote branch over an HTTPS GitHub URL
- does: supplies the token through a transient `GH_TOKEN` credential helper rather than a URL, Git configuration, or process argument
- does: when `verify` is true, compares the remote branch head with the local branch head after pushing
- returns: `false` when no GitHub target exists, the repository cannot be opened, the push fails, or verification fails
- returns: `true` after a successful push when verification is disabled
- returns: `true` after a successful push whose remote head equals the local head when verification is enabled
- code: `workflows/src/workhorse_workflows/kit/github.py::push_branch`

### sync_to_origin

- sig: `sync_to_origin(path: str | Path, token: str, base: str) -> str | None`
- does: derives the GitHub slug from the repository's `origin` URL
- does: fetches `base` from the GitHub repository over HTTPS using the transient credential helper
- does: resets the local `base` branch to the fetched `FETCH_HEAD`
- returns: the new abbreviated `HEAD` SHA after fetch and reset succeed
- returns: `None` when the origin is not a recognized GitHub URL, the repository cannot be opened, or any fetch, checkout, or SHA lookup fails
- code: `workflows/src/workhorse_workflows/kit/github.py::sync_to_origin`
