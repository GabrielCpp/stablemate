"""The /admin endpoints the test build exposes so a journey can move the clock,
take the store down and start from nothing. None takes a credential."""

from ostler.book import Answer, Endpoint, Refusal, Refusals

from .shapes import CLOCK, ERROR, STORE
from ..model import actions


class ReadClock(Endpoint):
    method = "GET"
    path = "/admin/clock"
    answers = (Answer(200, CLOCK, "the day the service believes it is"),)
    source = ("app.py::admin_handler",)
    does = "Reads the service's today."
    carries = actions.TellDay


class SetClock(Endpoint):
    method = "POST"
    path = "/admin/clock"
    body = CLOCK
    answers = (Answer(204, None, "today moved; every status is read against the new day"),
               Answer(400, ERROR, "not a date"))
    refusals = Refusals(missing=Refusal("Due date must be a date", 400))
    source = ("app.py::admin_handler",)
    does = "Moves the service's today."
    carries = actions.MoveClock


class SetStore(Endpoint):
    method = "POST"
    path = "/admin/store"
    body = STORE
    answers = (Answer(204, None, "the switch moved"), Answer(400, ERROR, "not a boolean"))
    source = ("app.py::admin_handler",)
    does = "Takes the store down or brings it back; while down every /todos call answers 503."
    carries = actions.SwitchStore


class Reset(Endpoint):
    method = "POST"
    path = "/admin/reset"
    answers = (Answer(204, None, "empty store, the real date, store up"),)
    source = ("app.py::admin_handler",)
    does = "Starts from nothing."
    carries = actions.Wipe
