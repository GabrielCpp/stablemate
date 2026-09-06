---
type: concept
slug: repository-observation
title: Repository observation
---
# Repository observation

Repository state is diagnostic evidence, not a prediction of workflow behavior. Git failures,
non-repositories, and detached heads produce absent fields rather than failing the run. A cached
HEAD is reused within its TTL and refreshed at boundaries.

- code: `workhorse/workhorse/gitstate.py`

### observe
- sig: `observe(path: str | Path, *, dirty: bool = True, stash: bool = False) -> RepoState`
- does: records repository root, origin, HEAD, branch, and optionally dirty state
- does: records a stash-created commit only when requested and work exists
- returns: an observed `RepoState`, or an empty state when no repository can answer
- code: `workhorse/workhorse/gitstate.py::observe`
- tests: `workhorse/tests/test_gitstate.py::test_observe_reports_head_branch_and_clean`

### observe_scope
- sig: `observe_scope(cwd: str | Path, add_dirs: Sequence[str | Path] = ()) -> RepositorySnapshot`
- does: records the cwd and additional directories in request order
- does: deduplicates multiple paths belonging to one Git root while preserving unversioned directories
- returns: an immutable snapshot of the declared execution scope
- code: `workhorse/workhorse/gitstate.py::observe_scope`
- tests: `workhorse/tests/test_gitstate.py::test_scope_keeps_multiple_git_roots_and_an_unversioned_primary`

### RepoState.attributes
- sig: `RepoState.attributes(prefix: str) -> dict[str, str | bool]`
- returns: only observed non-empty attributes under the supplied prefix
- code: `workhorse/workhorse/gitstate.py::RepoState.attributes`

### RepositorySnapshot.attributes
- sig: `RepositorySnapshot.attributes() -> dict[str, str]`
- returns: primary workspace attributes and a compact JSON list of all declared directories
- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot.attributes`

### HeadWatch.head
- sig: `HeadWatch.head() -> str`
- returns: cached HEAD until the TTL expires, then refreshes it
- code: `workhorse/workhorse/gitstate.py::HeadWatch.head`

### HeadWatch.refresh
- sig: `HeadWatch.refresh() -> str`
- does: reads HEAD immediately and resets the cache timestamp
- returns: the current HEAD, or an empty string when Git cannot answer
- code: `workhorse/workhorse/gitstate.py::HeadWatch.refresh`

### HeadWatch.state
- sig: `HeadWatch.state(*, dirty: bool = True, stash: bool = False) -> RepoState`
- returns: a full observation and updates the cached HEAD
- code: `workhorse/workhorse/gitstate.py::HeadWatch.state`

### bind
- sig: `bind(path: str | Path, ttl_s: float = DEFAULT_TTL_S) -> None`
- does: installs a module-level `HeadWatch` for the run's working tree
- code: `workhorse/workhorse/gitstate.py::bind`

### unbind
- sig: `unbind() -> None`
- consistency: unbind removes the module-level repository observer
- verify: removed(subject="the bound module-level repository observer")
- code: `workhorse/workhorse/gitstate.py::unbind`

### current_head
- sig: `current_head(*, refresh: bool = False) -> str`
- returns: the bound tree's cached or refreshed HEAD, or an empty string when unbound
- code: `workhorse/workhorse/gitstate.py::current_head`

### current_state
- sig: `current_state(*, dirty: bool = True, stash: bool = False) -> RepoState`
- returns: a full bound-tree observation, or an empty state when unbound
- code: `workhorse/workhorse/gitstate.py::current_state`

### current_scope
- sig: `current_scope(cwd: str | Path | None = None, add_dirs: Sequence[str | Path] = (), *, refresh: bool = False) -> RepositorySnapshot`
- returns: the bound observer's cached or refreshed scope snapshot, or an empty snapshot when unbound
- code: `workhorse/workhorse/gitstate.py::current_scope`
