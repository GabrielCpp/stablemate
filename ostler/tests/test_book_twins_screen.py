from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from ostler.book import Action, Answer, Done, Endpoint, Field, Journey, Model, Object, Refusal, Refusals, Rule, Service, Str
from ostler.book.inputs import play
from ostler.book.model import Refused

from book_fakes import Quiet, no_stack

DAY = date(2026, 11, 4)


class Notes(Model):
    def apply(self, request: Any) -> None:
        title = request.body_value["title"]
        if not title.strip() or len(title) > 10:
            raise Refused(TOO_LONG)

    def rows(self) -> tuple[object, ...]:
        return ()

    def copy(self) -> Notes:
        return Notes(self.today)


TOO_LONG = Rule("title unusable", lambda a, s, by: True)


class Rename(Endpoint):
    method = "POST"
    path = "/rename"
    body = Object("Rename", title=Field(Str(max_len=10)))
    answers = (Answer(200, None, "renamed"), Answer(400, None, "refused"))
    carries = Action


class Opens(Journey):
    def steps(self, today: date) -> Iterator[object]:
        yield Rename({"title": "abc"})


class Page(Quiet):
    def __init__(self) -> None:
        self.shows = "idle"

    def fresh(self) -> Model:
        self.shows = "idle"
        return Notes(DAY)

    def watched(self, model: Model) -> tuple[object, ...]:
        return self.rows()

    def rows(self) -> tuple[object, ...]:
        return ({"shows": self.shows},)

    def perform(self, step: Any) -> Done | Refusal:
        title = step.body_value.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 10:
            self.shows = "failed"
            return Refusal("title unusable", 400)
        self.shows = "done"
        return Done(({"shows": self.shows},))


def test_a_pair_the_app_answers_alike_is_not_split_by_the_failure_screen_a_refused_class_left():
    service = Service[Notes](name="notes", new_model=Notes, surface=lambda environment: Page(), journeys=(Opens,), stack=no_stack,
                             endpoints=(Rename,), refusals=Refusals(wrong_type=Refusal("title unusable", 400), missing=Refusal("title unusable", 400)))
    surface = Page()
    tried = play(service, surface, surface.fresh, only=frozenset({"Rename"}))
    assert any(s.clean for s in tried.sent)
    assert tried.twins_played
    assert tried.underspecified == []
