---
type: concept
slug: base-library-cache
title: stablemate base-library cache
---
# stablemate base-library cache

The cache stores the base library's documents without a repository checkout. It fetches only
`base-library/` from the configured public ref, records the commit in `.commit`, and removes
`.git` before exposing the content. Normal lookup is frozen and never accesses the network;
explicit refresh is the only operation that updates an existing cache.

- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py`

## Methods

### cache_root
- sig: `cache_root() -> Path`
- does: use `STABLEMATE_CACHE_DIR` when set, otherwise return the platform cache directory for `stablemate`
- verify: json_path(path="$.cache_root", equals="/tmp/stablemate-cache")
- returns: the shared cache root
- verify: json_path(path="$.cache_root", matches="stablemate$")
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::cache_root`

### cached_library_dir
- sig: `cached_library_dir() -> Path`
- does: append `library` to the cache root
- verify: json_path(path="$.cached_library_dir", equals="/tmp/stablemate-cache/library")
- returns: the directory containing cached base content
- verify: json_path(path="$.cached_library_dir", matches="library$")
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::cached_library_dir`

### fetch_allowed
- sig: `fetch_allowed() -> bool`
- does: permit fetching unless `STABLEMATE_FETCH_BASE` is one of `0`, `false`, `no`, or `off`, case-insensitively after trimming
- verify: json_path(path="$.fetch_allowed", equals=false)
- returns: whether network fetching is allowed
- verify: json_path(path="$.fetch_allowed", equals=true)
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::fetch_allowed`

### cached_commit
- sig: `cached_commit(clone: Path | None = None) -> str | None`
- does: read and trim `.commit` from the supplied clone or the cached library directory
- verify: json_path(path="$.cached_commit", equals="abc123")
- returns: the recorded commit, or `None` for a missing, empty, or unreadable sidecar
- verify: json_path(path="$.cached_commit", matches="^[0-9a-f]+$")
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::cached_commit`

### remote_commit
- sig: `remote_commit() -> str | None`
- does: query `BASE_REPO_REF` with `git ls-remote`
- verify: json_path(path="$.remote_commit", matches="^[0-9a-f]{40}$")
- returns: the remote commit hash, or `None` when git, the network, or the ref is unavailable
- verify: json_path(path="$.remote_commit", equals=None)
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::remote_commit`

### cached_base
- sig: `cached_base() -> Path | None`
- does: accept the cache only when its `base-library/` content passes `is_library_dir`
- verify: absent(subject="cached base with an invalid library layout")
- returns: the usable cached base path, or `None`; never fetches
- verify: absent(subject="network fetch during cached base lookup")
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::cached_base`

### ensure_cached_base
- sig: `ensure_cached_base(*, quiet: bool = False) -> Path | None`
- does: return an existing usable cache, otherwise fetch a sparse base-library checkout when fetching is enabled
- verify: created(subject="base-library cache when no usable cache exists")
- does: leave an unusable existing cache in place and return `None` rather than overwrite it
- verify: unchanged(subject="unusable existing base-library cache")
- does: use a process-specific temporary sibling and rename it into place, accepting a concurrent winner's cache
- verify: keys_unchanged(subject="base-library cache after concurrent ensure")
- returns: the usable cached base, or `None` when fetching is disabled or fails
- verify: absent(subject="usable cached base when fetching is disabled or fails")
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::ensure_cached_base`

### refresh_cached_base
- sig: `refresh_cached_base(*, quiet: bool = False) -> Path | None`
- does: fetch the base when no usable cache exists
- verify: created(subject="base-library cache when no usable cache exists")
- does: compare the recorded local commit with the remote before replacing stale content
- verify: conflict_on_stale(subject="base-library cache", token="recorded local commit")
- does: retain and return the existing usable cache when remote discovery or replacement fails
- verify: unchanged(subject="existing usable base-library cache")
- returns: the refreshed or retained cache, or `None` when no cache can be obtained
- verify: persists(subject="refreshed or retained base-library cache")
- returns: `None` when no cache can be obtained
- verify: absent(subject="usable cached base when no cache can be obtained")
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::refresh_cached_base`
