---
type: concept
slug: qa-working-directory
title: QA working directory
---
# QA working directory

A `working-directory:` bullet on a runbook, a server or a stack step says where its command runs. A plain value is a path under the docs home, which holds the book. A value of `repo://<member>/<path>` is a path in the checkout of that workspace member, so a book kept in the docs home can run its stack inside the product repository it documents. A member the run's workspace lacks fails the bring-up with a message that names the member and lists the members the run has. A step with no value of its own inherits the runbook's.

- code: `ostler/ostler/qa/runbook.py::resolve_directory` @66911fe4abd5
- code: `ostler/ostler/qa/runbook.py::WorkingDirectoryError` @66911fe4abd5
- code: `ostler/ostler/step_commands.py::_directory_held` @a44a1ff496dd
- rule: write a `working-directory:` as a plain path when the stack lives in the docs home, and as `repo://<member>/<path>` when it lives in a workspace member
- rule: the doctor refuses a fixture step whose `repo://` directory is missing from a member that is present, and leaves an unknown member to the bring-up, which names it
- rule: a stack runs in the member checkout and never writes a book page there
- tests: `ostler/tests/test_qa_runbook_workspace.py::test_a_runbook_step_and_the_app_run_in_the_member_checkout`
- tests: `ostler/tests/test_qa_runbook_workspace.py::test_a_member_the_workspace_lacks_fails_naming_it_and_the_known_ones`
- tests: `ostler/tests/test_qa_runbook_workspace.py::test_a_fixture_step_directory_a_member_lacks_is_refused`
