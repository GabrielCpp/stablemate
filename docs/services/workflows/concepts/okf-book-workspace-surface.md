---
type: concept
slug: okf-book-workspace-surface
title: okf-book workspace surface
---
# okf-book workspace surface

Under a workspace, a `surfaces` entry of `workhorse-okf-book` names the member that holds the product in its `repo` field. The run reads the product's source from that member and writes the book to the docs home. The scenarios it compiles run against the member's cited files, and the stack the book describes comes up in the member checkout. The member tree is never written. The writer reads the surface's source folder in place in the member checkout, which the turn receives as an added directory, so the run copies no source. The writer's prompt tells it that tests and git-ignored files are no part of the book, and doctor refuses a `code:` bullet that cites a test file. The reground turn for a changed cited file reads a member's file in place in the same way.

A surface of kind `grpc` also names a `contract`, the folder of its repository that holds the service's `.proto` files, relative to the repository root (the member when `repo` is set). The writer reads that folder in place as a second added directory beside the entry folder, and its prompt cites the folder in a `contract:` bullet. The prompt for a `grpc` surface asks for one `rpc` page per rpc the contract declares and a `runbook` with `driver: grpc`, and it leaves out the screen and journey guidance. A surface whose contract names no folder of its repository is a blocker, the same as an entry that names none.

- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::source_repo` @8f4e2afc037e
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::SourceRepo` @8f4e2afc037e
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_compilation.py::compile_services` @c55b3025b98a
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/surface.py::Surface` @082af3baf3dd
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/writer_request.py::writer_request` @ddc7df3e2e91
- code: `workflows/src/workhorse_workflows/okf_book/main/flow.py::OkfBook.check_source` @cfc3b77ff93e
- code: `workflows/src/workhorse_workflows/okf_book/main/reground_book_flow.py::RegroundBook` @b82da8d89134
- rule: `repo` is required when a workspace is active and refused when none is, and it must name a member of that workspace
- rule: the reground turn reads a member's file in the member checkout, given as an added directory, and builds no source view
- rule: the writer reads the surface's source folder in place, given as an added directory, and the run copies no source
- rule: `contract` is required for a `grpc` surface, refused for a `cli`, `web` or `mobile` one, and allowed for an `http` one
- rule: the writer reads a surface's contract folder in place, given as a second added directory, and a contract that names no folder of its repository blocks the surface
- rule: tests and git-ignored files are left out of the book by the writer's prompt and refused by doctor, not hidden by a copy
- rule: the book lands in the docs home, and the member tree is never written
- rule: a product path on a page is written `repo://<member>/<path>`, in a `code:` bullet, a `working-directory:` and a `contract:`
- tests: `workflows/tests/okf_book/main/test_reground_workspace.py::test_a_changed_member_file_is_read_in_the_member_checkout`
- tests: `workflows/tests/okf_book/main/test_grpc_surface.py::test_a_grpc_surface_requires_a_contract`
- tests: `workflows/tests/okf_book/main/test_grpc_surface.py::test_the_writer_is_given_the_contract_folder_as_its_second_added_directory`
- tests: `workflows/tests/okf_book/main/test_grpc_surface.py::test_a_grpc_surface_whose_contract_is_no_folder_is_a_blocker`
- tests: `workflows/tests/okf_book/main/test_workspace_run.py::test_the_member_repo_is_left_untouched`
- tests: `workflows/tests/okf_book/main/test_workspace_run.py::test_the_writer_reads_the_member_folder_in_place_as_an_added_directory`
- tests: `workflows/tests/okf_book/main/test_workspace_run.py::test_no_copy_of_the_member_source_is_made_for_the_writer`
- tests: `workflows/tests/okf_book/main/test_workspace_run.py::test_the_scenario_compiled_for_the_members_cited_claim_passes`
