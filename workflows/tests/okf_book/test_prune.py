"""A page whose every cited file is gone is deleted in its own commit, with its entries link."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import commits, git

from workhorse_workflows.okf_book.entries import EntryLink, read_entries, write_entries
from workhorse_workflows.okf_book.prune import commit_removal, is_orphaned, orphaned_pages, remove_page

SCREENS = Path("docs/features/web-app/gui/screens")


def test_a_page_whose_source_is_deleted_goes_in_its_own_commit(app: Callable[[str], Path]) -> None:
    repo = app("globex")
    _ = write_entries(repo, "web-app", [
        EntryLink("Widgets", "gui/screens/widget-list.md"),
        EntryLink("New widget", "gui/screens/new-widget.md"),
    ])
    _ = git(repo, "add", "-A")
    _ = git(repo, "commit", "-q", "-m", "entries")
    _ = git(repo, "rm", "-q", "app/web-app/static/new.html", "app/web-app/static/new.js")
    _ = git(repo, "commit", "-q", "-m", "drop the new-widget page")

    gone = orphaned_pages(repo, "web-app")
    assert gone == (f"{SCREENS}/new-widget.md",)

    paths = remove_page(repo, gone[0])
    assert commit_removal(repo, gone[0], paths)
    assert remove_page(repo, gone[0]) == paths
    assert not commit_removal(repo, gone[0], paths)

    assert not (repo / SCREENS / "new-widget.md").exists()
    assert (repo / SCREENS / "widget-list.md").is_file()
    assert [link.target for link in read_entries(repo, "web-app")] == ["gui/screens/widget-list.md"]
    assert commits(repo)[:2] == ["docs(web-app): delete new-widget, its source is gone", "drop the new-widget page"]
    assert git(repo, "status", "--porcelain") == ""


def test_a_page_that_cites_nothing_or_one_live_file_is_kept(tmp_path: Path) -> None:
    _ = (tmp_path / "live.py").write_text("", encoding="utf-8")
    page = tmp_path / "page.md"
    _ = page.write_text("# p\n\n- code: `live.py::f`\n- code: `dead.py::g`\n", encoding="utf-8")
    bare = tmp_path / "bare.md"
    _ = bare.write_text("# p\n\nprose\n", encoding="utf-8")
    fenced = tmp_path / "fenced.md"
    _ = fenced.write_text("# p\n\n```\n- code: `dead.py::g`\n```\n", encoding="utf-8")
    assert not is_orphaned(tmp_path, page)
    assert not is_orphaned(tmp_path, bare)
    assert not is_orphaned(tmp_path, fenced)
