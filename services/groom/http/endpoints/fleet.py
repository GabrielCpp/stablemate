"""What an operator reads: the fleet, one run, and the attendant switch."""

from ostler.book import Answer, Endpoint, Field, Object

from ...model import actions
from .shapes import ATTEND, ATTEND_INPUT, ERROR, FLEET, RUN_ID, WORKER

APP = "groom/groom/app.py::"
PROJECTION = "groom/groom/projection.py::"


class ReadFleet(Endpoint):
    method = "GET"
    path = "/api/state"
    query = Object(q=Field(RUN_ID, required=False, does="keeps the runs where this text, in any case, is part of the name, repo, branch, node, run id or a gate path"))
    answers = (Answer(200, FLEET, "the fleet as the dashboard shows it, filtered by q"),)
    source = (APP + "api_state", PROJECTION + "fleet_rows", PROJECTION + "matches", PROJECTION + "attention_events", "groom/groom/attention.py")
    does = (
        "Reads the fleet. Runs come blocked first, then running, then finished, each group by name. The attention list "
        "covers every run and ignores q."
    )
    carries = actions.ReadFleet


class ReadWorker(Endpoint):
    method = "GET"
    path = "/worker/{container_id}"
    params = Object(container_id=Field(RUN_ID, does="the run's container id"))
    answers = (Answer(200, WORKER, "the run with its gates, or {found: false} for a run groom never heard of"),)
    source = (APP + "worker_detail", PROJECTION + "gate_dict", PROJECTION + "question_preview")
    does = "Reads one run: its state, node, header and the gates it waits on. An unknown run is not an error."
    carries = actions.ReadWorker


class ReadAttend(Endpoint):
    method = "GET"
    path = "/api/settings/attend"
    answers = (Answer(200, ATTEND, "the attendant's settings"),)
    source = (APP + "attend_settings_get",)
    does = "Reads whether an attendant answers the gates that block runs."
    carries = actions.ReadAttend


class SetAttend(Endpoint):
    method = "POST"
    path = "/api/settings/attend"
    body = ATTEND_INPUT
    answers = (Answer(201, ATTEND, "the settings after the switch"), Answer(400, ERROR, "the body is not JSON, or is not an object"))
    source = (APP + "attend_settings_post",)
    does = "Turns the attendant on or off. Anything but true counts as off."
    carries = actions.SetAttend


ALL = (ReadFleet, ReadWorker, ReadAttend, SetAttend)
