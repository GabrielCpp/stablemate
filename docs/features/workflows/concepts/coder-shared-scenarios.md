---
type: concept
slug: coder-shared-scenarios
title: Coder shared scenario parsing
---
# Coder shared scenario parsing

- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::__all__`
- tests: `workflows/tests/coder/shared/test_scenarios.py::test_scenarios_are_parsed_with_their_ac_and_level`

This module reads a plan's Test Scenarios section for the QA lane. It recognizes scenario
headings, preserves each scenario's title, AC, and level, and identifies levels that the
development plan routes away from automated tests. It reads the selected layer plan before the
root `plan.md`, and does not merge a partially parsed layer plan with the root copy.

## Fields

### title
- type: `str`
- default: none
- required: true
- semantics: the non-empty text after the scenario heading's colon
- verify: count(subject="scenario titles", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::Scenario`

### ac
- type: `str`
- default: none
- required: true
- semantics: the trimmed value of the scenario's AC bullet, or an empty string when that bullet is absent
- verify: count(subject="scenario acceptance-criterion values", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::Scenario`

### level
- type: `str`
- default: none
- required: true
- semantics: the trimmed value of the scenario's Level bullet, or an empty string when that bullet is absent
- verify: count(subject="scenario levels", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::Scenario`

## Methods

### writes_no_test
- sig: `Scenario.writes_no_test -> bool`
- does: treats `qa-only`, `qa only`, `e2e`, `end-to-end`, and `manual` as no-test levels after removing a spaced dash, hyphen, parenthesis, or comma justification
- returns: `true` only when the normalized level head is in the no-test vocabulary
- verify: count(subject="no-test scenario classifications", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::Scenario.writes_no_test`
- tests: `workflows/tests/coder/shared/test_scenarios.py::test_scenarios_are_parsed_with_their_ac_and_level`

### parse_scenarios
- sig: `parse_scenarios(text: str) -> list[Scenario]`
- does: accepts a numbered or unnumbered Test Scenarios heading whose first two words are `test scenarios`
- does: collects scenario headings in source order until the enclosing scenario-list section ends
- does: skips a scenario heading whose colon has no title
- does: extracts AC and Level bullet values while removing supported emphasis around bullet values
- returns: an empty list when no Test Scenarios section exists, otherwise the recognized scenarios in source order
- verify: count(subject="parsed scenario lists", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::parse_scenarios`
- tests: `workflows/tests/coder/shared/test_scenarios.py::test_the_section_ends_at_the_next_heading`

### qa_only_scenarios
- sig: `qa_only_scenarios(spec_abs: Path | None, plan_file: str) -> list[Scenario]`
- does: returns no obligations when the specification directory is absent
- does: reads the selected plan file and then `plan.md` as a fallback, suppressing unreadable-file errors
- does: selects the first readable plan that parses to at least one scenario
- returns: only scenarios whose level is classified by `writes_no_test`, preserving their source order
- verify: count(subject="QA-only scenario subsets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::qa_only_scenarios`
- tests: `workflows/tests/coder/shared/test_scenarios.py::test_the_layer_plan_is_read_before_the_root_plan`
