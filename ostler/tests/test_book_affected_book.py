"""`ostler book affected` also reads the book's own folder, and says so when a change selects no play."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from book_fakes import git
from ostler.book import cli
from ostler.book.bookdiff import changed_classes

API = "services/api"


@pytest.fixture
def repo(root: Path) -> tuple[Path, str]:
    (root / ".gitignore").write_text("__pycache__/\nnode_modules/\n")
    git(root, "init", "--quiet")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "base")
    return root, git(root, "rev-parse", "--short", "HEAD").strip()


def affect(where: Path, base: str, tmp_path: Path, capsys: Any) -> tuple[int, dict[str, Any], str]:
    out = tmp_path / "out"
    code = cli.main(["affected", "services.api", "--app", str(where), "--since", base, "--out", str(out)])
    return code, json.loads((out / "api-affected.json").read_text()), capsys.readouterr().out


def edit(where: Path, path: str, old: str, new: str) -> None:
    file = where / path
    text = file.read_text()
    assert old in text
    file.write_text(text.replace(old, new))


def test_an_edited_endpoint_class_of_the_book_selects_the_plays_of_that_endpoint(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/endpoints/todos.py", "Creates one todo;", "Makes one todo;")
    code, found, out = affect(where, base, tmp_path, capsys)
    assert [(c["path"], c["function"], c["element"]) for c in found["chains"]] == [(f"book {API}/endpoints/todos.py", "AddTodo", "AddTodo")]
    assert f"book {API}/endpoints/todos.py:AddTodo -> AddTodo (endpoint, direct)" in out
    assert found["chains"][0]["plays"][0] == "AddTodo"
    assert (code, found["plan"], found["whole"], found["only"], found["diff"]["book_files"]) == (0, "partial", False, ["AddTodo"], 1)
    assert "AWeekOfChores" in found["journeys"]


def test_an_edited_journey_class_selects_that_journey(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/journeys/clear_the_list.py", "removes everything", "takes away everything")
    code, found, out = affect(where, base, tmp_path, capsys)
    assert [(c["element"], c["kind"], c["plays"]) for c in found["chains"]] == [("ClearTheList", "journey", ["ClearTheList"])]
    assert (code, found["plan"], found["only"], found["journeys"], found["by_journey"]) == (0, "partial", [], ["ClearTheList"], ["ClearTheList"])
    assert "--journey 'ClearTheList'" in out.splitlines()[-1]


def test_an_edit_to_a_shared_book_file_makes_the_whole_book_affected_with_the_reason(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/service.py", '"8080"', '"8081"')
    code, found, out = affect(where, base, tmp_path, capsys)
    reason = f"a shared book file changed: {API}/service.py"
    assert (code, found["plan"], found["whole"], found["reason"]) == (0, "whole", True, reason)
    assert found["fallbacks"] == [{"path": f"{API}/service.py", "why": reason}]
    assert out.splitlines()[-1] == "ostler book run services.api"


def test_an_untracked_book_file_counts(repo, tmp_path, capsys):
    where, base = repo
    (where / API / "extra.py").write_text("class Extra:\n    pass\n")
    _, found, _ = affect(where, base, tmp_path, capsys)
    assert found["diff"]["book_files"] == 1
    assert (found["plan"], found["whole"]) == ("whole", True)
    assert found["reason"] == f"a shared book file changed: {API}/extra.py"


def test_a_change_outside_every_root_is_not_computed_and_the_plan_is_empty(repo, tmp_path, capsys):
    where, base = repo
    edit(where, "ruff.toml", "", "# changed\n")
    code, found, out = affect(where, base, tmp_path, capsys)
    assert out.splitlines()[1] == "plan: empty, 1 changed files select no play"
    assert (code, found["plan"], found["chains"], found["whole"]) == (1, "empty", [], False)
    assert found["diff"] == {"app_files": 0, "book_files": 0, "not_computed": {"count": 1, "paths": ["ruff.toml"]}}
    assert out.splitlines()[-1] == "nothing to play: the changed files select no play"


def test_the_not_computed_paths_are_capped_with_a_count(repo, tmp_path, capsys):
    where, base = repo
    for n in range(60):
        (where / f"note{n}.txt").write_text("x")
    _, found, _ = affect(where, base, tmp_path, capsys)
    assert found["diff"]["not_computed"]["count"] == 60
    assert len(found["diff"]["not_computed"]["paths"]) == 50


def test_no_change_at_all_gives_the_plan_none(repo, tmp_path, capsys):
    where, base = repo
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert (code, found["plan"], found["diff"]["not_computed"]["count"]) == (0, "none", 0)


def test_a_deleted_class_needs_no_play_and_a_new_one_is_a_changed_class():
    old = "import os\n\n\nclass A:\n    x = 1\n\n\nclass B:\n    y = 2\n"
    assert changed_classes("p.py", old, "import os\n\n\nclass A:\n    x = 1\n") == ([], None)
    assert changed_classes("p.py", old, old + "\n\nclass C:\n    z = 3\n") == (["C"], None)
    assert changed_classes("p.py", old, old.replace("x = 1", "x = 5")) == (["A"], None)
    assert changed_classes("p.py", None, "import os\n\n\nclass C:\n    z = 3\n") == (["C"], None)
    assert changed_classes("p.py", old, None) == ([], None)


def test_a_line_outside_every_class_or_a_file_that_does_not_parse_makes_the_whole_book_affected():
    old = "LIMIT = 1\n\n\nclass A:\n    x = 1\n"
    assert changed_classes("p.py", old, old.replace("LIMIT = 1", "LIMIT = 2")) == ([], "a shared book file changed: p.py")
    assert changed_classes("p.py", old, "class (A:\n") == ([], "a book file does not parse: p.py")


def test_run_only_with_an_empty_value_is_an_argument_error(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["run", "services.api", "--only", ""])
    assert stopped.value.code == 2
    assert "--only is empty" in capsys.readouterr().err
