---
type: flow
slug: verify-and-repair-generated-outputs
title: Verify and repair generated outputs
---
# Verify and repair generated outputs

- start: a repository has an `agents.yml` selection and generated outputs that may be missing, changed, extra, or have edited hook-manager fences
- steps:
  - [check for drift](../farrier-invocations.md#check-for-drift)
  - [resolve a generated file to its library source](../farrier-invocations.md#resolve-a-generated-file)
  - [install regenerated outputs](../farrier-invocations.md#regenerate-outputs)
- end: a render writes the expected generated output set into the repository (commands: [install](../farrier-commands-install.md#install))
- verify: created(subject="c203/.claude/skills/acme-demo/SKILL.md")
- fixture: demo-skill-repo dir=c202
- fixture: generated-demo-skill dir=c206
- fixture: demo-skill-repo dir=c203
- detail: [drift report](../concepts/drift-report.md)
- tests: `farrier/tests/test_drift_report.py::test_a_hand_edit_names_the_file_the_edit_belongs_in`
- tests: `farrier/tests/test_drift_report.py::test_the_report_says_the_comparison_is_against_the_working_tree`
- tests: `farrier/tests/test_drift_report.py::test_the_prefix_lines_survive_for_the_other_two_verdicts`
- tests: `farrier/tests/test_drift_report.py::test_a_current_repo_reports_nothing`
