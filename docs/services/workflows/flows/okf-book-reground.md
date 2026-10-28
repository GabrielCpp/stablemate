---
type: flow
slug: okf-book-reground
title: okf-book reground pass
---
# okf-book reground pass

The `RegroundBook` sub-flow reads each file a book cites that changed since its citation was
stamped, one turn per changed file, before any owner turn repairs a page against it. A turn names
the nodes a change bears on; those come back as failures for the book's owner, and every other
citation of the file is stamped on the file as it is now. The turn writes nothing itself: the flow
restores the tree after each turn and commits only the stamps. It is entered by the
[check-okf-book flow](check-okf-book.md) before a book with a changed citation is routed to its
owner.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-okf-book.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-okf-book.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [check-okf-book flow](check-okf-book.md)
- tests: `workflows/tests/okf_book/main/test_reground.py::test_a_changed_cited_file_sends_its_citing_nodes_to_the_repair`

The stages, in order: [list](#list), [read](#read), [stamp](#stamp), [commit](#commit).

The flow starts when it is handed a service whose book cites at least one file that changed since
the citation was stamped.
It ends on a `Regrounded` result naming the failures the owner's next turn must repair, and how
many citations the pass restamped unread because the change spared them.

The implementation is `workflows/src/workhorse_workflows/okf_book/main/reground_book_flow.py::RegroundBook`.

- code: `workflows/src/workhorse_workflows/okf_book/main/reground_book_flow.py::RegroundBook` @1228ac2f98a9

## Steps

### list

- kind: prepare

`start` lists every file the book cites that changed since its stamp, each with the nodes citing
it.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::stale_files` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::StaleFile` @bf08d51b9f51

### read

- kind: drive

`read_change` reads one changed file as its diff from the version the book was stamped on. A file
whose stamped version no commit holds sends every citing node to the repair unread, since nothing
proves what changed. Otherwise one turn reads the diff and names the nodes the change bears on;
a turn that ends without a verdict leaves its citations as they are, so a reading that failed
blocks no repair that did not need one.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::stamped_text` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::unread_problems` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::affected_problems` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::reground_template_args` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::keep_old_version` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/source_view.py::build_source_view` @303f3884bd67
- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::changed_since` @a6b5e7558709
- code: `workflows/src/workhorse_workflows/okf_book/shared/confine.py::restore` @a6b5e7558709
- code: `workflows/src/workhorse_workflows/okf_book/shared/source_repo.py::repository_root` @6e5aa862cb6d
- code: `workflows/src/workhorse_workflows/okf_book/shared/metrics.py::turn_metric` @141af4ec2fee

### stamp

- kind: run

`stamp_spared_citations` restamps, on the file as it is now, every citation the change spares: the
ones no turn named as affected by what changed.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::spared_pairs` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::stamp_spared` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::with_problems` @bf08d51b9f51

### commit

- kind: run

`commit_stamps` renders the repo's agent files and commits the pages whose stamps changed, under a
message naming the restamp. A failed render, or a commit the repository still refuses after a
turn at fixing it, waits for the operator. The result carries the failures the list and read
stages found, for the owner's next turn to repair.

- code: `workflows/src/workhorse_workflows/okf_book/main/nodes/stale_citations.py::Regrounded` @bf08d51b9f51
- code: `workflows/src/workhorse_workflows/okf_book/shared/book_commits.py::repaired_book_commit_message` @4ecb25dbf13a
