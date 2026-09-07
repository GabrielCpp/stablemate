---
type: concept
slug: live-lookup-result
title: Live lookup result fields
---
# Live lookup result fields

A live lookup result has two complementary fields rather than competing alternatives. The lookup
accepts a returned directory only when it belongs to the requested workflow and exists on the
current machine. A caller resolving a target uses `run_dir` only when it is present; otherwise it
uses `note` to explain whether groom was unavailable, returned an unusable directory, or found no
matching live run.

- code: `workhorse/workhorse/cli/target.py::LiveLookup`
- rule: use `run_dir` to select a locally usable target; use `note` to report the resolution or miss
- tests: `workhorse/tests/test_control_command.py::test_an_id_groom_knows_resolves_to_the_run_dir_groom_names`
