---
type: flow
slug: okf-builder-audit
title: OKF-builder audit workflow
---
# OKF-builder audit workflow

- start: a source scope (files, directories, service filter) and an optional turn budget
- steps:
  - [assess-audit](#assess-audit)
  - [audit-packet-review](#audit-packet-review)
- end: a behavior audit report showing assessed packets, unaudited packets (if budget exhausted), repairs discovered, and schema limitations
- verify: http_status(code=200, title="Assessment complete")
- detail: [okf-builder audit module](../concepts/okf-builder-audit-module.md)
- tests: `workflows/tests/okf_builder/test_audit.py::test_standalone_audit_is_registered`
- tests: `workflows/tests/okf_builder/test_audit.py::test_cli_dry_run_preflights_and_drives_audit`
- tests: `workflows/tests/okf_builder/test_audit.py::test_read_only_audit_reports_missing_behavior_and_persists_receipts`
- tests: `workflows/tests/okf_builder/test_audit.py::test_uncited_exported_file_is_queued_without_a_packet`

## Assess audit

Rebuild the audit packet scope from current source and book, reusing only receipts bound to the current review contract.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::assess_audit`
- detail: [assess_audit entry points](../concepts/assess-audit-entry-points.md)
- tests: `workflows/tests/okf_builder/test_audit.py::test_book_to_source_mismatches_queue_only_the_selected_book`
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_rebuilds_source_and_claims_before_reusing_receipts`
- tests: `workflows/tests/okf_builder/test_audit.py::test_sampling_and_unsupported_source_are_explicit_partial_reports`

## Audit packet review

On each pass:

1. Run preparation once: read source and book, write `preparation.json` and one `packet.json`
   per selected packet under `<run_dir>/behavior-audit/<digest>/`. Gate to the operator if the
   evidence is unreadable, or finish the run once no packets remain.
2. Take the next pending packet. If it carries no candidates and no claims, record an empty
   verdict without dispatching to the reviewer
3. Otherwise, if a turn budget is set and already spent, stop the run and record the packet and
   any that follow as unaudited
4. Otherwise spend one turn: dispatch the packet, and the previous failure as feedback on a retry,
   to the reviewer agent, and persist the returned verdict, report, and review contract binding
5. If the review contract changed mid-pass, or the reviewer turn was invalid or failed, retry once
   with the failure recorded as feedback; a second failure on the same packet gates to the
   operator instead of retrying again
6. Continue to the next pass; the iteration scans receipts against the prepared packets cached
   from step 1, so the per-packet work is receipt lookup rather than source and book reads

- code: `workflows/src/workhorse_workflows/okf_builder/audit/flow.py::Audit.start`
- tests: `workflows/tests/okf_builder/test_audit.py::test_invalid_verdicts_retry_twice_then_checkpoint_await`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_spent_reviewer_turn_is_gated_not_fatal`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_single_transient_blip_does_not_count_against_verdict_budget`
- tests: `workflows/tests/okf_builder/test_audit.py::test_three_consecutive_transient_failures_gate_with_models_dev_in_the_message`
- tests: `workflows/tests/okf_builder/test_audit.py::test_setup_warmup_failure_gates_before_any_packet_is_dispatched`
- tests: `workflows/tests/okf_builder/test_audit.py::test_turn_budget_ends_the_pass_with_the_unaudited_packets_listed`
- tests: `workflows/tests/okf_builder/test_audit.py::test_unsupported_files_become_out_of_scope_items`
- tests: `workflows/tests/okf_builder/test_audit.py::test_unresolved_classifies_ungrounded_packet_as_no_source`
- tests: `workflows/tests/okf_builder/test_audit.py::test_unresolved_classifies_grounded_judgment_as_model_judgment`
- tests: `workflows/tests/okf_builder/test_audit.py::test_validation_error_resolution_path_is_retry_then_ship`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_dropped_verdict_is_re_asked_on_its_own_not_by_re_asking_the_packet`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_repair_answered_for_exactly_the_owed_items_completes_the_pass`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_repair_naming_a_foreign_id_is_rejected_not_remembered`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_repair_that_also_comes_back_short_still_reaches_the_operator_gate`

