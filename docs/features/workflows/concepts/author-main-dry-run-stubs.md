---
type: concept
slug: author-main-dry-run-stubs
title: Author main dry-run stubs
---
# Author main dry-run stubs

The Author main registry uses these callbacks as deterministic replacements for its validation
and verification nodes when a run is started with `--dry-run`. They accept and ignore the node
arguments, returning affirmative result models so the dry-run follows the successful gate paths.
The callbacks do not themselves provide a human-mode escape from an `Await`.

- code: `workflows/src/workhorse_workflows/author/main/nodes/_stubs.py`

## Methods

### clean
Returns the successful result shared by `validate_story`, `check_story_grounding`,
`validate_coverage`, and `validate_artifacts`.

- sig: `clean(*_args: object, **_kwargs: object) -> Defects`
- does: ignores all positional and keyword arguments
- verify: count(subject="clean stub invocations with arbitrary node arguments", equals=1)
- returns: a `Defects` result with `ok=True`
- verify: json_path(path="$.ok", equals=true)
- returns: the default empty `errors` string
- verify: json_path(path="$.errors", equals="")
- code: `workflows/src/workhorse_workflows/author/main/nodes/_stubs.py::clean`

### holds
Returns the successful result shared by `verify_reconcile` and `verify_integrity`.

- sig: `holds(*_args: object, **_kwargs: object) -> VerifyReport`
- does: ignores all positional and keyword arguments
- verify: count(subject="holds stub invocations with arbitrary node arguments", equals=1)
- returns: a `VerifyReport` result with `holds=True`
- verify: json_path(path="$.holds", equals=true)
- returns: the default false `skipped` value
- verify: json_path(path="$.skipped", equals=false)
- returns: the default empty `errors` string
- verify: json_path(path="$.errors", equals="")
- returns: the default empty `report` string
- verify: json_path(path="$.report", equals="")
- code: `workflows/src/workhorse_workflows/author/main/nodes/_stubs.py::holds`
