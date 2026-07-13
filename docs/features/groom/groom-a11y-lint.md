---
type: cli
slug: groom-a11y-lint
title: groom-a11y-lint
---
# groom-a11y-lint

- binary: `python -m groom.a11y_lint`
- code: groom/groom/a11y_lint.py::main
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean

`groom-a11y-lint` is the static accessibility-checking CLI surface for groom's
hand-authored HTML templates and the static half of the [groom dashboard](gui/screens/groom-dashboard.md)
accessibility gate. Its checks are defined by the importable
[Groom a11y lint](concepts/groom-a11y-lint.md) engine. It has no packaged
console-script entry in `pyproject.toml`; the executable form is the Python
module command above. Running it with no arguments scans the package's shipped
`templates/` directory, while running it with one or more path arguments scans
only those HTML files or directories.

The command reports template accessibility findings in a stable line-oriented
format, prints a final count summary, and exits non-zero when any finding is
present. It performs no runtime browser, CSS, JavaScript event-delegation, or
post-swap DOM analysis; those remain outside this CLI surface.

Target expansion is specified by the [Groom a11y HTML file selector](concepts/groom-a11y-html-file-selector.md),
which preserves argument order, sorts each directory's recursive HTML matches,
ignores non-HTML path targets, and selects `.html` path targets for reading by
suffix.

Invalid Python/module invocations fail before this CLI's `main` function runs.
Within `main`, non-HTML path arguments are ignored, directory arguments are
searched recursively for `*.html`, and any path argument whose suffix is `.html`
is selected for reading. A missing or unreadable `.html` path therefore fails as
a file-read error, while a missing non-HTML path contributes no selected files.
An empty target set is a clean run with a zero-file summary. Target expansion is
evaluated once for linting and again for the summary file count, so the summary
reports the selected-file count visible at summary time.

## Commands

### lint

- usage: `python -m groom.a11y_lint [PATH ...]`
- parent: [groom-a11y-lint](#groom-a11y-lint)
- flags:
  - none: this command accepts no options or switches.
- args:
  - `PATH ...`
    - type: path list
    - required: false
    - default: the package-local `groom/templates/` directory.
    - Each value is interpreted as a filesystem path relative to the caller's current working directory unless absolute.
    - Expansion follows the [Groom a11y HTML file selector](concepts/groom-a11y-html-file-selector.md): directories contribute sorted recursive `*.html` matches, any target path whose suffix is `.html` is selected for reading, and paths with other suffixes contribute no files and do not create a diagnostic by themselves.
- does:
  - Resolves the optional target paths, defaulting to the package's shipped
    template directory when no paths are provided.
  - Expands target directories and path arguments through the [Groom a11y HTML file selector](concepts/groom-a11y-html-file-selector.md).
  - Reads each selected HTML file as UTF-8 text and applies the static groom
    accessibility rules implemented by `lint_html`.
  - Emits every finding with the source path, source line, rule code, and human
    message.
  - Emits a final summary and returns a process status that makes the command
    suitable for a CI or documentation gate.
- code: groom/groom/a11y_lint.py::main
- stdout:
  - For each finding, prints one line in the form
    `PATH:LINE: CODE MESSAGE`.
  - After all findings, prints a blank line followed by
    `a11y-lint: N finding in M file(s)` when there is exactly one finding, or
    `a11y-lint: N findings in M file(s)` otherwise; `N` is the total finding
    count and `M` is the number of HTML files selected from the given targets.
- stderr:
  - none from the lint contract itself.
- exits:
  - `0` when no findings are reported.
  - `1` when one or more findings are reported.
  - Python-level file read, permission, text decoding, or import failures
    propagate as normal interpreter errors rather than formatted accessibility
    findings; this includes a missing path selected because its suffix is
    `.html`.
- finding-codes:
  - `A11Y001`: `<html>` has no `lang` attribute.
  - `A11Y002`: form input, textarea, or select has no accessible label.
  - `A11Y003`: image-like content is missing required alt text.
  - `A11Y004`: HTMX, websocket, or inline action is attached to a non-native
    interactive tag.
  - `A11Y005`: ARIA widget role is present on an element that is not keyboard
    focusable.
  - `A11Y006`: button, link, or ARIA widget control has no accessible name.
  - `A11Y007`: HTMX out-of-band swap target has no live-region semantics.
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean

## Invocations

### invoke-lint

This invocation is the executable behavior of the [lint](#lint) command. It
expands the requested filesystem targets, applies the [Groom a11y lint](concepts/groom-a11y-lint.md)
rule engine to every selected HTML file, reports all findings, and exits with a
status code suitable for gates that treat any static accessibility finding as a
failure.

- on: [lint](#lint)
- trigger: `python -m groom.a11y_lint [PATH ...]`
- when:
  - The Python module imports successfully and calls `main`.
  - Each argument, when present, is a filesystem path string; no CLI option parsing
    or path validation occurs before target expansion.
- does:
  - Uses the supplied `argv` object as the argument list when one is passed;
    otherwise uses the process arguments after the module name.
  - Converts every argument string to a filesystem path target; if no arguments
    exist, uses the package-local `templates/` directory as the only target.
  - Expands the targets through the [Groom a11y HTML file selector](concepts/groom-a11y-html-file-selector.md) before linting: targets are visited in argument order, each directory contributes sorted recursive `*.html` matches, each path target with suffix `.html` contributes itself, and path targets with other suffixes contribute no files.
  - Reads each selected HTML file as UTF-8 text and passes the text plus the file
    path string to the documented `lint_html` static lint engine.
  - Accumulates findings across all selected files in target-expansion and
    per-document parser order; the command does not sort, deduplicate, or stop
    early after the first finding.
  - Prints each accumulated finding by using the finding string format.
  - Re-expands the same targets through the [Groom a11y HTML file selector](concepts/groom-a11y-html-file-selector.md) to calculate the summary file count, then prints a blank line and the final summary. The noun is `finding` only when `N == 1`; otherwise it is `findings`. The file-count noun remains the literal text `file(s)`.
  - Returns `1` when at least one finding exists, otherwise returns `0`.
  - Propagates filesystem read errors, permission errors, invalid text encoding,
    and unexpected parser/lint failures instead of converting them to formatted
    accessibility findings or exit code `1`; a missing `.html` argument reaches
    this path because suffix-based target expansion selects it for reading.
- emits:
  - stdout finding line: `PATH:LINE: CODE MESSAGE` for each finding.
  - stdout summary: `a11y-lint: N finding in M file(s)` when `N == 1`, or
    `a11y-lint: N findings in M file(s)` otherwise, after a leading blank line.
  - exit status `0` for a clean scan and `1` for any finding.
- consumes:
  - `PATH ...` arguments from the command line.
  - HTML file contents read as UTF-8.
  - Static accessibility findings returned by the [Groom a11y lint](concepts/groom-a11y-lint.md)
    engine.
- code: groom/groom/a11y_lint.py::main
