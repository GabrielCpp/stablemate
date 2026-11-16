"""The rules over every entry of a list, and the picked entry: the pure rules, a pick judged in a page, the fixture web book and the check."""

from __future__ import annotations

import dataclasses
import functools
import tempfile
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, cast

import pytest

from book_todo import module
from ostler.book import BookError, Browser, Screen, T
from ostler.book.entries import in_order, no_repeat
from ostler.book.screen import Lists, Select


def _said(rule) -> str:
    return (rule.__doc__ or "").splitlines()[0]


def test_in_order_holds_on_entries_that_ascend():
    assert in_order()(["ana", "bo", "bo", "cy"]) == []


def test_in_order_names_the_first_entry_that_comes_before_the_one_ahead_of_it():
    assert in_order()(["ana", "cy", "bo", "ab"]) == ["'bo' comes after 'cy'"]


def test_in_order_of_a_callable_judges_the_key_it_returns():
    def length(entry):
        return len(entry)

    assert in_order(length)(["a", "bb", "ccc"]) == []
    assert in_order(length)(["a", "ccc", "bb"]) == ["'bb' comes after 'ccc'"]
    assert _said(in_order(length)) == "in order of length"


def test_in_order_of_a_field_path_reads_dict_entries():
    rule = in_order("owner.name")
    assert rule([{"owner": {"name": "ana"}}, {"owner": {"name": "bo"}}]) == []
    assert rule([{"owner": {"name": "bo"}}, {"owner": {"name": "ana"}}]) == [
        "{'owner': {'name': 'ana'}} comes after {'owner': {'name': 'bo'}}"]
    assert _said(rule) == "in order of owner.name"


def test_in_order_with_no_key_says_in_order_alone():
    assert _said(in_order()) == "in order"


def test_no_repeat_names_a_repeated_entry_once():
    assert no_repeat()(["ana", "bo", "ana", "ana", "bo"]) == ["'ana' is shown 3 times", "'bo' is shown 2 times"]
    assert no_repeat()(["ana", "bo"]) == []


def test_no_repeat_of_a_field_path_names_the_repeated_value():
    rule = no_repeat("tag")
    assert rule([{"tag": "a"}, {"tag": "b"}, {"tag": "a"}]) == ["'a' is shown 2 times"]
    assert _said(rule) == "no repeat of tag"


def test_a_rule_with_no_docstring_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="the entries rule .* has no docstring"):
        Lists(entries=(lambda entries: [],))


def test_entries_given_one_rule_instead_of_a_tuple_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="entries takes a tuple of rules, not one rule"):
        Lists(entries=cast(Any, in_order()))


def test_a_list_that_states_only_its_entries_or_only_its_picked_entry_states_something():
    assert Lists(entries=(in_order(),)).entries
    assert Lists(picked="Anyone").picked == "Anyone"


def test_a_picked_function_with_no_docstring_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="the picked function .* has no docstring"):
        Lists(picked=lambda model, by: "Anyone")


def test_the_description_of_a_screen_shows_the_rules_and_the_picked_entry():
    class Owners(Screen):
        who = Select("who", T(en="Who", fr="Qui"), "filters by owner",
                     lists=Lists(head=(T(en="Anyone", fr="Tous"),), entries=(in_order(), no_repeat("name")), picked=T(en="Anyone", fr="Tous")))

    assert "lists: 'Anyone'; entries in order, no repeat of name; picked 'Anyone'" in Owners.describe("en")
    assert "lists: 'Tous'; entries in order, no repeat of name; picked 'Tous'" in Owners.describe("fr")


def test_the_description_shows_a_picked_function_by_its_docstring():
    def first(model, by):
        """the first user of the model"""
        return "ana"

    class Owners(Screen):
        who = Select("who", "Who", lists=Lists(picked=first))

    assert "lists: picked the first user of the model" in Owners.describe("en")


class Native(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), entries=(in_order(), no_repeat()), picked="Anyone"))


class Ordered(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), entries=(in_order(),)))


class Single(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), entries=(no_repeat(),)))


class Preset(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), picked="Anyone"))


def _first_of_the_model(model, by):
    """the entry the model selects"""
    return "bo"


class Modelled(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), picked=_first_of_the_model))


def _native(entries: list[str]) -> str:
    options = "".join(f'<option value="{e}">{e}</option>' for e in entries)
    return ('<!doctype html><html><body><select id="who" data-testid="who"><option value="">Anyone</option>' + options + "</select>"
            "<script>const p = new URLSearchParams(location.search).get('pre'); if (p) document.getElementById('who').value = p;</script>"
            "</body></html>")


def _popup(entries: list[str]) -> str:
    options = "".join(f'<li role="option" data-value="{e}">{e}</li>' for e in entries)
    return (
        '<!doctype html><html><body>'
        '<button id="who" data-testid="who" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-controls="lb">Anyone</button>'
        '<ul id="lb" role="listbox" hidden><li role="option" data-value="" aria-selected="true">Anyone</li>' + options + "</ul>"
        "<script>"
        "const box = document.getElementById('who'), lb = document.getElementById('lb');"
        "const shut = () => { lb.hidden = true; box.setAttribute('aria-expanded', 'false'); };"
        "const pre = new URLSearchParams(location.search).get('pre');"
        "for (const li of lb.querySelectorAll('li')) {"
        "  if (pre !== null) li.setAttribute('aria-selected', li.textContent === pre ? 'true' : 'false');"
        "  li.addEventListener('click', () => { for (const o of lb.querySelectorAll('li')) o.setAttribute('aria-selected', o === li ? 'true' : 'false');"
        "    box.textContent = li.textContent; shut(); });"
        "}"
        "box.addEventListener('click', () => { lb.hidden = false; box.setAttribute('aria-expanded', 'true'); });"
        "document.addEventListener('keydown', (e) => { if (e.key === 'Escape') shut(); });"
        "</script></body></html>")


@contextmanager
def _page(entries: list[str], screen: type[Screen], popup: bool = False) -> Iterator[Browser]:
    with tempfile.TemporaryDirectory() as root:
        (Path(root) / "index.html").write_text((_popup if popup else _native)(entries))
        server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=root))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with _opened(server, screen) as found:
            yield found


@contextmanager
def _opened(server: ThreadingHTTPServer, screen: type[Screen]) -> Iterator[Browser]:
    found = Browser(f"http://127.0.0.1:{server.server_address[1]}", "en", lang_query=None)
    found.feeding((screen,))
    found.start()
    try:
        found.open("/")
        yield found
    finally:
        found.stop()
        server.shutdown()
        server.server_close()


def test_a_pick_passes_when_the_entries_are_in_order():
    with _page(["ana", "bo", "cy"], Ordered) as browser:
        browser.fill(Ordered.who, "bo")
        assert browser.list_faults() == []
        assert browser.lists_read() == {"Ordered.who"}


def test_a_pick_fails_when_the_app_leaves_the_entries_unsorted():
    with _page(["ana", "cy", "bo"], Ordered) as browser:
        browser.fill(Ordered.who, "bo")
        assert browser.list_faults() == ["the list Ordered.who breaks \"in order\": 'bo' comes after 'cy'"]


def test_a_pick_passes_when_no_entry_is_repeated():
    with _page(["ana", "bo"], Single) as browser:
        browser.fill(Single.who, "bo")
        assert browser.list_faults() == []


def test_a_pick_fails_when_a_user_is_listed_twice():
    with _page(["ana", "bo", "ana"], Single) as browser:
        browser.fill(Single.who, "bo")
        assert browser.list_faults() == ["the list Single.who breaks \"no repeat\": 'ana' is shown 2 times"]


def test_the_head_is_left_out_of_the_entries_a_rule_judges():
    with _page(["ana", "bo"], Native) as browser:
        browser.fill(Native.who, "bo")
        assert browser.list_faults() == []


def test_picked_passes_when_the_head_is_selected_first():
    with _page(["ana", "bo"], Preset) as browser:
        browser.fill(Preset.who, "bo")
        assert browser.list_faults() == []


def test_picked_fails_when_the_app_preselects_another_entry():
    with _page(["ana", "bo"], Preset) as browser:
        browser.open("/?pre=ana")
        browser.fill(Preset.who, "bo")
        assert browser.list_faults() == ["the list Preset.who has 'ana' selected before the pick, the book says 'Anyone'"]


def test_picked_is_judged_on_the_first_pick_after_a_load_and_not_on_a_second_pick_of_the_same_list():
    with _page(["ana", "bo"], Preset) as browser:
        browser.fill(Preset.who, "ana")
        browser.fill(Preset.who, "bo")
        assert browser.list_faults() == []


def test_picked_is_judged_again_after_the_page_loads_again():
    with _page(["ana", "bo"], Preset) as browser:
        browser.fill(Preset.who, "ana")
        browser.open("/?pre=bo")
        browser.fill(Preset.who, "ana")
        assert browser.list_faults() == ["the list Preset.who has 'bo' selected before the pick, the book says 'Anyone'"]


def test_picked_is_judged_against_what_the_model_said_before_the_step():
    with _page(["ana", "bo"], Modelled) as browser:
        browser.expecting({"Modelled.who": ([], [], "bo")})
        browser.fill(Modelled.who, "ana")
        assert browser.list_faults() == ["the list Modelled.who has 'Anyone' selected before the pick, the book says 'bo'"]
        assert browser.claims_judged() == {"Modelled.who": frozenset({"picked"})}


def test_a_picked_function_is_not_judged_on_a_pick_outside_a_step():
    with _page(["ana", "bo"], Modelled) as browser:
        browser.fill(Modelled.who, "ana")
        assert browser.list_faults() == []
        assert browser.claims_judged() == {"Modelled.who": frozenset()}


def test_a_rule_is_judged_on_a_popup_list_too():
    with _page(["ana", "cy", "bo", "bo"], Native, popup=True) as browser:
        browser.fill(Native.who, "bo")
        assert browser.list_faults() == [
            "the list Native.who breaks \"in order\": 'bo' comes after 'cy'",
            "the list Native.who breaks \"no repeat\": 'bo' is shown 2 times"]


def test_picked_is_judged_on_a_popup_list_from_the_option_marked_selected():
    with _page(["ana", "bo"], Preset, popup=True) as browser:
        browser.fill(Preset.who, "bo")
        assert browser.list_faults() == []
        browser.open("/?pre=ana")
        browser.fill(Preset.who, "bo")
        assert browser.list_faults() == ["the list Preset.who has 'ana' selected before the pick, the book says 'Anyone'"]


def test_the_account_of_a_run_says_which_claims_a_pick_judged():
    from ostler.book.listing import account

    class Both(Screen):
        who = Select("who", "Who", lists=Lists(head=("Anyone",), entries=(in_order(),), picked="Anyone"))

    with _page(["ana", "bo"], Both) as browser:
        browser.fill(Both.who, "bo")
        assert browser.claims_judged() == {"Both.who": frozenset({"entries", "picked"})}
        assert "- Both.who: entries, picked" in account((Both,), browser.lists_read(), browser.claims_judged())


def _run(bug: str | None, tmp_path: Path, journey: str):
    from test_book_web import _run as played, _stack, _stop

    stack = _stack(bug)
    try:
        return played(stack, tmp_path, journey)
    finally:
        _stop(stack)


def test_the_fixture_web_book_is_green_on_the_correct_app_with_its_rules_stated(tmp_path: Path):
    done = _run(None, tmp_path, "AWeekOfChores")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "ListPage.assignee: derived, always, entries" in done.stdout
    assert "AddForm.assignee: derived, entries, picked" in done.stdout


def test_a_user_listed_twice_turns_the_run_red_at_the_step_that_picks_in_the_list(tmp_path: Path):
    done = _run("duplicate-user", tmp_path, "AWeekOfChores")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the list AddForm.assignee breaks \"no repeat\": 'ana' is shown 2 times" in done.stdout
    assert "FAIL  AWeekOfChores" in done.stdout


def test_users_left_unsorted_turn_the_run_red_at_the_step_that_picks_in_the_list(tmp_path: Path):
    done = _run("unsorted-users", tmp_path, "AWeekOfChores")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the list AddForm.assignee breaks \"in order\": " in done.stdout


def test_a_select_that_preselects_the_first_user_turns_the_run_red_at_the_step_that_picks_in_the_list(tmp_path: Path):
    done = _run("preselect-user", tmp_path, "AWeekOfChores")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the list AddForm.assignee has " in done.stdout and "selected before the pick, the book says 'Nobody'" in done.stdout


def _bare(**components):
    service = module("services.web.service").service
    screen = type("Bare", (Screen,), components)
    return dataclasses.replace(service, screens=(screen,))


def test_the_check_notes_a_select_with_a_shape_and_no_claim_and_does_not_fail_on_it(capsys: pytest.CaptureFixture[str]):
    from ostler.book import Str
    from ostler.book.check import report, unstated_lists
    from ostler.book.http import Field as Wire

    found = unstated_lists(_bare(size=Select(None, "Size", takes="size", holds=Wire(Str()))))
    assert [(f.name, f.blocks, f.told) for f in found] == [("screen Bare.size", False, True)]
    report(found)
    out = capsys.readouterr().out
    assert "NOTE   screen Bare.size: nothing states what its list holds" in out
    assert "check: 0 findings, 1 note" in out
    assert not any(not f.told for f in found)


def test_a_select_with_a_shape_and_its_options_or_its_list_gets_no_note():
    from ostler.book import Str
    from ostler.book.check import unstated_lists
    from ostler.book.http import Field as Wire

    shape = Wire(Str())
    assert unstated_lists(_bare(a=Select(None, "A", takes="a", holds=shape, options=("x",)),
                                b=Select(None, "B", takes="b", holds=shape, lists=Lists(entries=(in_order(),))))) == []


def test_a_select_with_no_shape_and_no_claim_keeps_its_one_blocking_finding_and_gets_no_note():
    from ostler.book.check import shape_faults, unstated_lists

    service = _bare(who=Select(None, "Who"))
    assert unstated_lists(service) == []
    assert [(f.name, f.blocks, f.told) for f in shape_faults(service)] == [("screen Bare.who", True, False)]
