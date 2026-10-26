"""A book whose cited file changed is read against the change before any repair: the nodes the change bears on reach the writer, and every other citation of the file is stamped on the file as it is now."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import PAGE
from okf_book.support import MEMBER, MEMBER_FILE, MEMBER_SOURCE, Workspace
from ostler.stamp import digest_file

from workhorse_workflows.okf_book.main.nodes.gate import keep_failures, take_failures
from workhorse_workflows.okf_book.main.nodes.stale_citations import stale_files
from workhorse_workflows.okf_book.shared.page_check import PageProblem
LEDGER_PAGE = "docs/services/tally/concepts/ledger-file.md"

def test_failures_kept_twice_for_a_page_are_both_read(tmp_path: Path) -> None:
    keep_failures(tmp_path, "tally", {PAGE: (PageProblem(PAGE, "first"),)})
    keep_failures(tmp_path, "tally", {PAGE: (PageProblem(PAGE, "second"),), LEDGER_PAGE: (PageProblem(LEDGER_PAGE, "third"),)})

    kept = take_failures(tmp_path, "tally")

    assert [problem.text for problem in kept[PAGE]] == ["first", "second"]
    assert [problem.text for problem in kept[LEDGER_PAGE]] == ["third"]


def test_a_member_file_the_book_cites_is_listed_stale_with_its_repository_once_it_changes(workspace: Workspace) -> None:
    stamped = digest_file(MEMBER_SOURCE.encode())
    page = workspace.docs / "docs/services/ledger/handlers.md"
    page.parent.mkdir(parents=True)
    cited = f"repo://{MEMBER}/{MEMBER_FILE}::list_entries@{stamped}"
    _ = page.write_text(f"---\ntype: screen\nslug: handlers\ntitle: Handlers\n---\n# Handlers\n\n- code: `{cited}`\n\nWhat lists entries.\n", encoding="utf-8")
    _ = (workspace.member / MEMBER_FILE).write_text(MEMBER_SOURCE + "\n# changed\n", encoding="utf-8")

    files = stale_files(workspace.docs, "ledger")

    assert [(file.repository, file.path, file.digest) for file in files] == [(MEMBER, MEMBER_FILE, stamped)]
    assert [cited.page for cited in files[0].nodes] == ["docs/services/ledger/handlers.md"]
