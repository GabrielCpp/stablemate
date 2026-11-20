"""Where an interaction leaves the person, as the surface shows it: how a page is told to be on a screen, which screen a step
should leave the person on, and what the run says of a step that does not."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from book_fakes import Plain, Quiet
from ostler.book import Action, Done, Interaction, PageSurface, Refusal, Screen, State
from ostler.book.journey import StepResult
from ostler.book.landing import Leaving, expected, judge
from ostler.book.runner import attempt
from ostler.book.screen import Text


DAY = date(2026, 11, 20)


class Late(Exception):
    pass


class FakePage:
    def __init__(self, url: str):
        self.url = url

    def wait_for_url(self, wanted: Any) -> None:
        if not wanted(self.url):
            raise Late


class FakeBrowser:
    def __init__(self, base: str, url: str, shown: tuple[Any, ...] = ()):
        self.base = base
        self.page = FakePage(url)
        self.shown = shown

    def visible(self, component: Any) -> bool:
        return component in self.shown

    def wait_for(self, component: Any) -> None:
        if component not in self.shown:
            raise Late


class Fake(PageSurface):
    def __init__(self, url: str = "http://app.test/", shown: tuple[Any, ...] = (), base: str = "http://app.test") -> None:
        self.browser: Any = FakeBrowser(base, url, shown)

    def timeouts(self) -> tuple[type[Exception], ...]:
        return (Late,)


def routed(route: str) -> type[Screen]:
    return type("Routed", (Screen,), {"route": route})


@pytest.mark.parametrize("route, url, on", [
    ("/", "http://app.test/", True),
    ("/", "http://app.test", True),
    ("/", "http://app.test/?lang=fr", True),
    ("/assign", "http://app.test/assign", True),
    ("/assign", "http://app.test/assign/", True),
    ("/assign", "http://app.test/assign?x=1#top", True),
    ("/assign", "http://app.test/", False),
    ("/assign", "http://app.test/assign/more", False),
    ("/assign", "http://app.test/assignment", False),
    ("/tickets/[id]", "http://app.test/tickets/7", True),
    ("/tickets/{id}", "http://app.test/tickets/7", True),
    ("/tickets/:id", "http://app.test/tickets/7", True),
    ("/tickets/$id", "http://app.test/tickets/7", True),
    ("/tickets/$id/", "http://app.test/tickets/7/?tab=a", True),
    ("/tickets/[id]", "http://app.test/tickets", False),
    ("/tickets/{id}", "http://app.test/tickets/7/edit", False),
    ("/tickets/:id/edit", "http://app.test/tickets/7/edit", True),
    ("/tickets/:id/edit", "http://app.test/tickets/7/view", False),
])
def test_a_page_is_on_a_screen_when_its_path_matches_the_route_in_each_spelling(route: str, url: str, on: bool):
    surface = Fake(url)
    assert surface.on(routed(route)) is on
    assert surface.arrive(routed(route)) is on


def test_the_path_below_the_base_address_is_the_one_the_route_matches():
    assert Fake("http://app.test/app/assign", base="http://app.test/app").on(routed("/assign")) is True
    assert Fake("http://app.test/app", base="http://app.test/app").on(routed("/")) is True
    assert Fake("http://app.test/application", base="http://app.test/app").on(routed("/")) is False


def test_only_the_asked_screen_is_judged_when_the_route_matches_several():
    assert Fake().on(routed("/")) is True
    assert Fake().on(routed("/assign")) is False


def test_a_screen_with_a_root_and_no_route_is_on_when_its_root_is_visible():
    root = Text("panel")
    Panel = type("Panel", (Screen,), {"root": root})
    assert Fake(shown=(root,)).on(Panel) is True
    assert Fake().on(Panel) is False
    assert Fake(shown=(root,)).arrive(Panel) is True
    assert Fake().arrive(Panel) is False


def test_a_screen_with_a_route_and_a_root_is_on_only_when_both_hold():
    root = Text("panel")
    Both = type("Both", (Screen,), {"route": "/both", "root": root})
    assert Fake("http://app.test/both", shown=(root,)).on(Both) is True
    assert Fake("http://app.test/other", shown=(root,)).on(Both) is False
    assert Fake("http://app.test/both").on(Both) is False
    assert Fake("http://app.test/both", shown=(root,)).arrive(Both) is True
    assert Fake("http://app.test/both").arrive(Both) is False
    assert Fake("http://app.test/other", shown=(root,)).arrive(Both) is False


def test_two_screens_that_share_a_route_are_told_apart_by_their_roots():
    one, two = Text("one"), Text("two")
    First = type("First", (Screen,), {"route": "/", "root": one})
    Second = type("Second", (Screen,), {"route": "/", "root": two})
    surface = Fake(shown=(two,))
    assert (surface.on(First), surface.on(Second)) == (False, True)


def test_a_screen_inside_another_is_told_by_its_root_or_else_by_its_host():
    root = Text("dialog")
    Host = routed("/list")
    Rooted = type("Rooted", (Screen,), {"inside": Host, "root": root})
    Bare = type("Bare", (Screen,), {"inside": Host})
    assert Fake("http://app.test/list").on(Rooted) is False
    assert Fake("http://app.test/list", shown=(root,)).on(Rooted) is True
    assert Fake("http://app.test/list").on(Bare) is True
    assert Fake("http://app.test/").on(Bare) is False
    assert Fake("http://app.test/").arrive(Bare) is False


def test_a_screen_with_neither_route_nor_root_cannot_be_told():
    Neither = type("Neither", (Screen,), {})
    assert Fake().on(Neither) is None
    assert Fake().arrive(Neither) is None
    assert Fake().on(type("Hosted", (Screen,), {"inside": Neither})) is None


class Home(Screen):
    route = "/"


class Next(Screen):
    route = "/next"


class Nudge(Action[None, State]):
    pass


class Go(Interaction[None]):
    screen = Home
    leads_to = Next
    does = "follows the link"


class Tap(Interaction[None]):
    screen = Home
    does = "presses a button"


class Heard(Interaction[None]):
    leads_to = Next
    does = "opens a deep link"
    carries = Nudge


class Nowhere(Interaction[None]):
    does = "reads the clock"
    carries = Nudge


def result(model: Any = None, app: Any = None) -> StepResult:
    return StepResult(None, model, app, (), (), True)


def test_an_accepted_act_with_a_leads_to_is_expected_on_the_screen_it_leads_to():
    assert expected(Go(), result(Done(), Done())) == (Next, True)


def test_an_accepted_act_with_no_leads_to_is_expected_to_stay():
    assert expected(Tap(), result(Done(), Done())) == (Home, False)


def test_an_act_the_model_refused_stays_where_it_was_whatever_it_leads_to():
    assert expected(Go(), result(Refusal("no", 422), Refusal("no", 422))) == (Home, False)


def test_an_act_from_outside_the_screens_that_leads_to_one_is_expected_there():
    assert expected(Heard(), result(Done(), Done())) == (Next, True)


def test_an_act_with_no_screen_and_no_leads_to_has_no_expectation():
    assert expected(Nowhere(), result(Done(), Done())) == (None, False)


def test_an_act_the_model_does_not_carry_is_judged_on_what_the_app_answered():
    assert expected(Go(), result(None, Done())) == (Next, True)
    assert expected(Go(), result(None, Refusal("no", 422))) == (Home, False)


class Where(Quiet):
    def __init__(self, on: bool | None, arrived: bool | None) -> None:
        self.asked: list[str] = []
        self.here = on
        self.came = arrived

    def on(self, screen: type[Screen]) -> bool | None:
        self.asked.append(f"on {screen.__name__}")
        return self.here

    def arrive(self, screen: type[Screen]) -> bool | None:
        self.asked.append(f"arrive {screen.__name__}")
        return self.came


@pytest.fixture(autouse=True)
def nobody_left(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Leaving, "names", {})


def test_a_stated_leads_to_that_the_person_reaches_passes_and_waits_for_it():
    surface = Where(on=False, arrived=True)
    taken = result(Done(), Done())
    judge(Go(), taken, surface)
    assert surface.asked == ["arrive Next"]
    assert taken.ok and taken.note == ""


def test_a_stated_leads_to_that_the_person_never_reaches_fails_the_step_and_says_so():
    taken = result(Done(), Done())
    judge(Go(), taken, Where(on=True, arrived=False))
    assert not taken.ok
    assert taken.note == "the act did not land on Next: the book states it leads there"


def test_a_surface_that_cannot_tell_checks_nothing():
    taken = result(Done(), Done())
    judge(Go(), taken, Where(on=None, arrived=None))
    judge(Tap(), taken, Where(on=None, arrived=None))
    assert taken.ok and taken.note == "" and Leaving.line() == ""
    judge(Tap(), taken, Quiet())
    assert taken.ok and taken.note == ""


def test_an_act_with_no_leads_to_asks_once_and_never_waits():
    surface = Where(on=True, arrived=False)
    taken = result(Done(), Done())
    judge(Tap(), taken, surface)
    assert surface.asked == ["on Home"]
    assert taken.ok and taken.note == "" and Leaving.line() == ""


def test_an_act_with_no_leads_to_that_left_its_screen_is_noted_and_does_not_fail():
    taken = result(Done(), Done())
    judge(Tap(), taken, Where(on=False, arrived=True))
    assert taken.ok
    assert taken.note == "the act left Home and the book states no leads_to"


def test_a_refused_act_is_judged_on_its_own_screen_and_not_on_what_it_leads_to():
    surface = Where(on=False, arrived=True)
    taken = result(Refusal("no", 422), Refusal("no", 422))
    judge(Go(), taken, surface)
    assert surface.asked == ["on Home"]
    assert taken.ok and "the act left Home" in taken.note


def test_a_step_that_crashed_or_was_skipped_or_already_failed_is_not_judged():
    surface = Where(on=False, arrived=False)
    crashed = StepResult(None, None, None, (), (), False, "crashed: boom")
    skipped = StepResult(None, None, None, (), (), True, skipped="why")
    failed = StepResult(None, Done(), Done(), (), (), False, "rows differ")
    for taken in (crashed, skipped, failed):
        judge(Go(), taken, surface)
    assert surface.asked == []


def test_a_step_that_is_not_an_interaction_is_not_judged():
    surface = Where(on=False, arrived=False)
    judge(object(), result(Done(), Done()), surface)
    assert surface.asked == []


def test_the_run_lists_each_interaction_that_left_its_screen_once():
    for step in (Tap(), Go(), Tap(), Tap()):
        judge(step, result(Done(), Done()), Where(on=False, arrived=True))
    assert Leaving.line() == "1 interactions left their screen with no leads_to stated: Tap"

    class Other(Interaction[None]):
        screen = Next
        does = "presses another button"

    judge(Other(), result(Done(), Done()), Where(on=False, arrived=True))
    assert Leaving.line() == "2 interactions left their screen with no leads_to stated: Tap, Other"
    Leaving.begin()
    assert Leaving.line() == ""


def test_a_step_taken_on_the_surface_has_its_landing_judged_where_the_result_is_finished():
    surface = Where(on=False, arrived=False)
    landed = attempt(Go(), Plain(DAY), surface)
    assert not landed.ok
    assert "the act did not land on Next" in landed.note
    stayed = attempt(Tap(), Plain(DAY), surface)
    assert stayed.ok and "the act left Home and the book states no leads_to" in stayed.note
    assert Leaving.line() == "1 interactions left their screen with no leads_to stated: Tap"
