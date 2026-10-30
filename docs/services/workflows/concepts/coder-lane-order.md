---
type: concept
slug: coder-lane-order
title: Coder lane order
---
# Coder lane order

A story in the Coder main loop passes through its lanes in one order: prepare, specify, dev, document, QA, drain, finalize, commit. `specify` and `document` are the two phases of the one [docs flow](../flows/coder-docs.md). `specify` runs the spec phase before any code. It writes the story's behaviour model and the book delta it implies. The main loop records the nodes it wrote and commits the book pages the pass left uncommitted. `dev` builds to those nodes. `document` runs the build phase after dev and grounds the book in the code.

A QA refix sends the story back to dev and then through `document` and QA again. It does not run `specify` a second time. The spec nodes recorded by the first pass stay in force for the whole story.

- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder` @17e7f2fe6bf3
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs` @ea9cbe7a4c39
- rule: the book is written before dev from a behaviour model, so dev builds to the book's `verify:` checks and QA compiles its plan from them on its first pass
- rule: the build pass after dev grounds `code:` bullets and never rewrites a spec bullet the build contradicts
- rule: a refix goes dev, document, QA and never specifies again, because the spec describes the story and a defect in the build does not change it
- rule: the spec pass has no diff, so it skips context classification, source provenance and the grounding worklist, and its gate is `doctor` on the nodes it wrote
- rule: the spec pass's book delta is committed by the workflow before dev starts, so dev's clean-repo check never counts the spec as dev's leftovers
- rule: the spec pass and the build pass keep separate owner conversations, because they see different books
- rule: a path reopens a proof only when its bytes changed after the passing QA saw them
- rule: the artifacts dir, the book and tool output are never product, so they never reopen a docs pass, and the artifacts dir and tool output never reopen a proof
- rule: a book page edited after the passing QA reopens only the scenarios that cover it
- tests: `workflows/tests/coder/test_workflow.py::test_a_leftover_qa_already_passed_over_commits_without_a_rerun_or_a_docs_pass`
- tests: `workflows/tests/coder/shared/test_worktree.py::test_a_book_page_and_a_spec_file_do_not_count_as_a_code_change`
- tests: `workflows/tests/coder/test_workflow.py::test_the_story_is_specified_before_dev_and_a_refix_does_not_specify_again`
- tests: `workflows/tests/coder/test_workflow.py::test_the_spec_passs_book_page_is_committed_before_dev_starts`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_spec_pass_writes_the_book_before_any_diff_exists`
