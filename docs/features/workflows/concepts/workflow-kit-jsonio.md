---
type: concept
slug: workflow-kit-jsonio
title: Workflow kit JSON I/O
---
# Workflow kit JSON I/O

The JSON I/O kit parses VSCode JSON-with-comments with a JSON5 parser instead of stripping
comment-looking text. URLs and network paths containing `//` remain string values, while line
comments, block comments, and trailing commas remain accepted. Invalid input still raises rather
than being repaired into an invented workspace configuration.

- code: `workflows/src/workhorse_workflows/kit/jsonio.py::load_jsonc`
- code: `workflows/src/workhorse_workflows/kit/jsonio.py::load_json`
- tests: `workflows/tests/test_kit_jsonio.py::test_a_url_in_a_string_is_not_a_comment`
- tests: `workflows/tests/test_kit_jsonio.py::test_a_double_slash_path_in_a_string_survives`
- tests: `workflows/tests/test_kit_jsonio.py::test_line_and_block_comments_are_still_honored`
- tests: `workflows/tests/test_kit_jsonio.py::test_genuinely_broken_input_still_raises`

## Methods

### load_jsonc
- sig: `load_jsonc(text: str) -> dict`
- does: parses JSON5 input, including JSON comments and trailing commas
- verify: json_path(path="$.folders[0].path", equals="api-service")
- does: preserves `//` sequences occurring inside string values
- verify: json_path(path="$.url", equals="https://example.com")
- raises: raises `ValueError` when the input is not parseable
- verify: count(subject="parse errors raised for malformed JSONC input", equals=1)
- returns: returns the parsed mapping without repairing invalid input
- verify: json_path(path="$.trailing", equals=1)
- code: `workflows/src/workhorse_workflows/kit/jsonio.py::load_jsonc`
- tests: `workflows/tests/test_kit_jsonio.py::test_a_url_in_a_string_is_not_a_comment`
- tests: `workflows/tests/test_kit_jsonio.py::test_a_double_slash_path_in_a_string_survives`
- tests: `workflows/tests/test_kit_jsonio.py::test_line_and_block_comments_are_still_honored`
- tests: `workflows/tests/test_kit_jsonio.py::test_genuinely_broken_input_still_raises`

### load_json
- sig: `load_json(path: Path, label: str, logger: logging.Logger) -> dict`
- does: reads the file as UTF-8 and parses strict JSON
- verify: json_path(path="$.name", equals="workflow")
- does: logs a warning when the file does not exist
- verify: count(subject="missing-file warning records", equals=1)
- does: logs a warning when the file cannot be read or contains invalid JSON
- verify: count(subject="unreadable-file warning records", equals=1)
- returns: returns an empty mapping after any missing, unreadable, or invalid-file case
- verify: count(subject="returned mapping entries after a load failure", equals=0)
- code: `workflows/src/workhorse_workflows/kit/jsonio.py::load_json`
