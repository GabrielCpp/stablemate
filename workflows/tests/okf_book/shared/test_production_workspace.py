"""A workspace book's obligations come from the member that holds the product source, and the docs home is never walked."""
from __future__ import annotations

import json
from typing import cast
from pathlib import Path

from okf_book.support import BOOK, MEMBER, MEMBER_FILE, SERVICE, Workspace, git, ledger_pages

from workhorse_workflows.okf_book.shared.book_compilation import compile_services
from workhorse_workflows.okf_book.shared.production import production_files, walk_roots
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo


def _book(workspace: Workspace) -> None:
    for name, text in ledger_pages(18080).items():
        page = workspace.docs / BOOK / name
        page.parent.mkdir(parents=True, exist_ok=True)
        _ = page.write_text(text, encoding="utf-8")


def _grow_member(workspace: Workspace) -> None:
    _ = (workspace.member / "api" / "store.py").write_text("ENTRIES = []\n", encoding="utf-8")
    _ = (workspace.member / "api" / "handlers.py").write_text("from api.store import ENTRIES\n\n\ndef list_entries():\n    return ENTRIES\n", encoding="utf-8")
    _ = (workspace.member / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    _ = git(workspace.member, "add", ".")
    _ = git(workspace.member, "commit", "-m", "grow")


def test_the_walk_starts_at_the_member_files_the_entry_pages_cite(workspace: Workspace) -> None:
    _book(workspace)

    assert walk_roots(workspace.docs, SERVICE, SourceRepo(name=MEMBER, path=workspace.member)) == {MEMBER_FILE}


def test_the_production_set_is_the_member_s_reached_files_and_stack_files(workspace: Workspace) -> None:
    _book(workspace)
    _grow_member(workspace)

    files = production_files(workspace.docs, SERVICE, SourceRepo(name=MEMBER, path=workspace.member))

    assert files == {MEMBER_FILE, "api/store.py", "compose.yml"}


def test_a_citation_of_another_repository_starts_no_walk(workspace: Workspace) -> None:
    _book(workspace)

    assert walk_roots(workspace.docs, SERVICE, SourceRepo(name="web-app", path=workspace.member)) == frozenset()


def test_a_claim_that_cites_a_member_file_is_grounded_in_the_member_and_compiles_a_scenario(workspace: Workspace, tmp_path: Path) -> None:
    _book(workspace)
    source = SourceRepo(name=MEMBER, path=workspace.member)

    compiled = compile_services(workspace.docs, [SERVICE], source, tmp_path)

    packet = cast("dict[str, list[dict[str, str]]]", json.loads((tmp_path / "qa-okf-context.json").read_text(encoding="utf-8")))
    assert packet["healthFindings"] == []
    assert [unit["id"] for unit in packet["changedUnits"]] == [f"repo://{MEMBER}/{MEMBER_FILE}"]
    assert compiled.plan is not None
    assert compiled.gaps == ()
    assert any(obligation.startswith("okf:") and "list-entries" in obligation for obligation in compiled.obligations)


def test_outside_a_workspace_the_source_is_the_book_s_own_repository(tmp_path: Path) -> None:
    _ = (tmp_path / "api").mkdir()
    _ = (tmp_path / "api" / "handlers.py").write_text("def list_entries():\n    return []\n", encoding="utf-8")
    page = tmp_path / BOOK / "ledger-api.md"
    page.parent.mkdir(parents=True)
    _ = page.write_text("---\ntype: server\nslug: ledger-api\ntitle: Ledger API\n---\n# Ledger API\n\n- code: `api/handlers.py::list_entries`\n", encoding="utf-8")
    _ = (tmp_path / BOOK / "entries.md").write_text("---\ntype: entries\ntitle: Ledger\n---\n# Ledger\n\n- [Ledger API](ledger-api.md)\n", encoding="utf-8")

    assert walk_roots(tmp_path, SERVICE, SourceRepo(path=tmp_path)) == {"api/handlers.py"}
