---
type: concept
slug: source-naming-selection
title: Source naming and selection
---
# Source naming and selection

Source selection accepts several stable aliases for a source while rendering uses the grouped public
name. Matching is case-insensitive and normalizes dots and underscores to dashes without changing
glob metacharacters. Exclusion is applied after inclusion, and a selected result is sorted by id.

- code: `farrier/farrier/sources.py::selected_sources`
- tests: `farrier/tests/test_group_prefix.py::test_a_skill_stays_selectable_by_every_spelling`
- detail: [agents.yml source selections](../agents-yml-config.md#fields--skills--prompts--roots)

## Methods

### method: public_id
- sig: `public_id(source: Source) -> str`
- does: returns the kebab-cased basename of the source id without group or repository prefixes
- returns: the bare public source name
- verify: count(subject="bare public source id", equals=1)
- code: `farrier/farrier/sources.py::public_id`

### method: group_id
- sig: `group_id(source: Source) -> str`
- does: prefixes the bare public id with the kebab-cased immediate parent group
- returns: the grouped name, collapsing an adjacent duplicate group segment
- verify: count(subject="grouped source id", equals=1)
- code: `farrier/farrier/sources.py::group_id`

### method: public_name
- sig: `public_name(prefix: str, source: Source) -> str`
- does: prefixes the grouped source id with the supplied repository prefix
- returns: the installed public name with adjacent duplicate prefix segments collapsed
- verify: count(subject="installed public source name", equals=1)
- code: `farrier/farrier/sources.py::public_name`

### method: matches
- sig: `matches(source: Source, patterns: set[str]) -> bool`
- does: compares patterns against the source id, bare id, grouped id, relative path, and recognized suffix-stripped paths
- does: treats a pattern as matching when any normalized pattern matches any candidate case-insensitively
- returns: `true` when at least one pattern selects the source
- verify: count(subject="source aliases matched by one selection pattern", equals=1)
- code: `farrier/farrier/sources.py::matches`

### method: selected_sources
- sig: `selected_sources(all_sources: list[Source], include_patterns: set[str], exclude_patterns: set[str]) -> list[Source]`
- does: retains sources matching an inclusion pattern and not matching an exclusion pattern
- returns: selected sources sorted by source id
- verify: count(subject="sources retained after exclusion", equals=1)
- code: `farrier/farrier/sources.py::selected_sources`
- tests: `farrier/tests/test_selection_misses.py::test_valid_selection_still_installs`

### method: is_glob
- sig: `is_glob(pattern: str) -> bool`
- does: classifies a selection entry as a filter when it contains `*`, `?`, or `[` characters
- returns: `true` for glob filters and `false` for literal names
- verify: count(subject="glob selection classification", equals=1)
- code: `farrier/farrier/sources.py::is_glob`

### method: unmatched_patterns
- sig: `unmatched_patterns(all_sources: list[Source], include_patterns: set[str]) -> tuple[list[str], list[str]]`
- does: separates include entries that match no source into literal and glob lists
- returns: `(literals, globs)` sorted within each list
- verify: count(subject="unmatched literal and glob selections", equals=2)
- code: `farrier/farrier/sources.py::unmatched_patterns`

### method: build_lookup
- sig: `build_lookup(sources: list[Source], prefix: str) -> dict[str, Source]`
- does: indexes each source by its id, public aliases, prefixed public name, relative path, and recognized suffix-stripped paths
- raises: exits when two different sources claim the same normalized lookup key
- returns: a normalized alias-to-source lookup
- verify: count(subject="source lookup aliases", equals=1)
- code: `farrier/farrier/sources.py::build_lookup`

### method: build_policy_lookup
- sig: `build_policy_lookup(sources: list[Source]) -> dict[str, Source]`
- does: indexes policy sources by id, bare basename, relative path, and suffix-stripped relative path without adding a repository prefix
- raises: exits when two different policies claim the same normalized lookup key
- returns: a normalized policy-name lookup
- verify: count(subject="policy lookup aliases", equals=1)
- code: `farrier/farrier/sources.py::build_policy_lookup`
