---
type: concept
title: Shared core
---
# Shared core

Every stablemate tool has to agree on the same runtime state: the home config, where the base
library is, and its shared cache. Workhorse carries its own copy of that shared core, so it reads
the config and finds the library the same way the other tools do. The config rules are in
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

- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py::base_library_dir` @42eebfdfea77
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::ensure_cached_base` @79e1cc13c672
- code: `workhorse/workhorse/_vendor/stablemate_core/base_cache.py::refresh_cached_base` @79e1cc13c672
- code: `workhorse/workhorse/_vendor/stablemate_core/layout.py::is_library_dir` @d69e52175abc
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::SkillRefs` @ebf1b69c7565
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::MissingSkill` @ebf1b69c7565
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock` @99322cfda640
- code: `workhorse/workhorse/_vendor/stablemate_core/__init__.py` @3b3d6fe59b0c
- code: `workhorse/workhorse/_vendor/stablemate_core/README.md` @3e20339d4474
- code: `workhorse/workhorse/_vendor/__init__.py` @d63f5d827a00
