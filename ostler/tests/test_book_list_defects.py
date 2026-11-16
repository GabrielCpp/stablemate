"""Entry rules on the list an app answers, and a known defect that names the rule a list breaks."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Iterator, cast

import pytest

from book_todo import FIXTURE, module, run_book
from ostler.book import Action, Answer, BookError, Defect, Endpoint, Field, List, Object, Rule, Str
from ostler.book.check import defect_faults
from ostler.book.entries import has, in_order, no_repeat
from ostler.book.http import apart, breaches
from ostler.book.search import defect_lines

DEFECT = '''    rules = (rules.unknown_status,)
    defects = (Defect("a blank todo heads the list", lambda a, s, by: a.text is None and a.assignee is None and a.status is None,
                      breaks=HAS_TITLE, why="The list starts with an entry nobody wrote."),)
'''


def _server(bug: str | None) -> Iterator:
    server = module("app").TodoServer(bug=bug).start()
    yield server
    server.stop()


@pytest.fixture
def blank_app() -> Iterator:
    yield from _server("blank")


@pytest.fixture
def stranger_app() -> Iterator:
    yield from _server("stranger")


@pytest.fixture
def repeating_app() -> Iterator:
    yield from _server("repeat")


@pytest.fixture
def offshape_app() -> Iterator:
    yield from _server("offshape")


@pytest.fixture
def ghost_app() -> Iterator:
    yield from _server("ghost")


@pytest.fixture
def drifting_app() -> Iterator:
    yield from _server("ghost_drift")


@pytest.fixture
def clean_app() -> Iterator:
    yield from _server(None)


def _declared(tmp_path: Path, breaks: str = "HAS_TITLE", repeat: bool = True) -> Path:
    book = tmp_path / "book"
    book.mkdir()
    shutil.copytree(FIXTURE / "services", book / "services")
    actions = book / "services" / "api" / "model" / "actions.py"
    text = actions.read_text()
    text = text.replace("from ostler.book import Action,", "from ostler.book import Action, Defect,")
    text = text.replace("from .state import", f"from .lists import {breaks}\nfrom .state import")
    old = "    accept = Query\n    rules = (rules.unknown_status,)\n"
    assert old in text
    actions.write_text(text.replace(old, "    accept = Query\n" + DEFECT.replace("HAS_TITLE", breaks)))
    lists = book / "services" / "api" / "model" / "lists.py"
    stated = lists.read_text()
    if not repeat:
        stated = stated.replace("TODOS = (HAS_ID, HAS_TITLE, ONCE)", "TODOS = (HAS_ID, HAS_TITLE)")
    stated = stated.replace("import has, no_repeat", "import has, in_order, no_repeat")
    lists.write_text(stated + 'UNSTATED = in_order("id")\n')
    return book


@pytest.fixture
def declared(tmp_path: Path) -> Path:
    return _declared(tmp_path)


@pytest.fixture
def ghosted(tmp_path: Path) -> Path:
    return _declared(tmp_path, repeat=False)


@pytest.fixture
def unstated(tmp_path: Path) -> Path:
    return _declared(tmp_path, breaks="UNSTATED")


def _run(cwd: Path, port: int, out: Path):
    return run_book(["run", "services.api", "--no-stack", "--out", str(out)], port, cwd)


def test_has_holds_when_every_entry_has_a_value():
    assert has("id")([{"id": "a"}, {"id": 0}, {"id": False}]) == []


@pytest.mark.parametrize("entry", [{}, {"id": None}, {"id": ""}, {"id": []}, {"id": {}}])
def test_has_breaks_on_a_missing_null_or_empty_value(entry):
    assert has("id")([{"id": "a"}, entry]) == [f"entry 1 has no id: {entry!r}"]


def test_has_reads_a_dotted_path():
    rule = has("owner.name")
    assert rule([{"owner": {"name": "ana"}}]) == []
    assert rule([{"owner": {}}, {"owner": None}]) == ["entry 0 has no owner.name: {'owner': {}}", "entry 1 has no owner.name: {'owner': None}"]


def test_has_cuts_the_entry_it_names_at_120_characters():
    said = has("id")([{"note": "x" * 300}])[0]
    assert said.startswith("entry 0 has no id: {'note': 'xxx")
    assert len(said.split(": ", 1)[1]) <= 123


def test_has_says_what_every_entry_has_in_its_first_docstring_line():
    assert (has("id").__doc__ or "").splitlines()[0] == "every entry has id"


def test_a_list_refuses_a_rule_with_no_docstring():
    def bare(entries):
        return []

    with pytest.raises(BookError, match="no docstring"):
        List(Str(), entries=(bare,))


def test_a_list_refuses_one_bare_rule():
    with pytest.raises(BookError, match="takes a tuple of rules"):
        List(Str(), entries=cast(Any, has("id")))


def test_a_list_describes_the_rules_it_states():
    assert List(Str(), entries=(has("id"), no_repeat("id"))).describe() == "[string] (every entry has id, no repeat of id)"


def test_a_list_nested_in_an_object_is_judged_at_its_path():
    row = Object("Row", id=Field(Str()))
    page = Object("Page", rows=Field(List(row, entries=(has("id"),))))
    found = breaches(page, {"rows": [{"id": "a"}, {"id": ""}]})
    assert [(path, said) for path, _, said in found] == [("rows[]", "entry 1 has no id: {'id': ''}")]


def test_a_list_that_keeps_its_rules_is_not_judged_broken():
    row = Object("Row", id=Field(Str()))
    assert breaches(List(row, entries=(has("id"),)), [{"id": "a"}]) == []


def test_a_book_with_no_rules_judges_nothing():
    row = Object("Row", id=Field(Str()))
    assert breaches(List(row), [{"id": ""}]) == []


def test_a_list_that_breaks_a_rule_fails_the_step_and_names_the_endpoint_the_path_and_the_entry(blank_app, tmp_path):
    done = _run(FIXTURE, blank_app.port, tmp_path / "out")
    assert done.returncode == 3, done.stdout
    assert "FindTodos answers a list that breaks every entry has title at []: entry 0 has no title" in done.stdout


def test_a_rule_judges_an_entry_whose_id_the_book_never_learned(stranger_app, tmp_path):
    done = _run(FIXTURE, stranger_app.port, tmp_path / "out")
    assert done.returncode == 3, done.stdout
    assert "FindTodos answers a list that breaks every entry has title at []" in done.stdout


def test_a_list_that_keeps_its_rules_passes_the_run(clean_app, tmp_path):
    done = _run(FIXTURE, clean_app.port, tmp_path / "out")
    assert done.returncode == 0, done.stdout
    assert "5 pass, 0 known defects, 0 fail" in done.stdout


def test_a_defect_that_names_the_broken_rule_makes_the_step_known(declared, blank_app, tmp_path):
    done = _run(declared, blank_app.port, tmp_path / "out")
    assert done.returncode == 0, done.stdout
    assert "KNOWN  AWeekOfChores" in done.stdout
    assert "## Known defects" in done.stdout
    assert "breaks every entry has title: a blank todo heads the list (FindTodos)." in done.stdout.split("## Known defects", 1)[1]


def test_a_broken_rule_no_defect_names_still_fails_beside_a_declared_defect(declared, repeating_app, tmp_path):
    done = _run(declared, repeating_app.port, tmp_path / "out")
    assert done.returncode == 3, done.stdout
    assert "FindTodos answers a list that breaks no repeat of id" in done.stdout


def test_a_declared_defect_the_app_no_longer_shows_is_never_met_and_fails_the_run(declared, clean_app, tmp_path):
    done = _run(declared, clean_app.port, tmp_path / "out")
    assert done.returncode == 1, done.stdout
    assert "## Known defects never met (fails the run)" in done.stdout
    assert "a blank todo heads the list" in done.stdout.split("never met", 1)[1]


def _rule() -> Rule:
    return Rule("no", lambda a, s, by: False)


def test_breaks_with_over_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="breaks"):
        Defect("x", lambda a, s, by: True, breaks=has("id"), over=_rule())


def test_breaks_with_does_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="breaks"):
        Defect("x", lambda a, s, by: True, breaks=has("id"), does=lambda a, s, by: None)


def test_breaks_with_a_status_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="status"):
        Defect("x", lambda a, s, by: True, breaks=has("id"), status=404)


def test_breaks_with_a_rule_that_has_no_docstring_is_refused():
    def bare(entries):
        return []

    with pytest.raises(BookError, match="docstring"):
        Defect("x", lambda a, s, by: True, breaks=bare)


def _action() -> type[Action]:
    class Lister(Action):
        defects = (Defect("a blank asset heads the list", lambda a, s, by: True, breaks=has("id"), why="since the import"),)

    return Lister


def test_explain_shows_the_rule_a_known_defect_breaks():
    assert "  known defect: breaks every entry has id: 'a blank asset heads the list'" in _action().explain()


def test_an_endpoint_describe_shows_the_defect_of_its_action_and_the_rules_of_its_list():
    class Lists(Endpoint):
        path = "/things"
        answers = (Answer(200, List(Str(), entries=(has("id"),)), "the things"),)
        carries = _action()

    shown = Lists.describe()
    assert "[string] (every entry has id)" in shown
    assert "known defect: breaks every entry has id: 'a blank asset heads the list'" in shown


def test_search_shows_the_rule_a_known_defect_breaks():
    (head, *rest) = defect_lines(_action().defects[0])
    assert head == "breaks every entry has id: a blank asset heads the list"
    assert rest == ["why: since the import"]


def test_an_entry_off_the_shape_that_breaks_a_rule_alone_is_the_defects_and_makes_the_step_known(declared, offshape_app, tmp_path):
    done = _run(declared, offshape_app.port, tmp_path / "out")
    assert done.returncode == 0, done.stdout
    assert "KNOWN  AWeekOfChores" in done.stdout
    assert "answered outside the book" not in done.stdout


def test_an_entry_off_the_shape_fails_as_off_shape_when_no_defect_is_declared(offshape_app, tmp_path):
    done = _run(FIXTURE, offshape_app.port, tmp_path / "out")
    assert done.returncode == 3, done.stdout
    assert "answered outside the book" in done.stdout


def test_an_entry_that_breaks_the_rule_alone_is_left_out_of_the_comparison(ghosted, ghost_app, tmp_path):
    done = _run(ghosted, ghost_app.port, tmp_path / "out")
    assert done.returncode == 0, done.stdout
    assert "KNOWN  AWeekOfChores" in done.stdout


def test_the_entries_beside_the_one_left_out_are_still_compared(ghosted, drifting_app, tmp_path):
    done = _run(ghosted, drifting_app.port, tmp_path / "out")
    assert done.returncode == 3, done.stdout
    assert "drifted" in done.stdout


def _rows() -> Object:
    return Object("Row", id=Field(Str()))


def test_an_order_rule_broken_under_a_defect_leaves_every_entry_in_the_comparison():
    ordered = in_order("id")
    page = List(_rows(), entries=(ordered,))
    entries = [{"id": "b"}, {"id": "a"}, {"id": "c"}]
    assert ordered(entries)
    assert apart(page, entries, (ordered,)) == entries


def test_apart_leaves_out_only_the_entries_that_break_the_rule_alone_at_any_depth():
    titled = has("id")
    page = Object("Page", rows=Field(List(_rows(), entries=(titled,))))
    held = apart(page, {"rows": [{"id": "a"}, {"id": ""}, {"id": "b"}]}, (titled,))
    assert held == {"rows": [{"id": "a"}, {"id": "b"}]}


def test_apart_leaves_every_entry_when_no_rule_is_owed():
    titled = has("id")
    entries = [{"id": ""}]
    assert apart(List(_rows(), entries=(titled,)), entries, ()) == entries


def _checked(book: Path, port: int):
    run_book(["check", "services.api"], port, book)
    return run_book(["check", "services.api"], port, book)


def test_check_refuses_a_defect_whose_rule_no_list_of_its_actions_answers_states(unstated, clean_app):
    done = _checked(unstated, clean_app.port)
    assert done.returncode != 0, done.stdout
    assert "FindTodos" in done.stdout
    assert "a blank todo heads the list" in done.stdout
    assert "in order of id" in done.stdout


def test_check_accepts_a_defect_whose_rule_is_stated_in_a_list(declared, clean_app):
    done = _checked(declared, clean_app.port)
    assert "a blank todo heads the list" not in done.stdout
    assert done.returncode == 0, done.stdout


def test_check_accepts_a_defect_whose_rule_is_stated_in_a_nested_list():
    titled = has("id")

    class Lister(Action):
        defects = (Defect("a blank row", lambda a, s, by: True, breaks=titled),)

    class Nested(Endpoint):
        path = "/things"
        answers = (Answer(200, Object("Page", rows=Field(List(_rows(), entries=(titled,)))), "the things"),)
        carries = Lister

    class Other(Endpoint):
        path = "/others"
        answers = (Answer(200, List(_rows(), entries=(in_order("id"),)), "the others"),)
        carries = Lister

    class Service:
        endpoints = [Nested, Other]

    assert defect_faults(cast(Any, Service)) == []


def test_check_names_the_action_the_defect_and_the_rule_of_a_defect_no_list_states():
    titled = has("id")

    class Lister(Action):
        defects = (Defect("a blank row", lambda a, s, by: True, breaks=titled),)

    class Plain(Endpoint):
        path = "/things"
        answers = (Answer(200, List(_rows(), entries=(in_order("id"),)), "the things"),)
        carries = Lister

    class Service:
        endpoints = [Plain]

    (found,) = defect_faults(cast(Any, Service))
    assert found.blocks
    assert "Lister" in str(found) and "a blank row" in str(found) and "every entry has id" in str(found)
