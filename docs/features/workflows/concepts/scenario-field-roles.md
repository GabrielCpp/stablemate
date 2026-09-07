---
type: concept
slug: scenario-field-roles
title: Scenario field roles
---
# Scenario field roles

Each parsed `Scenario` combines three complementary attributes rather than offering three
alternative representations. `parse_scenarios` constructs every retained scenario with its
heading title plus the AC and Level bullet values. The title names the scenario in a QA plan,
the AC records its acceptance criterion, and the level determines whether the QA lane owns it.

No attribute ranks above or replaces another: callers use all three values for their respective
roles. AC and Level may be empty when their source bullets are absent, while a missing title
causes the parser to omit the scenario because it cannot be named.

- code: `workflows/src/workhorse_workflows/coder/shared/scenarios.py::Scenario`
- rule: use `title` to identify a scenario, `ac` to retain its acceptance criterion, and `level` to classify its test ownership; these complementary fields have no preferred substitute
