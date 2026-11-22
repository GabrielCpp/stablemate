"""`ostler book affected` also reads the book's own folder, and says so when a change selects no play."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from book_fakes import commit_files, git
from ostler.book import cli
from ostler.book.bookdiff import changed_defs, pieces

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


def test_an_edit_to_a_name_no_element_uses_in_a_file_that_reads_names_dynamically_makes_the_whole_book_affected_with_the_reason(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/service.py", '"8080"', '"8081"')
    code, found, out = affect(where, base, tmp_path, capsys)
    reason = f"{API}/service.py:PORT cannot be traced: {API}/service.py reads names with getattr or globals() and can see PORT"
    assert (code, found["plan"], found["whole"], found["reason"]) == (0, "whole", True, reason)
    assert found["fallbacks"] == [{"path": f"{API}/service.py", "why": reason}]
    assert out.splitlines()[-1] == "ostler book run services.api"


def test_an_untracked_book_file_counts(repo, tmp_path, capsys):
    where, base = repo
    (where / API / "extra.py").write_text("class Extra:\n    pass\n")
    _, found, _ = affect(where, base, tmp_path, capsys)
    assert found["diff"]["book_files"] == 1
    assert found["unused"] == [f"{API}/extra.py:Extra"]
    assert found["plan"] == "empty"


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
    assert changed_defs("p.py", old, "import os\n\n\nclass A:\n    x = 1\n") == ([], [], None)
    assert changed_defs("p.py", old, old + "\n\nclass C:\n    z = 3\n") == (["C"], [], None)
    assert changed_defs("p.py", old, old.replace("x = 1", "x = 5")) == (["A"], [], None)
    assert changed_defs("p.py", None, "import os\n\n\nclass C:\n    z = 3\n") == (["C"], [], None)
    assert changed_defs("p.py", old, None) == ([], [], None)


def test_a_changed_name_is_a_changed_name_and_a_changed_bare_line_or_a_file_that_does_not_parse_makes_the_whole_book_affected():
    old = "LIMIT = 1\n\n\nclass A:\n    x = 1\n"
    assert changed_defs("p.py", old, old.replace("LIMIT = 1", "LIMIT = 2")) == ([], ["LIMIT"], None)
    assert changed_defs("p.py", old, old + "\nprint(1)\n") == ([], [], "a shared book file changed: p.py")
    assert changed_defs("p.py", old, "class (A:\n") == ([], [], "a book file does not parse: p.py")


def test_the_import_lines_and_the_docstring_of_a_modified_file_are_ignored():
    old = '"""one"""\nimport os\n\nLIMIT = 1\n'
    assert changed_defs("p.py", old, '"""two"""\nimport os\nimport sys\nfrom a import b\n\nLIMIT = 1\n') == ([], [], None)


def test_the_pieces_of_a_file_name_each_definition_form():
    text = (
        '"""doc"""\nimport os\nfrom a import b\n\n'
        "A = 1\nB: int = 2\nC, D = 3, 4\n[E, F] = 5, 6\nG = H = 7\nI: int\n\n"
        "def f():\n    return 1\n\n\nasync def g():\n    return 2\n\n\n"
        "@deco\ndef h():\n    return 3\n\n\nclass K:\n    x = 1\n\n\n"
        "J.x = 1\nL += 1\nM, *N = 1, 2\nprint(1)\nif A:\n    O = 1\n__all__ = ['A']\n"
    )
    found = pieces(text)
    assert found is not None
    assert sorted(found.names) == ["A", "B", "C", "D", "E", "F", "G", "H", "I", "__all__", "f", "g", "h"]
    assert list(found.classes) == ["K"]
    assert found.names["h"].startswith("@deco\ndef h")
    assert found.rest.splitlines() == ["J.x = 1", "L += 1", "M, *N = 1, 2", "print(1)", "if A:", "    O = 1"]
    assert pieces("class (A:\n") is None


def settle(where: Path, path: str, *edits: tuple[str, str]) -> str:
    text = (where / path).read_text()
    for old, new in edits:
        assert old in text
        text = text.replace(old, new)
    return commit_files(where, {path: text})


ADMIN = f"{API}/endpoints/admin.py"


def test_a_changed_name_used_by_one_endpoint_of_its_own_file_selects_that_endpoint(repo, tmp_path, capsys):
    where, _ = repo
    base = settle(where, ADMIN, ("from ..model import actions\n", 'from ..model import actions\n\nBELIEF = "the day the service believes it is"\n'),
                  ('"the day the service believes it is"),)', "BELIEF),)"))
    edit(where, ADMIN, '"the day the service believes it is"\n', '"the day the service thinks it is"\n')
    code, found, out = affect(where, base, tmp_path, capsys)
    assert [(c["path"], c["function"], c["element"]) for c in found["chains"]] == [(f"book {ADMIN}", "BELIEF <- used by ReadClock", "ReadClock")]
    assert (code, found["plan"], found["whole"], found["only"], found["unused"]) == (0, "partial", False, ["ReadClock"], [])
    assert f"book {ADMIN}:BELIEF <- used by ReadClock -> ReadClock (endpoint, direct)" in out


def test_a_shape_defined_in_another_file_selects_the_endpoint_that_names_it(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/endpoints/shapes.py", 'STORE = Object("Store", down=Field(Bool()))', 'STORE = Object("Store", down=Field(Bool(), does="the switch"))')
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("STORE <- used by SetStore", "SetStore")]
    assert (code, found["plan"], found["whole"], found["only"]) == (0, "partial", False, ["SetStore"])


def test_a_name_used_by_a_name_that_an_endpoint_uses_selects_the_endpoint(repo, tmp_path, capsys):
    where, _ = repo
    base = settle(where, ADMIN, ("from ..model import actions\n", 'from ..model import actions\n\nBELIEF = "the day"\nSAID = BELIEF + " the service believes it is"\n'),
                  ('"the day the service believes it is"),)', "SAID),)"))
    edit(where, ADMIN, 'BELIEF = "the day"', 'BELIEF = "today"')
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("BELIEF <- used by SAID <- used by ReadClock", "ReadClock")]
    assert (code, found["plan"], found["only"]) == (0, "partial", ["ReadClock"])


def test_a_changed_helper_function_selects_what_the_action_that_uses_it_selects(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/model/actions.py", "    due = rules.as_date(a.due_on) if a.due_on is not None else None", "    due = rules.as_date(a.due_on) if a.due_on else None")
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert {(c["function"], c["kind"]) for c in found["chains"]} == {("record <- used by AddTodo", "action"), ("record <- used by ReplaceTodo", "action")}
    assert {"AddTodo", "UpdateTodo"} <= set(found["only"])
    assert (code, found["plan"]) == (0, "partial")


def test_a_changed_name_used_by_a_record_class_makes_the_whole_book_affected(repo, tmp_path, capsys):
    where, _ = repo
    base = commit_files(where, {
        f"{API}/records.py": "LIMIT = 1\n\n\nclass Row:\n    source = ()\n    size = LIMIT\n",
        f"{API}/service.py": (where / API / "service.py").read_text().replace("from .people import ANA\n", "from .people import ANA\nfrom .records import Row\n").replace("    endpoints=ENDPOINTS,\n", "    endpoints=ENDPOINTS,\n    records=(Row,),\n"),
    })
    edit(where, f"{API}/records.py", "LIMIT = 1", "LIMIT = 2")
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert [(c["function"], c["kind"]) for c in found["chains"]] == [("LIMIT <- used by Row", "record")]
    assert (code, found["plan"], found["whole"]) == (0, "whole", True)
    assert found["reason"] == "record Row changed: the whole book"


def test_an_import_only_edit_of_a_book_file_selects_nothing(repo, tmp_path, capsys):
    where, base = repo
    edit(where, f"{API}/endpoints/todos.py", "from ..model.lists import TODOS\n", "import json\n\nfrom ..model.lists import TODOS\n")
    code, found, out = affect(where, base, tmp_path, capsys)
    assert (code, found["plan"], found["chains"], found["fallbacks"], found["unused"]) == (1, "empty", [], [], [])
    assert found["diff"]["book_files"] == 1
    assert "nothing to play: the changed files select no play" == out.splitlines()[-1]


def test_a_changed_bare_statement_still_makes_the_whole_book_affected(repo, tmp_path, capsys):
    where, base = repo
    (where / ADMIN).write_text((where / ADMIN).read_text() + "\nprint('loaded')\n")
    _, found, _ = affect(where, base, tmp_path, capsys)
    assert (found["plan"], found["reason"]) == ("whole", f"a shared book file changed: {ADMIN}")


def test_a_changed_name_nobody_mentions_is_listed_as_used_by_nothing_and_selects_nothing(repo, tmp_path, capsys):
    where, _ = repo
    base = settle(where, ADMIN, ("from ..model import actions\n", "from ..model import actions\n\nSPARE = 1\n"))
    edit(where, ADMIN, "SPARE = 1", "SPARE = 2")
    code, found, out = affect(where, base, tmp_path, capsys)
    assert (code, found["plan"], found["chains"], found["unused"]) == (1, "empty", [], [f"{ADMIN}:SPARE"])
    assert "changed and used by nothing:" in out.splitlines()
    assert f"  {ADMIN}:SPARE" in out.splitlines()


def test_a_star_import_of_the_module_of_a_changed_name_makes_the_whole_book_affected(repo, tmp_path, capsys):
    where, _ = repo
    base = commit_files(where, {
        f"{API}/endpoints/caps.py": "CAP = 1\n",
        f"{API}/endpoints/capped.py": "from .caps import *\n\n\nclass Capped:\n    size = CAP\n",
    })
    edit(where, f"{API}/endpoints/caps.py", "CAP = 1", "CAP = 2")
    _, found, _ = affect(where, base, tmp_path, capsys)
    reason = f"{API}/endpoints/caps.py:CAP cannot be traced: CAP is star-imported from services.api.endpoints.caps in {API}/endpoints/capped.py"
    assert (found["plan"], found["reason"]) == ("whole", reason)


def test_a_changed_fixture_class_used_by_one_endpoint_selects_that_endpoint(repo, tmp_path, capsys):
    where, _ = repo
    base = settle(where, ADMIN, ("from ..model import actions\n", "from ..model import actions\n\n\nclass Clock:\n    label = 'the day'\n"),
                  ('"the day the service believes it is"),)', "Clock.label),)"))
    edit(where, ADMIN, "label = 'the day'", "label = 'today'")
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert [(c["function"], c["element"]) for c in found["chains"]] == [("Clock <- used by ReadClock", "ReadClock")]
    assert (code, found["plan"], found["whole"], found["only"], found["unused"]) == (0, "partial", False, ["ReadClock"], [])


def test_a_changed_helper_class_used_by_a_journey_lands_that_journey_in_by_journey(repo, tmp_path, capsys):
    where, _ = repo
    path = f"{API}/journeys/clear_the_list.py"
    base = commit_files(where, {
        f"{API}/journeys/helper.py": "class Note:\n    text = 'one'\n",
        path: "from .helper import Note\n\n" + (where / path).read_text() + "\n\nNOTED = Note\n",
    })
    text = (where / path).read_text()
    cls = next(line for line in text.splitlines() if line.startswith("class ") and "Journey" in line)
    (where / path).write_text(text.replace(cls + "\n", cls + "\n    note = Note\n", 1))
    edit(where, f"{API}/journeys/helper.py", "'one'", "'two'")
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert [(c["kind"], c["plays"]) for c in found["chains"] if c["element"] == "ClearTheList"][0] == ("journey", ["ClearTheList"])
    assert "ClearTheList" in found["by_journey"]
    assert (code, found["plan"]) == (0, "partial")


def test_a_changed_non_element_class_mentioned_nowhere_is_unused(repo, tmp_path, capsys):
    where, _ = repo
    base = settle(where, ADMIN, ("from ..model import actions\n", "from ..model import actions\n\n\nclass Spare:\n    x = 1\n"))
    edit(where, ADMIN, "x = 1", "x = 2")
    code, found, out = affect(where, base, tmp_path, capsys)
    assert (code, found["plan"], found["chains"], found["unused"]) == (1, "empty", [], [f"{ADMIN}:Spare"])
    assert f"  {ADMIN}:Spare" in out.splitlines()


def test_a_changed_non_element_class_used_by_a_record_class_makes_the_whole_book_affected(repo, tmp_path, capsys):
    where, _ = repo
    base = commit_files(where, {
        f"{API}/records.py": "class Size:\n    n = 1\n\n\nclass Row:\n    source = ()\n    size = Size\n",
        f"{API}/service.py": (where / API / "service.py").read_text().replace("from .people import ANA\n", "from .people import ANA\nfrom .records import Row\n").replace("    endpoints=ENDPOINTS,\n", "    endpoints=ENDPOINTS,\n    records=(Row,),\n"),
    })
    edit(where, f"{API}/records.py", "n = 1", "n = 2")
    code, found, _ = affect(where, base, tmp_path, capsys)
    assert [(c["function"], c["kind"]) for c in found["chains"]] == [("Size <- used by Row", "record")]
    assert (code, found["plan"], found["reason"]) == (0, "whole", "record Row changed: the whole book")


def test_run_only_with_an_empty_value_is_an_argument_error(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["run", "services.api", "--only", ""])
    assert stopped.value.code == 2
    assert "--only is empty" in capsys.readouterr().err


def test_a_change_in_another_book_of_a_namespaced_root_is_absent_from_the_diff_of_this_one(tmp_path, monkeypatch):
    from ostler._vendor.stablemate_core import config as cfgmod
    from ostler.book import bookdiff
    from ostler.book.change import Reading

    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(bookdiff, "index_of", lambda service: {})
    for name in ("api", "web"):
        (tmp_path / "services/acme" / name).mkdir(parents=True)
        (tmp_path / "services/acme" / name / "service.py").write_text("")
        (tmp_path / "services/acme" / name / "notes.py").write_text("x = 1\n")
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "--short", "HEAD").strip()
    (tmp_path / "services/acme/api/notes.py").write_text("x = 2\n")
    (tmp_path / "services/acme/web/notes.py").write_text("x = 3\n")
    found = bookdiff.book_diff(cast(Any, None), tmp_path, "services.acme.api", Reading(base=base))
    assert found.files == ["services/acme/api/notes.py"]
