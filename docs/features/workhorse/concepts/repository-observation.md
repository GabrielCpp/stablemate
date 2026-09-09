---
type: concept
slug: repository-observation
title: Repository observation
---
# Repository observation

Repository state is diagnostic evidence, not a prediction of workflow behavior. Git failures,
non-repositories, and detached heads produce absent fields rather than failing the run. A cached
HEAD is reused within its TTL and refreshed at boundaries. The module also records the complete
declared filesystem scope, retaining unversioned directories and deduplicating paths that resolve
to the same Git root.

- code: `workhorse/workhorse/gitstate.py`
- code: `workhorse/workhorse/gitstate.py::RepoState`
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot`
- code: `workhorse/workhorse/gitstate.py::HeadWatch`
- detail: [Repository snapshot contexts](repository-snapshot-contexts.md)
- detail: [Repository snapshot concept selection](repository-snapshot-concept-selection.md)
- detail: [Repository snapshot documentation context](repository-snapshot-documentation-context.md)
- detail: [Directory observation context](directory-observation-context.md)
- detail: [RepoState concept selection](repo-state-concept-selection.md)

### method: observe
- sig: `observe(path: str | Path, *, dirty: bool = True, stash: bool = False) -> RepoState`
- does: records repository root, origin, HEAD, branch, and optionally dirty state
- verify: json_path(path="$.head", matches="^.+$")
- does: records a stash-created commit only when requested and work exists
- verify: json_path(path="$.stash", matches="^.+$")
- returns: an observed `RepoState`, or an empty state when no repository can answer
- verify: absent(subject="repository observation fields after Git cannot answer")
- code: `workhorse/workhorse/gitstate.py::observe`
- code: `workhorse/tests/test_gitstate.py::test_observe_reports_head_branch_and_clean`
- code: `workhorse/tests/test_gitstate.py::test_observe_preserves_the_exact_origin_url`
- code: `workhorse/tests/test_gitstate.py::test_observe_reports_a_dirty_tree_and_can_snapshot_it`
- tests: `workhorse/tests/test_gitstate.py::test_observe_reports_head_branch_and_clean`,
  `workhorse/tests/test_gitstate.py::test_observe_reports_a_dirty_tree_and_can_snapshot_it`,
  `workhorse/tests/test_gitstate.py::test_a_non_repo_is_observed_as_nothing_rather_than_as_clean`

### method: observe_scope
- sig: `observe_scope(cwd: str | Path, add_dirs: Sequence[str | Path] = ()) -> RepositorySnapshot`
- does: records the cwd and additional directories in request order
- verify: count(subject="declared directories in their requested order", equals=3)
- does: deduplicates multiple paths belonging to one Git root while preserving unversioned directories
- verify: count(subject="distinct repository and unversioned scope entries", equals=3)
- returns: an immutable snapshot of the declared execution scope
- verify: persists(subject="immutable repository scope snapshot")
- code: `workhorse/workhorse/gitstate.py::observe_scope`
- code: `workhorse/tests/test_gitstate.py::test_scope_keeps_multiple_git_roots_and_an_unversioned_primary`
- tests: `workhorse/tests/test_gitstate.py::test_scope_keeps_multiple_git_roots_and_an_unversioned_primary`

## Types

### field: RepoState
- type: frozen record
- semantics: one point-in-time observation whose empty values mean that Git did not provide that fact
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: path
- type: `str`
- default: `""`
- required: false
- semantics: directory passed to the observation
- verify: json_path(path="$.path", equals="")
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: root
- type: `str`
- default: `""`
- required: false
- semantics: resolved Git worktree root
- verify: json_path(path="$.root", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: origin
- type: `str`
- default: `""`
- required: false
- semantics: exact URL returned for the `origin` remote
- verify: json_path(path="$.origin", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: head
- type: `str`
- default: `""`
- required: false
- semantics: full commit identifier observed at the sample moment
- verify: json_path(path="$.head", matches="^[0-9a-f]{40}$")
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: branch
- type: `str`
- default: `""`
- required: false
- semantics: branch name, empty for a detached HEAD or an unavailable repository
- verify: json_path(path="$.branch", equals="main")
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: dirty
- type: `bool | None`
- default: `None`
- required: false
- semantics: true or false when status was checked, and None when it was not observed
- verify: json_path(path="$.dirty", equals=false)
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

#### field: stash
- type: `str`
- default: `""`
- required: false
- semantics: commit identifier created by an explicit WIP snapshot request
- verify: json_path(path="$.stash", matches="^[0-9a-f]{40}$")
- code: `workhorse/workhorse/gitstate.py::RepoState`
- detail: [RepoState fields](repo-state-fields.md)

### field: DirectoryObservation
- type: frozen record
- semantics: one directory in the declared execution scope and its Git identity, if any
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: path
- type: `str`
- required: true
- semantics: expanded and resolved directory path
- verify: json_path(path="$.path", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: role
- type: `str`
- required: true
- semantics: `cwd` for the primary directory or `add_dir` for an additional directory
- verify: json_path(path="$.role", matches="^(cwd|add_dir)$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: vcs
- type: `str`
- required: true
- semantics: `git` for a Git root and `unversioned` when no Git identity is available
- verify: json_path(path="$.vcs", matches="^(git|unversioned)$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: root
- type: `str`
- default: `""`
- required: false
- semantics: resolved Git root, empty for an unversioned directory
- verify: json_path(path="$.root", equals="")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: origin
- type: `str`
- default: `""`
- required: false
- semantics: exact origin URL for a Git directory
- verify: json_path(path="$.origin", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: branch
- type: `str`
- default: `""`
- required: false
- semantics: observed branch name
- verify: json_path(path="$.branch", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

#### field: head
- type: `str`
- default: `""`
- required: false
- semantics: observed full HEAD identifier
- verify: json_path(path="$.head", matches="^[0-9a-f]{40}$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- detail: [Directory observation fields](directory-observation-fields.md)

### field: RepositorySnapshot
- type: frozen record
- default: empty tuple of directories
- required: true
- semantics: immutable ordered collection of distinct declared directories
- verify: count(subject="directories in an empty repository snapshot", equals=0)
- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot`
- detail: [Repository snapshot concept selection](repository-snapshot-concept-selection.md)
- detail: [Repository snapshot field selection](repository-snapshot-field-selection.md)
- detail: [Repository snapshot documentation context](repository-snapshot-documentation-context.md)

#### field: directories
- type: `tuple[DirectoryObservation, ...]`
- default: `()`
- required: true
- semantics: primary directory followed by additional directories after Git-root deduplication
- verify: count(subject="directories in a populated repository snapshot", equals=3)
- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot`
- detail: [Repository snapshot field selection](repository-snapshot-field-selection.md)

### field: HeadWatch
- type: TTL-cached repository observer
- semantics: caches HEAD and scope observations for one working tree
- code: `workhorse/workhorse/gitstate.py::HeadWatch`

#### field: path
- type: `str`
- required: true
- semantics: working tree path used by HEAD and full-state observations
- verify: json_path(path="$.path", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::HeadWatch.path`

## Methods

### RepoState.observed
- sig: `RepoState.observed -> bool`
- returns: true only when a non-empty HEAD was observed
- verify: json_path(path="$.observed", equals=true)
- code: `workhorse/workhorse/gitstate.py::RepoState.observed`

### RepoState.attributes
- sig: `RepoState.attributes(prefix: str) -> dict[str, str | bool]`
- returns: only observed non-empty attributes under the supplied prefix
- verify: json_path(path="$.git.head.start", equals="abc")
- code: `workhorse/workhorse/gitstate.py::RepoState.attributes`

### DirectoryObservation.as_dict
- sig: `DirectoryObservation.as_dict() -> dict[str, str]`
- does: returns all directory identity fields using their serialized names
- verify: json_path(path="$.vcs", equals="git")
- returns: a string-valued dictionary suitable for the repository list attribute
- verify: json_path(path="$.path", matches="^.+$")
- code: `workhorse/workhorse/gitstate.py::DirectoryObservation.as_dict`

### RepositorySnapshot.attributes
- sig: `RepositorySnapshot.attributes() -> dict[str, str]`
- does: returns primary workspace path and VCS attributes
- verify: json_path(path="$.workspace.vcs", equals="unversioned")
- does: serializes every declared directory as compact, sorted-key JSON
- verify: json_path(path="$.workhorse.repositories", matches="^\\[.*\\]$")
- does: omits primary Git fields when the primary directory is unversioned
- verify: absent(subject="git.head attribute for an unversioned primary directory")
- returns: primary workspace attributes and a compact JSON list of all declared directories
- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot.attributes`

### HeadWatch.head
- sig: `HeadWatch.head() -> str`
- does: reuses a non-expired cached HEAD without invoking Git again
- verify: count(subject="HEAD reads during the cache TTL", equals=1)
- returns: cached HEAD until the TTL expires, then refreshes it
- code: `workhorse/workhorse/gitstate.py::HeadWatch.head`

### HeadWatch.refresh
- sig: `HeadWatch.refresh() -> str`
- does: reads HEAD immediately and resets the cache timestamp
- verify: count(subject="HEAD reads for explicit refresh followed by cached head", equals=1)
- returns: the current HEAD, or an empty string when Git cannot answer
- verify: json_path(path="$.head", matches="^[0-9a-f]{40}$")
- code: `workhorse/workhorse/gitstate.py::HeadWatch.refresh`

### HeadWatch.state
- sig: `HeadWatch.state(*, dirty: bool = True, stash: bool = False) -> RepoState`
- does: observes the full state and updates the cached HEAD timestamp
- verify: json_path(path="$.head", matches="^[0-9a-f]{40}$")
- returns: a full observation and updates the cached HEAD
- code: `workhorse/workhorse/gitstate.py::HeadWatch.state`

### HeadWatch.scope
- sig: `HeadWatch.scope(cwd: str | Path | None = None, add_dirs: Sequence[str | Path] = (), *, refresh: bool = False) -> RepositorySnapshot`
- does: observes the requested primary and additional directories
- verify: count(subject="directories in a cached scope snapshot", equals=3)
- does: reuses a non-expired snapshot unless refresh is true
- verify: count(subject="scope observations within the cache TTL", equals=1)
- returns: an immutable repository snapshot
- verify: persists(subject="repository scope snapshot")
- code: `workhorse/workhorse/gitstate.py::HeadWatch.scope`

### bind
- sig: `bind(path: str | Path, ttl_s: float = DEFAULT_TTL_S) -> None`
- does: installs a module-level `HeadWatch` for the run's working tree
- verify: created(subject="bound repository observer")
- code: `workhorse/workhorse/gitstate.py::bind`

### unbind
- sig: `unbind() -> None`
- code: `workhorse/workhorse/gitstate.py::unbind`
- consistency: repository-observer — unbind removes the module-level repository observer
- verify: removed(subject="the bound module-level repository observer")

### current_head
- sig: `current_head(*, refresh: bool = False) -> str`
- returns: the bound tree's cached or refreshed HEAD, or an empty string when unbound
- verify: absent(subject="HEAD value when no repository observer is bound")
- code: `workhorse/workhorse/gitstate.py::current_head`
- code: `workhorse/tests/test_gitstate.py::test_head_is_cached_until_refreshed`

### current_state
- sig: `current_state(*, dirty: bool = True, stash: bool = False) -> RepoState`
- returns: a full bound-tree observation, or an empty state when unbound
- verify: absent(subject="repository observation fields when no observer is bound")
- code: `workhorse/workhorse/gitstate.py::current_state`

### current_scope
- sig: `current_scope(cwd: str | Path | None = None, add_dirs: Sequence[str | Path] = (), *, refresh: bool = False) -> RepositorySnapshot`
- returns: the bound observer's cached or refreshed scope snapshot, or an empty snapshot when unbound
- verify: absent(subject="repository scope attributes when no observer is bound")
- code: `workhorse/workhorse/gitstate.py::current_scope`

### bound
- sig: `bound() -> HeadWatch | None`
- returns: the module-level observer when one is bound, otherwise None
- verify: absent(subject="bound repository observer after unbind")
- code: `workhorse/workhorse/gitstate.py::bound`
