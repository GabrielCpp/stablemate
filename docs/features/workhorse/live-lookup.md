---
type: format
slug: live-lookup
title: Live lookup result
---
# Live lookup result

A result of asking groom where a workflow's live run directory is located. The result is usable
only when `run_dir` is a directory on the current machine; all misses preserve a human-readable
`note` rather than raising a network or response-shape exception.

- code: `workhorse/workhorse/cli/target.py::LiveLookup`
- detail: [run target resolution](concepts/run-target-resolution.md)

## Fields

### field: run_dir
- type: `Path | None`
- default: `None`
- verify: json_path(path="$.run_dir", matches="^None$")
- required: true
- verify: json_path(path="$.run_dir", matches=".+")
- semantics: the one locally existing run directory accepted from groom, or `None` for every miss
- verify: json_path(path="$.run_dir", matches=".+")
- code: `workhorse/workhorse/cli/target.py::LiveLookup`
- detail: [live lookup result fields](concepts/live-lookup-result.md)

### field: note
- type: `str`
- default: none
- verify: json_path(path="$.note", matches="^resolved 'ghost' via groom: .+$")
- required: true
- verify: json_path(path="$.note", equals="groom at http://127.0.0.1:1 not reachable")
- semantics: explains the successful resolution or why groom's answer cannot be used
- verify: json_path(path="$.note", matches="^groom at .* knows no live run 'ghost' for workflow 'demo'$" )
- code: `workhorse/workhorse/cli/target.py::LiveLookup`
- tests: `workhorse/tests/test_control_command.py::test_an_id_groom_knows_resolves_to_the_run_dir_groom_names`
- detail: [live lookup result fields](concepts/live-lookup-result.md)
