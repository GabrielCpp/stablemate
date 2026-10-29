"""A citation names a file of a repository and, once stamped, the digest the page was written against."""
from __future__ import annotations

from pathlib import Path

from okf_book.support import MEMBER, MEMBER_FILE, MEMBER_SOURCE, Workspace
from ostler.stamp import digest_citation, digest_file

from workhorse_workflows.okf_book.shared.citations import Citation, citations_in, cites_changed_file

PAGE_FOLDER = "docs/services/ledger"


def test_a_citation_reads_its_repository_path_digest_and_symbol() -> None:
    text = "- code: `a/b.py::f` @0123456789ab\n- code: `repo://api-service/c.go::g`\n- code: d.py@ba9876543210\n"
    assert citations_in(text) == (
        Citation("a/b.py", "0123456789ab", "f"),
        Citation("c.go", None, "g", "api-service"),
        Citation("d.py", "ba9876543210"),
    )


def _page(docs: Path, cited: str) -> None:
    page = docs / PAGE_FOLDER / "list.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    _ = page.write_text(f"# List\n\n- code: `{cited}`\n", encoding="utf-8")


def test_a_citation_of_a_member_file_is_stale_once_the_member_file_changes(workspace: Workspace) -> None:
    stamped = digest_file(MEMBER_SOURCE.encode())
    _page(workspace.docs, f"repo://{MEMBER}/{MEMBER_FILE}::list_entries@{stamped}")
    assert not cites_changed_file(workspace.docs, "ledger")

    _ = (workspace.member / MEMBER_FILE).write_text(MEMBER_SOURCE + "\n# changed\n", encoding="utf-8")

    assert cites_changed_file(workspace.docs, "ledger")


def test_a_citation_of_a_repository_the_workspace_lacks_is_not_stale(workspace: Workspace) -> None:
    _page(workspace.docs, f"repo://globex/{MEMBER_FILE}::list_entries@0123456789ab")

    assert not cites_changed_file(workspace.docs, "ledger")


def test_a_symbol_citation_is_stale_only_when_its_declaration_changes(workspace: Workspace) -> None:
    source = (workspace.member / MEMBER_FILE).read_text(encoding="utf-8")
    stamped = digest_citation(MEMBER_FILE, source.encode(), "list_entries")
    _page(workspace.docs, f"repo://{MEMBER}/{MEMBER_FILE}::list_entries@{stamped}")

    _ = (workspace.member / MEMBER_FILE).write_text(source + "\n\ndef added() -> None:\n    pass\n", encoding="utf-8")
    assert not cites_changed_file(workspace.docs, "ledger")

    _ = (workspace.member / MEMBER_FILE).write_text(source.replace("return []", "return [1]"), encoding="utf-8")
    assert cites_changed_file(workspace.docs, "ledger")
