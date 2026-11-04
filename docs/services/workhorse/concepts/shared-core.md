---
type: concept
title: Shared core
---
# Shared core

Every stablemate tool has to agree on the same runtime state: the home config, where the base
library is, and its shared cache. Workhorse carries that shared core, so it reads
the config and finds the library the same way the other tools do. In a checkout,
`workhorse/_vendor/stablemate_core` is a symlink to `core/stablemate_core` at the repository
root. A built wheel holds real files at that path. A `stablemate_core.sha256` digest beside the
link is rewritten by `make vendor` with every core change, which is what makes release-please
release workhorse, and `make check-vendor` fails when the link or the digest is wrong. The config rules are in
[profiles and config](profiles-and-config.md).

A library directory is any directory that holds a `library/` folder of skills and prompts. The
base library is the first usable one of these:

1. `$STABLEMATE_BASE_DIR`.
2. The config's `base_dir`.
3. The `base-library` folder of the config's `stablemate_dir` checkout.
4. The shared cache, at `library/base-library` under `$STABLEMATE_CACHE_DIR` or the user cache
   directory `stablemate`.

When none is usable, the cache is filled by a shallow sparse clone of the `base-library/` folder
from `https://github.com/GabrielCpp/stablemate.git`. The clone prints
`[stablemate] fetching base library: ...` and then `[stablemate] base library cached at ...`.
Setting `STABLEMATE_FETCH_BASE` to `0`, `false`, `no` or `off` turns the fetch off. A cache
directory that holds no usable library is left alone with a warning to delete it. A refresh swaps
in a new copy only when the remote commit differs, and keeps the cached copy when the remote is
unreachable.

Prompts name skills through helpers that resolve against what the harness installs, as
[prompt rendering](prompt-rendering.md) describes. A name that no installed skill or prompt
answers fails with `no installed skill or prompt is named '<name>'`. Code that waits takes a
clock as a dependency, and the system clock is the only one that sleeps for real.

- rule: a checkout holds a symlink and a digest, a built distribution holds real files, and a core change rewrites the digest of every tool so release-please releases it
- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py::base_library_dir` @004b46181627
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::ensure_cached_base` @bdbe0fae9566
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::refresh_cached_base` @e7ac6de61462
- code: `workhorse/workhorse/_vendor/stablemate_core/layout.py::is_library_dir` @be10d5c83213
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::SkillRefs` @0da19e1c7333
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::MissingSkill` @0db28ee1bfdf
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock` @1fcd1289ac40
- code: `workhorse/workhorse/_vendor/stablemate_core/__init__.py` @3b3d6fe59b0c
- code: `workhorse/workhorse/_vendor/stablemate_core/README.md` @5b6917a9704e
- code: `workhorse/workhorse/_vendor/__init__.py` @4b7e17d3161f
