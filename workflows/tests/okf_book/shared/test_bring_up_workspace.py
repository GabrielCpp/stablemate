"""A runbook that places a step in a workspace member the run lacks fails the bring-up naming the member and the members it has."""
from __future__ import annotations

import logging

from okf_book.support import BOOK, MEMBER, SERVICE, Workspace, ledger_pages

from workhorse_workflows.okf_book.shared.book_run import bring_up


def test_a_step_in_a_member_the_workspace_lacks_fails_the_bring_up_naming_it(workspace: Workspace) -> None:
    for name, text in ledger_pages(18081).items():
        page = workspace.docs / BOOK / name
        page.parent.mkdir(parents=True, exist_ok=True)
        _ = page.write_text(text.replace(f"repo://{MEMBER}/.", "repo://billing/."), encoding="utf-8")

    stack = bring_up(logging.getLogger("bring-up"), workspace.docs, SERVICE)

    assert not stack.up
    assert "billing" in stack.notes
    assert MEMBER in stack.notes
    assert stack.owned == ()
