---
type: concept
slug: live-source
title: LiveSource — immutable bind-source generations
---
# LiveSource — immutable bind-source generations

`LiveSource` stages a package from a read-only host bind into a fresh, container-local
generation before installing it. The bind is never imported directly: a running process
continues importing its completed generation while a later refresh copies and installs a new
one. The [workhorse command](../workhorse.md) exposes this as an engine concept used by the
container harness.

- code: `workhorse/livesource.py::LiveSource`
- tests: `workhorse/tests/test_livesource.py::test_an_edit_to_the_bind_does_not_reach_an_existing_generation`,
  `workhorse/tests/test_livesource.py::test_a_failed_install_leaves_the_previous_generation_in_place`

The source directory is copied once, with generated or dependency directories excluded. A
successful refresh installs the new copy and retains the newest two generations; an absent bind,
copy failure, missing `uv`, or failed install leaves the prior installed generation untouched.

## Fields

### name
- type: `str`
- default: none
- required: true
- semantics: package name used in diagnostics and generation-install log messages
- verify: count(subject="required LiveSource constructor fields", equals=4)
- code: `workhorse/livesource.py::LiveSource`

### mount
- type: `Path`
- default: none
- required: true
- semantics: read-only source bind
- verify: unchanged(subject="source mount after staging")
- semantics: a missing directory means this source is disabled, not erroneous
- verify: absent(subject="missing live-source mount treated as a staging error")
- code: `workhorse/livesource.py::LiveSource`

### root
- type: `Path`
- default: none
- required: true
- semantics: container-local directory containing numeric generation directories for this source
- verify: created(subject="container-local live-source generation root")
- code: `workhorse/livesource.py::LiveSource`

### with_editable
- type: `tuple[Path, ...]`
- default: `()`
- required: false
- semantics: additional local packages passed to `uv tool install --with-editable` alongside the staged package
- verify: count(subject="extra editable packages passed to the install command", equals=1)
- code: `workhorse/livesource.py::LiveSource`

## Methods

### generations
- sig: `generations(root: Path) -> list[Path]`
- does: return only immediate child directories whose names are numeric generation identifiers
- verify: count(subject="numeric generation directories returned from a populated root", equals=2)
- does: order returned generations lexically from oldest to newest
- verify: count(subject="chronologically ordered generation names", equals=2)
- returns: an empty list when `root` is not a directory
- verify: count(subject="generations returned for a missing root", equals=0)
- code: `workhorse/livesource.py::generations`
- tests: `workhorse/tests/test_livesource.py::test_each_stage_is_a_new_directory_so_nothing_is_mutated_in_place`,
  `workhorse/tests/test_livesource.py::test_no_mount_stages_nothing_and_is_not_an_error`

### stage
- sig: `stage(source: LiveSource) -> Path | None`
- does: return `None` without creating a generation when the source mount is absent
- verify: absent(subject="generation staged from an absent mount")
- does: choose the next four-digit generation number after the newest existing generation, or `0001` when none exists
- verify: created(subject="next numbered live-source generation")
- does: create the generation root and copy the mount into the new directory while preserving symlinks
- verify: created(subject="copied live-source generation")
- does: exclude `.git`, `.venv`, `node_modules`, `__pycache__`, `*.pyc`, `.pytest_cache`, and `.ruff_cache` from the copy
- verify: absent(subject="ignored dependency and cache directories in a staged generation")
- does: remove a partially copied target and return `None` when copying raises `OSError`
- verify: absent(subject="partially copied generation after staging failure")
- returns: the new generation path after a successful copy
- verify: created(subject="returned staged generation path")
- code: `workhorse/livesource.py::stage`
- tests: `workhorse/tests/test_livesource.py::test_a_generation_is_a_copy_of_the_bind_not_the_bind`,
  `workhorse/tests/test_livesource.py::test_each_stage_is_a_new_directory_so_nothing_is_mutated_in_place`,
  `workhorse/tests/test_livesource.py::test_the_expensive_and_useless_directories_are_not_copied`

### install
- sig: `install(source: LiveSource, generation: Path, bin_dir: Path) -> bool`
- does: invoke `uv tool install --force --editable <generation> --no-sources` with `UV_TOOL_BIN_DIR` set to `bin_dir`
- verify: exit_status(code=0)
- does: append one `--with-editable <path>` pair for every path in `source.with_editable`
- verify: count(subject="extra editable install arguments for one configured package", equals=1)
- does: return `False` and keep the prior installation when `uv` exits nonzero
- verify: exit_status(code=1)
- does: return `False` and log a warning when starting `uv` raises `OSError`
- verify: exit_status(code=1)
- returns: `True` only when the install subprocess exits with status zero
- verify: exit_status(code=0)
- code: `workhorse/livesource.py::install`
- tests: `workhorse/tests/test_livesource.py::test_install_points_uv_at_the_copy_never_at_the_bind`,
  `workhorse/tests/test_livesource.py::test_extra_local_packages_are_installed_alongside`,
  `workhorse/tests/test_livesource.py::test_a_failed_install_leaves_the_previous_generation_in_place`,
  `workhorse/tests/test_livesource.py::test_uv_missing_entirely_is_reported_not_raised`

### prune
- sig: `prune(root: Path, keep: int = KEEP_GENERATIONS) -> None`
- does: remove every generation older than the newest `keep` generations
- verify: count(subject="generations remaining after pruning to two", equals=2)
- does: remove all generations when `keep` is zero or negative
- verify: count(subject="generations remaining after pruning with nonpositive keep", equals=0)
- does: ignore removal errors so pruning cannot make a successful refresh fail
- verify: exit_status(code=0)
- returns: `None` after best-effort pruning
- verify: exit_status(code=0)
- code: `workhorse/livesource.py::prune`
- tests: `workhorse/tests/test_livesource.py::test_the_previous_generation_survives_a_refresh`

### refresh
- sig: `refresh(source: LiveSource, bin_dir: Path) -> Path | None`
- does: stage a fresh generation before attempting its installation
- verify: created(subject="fresh generation before live-source installation")
- does: remove the staged generation when installation fails
- verify: absent(subject="failed live-source generation")
- does: leave the previously installed generation present when staging or installation fails
- verify: created(subject="previous live-source generation after failed refresh")
- does: prune older generations only after installation succeeds
- verify: count(subject="surviving generations after four successful refreshes", equals=2)
- returns: the newly installed generation on success and `None` when no change was installed
- verify: count(subject="successful refresh result generations", equals=1)
- code: `workhorse/livesource.py::refresh`
- tests: `workhorse/tests/test_livesource.py::test_no_mount_stages_nothing_and_is_not_an_error`,
  `workhorse/tests/test_livesource.py::test_a_failed_install_leaves_the_previous_generation_in_place`,
  `workhorse/tests/test_livesource.py::test_the_previous_generation_survives_a_refresh`
