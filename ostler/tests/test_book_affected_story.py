"""`ostler book affected --story` reads the commits that carry the story's trailer, with the uncommitted work, and prints the selection first."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from book_fakes import affected_report, app_repo, commit_files, git, sourced_book
from ostler.book import cli
from test_book_affected import FILES, edited

API = "services/api"
STORY = "feat: x\n\nStory: ACME-1"
OTHER = "feat: y\n\nStory: ACME-2"


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    return app_repo(tmp_path, FILES)


def affect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, service: Any, where: Path, capsys: Any, *args: str) -> tuple[int, dict[str, Any], str]:
    return affected_report(monkeypatch, tmp_path, service, capsys, "--app", str(where), *args)


BOOK: dict[str, tuple[str, ...]] = {"RemoveItem": ("remove.go::Remove",), "PutItem": ("svc.go::Server.Get",)}


def test_under_story_the_commits_of_other_work_between_the_storys_are_not_read(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    commit_files(where, edited("other.go", "return 1", "return 2"), OTHER)
    commit_files(where, edited("svc.go", 'return "b"', 'return "z"'), STORY)
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book(BOOK), where, capsys, "--story", "ACME-1")
    assert (code, found["uncovered"], found["only"], len(found["commits"]), found["story"]) == (0, [], ["PutItem", "RemoveItem"], 2, "ACME-1")
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book(BOOK), where, capsys, "--since", base)
    assert (code, [u["path"] for u in found["uncovered"]]) == (1, ["other.go"])


def test_under_story_the_uncommitted_work_is_read_and_the_header_says_so(monkeypatch, tmp_path, capsys, repo):
    where, _ = repo
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    (where / "svc.go").write_text(edited("svc.go", 'return "b"', 'return "z"')["svc.go"])
    code, found, out = affect(monkeypatch, tmp_path, sourced_book(BOOK), where, capsys, "--story", "ACME-1")
    assert (code, found["only"], found["dirty"]) == (0, ["PutItem", "RemoveItem"], True)
    assert out.splitlines()[0].startswith("affected services.shelf: story ACME-1, 1 commit, ")
    assert out.splitlines()[0].endswith(" and the uncommitted work")


def test_under_story_with_no_commit_carrying_the_trailer_the_command_exits_2_and_writes_no_report(monkeypatch, tmp_path, capsys, repo):
    where, _ = repo
    commit_files(where, edited("remove.go", "return id", "return id + id"), "feat: x\n\nsee ACME-1")
    code, found, out = affect(monkeypatch, tmp_path, sourced_book(BOOK), where, capsys, "--story", "ACME-1")
    assert code == 2
    assert "Story: ACME-1" in out
    assert found == {}
    assert not (tmp_path / "out" / "shelf-affected.json").exists()


def test_under_story_since_bounds_the_commits_read(monkeypatch, tmp_path, capsys, repo):
    where, _ = repo
    first = commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    commit_files(where, edited("svc.go", 'return "b"', 'return "z"'), STORY)
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book(BOOK), where, capsys, "--story", "ACME-1", "--since", first)
    assert (code, found["only"], len(found["commits"]), found["base"]) == (0, ["PutItem"], 1, first)


def test_under_story_no_verified_commit_is_needed(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    commit_files(where, edited("remove.go", "return id", "return id + id"), STORY)
    code, found, _ = affect(monkeypatch, tmp_path, sourced_book(BOOK), where, capsys, "--story", "ACME-1")
    assert (code, found["only"], found["base"]) == (0, ["RemoveItem"], base)


def test_the_print_names_the_plan_and_the_selection_before_any_file_and_lists_the_files_not_judged_last(root, tmp_path, capsys):
    (root / ".gitignore").write_text("__pycache__/\nnode_modules/\n")
    git(root, "init", "--quiet")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "base")
    for n in range(60):
        (root / f"note{n}.txt").write_text("x")
    todos = root / API / "endpoints" / "todos.py"
    commit_files(root, {f"{API}/endpoints/todos.py": todos.read_text().replace("Creates one todo;", "Makes one todo;")}, STORY)
    out_dir = tmp_path / "out"
    code = cli.main(["affected", "services.api", "--app", str(root), "--story", "ACME-1", "--out", str(out_dir)])
    lines = capsys.readouterr().out.splitlines()
    found = json.loads((out_dir / "api-affected.json").read_text())
    assert code == 0
    assert "plan: partial" in lines[:10]
    assert any(line.startswith("calls (1): AddTodo") for line in lines[:10])
    judged = next(i for i, line in enumerate(lines) if line.startswith("not judged"))
    assert judged > next(i for i, line in enumerate(lines) if line.startswith("not computed:"))
    assert [line for line in lines[judged + 1:] if line.startswith("  note")] == [f"  note{n}.txt" for n in sorted(range(60), key=str)[:20]]
    assert lines[judged + 21] == "  and 40 more"
    assert len(found["diff"]["not_computed"]["paths"]) == 50


def test_without_story_the_print_of_a_whole_plan_changes_only_in_order_and_cap(monkeypatch, tmp_path, capsys, repo):
    where, base = repo
    head = commit_files(where, edited("drawer.go", "return 1", "return 2"))
    code, found, out = affect(monkeypatch, tmp_path, sourced_book({"Drawer": ("drawer.go::Open",)}), where, capsys, "--since", base)
    lines = out.splitlines()
    assert lines[-1] == "ostler book run services.shelf"
    assert lines[:2] == [f"affected services.shelf: {base}..{head}", "plan: whole"]
    old = [
        f"affected services.shelf: {base}..{head}",
        "plan: whole",
        "changed: 1 app files, 0 book files, 0 not judged",
        "fallbacks:",
        "  drawer.go: record Drawer changed: the whole book",
        "chains:",
        "  drawer.go::Open -> Drawer (record, direct) -> the whole book",
        "not computed: " + "; ".join(found["not_computed"]),
        f"written: {tmp_path / 'out' / 'shelf-affected.json'}",
        "ostler book run services.shelf",
    ]
    added = ["calls: none", "journeys: none", "owed to a whole play (1): record Drawer changed: the whole book"]
    assert set(added) <= set(lines)
    assert Counter(lines) - Counter(added) == Counter(old)


def test_a_journey_the_story_added_is_selected_while_a_changed_record_makes_the_plan_whole(root, tmp_path, capsys):
    (root / ".gitignore").write_text("__pycache__/\nnode_modules/\n")
    git(root, "init", "--quiet")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "base")
    commit_files(root, {
        f"{API}/records.py": "LIMIT = 1\n\n\nclass Row:\n    source = ()\n    size = LIMIT\n",
        f"{API}/service.py": (root / API / "service.py").read_text().replace("from .people import ANA\n", "from .people import ANA\nfrom .records import Row\n").replace("    endpoints=ENDPOINTS,\n", "    endpoints=ENDPOINTS,\n    records=(Row,),\n"),
    }, "chore: records")
    todos = root / API / "endpoints" / "todos.py"
    commit_files(root, {f"{API}/endpoints/todos.py": todos.read_text().replace("Creates one todo;", "Makes one todo;")}, OTHER)
    journeys = root / API / "journeys"
    commit_files(root, {
        f"{API}/journeys/clear_the_list_twice.py": (journeys / "clear_the_list.py").read_text().replace("class ClearTheList(", "class ClearTheListTwice("),
        f"{API}/journeys/__init__.py": (journeys / "__init__.py").read_text().replace("from .clear_the_list import ClearTheList\n", "from .clear_the_list import ClearTheList\nfrom .clear_the_list_twice import ClearTheListTwice\n").replace("TheStoreIsDown)", "TheStoreIsDown, ClearTheListTwice)"),
        f"{API}/records.py": (root / API / "records.py").read_text().replace("LIMIT = 1", "LIMIT = 2"),
    }, STORY)
    out_dir = tmp_path / "out"
    code = cli.main(["affected", "services.api", "--app", str(root), "--story", "ACME-1", "--out", str(out_dir)])
    found = json.loads((out_dir / "api-affected.json").read_text())
    assert (code, found["plan"]) == (0, "whole")
    assert "ClearTheListTwice" in found["journeys"]
    assert "ClearTheListTwice" in found["by_journey"]
    assert "record Row changed: the whole book" in found["owed"]
    assert "AddTodo" not in found["only"]
