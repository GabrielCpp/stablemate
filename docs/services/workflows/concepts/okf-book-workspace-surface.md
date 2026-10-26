---
type: concept
slug: okf-book-workspace-surface
title: okf-book workspace surface
---
# okf-book workspace surface

Under a workspace, a `surfaces` entry of `workhorse-okf-book` names the member that holds the product in its `repo` field. The run reads the product's source from that member and writes the book to the docs home. The scenarios it compiles run against the member's cited files, and the stack the book describes comes up in the member checkout. The member tree is never written.

- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::source_repo` @8f4e2afc037e
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::SourceRepo` @8f4e2afc037e
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_compilation.py::compile_services` @c55b3025b98a
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/source_view.py::build_source_view` @303f3884bd67
- rule: `repo` is required when a workspace is active and refused when none is, and it must name a member of that workspace
- rule: the book lands in the docs home, and the member tree is never written
- rule: a product path on a page is written `repo://<member>/<path>`, in a `code:` bullet, a `working-directory:` and a `contract:`
- tests: `workflows/tests/okf_book/main/test_workspace_run.py::test_the_member_repo_is_left_untouched`
- tests: `workflows/tests/okf_book/main/test_workspace_run.py::test_the_scenario_compiled_for_the_members_cited_claim_passes`
