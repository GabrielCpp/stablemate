---
type: concept
slug: source-naming-selection
title: Source naming and selection
---
# Source naming and selection

Source selection accepts several stable aliases for a source while rendering uses its library name:
the folder that holds the source, unique across its library whatever category groups it. Matching is
case-insensitive and normalizes dots and underscores to dashes without changing
glob metacharacters. Exclusion is applied after inclusion, and a selected result is sorted by id.

- code: `farrier/farrier/sources.py::selected_sources` @49ff73abb08d
- tests: `farrier/tests/test_installed_name.py::test_a_skill_is_selectable_by_its_path_or_its_name`
- detail: [agents.yml source selections](../formats/agents-yml-config.md#skills-prompts-roots)

## Methods

### method: library_name
- sig: `library_name(source: Source) -> str`
- does: returns the kebab-cased folder name of the source id, with no category or repository prefix
- returns: the name every reference to the source uses
- verify: count(subject="library source name", equals=1)
- code: `farrier/farrier/sources.py::library_name` @49ff73abb08d

### method: layered_sources
- sig: `layered_sources(kind: str, *parts: str) -> tuple[list[Source], list[tuple[Source, Source]]]`
- does: loads each layer's sources and keeps, per library name, the copy from the highest layer
- raises: exits when two sources in one layer share a library name
- returns: the winning sources, and each `(winner, loser)` pair an overlay override produced
- verify: count(subject="overlay overrides of a base source", equals=1)
- code: `farrier/farrier/sources.py::layered_sources` @49ff73abb08d

### method: public_name
- sig: `public_name(prefix: str, source: Source) -> str`
- does: prefixes the library name with the supplied repository prefix
- returns: the installed public name with adjacent duplicate prefix segments collapsed
- verify: count(subject="installed public source name", equals=1)
- code: `farrier/farrier/sources.py::public_name` @49ff73abb08d

### method: matches
- sig: `matches(source: Source, patterns: set[str]) -> bool`
- does: compares patterns against the source id, library name, relative path, and recognized suffix-stripped paths
- does: treats a pattern as matching when any normalized pattern matches any candidate case-insensitively
- returns: `true` when at least one pattern selects the source
- verify: count(subject="source aliases matched by one selection pattern", equals=1)
- code: `farrier/farrier/sources.py::matches` @49ff73abb08d

### method: selected_sources
- sig: `selected_sources(all_sources: list[Source], include_patterns: set[str], exclude_patterns: set[str]) -> list[Source]`
- does: retains sources matching an inclusion pattern and not matching an exclusion pattern
- returns: selected sources sorted by source id
- verify: count(subject="sources retained after exclusion", equals=1)
- code: `farrier/farrier/sources.py::selected_sources` @49ff73abb08d
- tests: `farrier/tests/test_selection_misses.py::test_valid_selection_still_installs`

### method: is_glob
- sig: `is_glob(pattern: str) -> bool`
- does: classifies a selection entry as a filter when it contains `*`, `?`, or `[` characters
- returns: `true` for glob filters and `false` for literal names
- verify: count(subject="glob selection classification", equals=1)
- code: `farrier/farrier/sources.py::is_glob` @49ff73abb08d

### method: unmatched_patterns
- sig: `unmatched_patterns(all_sources: list[Source], include_patterns: set[str]) -> tuple[list[str], list[str]]`
- does: separates include entries that match no source into literal and glob lists
- returns: `(literals, globs)` sorted within each list
- verify: count(subject="unmatched literal and glob selections", equals=2)
- code: `farrier/farrier/sources.py::unmatched_patterns` @49ff73abb08d

### method: build_lookup
- sig: `build_lookup(sources: list[Source]) -> dict[str, Source]`
- does: indexes each source by its library name alone
- raises: exits when two different sources claim the same library name
- returns: a normalized alias-to-source lookup
- verify: count(subject="source lookup aliases", equals=1)
- code: `farrier/farrier/sources.py::build_lookup` @49ff73abb08d

### method: build_policy_lookup
- sig: `build_policy_lookup(sources: list[Source]) -> dict[str, Source]`
- does: indexes policy sources by id, library name, relative path, and suffix-stripped relative path without adding a repository prefix
- raises: exits when two different policies claim the same normalized lookup key
- returns: a normalized policy-name lookup
- verify: count(subject="policy lookup aliases", equals=1)
- code: `farrier/farrier/sources.py::build_policy_lookup` @49ff73abb08d
