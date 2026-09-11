---
type: concept
slug: okf-builder-shared-checkpoint
title: OKF-builder checkpoint gate
---
# OKF-builder checkpoint gate

This module is the deterministic convergence gate after the worklist drain. It optionally applies
Ostler autofixes and formatting, reloads the graph, scopes all doctor findings to the selected
feature book, and creates one repair item for each `(file, node, doctor code)` group. It treats
warnings as standing findings, distinguishes source-grounded repairs, and fingerprints findings
to count unchanged stalls.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/checkpoint.py`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_warning_is_a_standing_finding`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_findings_outside_the_book_are_not_this_run_s_problem`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_one_item_per_node_and_code`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_the_item_order_is_the_drain_order`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_group_finding_is_one_item_scoped_to_every_competitor`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_two_competitions_sharing_a_document_stay_two_items`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_ref_that_is_not_a_node_groups_by_the_file`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_an_indexed_file_node_ref_mints_one_item_per_bullet`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_grounded_code_is_a_flag_not_a_kind`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_node_past_the_chunk_cap_splits_into_distinct_items`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_book_with_warnings_and_no_errors_is_dirty`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_pending_repair_whose_finding_stopped_firing_is_closed_at_the_checkpoint`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_the_drain_settles_a_stale_repair_before_it_is_picked`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_the_settle_is_amortized_over_the_drain`
- code: `workflows/tests/okf_builder/test_checkpoint.py::test_a_settle_with_nothing_to_settle_does_not_read_doctor`
- tests: `workflows/tests/okf_builder/test_checkpoint.py`

## Methods

### scoped_findings
- sig: `scoped_findings(report: dict, repo_root: str, features: str) -> list[dict]`
- does: retains doctor findings whose paths are the selected feature root or one of its descendants
- verify: count(subject="scoped OKF-builder doctor findings", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/checkpoint.py::scoped_findings`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_findings_outside_the_book_are_not_this_run_s_problem`

### checkpoint_book
- sig: `checkpoint_book(logger: logging.Logger, repo_root: str = ".", features_root: str = "", prev_round: int = 0, prev_signature: str = "", prev_stall: int = 0) -> Checkpoint`
- does: applies Ostler autofix and formatting to the selected feature book before doctor evaluation
- verify: count(subject="canonicalized OKF-builder books", equals=1)
- does: reloads the graph after formatting so doctor evaluates the written book
- verify: count(subject="reloaded OKF-builder checkpoint graphs", equals=1)
- does: reports every scoped doctor finding, including warnings, as standing convergence work
- verify: count(subject="standing OKF-builder doctor findings", equals=1)
- does: creates repair items grouped by file, node, and doctor code
- verify: created(subject="OKF-builder checkpoint repair items")
- verify: count(subject="OKF-builder checkpoint repair batches", equals=1)
- does: carries grounded status in each repair item
- verify: count(subject="grounded OKF-builder repair items", equals=1)
- does: bounds the findings carried by each repair item
- verify: count(subject="bounded OKF-builder repair item findings", equals=1)
- does: increments the stall count only when the finding signature is unchanged from the prior round
- verify: count(subject="unchanged OKF-builder finding signatures", equals=1)
- returns: checkpoint status, doctor output, round counters, repair items, and stall signature
- verify: count(subject="OKF-builder checkpoint results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/checkpoint.py::checkpoint_book`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_book_with_warnings_and_no_errors_is_dirty`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_warning_is_a_standing_finding`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_one_item_per_node_and_code`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_group_finding_is_one_item_scoped_to_every_competitor`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_two_competitions_sharing_a_document_stay_two_items`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_ref_that_is_not_a_node_groups_by_the_file`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_an_indexed_file_node_ref_mints_one_item_per_bullet`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_the_item_order_is_the_drain_order`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_grounded_code_is_a_flag_not_a_kind`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_node_past_the_chunk_cap_splits_into_distinct_items`

### settle_stale
- sig: `settle_stale(logger: logging.Logger, worklist_path: str, repo_root: str = ".", features_root: str = "", every: int = SETTLE_EVERY) -> Settled`
- does: closes pending repair rows mid-drain whose findings doctor no longer reports
- verify: created(subject="closed mid-drain stale OKF-builder repair rows")
- does: reads doctor on first entry and amortized after every N completed items
- verify: created(subject="amortized OKF-builder mid-drain doctor reads")
- does: compares standing repair items against the current doctor report to settle rows
- verify: created(subject="OKF-builder standing repair items for settlement")
- does: skips the doctor read when no pending fix items remain, reporting zero settled rows in that case
- verify: created(subject="OKF-builder settlement watermark update")
- returns: settlement status, pending item count, standing repair count, and settled count
- verify: created(subject="OKF-builder settlement results")
- code: `workflows/src/workhorse_workflows/okf_builder/shared/checkpoint.py::settle_stale`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_pending_repair_whose_finding_stopped_firing_is_closed_at_the_checkpoint`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_the_drain_settles_a_stale_repair_before_it_is_picked`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_the_settle_is_amortized_over_the_drain`
- tests: `workflows/tests/okf_builder/test_checkpoint.py::test_a_settle_with_nothing_to_settle_does_not_read_doctor`
