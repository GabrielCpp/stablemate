---
type: concept
slug: workflow-parameter-loading
title: Workflow parameter loading
---
# Workflow parameter loading

Workflow inputs may come from a JSON file, inline JSON, both, or neither. The loader reads the
file first and merges the inline object second, so inline keys win. Each source must be a JSON
object; unreadable files, invalid JSON, and arrays or scalar values terminate the CLI with an
error on stderr and status `1`.

- code: `workhorse/workhorse/cli/params.py::load_params`
- tests: `workhorse/tests/test_console_script.py::test_every_flag_reaches_the_engine`

## Methods

### load-params
- sig: `load_params(inline: str | None, file: str | None) -> dict[str, Any]`
- does: read the `file` source as text before processing inline JSON
- does: merge the file object into the result before the inline object
- does: let inline values replace file values for overlapping keys
- does: return an empty object when neither source is supplied
- raises: exit with status `1` after printing a file-read error when `file` cannot be read
- raises: exit with status `1` after printing a source-specific error when JSON decoding fails
- raises: exit with status `1` after printing a source-specific error when a decoded value is not an object
- returns: the merged key-to-value map
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/params.py::load_params`
