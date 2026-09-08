---
type: concept
slug: profile-selection
title: ProfileSelection — live model-set selection
---
# ProfileSelection — live model-set selection

`ProfileSelection` is the shared mutable box holding the name of the model profile a
run currently resolves. The runner is frozen, and workflow frame handoffs may copy the
runner reference, so the box is shared rather than replaced with a string on one copy.
An empty name means the run reads the configuration's top-level tables.

- code: `workhorse/workhorse/runner/ladder.py::ProfileSelection`
- tests: `workhorse/tests/test_model_resolution.py::test_the_box_is_shared_so_a_sub_flow_cannot_put_the_parent_back`
- detail: [ProfileSelection selection guidance](profile-selection-guidance.md)

## Fields

### name
- type: `str`
- default: `""`
- required: false
- semantics: the selected profile name
- verify: json_path(path="$.profile.name", equals="cheap")
- semantics: an empty name selects the top-level configuration tables
- verify: json_path(path="$.profile.name", equals="")
- code: `workhorse/workhorse/runner/ladder.py::ProfileSelection`
- tests: `workhorse/tests/test_model_resolution.py::test_a_switch_is_one_assignment_that_the_next_turn_reads`
