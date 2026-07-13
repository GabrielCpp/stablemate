---
type: concept
slug: groom-a11y-html-file-selector
title: Groom a11y HTML file selector
---
# Groom a11y HTML file selector

Groom a11y HTML file selector is the private target-expansion helper used by
the [groom-a11y-lint CLI invocation](../groom-a11y-lint.md#invoke-lint) before
it reads files and sends each document to the [Groom a11y lint](groom-a11y-lint.md)
engine. It turns the command's filesystem target list into the ordered list of
HTML files that the command will inspect.

- code: groom/groom/a11y_lint.py::_iter_html_files

## Contract

- input: a `list[pathlib.Path]` of target paths selected by the CLI.
- output: a `list[pathlib.Path]` containing only selected `.html` file paths.
- selection:
  - Directory targets contribute every descendant whose filename matches `*.html`.
  - File targets contribute only when the path suffix is exactly `.html`.
  - Missing paths, non-file paths that are not directories, and non-HTML file paths contribute no entries and do not create a diagnostic.
- ordering:
  - Target arguments are processed in their input order.
  - HTML files found under each directory are sorted within that directory target before being appended.
  - Individual HTML file targets are appended at the position of their target argument.
  - The selector does not globally sort, deduplicate, or normalize the final combined list.
- path-shape: returned paths preserve the `Path` objects produced by directory walking or supplied as file targets; relative targets remain relative to the caller's current working directory.
- errors: filesystem traversal errors from directory expansion are not converted into accessibility findings; they propagate to the CLI caller.
- empty-result: when no target contributes an HTML file, the selector returns an empty list.

## Methods

### method-_iter_html_files

- sig: `_iter_html_files(paths: list[Path]) -> list[Path]`
- abstract: false
- raises: no selector-specific exception is part of the contract; filesystem traversal failures propagate from the underlying path operation.
- code: groom/groom/a11y_lint.py::_iter_html_files
- does:
  - Starts with an empty selected-file list.
  - Visits every supplied target path in order.
  - For each directory target, appends that target's sorted recursive `*.html` matches.
  - For each non-directory target with suffix `.html`, appends the target itself.
  - Ignores every other target without reporting a finding or warning.
  - Returns the selected-file list for the CLI to read and lint.
