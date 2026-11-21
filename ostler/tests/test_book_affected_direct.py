"""`ostler book affected` splits what a story plays now from what the change reaches through shared code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from book_fakes import affected_report, app_repo, commit_files, committed_book, sourced_book, story_affected
from ostler.book.affected import Affected, reached_line
from test_book_affected import HANDLERS

API = "services/api"
STORY = "feat: x\n\nStory: ACME-1"

WIDE = ("package shelf\n\nfunc Put(id string) string {\n\treturn wide(id) + narrow(id)\n}\n\nfunc Remove(id string) string {\n\treturn wide(id)\n}\n\n"
        "func Other(id string) string {\n\treturn id\n}\n\nfunc wide(id string) string {\n\treturn id\n}\n\nfunc narrow(id string) string {\n\treturn id\n}\n")


def affect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, service: Any, where: Path, base: str, capsys: Any) -> tuple[int, dict[str, Any], str]:
    return affected_report(monkeypatch, tmp_path, service, capsys, "--app", str(where), "--since", base)


def test_a_journey_the_story_added_is_direct_while_a_changed_helper_reaches_every_endpoint(root, tmp_path, capsys):
    committed_book(root)
    journeys = root / API / "journeys"
    app = root / "app.py"
    commit_files(root, {
        "app.py": app.read_text().replace("        return False, None\n", "        return False, 0\n"),
        f"{API}/journeys/clear_the_list_twice.py": (journeys / "clear_the_list.py").read_text().replace("class ClearTheList(", "class ClearTheListTwice("),
        f"{API}/journeys/__init__.py": (journeys / "__init__.py").read_text().replace("from .clear_the_list import ClearTheList\n", "from .clear_the_list import ClearTheList\nfrom .clear_the_list_twice import ClearTheListTwice\n").replace("TheStoreIsDown)", "TheStoreIsDown, ClearTheListTwice)"),
    }, STORY)
    code, found, lines = story_affected(root, tmp_path, capsys)
    assert code == 0
    assert (found["direct_journeys"], found["direct_only"]) == (["ClearTheListTwice"], [])
    assert {"AddTodo", "ReadClock"} <= set(found["only"])
    assert found["reached"]["calls"] == len(found["only"])
    assert found["reached"]["causes"][0]["cause"] == "app.py::read_value"
    assert "ClearTheListTwice" in found["journeys"]
    assert lines[-1] == "ostler book run services.api --partial --journey 'ClearTheListTwice'"


def test_an_edited_endpoint_class_is_a_direct_call_and_the_print_leads_with_the_direct_lines(root, tmp_path, capsys):
    committed_book(root)
    todos = root / API / "endpoints" / "todos.py"
    commit_files(root, {f"{API}/endpoints/todos.py": todos.read_text().replace("Creates one todo;", "Makes one todo;")}, STORY)
    _, found, lines = story_affected(root, tmp_path, capsys)
    assert (found["direct_only"], found["direct_journeys"]) == (["AddTodo"], [])
    assert lines[2:5] == ["direct journeys: none", "direct calls (1): AddTodo", "reached beyond that: 0 calls, 0 journeys"]
    assert lines[5].startswith("changed: ")
    assert lines[6] == "calls (1): AddTodo"
    assert lines[-1] == "ostler book run services.api --only AddTodo"


def test_an_element_whose_source_names_the_changed_function_is_direct_and_one_reached_through_a_hop_is_not(monkeypatch, tmp_path, capsys):
    where, base = app_repo(tmp_path, {"h.go": HANDLERS})
    commit_files(where, {"h.go": HANDLERS.replace("func help(id string) string {\n\treturn id", "func help(id string) string {\n\treturn id + \"!\"")})
    book = sourced_book({"PutItem": ("h.go::help",), "RemoveItem": ("h.go::Remove",), "RestockItem": ("h.go::Other",)})
    _, found, _ = affect(monkeypatch, tmp_path, book, where, base, capsys)
    assert found["direct_only"] == ["PutItem"]
    assert found["only"] == ["PutItem", "RemoveItem"]
    assert found["reached"]["calls"] == 1
    assert found["reached"]["causes"][0] == {"cause": "h.go::help", "calls": 1, "journeys": 0}


def test_an_element_naming_a_file_whose_hunk_has_no_definition_line_is_direct(monkeypatch, tmp_path, capsys):
    files = {"config.go": "package shelf\n\n// sizes: a\n"}
    where, base = app_repo(tmp_path, files)
    commit_files(where, {"config.go": files["config.go"].replace("// sizes: a", "// sizes: b")})
    _, found, _ = affect(monkeypatch, tmp_path, sourced_book({"PutItem": ("config.go",)}), where, base, capsys)
    assert [w["elements"] for w in found["widened"]] == [["PutItem"]]
    assert found["direct_only"] == ["PutItem"]


def test_the_reached_causes_are_counted_beyond_the_direct_selection_and_sorted_by_calls(monkeypatch, tmp_path, capsys):
    where, base = app_repo(tmp_path, {"w.go": WIDE})
    commit_files(where, {"w.go": WIDE.replace("func wide(id string) string {\n\treturn id", "func wide(id string) string {\n\treturn id + \"!\"").replace("func narrow(id string) string {\n\treturn id", "func narrow(id string) string {\n\treturn id + \"?\"")})
    book = sourced_book({"PutItem": ("w.go::Put",), "RemoveItem": ("w.go::Remove",), "RestockItem": ("w.go::Other",)})
    _, found, out = affect(monkeypatch, tmp_path, book, where, base, capsys)
    expected = {"calls": 2, "journeys": 2, "causes": [{"cause": "w.go::wide", "calls": 2, "journeys": 2}, {"cause": "w.go::narrow", "calls": 1, "journeys": 2}]}
    assert found["direct_only"] == []
    assert found["reached"] == expected
    assert out.splitlines()[4] == reached_line(Affected("services.shelf", base, "head", False, reached=expected))
