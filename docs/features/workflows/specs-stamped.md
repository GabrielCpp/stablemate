---
type: format
slug: specs-stamped
title: Stamped specs result
---
# Stamped specs result

The stamping result reports how many direct markdown documents in a story spec directory received
an OKF type during the pass. Already typed documents are left unchanged, and only the directory's
immediate `*.md` children are considered. Untyped documents remaining after the pass fail the
workflow instead of producing a successful result; no-story and missing-directory inputs are
successful no-ops with a zero count.

- file: none — in-memory workflow result
- config: Ostler spec entity rules and the selected story spec directory
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::SpecsStamped`
- detail: [Coder story pipeline](concepts/story-pipeline.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`

## Fields

### stamped
- type: `int`
- default: `0`
- required: false
- semantics: number of direct markdown spec documents newly given an OKF type in this pass, excluding reserved files and already typed documents
- verify: json_path(path="$.stamped", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::SpecsStamped.stamped`
