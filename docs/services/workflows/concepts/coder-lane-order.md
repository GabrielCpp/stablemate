---
type: concept
slug: coder-lane-order
title: Coder lane order
---
# Coder lane order

A story in the Coder main loop passes through its lanes in one order: prepare, specify, dev, document, book QA, scenario QA, drain, finalize, commit. `specify` and `document` are the two phases of the one [docs flow](../flows/coder-docs.md). `specify` runs the spec phase before any code. It writes the story's behaviour model and the book delta it implies. The main loop records the nodes and the executable-book paths it wrote and commits what the pass left uncommitted, which for a covered service is only its `services/<name>/` folder. `dev` builds to those nodes. `document` runs the build phase after dev, grounds the book in the code, and commits the book pages that pass left uncommitted before QA runs. The [book lane](coder-book-qa-package.md) runs first of the two QA lanes: the service books the story touches are played against its code. The scenario lane follows it, so a story that holds both kinds of service is judged by both, in that order. The `finalize` recheck runs the build phase once more and commits nothing.

A refix from either QA lane sends the story back to dev and then through `document`, the book lane and the scenario lane again. It does not run `specify` a second time. The spec nodes recorded by the first pass stay in force for the whole story.

- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder` @03264fd820e2
- code: `workflows/src/workhorse_workflows/coder/book_qa/flow.py::BookQa` @552d7cda8ee9
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs` @2c7b8159826d
- rule: the book is written before dev from a behaviour model, so dev builds to the book's `verify:` checks and QA compiles its plan from them on its first pass
- rule: the build pass after dev grounds `code:` bullets and never rewrites a spec bullet the build contradicts
- rule: the build docs pass passes only when the book compiles into a QA plan with no defect gap on a page the story touched
- rule: QA starts from the plan the book compiles and amends it, and writes a plan by hand only when the book refuses to compile
- rule: the book lane runs before the scenario lane, and a book refix or replan is sent back before the scenario lane starts
- rule: a run killed in the scenario lane resumes there and does not replay the book lane
- rule: a story with no covered service passes the book lane with no agent call, so its QA is the scenario lane alone
- rule: a refix goes dev, document, the book lane, the scenario lane and never specifies again, because the spec describes the story and a defect in the build does not change it
- rule: a story whose services are all covered by an executable book writes its spec as book claims, gates the spec pass on `ostler book check` and no doctor, skips the document pass, and reads and writes no markdown book page
- rule: a story with an uncovered service keeps the markdown spec and document passes for that service only
- rule: a claim the spec pass writes into a covered book is expected red until the build, and a claim the build cannot meet is a block that names it
- rule: with every service covered, the scenario lane's packet passes with no obligation when no markdown page owns the changed code
- rule: the spec pass has no diff, so it skips context classification, source provenance and the grounding worklist, and its gate is `doctor` on the nodes it wrote
- rule: the spec pass's book delta is committed by the workflow before dev starts, so dev's clean-repo check never counts the spec as dev's leftovers
- rule: every pre-QA docs pass commits its book delta, so an owner's clean-repo check never counts the book as its leftovers
- rule: the finalize recheck leaves its book delta uncommitted, so an edit after the passing QA still reopens the scenarios that cover it
- rule: an owner's clean-repo check and the story commit skip the artifacts dir, because workflow lanes write their records there and each lane commits its own
- rule: the spec pass and the build pass keep separate owner conversations, because they see different books
- rule: a path reopens a proof only when its bytes changed after the passing QA saw them
- rule: the artifacts dir, the book and tool output are never product, so they never reopen a docs pass, and the artifacts dir and tool output never reopen a proof
- rule: a book page edited after the passing QA reopens only the scenarios that cover it
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_story_with_no_covered_service_passes_with_no_seat_and_no_stack`
- tests: `workflows/tests/coder/test_workflow.py::test_a_book_refix_reaches_the_dev_owner_before_the_scenario_qa_is_handed_off`
- tests: `workflows/tests/coder/test_workflow.py::test_a_run_killed_in_qa_resumes_on_the_scenario_qa_without_replaying_the_book_lane`
- tests: `workflows/tests/coder/test_workflow.py::test_a_leftover_qa_already_passed_over_commits_without_a_rerun_or_a_docs_pass`
- tests: `workflows/tests/coder/shared/test_worktree.py::test_a_book_page_and_a_spec_file_do_not_count_as_a_code_change`
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_is_specified_before_dev_and_a_refix_does_not_specify_again`
- tests: `workflows/tests/coder/test_workflow.py::test_the_spec_passs_book_page_is_committed_before_dev_starts`
- tests: `workflows/tests/coder/test_workflow.py::test_the_build_passs_book_page_is_committed_before_qa_runs`
- tests: `workflows/tests/coder/test_workflow.py::test_the_finalize_rechecks_book_edit_stays_uncommitted_until_the_leftovers_commit`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_book_that_does_not_compile_goes_back_to_the_owner_with_its_gaps`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_book_that_compiles_hands_the_owner_its_plan_as_the_standing_one`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_spec_pass_writes_the_book_before_any_diff_exists`
- tests: `workflows/tests/coder/docs/test_flow.py::test_an_all_covered_story_is_specified_with_the_book_check_and_no_doctor`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_red_book_check_sends_the_spec_pass_back_with_its_output`
- tests: `workflows/tests/coder/docs/test_flow.py::test_an_all_covered_story_skips_the_document_pass`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_mixed_story_keeps_the_markdown_path_for_the_uncovered_service_only`
- tests: `workflows/tests/coder/shared/test_story_commit.py::test_a_covered_services_spec_delta_commit_holds_only_its_book_folder`
- tests: `workflows/tests/coder/test_book_only_path.py::test_no_prompt_of_the_book_only_path_names_the_markdown_book`
- tests: `workflows/tests/coder/test_book_only_path.py::test_the_scenario_packet_of_an_all_covered_story_passes_with_no_obligation`
