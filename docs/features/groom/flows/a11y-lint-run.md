---
type: flow
slug: a11y-lint-run
title: a11y-lint run
---
# a11y-lint run

This journey covers the as-built static accessibility lint path from running
[`python -m groom.a11y_lint [PATH ...]`](../groom-a11y-lint.md#lint), through
the [invoke lint](../groom-a11y-lint.md#invoke-lint) command behavior, target
selection by the [Groom a11y HTML file selector](../concepts/groom-a11y-html-file-selector.md),
one-document scanning by [Groom a11y lint](../concepts/groom-a11y-lint.md),
parser/tree construction by the [Groom a11y HTML tree parser](../concepts/groom-a11y-html-tree-parser.md),
diagnostic creation in the [Groom a11y finding](../groom-a11y-finding.md)
format, line-oriented stdout rendering, final summary output, and the returned
process exit status. It is a CLI-only journey; browser rendering, CSS,
JavaScript event-delegation, runtime axe checks, and post-swap DOM inspection are
outside this static run.

- start: an operator, developer, test, or CI process starts
  `python -m groom.a11y_lint [PATH ...]` in an environment where the `groom`
  package can be imported. The optional `PATH ...` arguments are filesystem path
  strings supplied to the module command; when none are supplied, the command's
  only target is the package-local `groom/templates/` directory.
- code: groom/groom/a11y_lint.py::main
- code: groom/groom/a11y_lint.py::_iter_html_files
- code: groom/groom/a11y_lint.py::lint_html
- code: groom/groom/a11y_lint.py::_Tree
- code: groom/groom/a11y_lint.py::Finding
- steps:
  1. Python imports the `groom.a11y_lint` module and enters `main` through the
     module guard. Import-time behavior defines the static rule constants, the
     [Groom a11y node](../groom-a11y-node.md) and finding data shapes, the tree
     parser, the selector, and the lint engine; it does not read templates or
     emit findings before `main` runs.
  2. [invoke lint](../groom-a11y-lint.md#invoke-lint) chooses its argument list:
     it uses the caller-provided `argv` when called as a function and otherwise
     uses process arguments after the module name. It converts each argument to a
     filesystem path target and falls back to the shipped template directory when
     the list is empty.
  3. The [Groom a11y HTML file selector](../concepts/groom-a11y-html-file-selector.md)
     expands targets in argument order. Each directory contributes sorted
     recursive `*.html` matches, each non-directory target with suffix `.html`
     contributes that path, and missing paths or non-HTML paths contribute no
     selected file and no accessibility diagnostic by themselves.
  4. The command reads each selected HTML file as UTF-8 text. A selected but
     missing, unreadable, or undecodable `.html` path fails through the normal
     Python exception path instead of becoming a [Groom a11y finding](../groom-a11y-finding.md)
     or a formatted lint failure.
  5. For each successfully read file, [Groom a11y lint](../concepts/groom-a11y-lint.md#method-lint_html)
     scans the text with the file path string as the source label. The scan
     creates a [Groom a11y HTML tree parser](../concepts/groom-a11y-html-tree-parser.md),
     feeds the HTML text, and receives an ordered list of parsed element nodes.
  6. Parser callbacks build the tree as [Groom a11y node](../groom-a11y-node.md)
     records. Each start or self-closing tag creates one node with tag name,
     lowercased attribute map, source line, parent, children, and direct text;
     void elements are not left open, whitespace-only text is ignored, and
     malformed closing tags are tolerated according to the parser contract.
  7. The lint engine builds the set of explicit `<label for="...">` targets and
     visits parsed nodes in source order. It checks the documented static rules
     for missing document language, unlabeled form controls, missing image alt
     text, action attributes on non-native controls, unfocusable widget roles,
     unnamed controls, and out-of-band update targets without live-region
     semantics.
  8. Each failing rule appends one [Groom a11y finding](../groom-a11y-finding.md)
     with the source path label, the parsed source line, the stable `A11Y###`
     rule code, and the rule's human-readable message. Findings remain in
     target-expansion order, then parser node order, then per-node rule order;
     the command does not sort, deduplicate, or stop early.
  9. After all selected files have been scanned, the CLI prints every accumulated
     finding to stdout by using the finding string form `PATH:LINE: CODE MESSAGE`.
     Clean runs print no per-finding lines.
  10. The CLI expands the same target list through the selector a second time to
      compute the summary's selected-file count, then prints a blank line and
      `a11y-lint: N finding in M file(s)` when exactly one finding exists or
      `a11y-lint: N findings in M file(s)` otherwise.
  11. The CLI returns `1` when the accumulated finding list is non-empty and `0`
      when it is empty. Interpreter-level import failures, filesystem read
      failures, permission errors, decoding errors, and unexpected parser or lint
      exceptions propagate outside this normal clean-or-findings status contract.
- end: stdout contains zero or more stable finding lines followed by exactly one
  summary line for a normal run, and the process status distinguishes a clean
  static scan (`0`) from any reported accessibility finding (`1`). No source
  files, templates, browser state, server state, or persistent groom data are
  modified by the journey.
- verify: groom/tests/test_a11y_lint.py::test_missing_lang_flagged,
  groom/tests/test_a11y_lint.py::test_input_with_only_placeholder_flagged,
  groom/tests/test_a11y_lint.py::test_img_without_alt_flagged,
  groom/tests/test_a11y_lint.py::test_hx_post_on_div_flagged,
  groom/tests/test_a11y_lint.py::test_role_button_without_tabindex_flagged,
  groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_oob_target_without_live_flagged,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
