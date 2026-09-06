---
type: concept
slug: selection-errors
title: Selection error reporting
---
# Selection error reporting

Selection entries that name unavailable packs, skills, prompts, or roots use one diagnostic shape.
The formatter reports every missing literal selection in one invocation, offers only competitive
nearby names, lists the available catalog and searched library layers, and ends with the relevant
configuration fix plus the overlay escape hatch. Glob selections remain filters and are handled by
the caller as warnings when they match nothing.

- code: `farrier/farrier/selection_errors.py`
- tests: `farrier/tests/test_selection_misses.py::test_unknown_skill_fails_loudly`
- detail: [library layer](library-layer.md)

## Methods

### method: suggestions
- sig: `suggestions(name: str, available: list[str]) -> list[str]`
- does: return anagram-equivalent candidates first, treating case and separators as insignificant
- verify: count(subject="anagram-equivalent selection suggestions", equals=1)
- does: otherwise return at most three candidates whose difflib similarity reaches 0.6
- verify: count(subject="fuzzy selection suggestions at or above the cutoff", equals=1)
- does: order fuzzy candidates by descending similarity and then ascending candidate name
- verify: count(subject="ordered fuzzy selection suggestions", equals=1)
- does: omit a fuzzy runner-up when it scores more than 0.06 below the best candidate
- verify: count(subject="competitive fuzzy selection suggestions", equals=1)
- does: return no candidates when neither matching pass finds an acceptable candidate
- verify: count(subject="empty suggestions for unrelated selection", equals=1)
- returns: a list containing no more than three suggested names
- verify: count(subject="bounded selection suggestion list", equals=1)
- code: `farrier/farrier/selection_errors.py::suggestions`
- tests: `farrier/tests/test_selection_misses.py::test_suggestions_catch_transpositions_difflib_misses`
- tests: `farrier/tests/test_selection_misses.py::test_suggestions_drop_non_competitive_runners_up`

### method: unknown_selection_error
- sig: `unknown_selection_error(kind: str, missing: list[str], available: list[str], *, config_key: str = "", extra: str = "") -> str`
- does: label a single missing entry with the singular form of its plural kind, while labeling multiple entries with the plural kind
- verify: count(subject="selection error singular or plural label", equals=1)
- does: identify the agents.yml key with config_key, or use kind when config_key is empty
- verify: count(subject="selection error configuration key", equals=1)
- does: list missing names in sorted order and add close suggestions for each name
- verify: count(subject="sorted missing selection names", equals=1)
- does: include the available catalog sorted by name, capped at 40 entries with a remaining-count line when more exist
- verify: count(subject="bounded available selection catalog", equals=1)
- does: explain that no available entries usually indicate an unconfigured library layer when the catalog is empty
- verify: count(subject="empty selection catalog layer guidance", equals=1)
- does: include the ordered searched library-layer labels
- verify: count(subject="searched library layers in selection error", equals=1)
- does: append the caller-provided extra note when it is non-empty
- verify: count(subject="key-specific selection error note", equals=1)
- does: end with instructions to fix or remove the selection and configure a private overlay when needed
- verify: count(subject="selection error remediation instructions", equals=1)
- returns: the complete newline-separated diagnostic message
- verify: count(subject="complete selection error message", equals=1)
- code: `farrier/farrier/selection_errors.py::unknown_selection_error`
- tests: `farrier/tests/test_selection_misses.py::test_unknown_skill_fails_loudly`
- tests: `farrier/tests/test_selection_misses.py::test_unknown_pack_is_verbose`
- tests: `farrier/tests/test_selection_misses.py::test_every_miss_is_reported_in_one_run`
- tests: `farrier/tests/test_selection_misses.py::test_empty_catalog_says_the_layer_is_missing_not_the_name`
