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
- tests: `workflows/tests/test_kit_jsonio.py::test_a_url_in_a_string_is_not_a_comment`
- tests: `workflows/tests/test_kit_jsonio.py::test_a_double_slash_path_in_a_string_survives`
- tests: `workflows/tests/test_kit_jsonio.py::test_line_and_block_comments_are_still_honored`
- tests: `workflows/tests/test_kit_jsonio.py::test_genuinely_broken_input_still_raises`
