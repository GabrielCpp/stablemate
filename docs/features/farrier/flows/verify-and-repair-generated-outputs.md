---
type: flow
slug: verify-and-repair-generated-outputs
title: Verify and repair generated outputs
---
# Verify and repair generated outputs

- start: a repository has an `agents.yml` selection and generated outputs that may be missing, changed, extra, or have edited hook-manager fences
- verify: unchanged(subject="repository before and after farrier install --check")
- steps:
-  - [install --check](../farrier.md#install)
-  - [check expected outputs](../concepts/output-installation.md#method-check_outputs)
-  - [report drift and its editable source](../concepts/drift-report.md#method-report)
-  - [resolve a generated file to its library source](../farrier.md#source)
-  - [install regenerated outputs](../farrier.md#install)
- end: the upstream library source is corrected and a subsequent render restores the repository to the expected generated output set
- verify: count(subject="drift entries after regeneration", equals=0)
- detail: [drift report](../concepts/drift-report.md)
- tests: `farrier/tests/test_drift_report.py::test_a_hand_edit_names_the_file_the_edit_belongs_in`
- tests: `farrier/tests/test_drift_report.py::test_the_report_says_the_comparison_is_against_the_working_tree`
- tests: `farrier/tests/test_drift_report.py::test_the_prefix_lines_survive_for_the_other_two_verdicts`
- tests: `farrier/tests/test_drift_report.py::test_a_current_repo_reports_nothing`
