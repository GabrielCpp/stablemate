"""How a person moves between screens: the entries, edges, arrivals and chains the book states, what the check says of them, and what `explain` and `search` print."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from book_todo import module
from ostler.book import Action, Interaction, Phase, Screen, Transition, When
from ostler.book.affected import calls_of
from ostler.book.check import move_faults, move_notes
from ostler.book.domain import State
from ostler.book.reach import arrivals, chain, described, edges, entries, route_text, unreached
from ostler.book.screen import Button, Text
from ostler.book.search import cmd_explain, cmd_search, items

from test_book_web import _service


class Nudge(Action[None, State]):
    pass


shown = Phase("shown", because="the list has rows")
idle = Phase("idle")
save = Button("save", "Save", "keeps the draft")
page = Text("page-root")


class Home(Screen):
    route = "/"
    first = True


class Listing(Screen):
    route = "/list"
    phases = (idle, shown)
    transitions = (Transition(idle, When("200"), shown, then="rows replaced"),)
    save = save
    draft = Button("draft", "Draft", "opens the draft dialog")


class Detail(Screen):
    root = page


class Dialog(Screen):
    root = Text("dialog-root")
    inside = Listing
    shown_in = shown
    save = save


class Island(Screen):
    route = "/island"


class OpenList(Interaction[None]):
    screen = Home
    leads_to = Listing
    does = "follows the list link"


class OpenDetail(Interaction[None]):
    screen = Home
    leads_to = Detail
    does = "follows the detail link"


class ListToDetail(Interaction[None]):
    screen = Listing
    leads_to = Detail
    does = "presses a row"


class DetailToHome(Interaction[None]):
    screen = Detail
    leads_to = Home
    does = "follows the home link"


class Stay(Interaction[None]):
    screen = Listing
    does = "filters the list"


class Deep(Interaction[None]):
    leads_to = Island
    does = "opens a deep link"
    carries = Nudge


class OpenDialog(Interaction[None]):
    screen = Listing
    leads_to = Dialog
    does = "presses the draft button"


def _book(*screens: type[Screen], interactions: tuple[type[Interaction[Any]], ...] = ()) -> Any:
    return replace(_service(*screens, languages=("en",)), new_model=State, interactions=interactions)


BOOK = (Home, Listing, Detail, Dialog, Island)
MOVES = (OpenList, OpenDetail, ListToDetail, DetailToHome, Stay, Deep)


def test_the_entries_are_the_first_screens_then_the_targets_of_an_interaction_outside_the_screens():
    assert entries(_book(*BOOK, interactions=MOVES)) == [Home, Island]


def test_an_edge_is_an_interaction_that_starts_on_a_screen_and_leads_to_one():
    assert edges(_book(*BOOK, interactions=MOVES)) == [(Home, OpenList, Listing), (Home, OpenDetail, Detail),
                                                      (Listing, ListToDetail, Detail), (Detail, DetailToHome, Home)]


def test_the_arrivals_at_a_screen_are_the_interactions_that_lead_to_it():
    service = _book(*BOOK, interactions=MOVES)
    assert arrivals(service, Detail) == [OpenDetail, ListToDetail]
    assert arrivals(service, Island) == [Deep]
    assert arrivals(service, Dialog) == []


def test_the_chain_is_the_shortest_and_a_tie_goes_to_the_interaction_declared_first():
    service = _book(*BOOK, interactions=MOVES)
    assert chain(service, Home) == []
    assert chain(service, Listing) == [OpenList]
    assert chain(service, Detail) == [OpenDetail]
    assert chain(_book(*BOOK, interactions=(ListToDetail, OpenList, OpenDetail)), Detail) == [OpenDetail]
    assert chain(_book(*BOOK, interactions=(OpenList, ListToDetail, OpenDetail)), Detail) == [OpenDetail]


def test_a_longer_walk_is_taken_when_no_shorter_one_exists():
    service = _book(*BOOK, interactions=(OpenList, ListToDetail))
    assert chain(service, Detail) == [OpenList, ListToDetail]


def test_an_interaction_that_leads_to_an_embedded_screen_is_an_arrival_on_it():
    service = _book(*BOOK, interactions=(*MOVES, OpenDialog))
    assert arrivals(service, Dialog) == [OpenDialog]
    assert _faults(*BOOK, interactions=(*MOVES, OpenDialog)) == []
    assert chain(service, Dialog) == [OpenList]
    assert "reached by: OpenDialog on Listing\nhosted by: Listing\nshown in: shown\n" in described(service, Dialog, "en")


def test_a_screen_a_host_holds_is_reached_by_the_chain_to_its_host():
    service = _book(*BOOK, interactions=MOVES)
    assert chain(service, Dialog) == chain(service, Listing) == [OpenList]


def test_a_screen_no_walk_reaches_is_unreached_and_has_no_chain():
    service = _book(*BOOK, interactions=(OpenList,))
    assert unreached(service) == [Detail, Island]
    assert chain(service, Detail) is None
    assert unreached(_book(*BOOK, interactions=MOVES)) == []


def test_the_route_reads_as_the_interactions_with_their_screens():
    service = _book(*BOOK, interactions=(OpenList, ListToDetail, Deep))
    assert route_text(service, Detail) == "OpenList on Home then ListToDetail on Listing"
    assert route_text(service, Home) == "an entry"
    assert route_text(service, Island) == "an entry"
    assert route_text(_book(*BOOK), Detail) == "no walk reaches it"


def _faults(*screens: type[Screen], interactions: tuple[type[Interaction[Any]], ...] = ()) -> list[str]:
    return [str(f) for f in move_faults(_book(*screens, interactions=interactions))]


def test_a_leads_to_that_is_no_screen_of_the_book_is_refused():
    assert _faults(Home, interactions=(OpenList,)) == ["interaction OpenList: leads to Listing, which is not a screen of this book"]


def test_an_inside_that_is_no_screen_of_the_book_or_is_itself_is_refused():
    class Orphan(Screen):
        inside = Listing

    class Loop(Screen):
        pass

    Loop.inside = Loop
    assert _faults(Home, Orphan, Loop) == ["screen Orphan: is inside Listing, which is not a screen of this book",
                                           "screen Loop: is inside itself: `inside` names the screen that hosts it"]


def test_a_shown_in_that_is_no_phase_of_the_host_or_has_no_inside_is_refused():
    class Elsewhere(Screen):
        inside = Listing
        shown_in = Phase("other")

    class Alone(Screen):
        shown_in = shown

    assert _faults(Home, Listing, Elsewhere, Alone) == [
        "screen Elsewhere: is shown in other, which is not a phase of Listing",
        "screen Alone: states `shown_in` and no `inside`: name the screen that hosts it"]


def test_a_book_with_screens_and_no_first_screen_is_refused():
    assert _faults(Listing, Detail) == ["screens: no screen is first: mark the screen a person can open directly"]
    assert _faults() == []


def test_a_well_formed_book_has_no_refusal():
    assert _faults(*BOOK, interactions=MOVES) == []


def test_a_screen_no_walk_reaches_is_told_and_does_not_block():
    found = move_notes(_book(*BOOK, interactions=(OpenList,)))
    assert [(str(f), f.blocks, f.told) for f in found if f.name == "screen Detail"] == [
        ("screen Detail: nothing leads to it: state `leads_to` on the interaction that opens it, `inside` when another screen hosts it, "
         "or `first` when a person opens it directly", False, True)]


def test_a_screen_an_interaction_leads_to_with_no_route_and_no_root_is_told():
    class Bare(Screen):
        pass

    class ToBare(Interaction[None]):
        screen = Home
        leads_to = Bare
        does = "follows a link"

    found = move_notes(_book(Home, Bare, interactions=(ToBare,)))
    assert [(str(f), f.blocks) for f in found] == [
        ("screen Bare: an interaction leads to it and it states neither `route` nor `root`, so an arrival on it could not be recognised", False)]
    assert move_notes(_book(*BOOK, interactions=MOVES)) == []


def test_the_calls_of_a_screen_are_the_interactions_on_it_and_the_arrivals_at_it():
    service = _book(*BOOK, interactions=MOVES)
    assert calls_of(service, Detail, "screen") == {"DetailToHome", "OpenDetail", "ListToDetail"}
    assert calls_of(service, Listing, "screen") == {"ListToDetail", "Stay", "OpenList"}


def test_an_embedded_screen_with_no_interaction_and_no_arrival_reaches_no_call():
    assert calls_of(_book(*BOOK, interactions=MOVES), Dialog, "screen") == set()
    service = cast("Any", SimpleNamespace(interactions=(SimpleNamespace(__name__="Tap", screen=Home, leads_to=None),)))
    assert calls_of(service, Island, "screen") == set()


@pytest.fixture
def todo(root) -> Any:
    return module("services.web.service").service


@pytest.fixture
def kit(root) -> Any:
    return module("services.kit.service").service


def _explained(service: Any, name: str, capsys: pytest.CaptureFixture[str]) -> str:
    cmd_explain(service, SimpleNamespace(service="services.web", name=name))
    return capsys.readouterr().out


def test_the_fixture_books_state_no_refusal_and_no_note(todo, kit):
    assert move_faults(todo) == move_notes(todo) == []
    assert move_faults(kit) == move_notes(kit) == []


def test_explain_of_a_screen_prints_how_it_is_reached_and_the_way_from_an_entry(kit, capsys):
    out = _explained(kit, "Assign", capsys)
    assert "reached by: GoToAssign on Home" in out
    assert "from an entry: GoToAssign on Home" in out


def test_explain_of_an_embedded_screen_prints_its_host_its_phase_and_the_transitions_into_it(todo, capsys):
    out = _explained(todo, "RemoveDialog", capsys)
    assert "hosted by: ListPage\nshown in: ready\n" in out
    assert "on RemoveDialog, hosted by ListPage, an entry" in out
    assert "ListPage moves into ready:\n    loading --[200 with rows]--> ready; rows replaced\n" in out


def test_explain_of_an_interaction_prints_the_way_to_its_screen_and_where_it_leads(kit, capsys):
    out = _explained(kit, "GoBack", capsys)
    assert "from an entry: GoToAssign on Home\nleads to: Home\n" in out
    assert "stays on Home" in _explained(kit, "AddTodo", capsys)


def test_explain_of_a_component_prints_its_text_the_phases_that_hold_it_and_the_way_to_its_screen(todo, capsys):
    out = _explained(todo, "AddForm.save", capsys)
    assert out.splitlines()[1:] == ["button 'Save'      button    'Save'  POST /todos with the non-empty fields",
                                    "phase saving: disabled", "on AddForm, hosted by ListPage, an entry"]
    shown_out = _explained(todo, "ListPage.rows", capsys)
    assert "phase ready: shows\n" in shown_out + "\n" and "phase loading: hides\n" in shown_out + "\n"


def test_explain_of_a_component_that_the_screen_does_not_have_stops(todo):
    with pytest.raises(SystemExit):
        cmd_explain(todo, SimpleNamespace(service="services.web", name="AddForm.nothing"))


def test_a_phase_that_shows_a_component_is_named_with_its_reason(capsys):
    service = _book(*BOOK, interactions=MOVES)
    cmd_explain(service, SimpleNamespace(service="shop_book", name="Dialog.save"))
    assert capsys.readouterr().out.splitlines()[1:] == ["save               button    'Save'  keeps the draft", "on Dialog, hosted by Listing, reached by OpenList on Home"]


def test_search_of_a_screen_and_an_interaction_adds_the_way_to_its_screen(module, capsys):
    service = _book(*BOOK, interactions=(OpenList, ListToDetail))
    args = SimpleNamespace(service=module, term="presses a row", kind="interaction")
    assert cmd_search(service, args) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "        on Listing, reached by OpenList on Home"
    reach = {item.name: item.reach for item in items(service, module) if item.kind == "screen"}
    assert reach["Home"] == "on Home, reached by an entry"
    assert reach["Detail"] == "on Detail, reached by OpenList on Home then ListToDetail on Listing"
    assert reach["Dialog"] == "on Dialog, hosted by Listing, reached by OpenList on Home"
    assert reach["Island"] == "on Island, no walk from an entry reaches it"


def test_search_finds_a_component_by_its_label_and_its_text(module, capsys):
    service = _book(*BOOK, interactions=(OpenList,))
    assert cmd_search(service, SimpleNamespace(service=module, term="draft dialog", kind="component")) == 0
    out = capsys.readouterr().out.splitlines()
    draft = out.index(next(line for line in out if line.endswith("books/component  shop_book/test_book_reach:Listing.draft")))
    assert out[draft + 2] == "        on Listing, reached by OpenList on Home"
    assert cmd_search(service, SimpleNamespace(service=module, term="Draft", kind="component")) == 0
    assert "en: [Draft]" in capsys.readouterr().out
