---
type: format
slug: qa-deferrals
title: QA deferrals
---
# QA deferrals

The list of book page prefixes whose required obligations a caller has handed to another judge. The
caller writes it into the story's spec directory before it builds the QA context packet. Every build
of the packet, a repair rebuild included, reads it and marks the matching obligations as deferred, so
the marks hold whether or not the packet's health findings make it invalid.

- file: `qa-deferrals.json` in the story's spec directory, beside `qa-okf-context.json`
- code: `ostler/ostler/qa/compile.py::apply_deferrals` @439aa015bce5
- code: `ostler/ostler/qa/context.py::cmd_context` @2e5f40cd24df
- detail: [compiling a book into a QA plan](../concepts/compiling-a-book-into-a-qa-plan.md)
- detail: [coder book qa package](../../workflows/concepts/coder-book-qa-package.md)
- tests: `ostler/tests/test_qa_deferrals.py::test_the_build_defers_required_undeferred_obligations_under_a_prefix`
- tests: `ostler/tests/test_qa_deferrals.py::test_an_invalid_packet_still_carries_the_marks`
- tests: `ostler/tests/test_qa_deferrals.py::test_no_file_and_an_empty_list_defer_nothing`

The file is a JSON list. A missing, unreadable or empty file marks nothing. An entry that is not an
object, or that has no `prefix`, is ignored.

## Fields

### prefix

- type: `str`
- required: true
- semantics: an obligation whose `node` starts with the prefix matches, for example `docs/services/api/`
- semantics: only a required obligation with no `deferred` of its own is marked, so a gap the compiler found keeps its own reason and an optional obligation stays as it is
- verify: json_path(path="$[0].prefix", equals="docs/services/api/")
- code: `ostler/ostler/qa/compile.py::apply_deferrals` @439aa015bce5

### kind

- type: `str`
- required: false
- semantics: the `kind` the marked obligation carries in its `deferred` object
- verify: json_path(path="$[0].kind", equals="book")
- code: `ostler/ostler/qa/compile.py::apply_deferrals` @439aa015bce5

### detail

- type: `str`
- required: false
- semantics: the `detail` the marked obligation carries in its `deferred` object
- verify: json_path(path="$[0].detail", equals="judged by the executable book of api")
- code: `ostler/ostler/qa/compile.py::apply_deferrals` @439aa015bce5
