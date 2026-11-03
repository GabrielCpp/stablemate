---
type: concept
slug: qa-working-directory
title: QA working directory
---
# QA working directory

A `working-directory:` bullet on a runbook, a server or a stack step says where its command runs. A plain value is a path under the docs home, which holds the book. A value of `repo://<member>/<path>` is a path in the checkout of that workspace member, so a book kept in the docs home can run its stack inside the product repository it documents. A member the run's workspace lacks fails the bring-up with a message that names the member and lists the members the run has. A step with no value of its own inherits the runbook's.

- code: `ostler/ostler/qa/runbook.py::resolve_directory` @f838543065f2
- code: `ostler/ostler/qa/runbook.py::WorkingDirectoryError` @8f421fb0bd5f
- code: `ostler/ostler/step_commands.py::_directory_held` @7ddb4cf1b2d0
- rule: write a `working-directory:` as a plain path when the stack lives in the docs home, and as `repo://<member>/<path>` when it lives in a workspace member
- rule: the doctor refuses a fixture step whose `repo://` directory is missing from a member that is present, and leaves an unknown member to the bring-up, which names it
- rule: a stack runs in the member checkout and never writes a book page there
- rule: a scenario's commands run in the checkout itself, with no copy and no extra sandbox, because the coder workflow gives each story its own worktree and runs one scenario at a time; two runs that must not share a tree each take a worktree
- rule: a run's `qa/` folder holds that run's results and never a copy of the repository
- rule: the workflow's plan run removes the untracked files a pass left, so none reaches the story's commit, and a bare `ostler qa` removes nothing, because on a shared tree a new file may be another session's work
- rule: `working-directory: scenario:` on a fixture step reads as the checkout root, and leaves the book once the last client page drops it
- code: `ostler/ostler/qa/runbook.py::is_scenario_frame` @fb8e4f9ed087
- tests: `ostler/tests/test_qa_harness_book_fixtures.py::test_a_command_runs_in_the_checkout_and_copies_nothing_under_the_qa_folder`
- tests: `ostler/tests/test_qa_harness_book_fixtures.py::test_the_old_scenario_token_runs_a_fixture_step_at_the_checkout_root`
- tests: `ostler/tests/test_qa_runbook_workspace.py::test_a_runbook_step_and_the_app_run_in_the_member_checkout`
- tests: `ostler/tests/test_qa_runbook_workspace.py::test_a_member_the_workspace_lacks_fails_naming_it_and_the_known_ones`
- tests: `ostler/tests/test_qa_runbook_workspace.py::test_a_fixture_step_directory_a_member_lacks_is_refused`
