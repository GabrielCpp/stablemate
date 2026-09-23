"""A cold start stubs a book from its surface, and every run seeds its work list once."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from okf_book.support import EnumerateOnly, WorkListView, ScriptedRunner, commits, git, listing_runner
from ostler.stamp import stamp_page
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.graph import preflight, registry_graphs

from workhorse_workflows.okf_book.shared.budget import ALONE_CEILING_TOKENS, CHARS_PER_TOKEN
from workhorse_workflows.okf_book.shared.citations import book_pages
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, EntryLink, read_entries, write_entries
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.workflow import workflow

App = Callable[[str], Path]
RunBook = Callable[[EnumerateOnly, ScriptedRunner], WorkListView]
COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")


def _cold_start(app: App, run_book: RunBook) -> tuple[Path, ScriptedRunner, WorkListView]:
    repo = app("tally-cli")
    runner = listing_runner(*COMMANDS)
    result = run_book(EnumerateOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)
    return repo, runner, result


def _stamp_book(repo: Path) -> None:
    for page in book_pages(repo, "tally"):
        _ = stamp_page(repo, repo / FEATURES_DIR, page.relative_to(repo).as_posix())


def test_a_cold_start_links_each_command_and_walks_the_cli(app: App, run_book: RunBook) -> None:
    repo, runner, result = _cold_start(app, run_book)

    assert runner.total == 1
    assert [link.target for link in read_entries(repo, "tally")] == [f"tally.md#{c}" for c in COMMANDS]
    assert commits(repo)[0] == "docs(tally): stub the cli entry points"
    assert git(repo, "status", "--porcelain") == ""
    assert result.services == ("tally",)
    assert {"tally/cli.py", "tally/ledger.py", "tally/report.py", "tally/__main__.py"} <= set(result.files)
    assert not [path for path in result.files if "test" in Path(path).name]
    assert result.pruned == ()


def test_a_cold_start_commits_only_the_pages_it_stubbed(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    stray = repo / FEATURES_DIR / "tally" / "notes.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    _ = stray.write_text("# notes\n", encoding="utf-8")

    _ = run_book(EnumerateOnly(repo_dir=str(repo), surfaces=(TALLY,)), listing_runner(*COMMANDS))

    assert commits(repo)[0] == "docs(tally): stub the cli entry points"
    assert git(repo, "status", "--porcelain").strip() == "?? docs/features/tally/notes.md"


def test_a_merge_pass_keeps_the_file_edited_since_its_stamp(app: App, run_book: RunBook) -> None:
    repo, _runner, _first = _cold_start(app, run_book)
    _stamp_book(repo)
    report = repo / "tally" / "report.py"
    untouched = run_book(EnumerateOnly(repo_dir=str(repo), merge_pass=True), listing_runner("unused"))
    _ = report.write_text(report.read_text(encoding="utf-8") + "\nEDITED = True\n", encoding="utf-8")

    merged = run_book(EnumerateOnly(repo_dir=str(repo), merge_pass=True), listing_runner("unused"))

    assert "tally/report.py" not in untouched.files
    assert set(merged.files) - set(untouched.files) == {"tally/report.py"}


def test_a_run_with_no_surfaces_and_no_book_asks_nothing(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    runner = listing_runner("unused")

    result = run_book(EnumerateOnly(repo_dir=str(repo)), runner)

    assert runner.total == 0
    assert result == WorkListView()


def test_a_run_deletes_each_orphaned_page_in_its_own_commit(app: App, run_book: RunBook) -> None:
    repo = app("globex")
    _ = write_entries(repo, "web-app", [
        EntryLink("Widgets", "gui/screens/widget-list.md"),
        EntryLink("New widget", "gui/screens/new-widget.md"),
    ])
    _ = git(repo, "add", "-A")
    _ = git(repo, "commit", "-q", "-m", "entries")
    _ = git(repo, "rm", "-q", "-r", "app/web-app/static")
    _ = git(repo, "commit", "-q", "-m", "drop the static site")
    screens = "docs/features/web-app/gui/screens"

    result = run_book(EnumerateOnly(repo_dir=str(repo)), listing_runner("unused"))

    assert sorted(result.pruned) == [f"{screens}/new-widget.md", f"{screens}/widget-list.md"]
    assert sorted(commits(repo)[:2]) == [
        "docs(web-app): delete new-widget, its source is gone",
        "docs(web-app): delete widget-list, its source is gone",
    ]
    assert git(repo, "status", "--porcelain") == ""


def test_an_entry_too_large_for_one_turn_blocks_until_the_operator_splits_it(
    app: App, run_book: RunBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    entry = repo / TALLY.entry
    original = entry.read_text(encoding="utf-8")
    line = "x = 1\n"
    _ = entry.write_text(line * (ALONE_CEILING_TOKENS * CHARS_PER_TOKEN // len(line) + 1), encoding="utf-8")
    asked: list[str] = []

    def operator(path: Path, **_kwargs: object) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        _ = entry.write_text(original, encoding="utf-8")
        _ = path.write_text("STATUS: ANSWERED\n\nSplit the entry.\n", encoding="utf-8")

    monkeypatch.setattr(pyflow_driver, "wait_for_answer", operator)
    runner = listing_runner(*COMMANDS)

    result = run_book(EnumerateOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert len(asked) == 1
    assert f"{TALLY.entry} is gone, or past the {ALONE_CEILING_TOKENS} tokens" in asked[0]
    assert runner.total == 1
    assert "tally/cli.py" in result.files


def test_the_dry_run_reads_every_prompt_and_every_transition() -> None:
    graphs = registry_graphs(workflow)
    prompts = {step.name for graph in graphs for node in graph.states for step in node.steps if step.kind == "agent"}
    assert preflight(graphs, workflow.directory()) == []
    assert prompts == {p.relative_to(workflow.directory()).as_posix() for p in workflow.directory().glob("*/prompts/*.md") if not p.name.startswith("_")}
