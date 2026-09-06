---
type: concept
slug: naming
title: Renderer naming and relative output paths
---
# Renderer naming and relative output paths

- code: `farrier/farrier/naming.py`

These stateless transforms define the names and references used by source selection and rendering.
They do not inspect a `Source` record or resolve a library layer. Source identifiers use POSIX
slashes, generated names use kebab case, and output references are relative to the file that emits
them. The renderer uses the repository directory name as its public prefix; configuration cannot
override that value. The naming rules complement the [source naming and selection](source-naming-selection.md)
concept, which applies these aliases to selected `Source` records.

## Methods

### method: kebab
- sig: `kebab(value: str) -> str`
- does: remove one trailing `.prompt` or `.instructions` suffix
- does: replace dots and underscores with dashes
- does: replace every run of characters other than ASCII letters, digits, dashes, or slashes with one dash
- does: collapse adjacent dashes
- verify: count(subject="kebab-cased value", equals=1)
- does: remove leading and trailing dashes
- verify: count(subject="kebab-cased value", equals=1)
- does: lowercase the result
- verify: count(subject="kebab-cased value", equals=1)
- returns: a normalized kebab-cased value while preserving slash separators
- code: `farrier/farrier/naming.py::kebab`

### method: compose_name
- sig: `compose_name(prefix: str, base: str) -> str`
- does: return `base` unchanged when the prefix is empty, equals the base, or already prefixes the base followed by a dash
- does: otherwise join the prefix and base with one dash
- returns: a name with no adjacent duplicate prefix segment
- verify: count(subject="composed name", equals=1)
- code: `farrier/farrier/naming.py::compose_name`
- tests: `farrier/tests/test_qa_evidence_ignore.py::test_qa_gitignore_follows_the_skill_that_ships_the_gate`

### method: repo_prefix
- sig: `repo_prefix(repo: Path) -> str`
- does: read the repository directory name
- returns: that directory name normalized by `kebab`
- verify: count(subject="repository-derived install prefix", equals=1)
- code: `farrier/farrier/naming.py::repo_prefix`
- tests: `farrier/tests/test_install_prefix.py::test_a_directory_name_is_kebab_cased_into_the_prefix`

### method: normalize_pattern
- sig: `normalize_pattern(pattern: str) -> str`
- does: remove one trailing `.md`, `.prompt`, or `.instructions` suffix
- does: replace dots and underscores with dashes without removing glob metacharacters
- returns: the lowercased pattern used for case-insensitive alias matching
- verify: count(subject="normalized selection pattern", equals=1)
- code: `farrier/farrier/naming.py::normalize_pattern`

### method: strip_known_suffix
- sig: `strip_known_suffix(path: Path) -> str`
- does: remove `.prompt.md` from the filename when present
- does: otherwise remove `.instructions.md` from the filename when present
- returns: the filename without its recognized compound suffix, or the ordinary `Path.stem` when neither suffix is present
- verify: count(subject="recognized source suffix removal", equals=1)
- code: `farrier/farrier/naming.py::strip_known_suffix`

### method: source_id
- sig: `source_id(root: Path, path: Path) -> str`
- does: compute the path relative to `root`
- does: raise the path-relative error from `Path.relative_to` when `path` is outside `root`
- does: for a `SKILL.md`, omit the filename and kebab-case every relative directory component
- does: for any other path, replace its filename with `strip_known_suffix` before kebab-casing each relative component
- does: join the normalized components with literal `/` separators
- returns: the kebab-cased relative components joined with `/`
- verify: count(subject="normalized source identifier", equals=1)
- code: `farrier/farrier/naming.py::source_id`

### method: yaml_quote
- sig: `yaml_quote(value: str) -> str`
- does: escape backslashes and double quotes in the supplied string
- returns: the escaped string enclosed in double quotes for YAML output
- verify: count(subject="quoted YAML scalar", equals=1)
- code: `farrier/farrier/naming.py::yaml_quote`

### method: relative_reference
- sig: `relative_reference(from_file: Path, to_file: Path) -> str`
- does: compute the operating-system relative path from `from_file`'s parent directory to `to_file`
- returns: the relative reference with forward slashes regardless of the host path separator
- verify: count(subject="relative output reference", equals=1)
- code: `farrier/farrier/naming.py::relative_reference`
