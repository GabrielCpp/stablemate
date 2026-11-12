"""The /push endpoints a workflow reports to. Each call upserts the run it names,
and the answer only says whether groom took it."""

from ostler.book import Answer, Endpoint

from ...model import actions
from .shapes import ACK, BLOCKED, ERROR, EXITED, PROGRESS

APP = "groom/groom/app.py::"
STATE = "groom/groom/state.py::upsert_workflow"
BAD_BODY = Answer(400, ERROR, "the body is not JSON, or is not an object")
TOOK_IT = "{ok: true}: groom took the push and the run is on the fleet"
IGNORED = "{ok: false}: the push named no run, so groom changed nothing"


class PushProgress(Endpoint):
    method = "POST"
    path = "/push/progress"
    body = PROGRESS
    answers = (Answer(201, ACK, TOOK_IT + " running; a new run is named by its name or else its container id"), BAD_BODY)
    source = (APP + "push_progress", STATE)
    does = (
        "A workflow says it is running, in a node. A run groom has not seen joins the fleet; one it has seen is "
        "running again and keeps its gates. A field the push leaves out stays as it was."
    )
    carries = actions.PushProgress


class PushBlocked(Endpoint):
    method = "POST"
    path = "/push/blocked"
    body = BLOCKED
    answers = (Answer(201, ACK, TOOK_IT + " blocked on the gate file"), BAD_BODY)
    source = (APP + "push_blocked", STATE)
    does = (
        "A workflow says it waits on the operator at a gate file. The run is blocked and holds one gate per file path; "
        "a second push for the same path replaces its question. It needs both a container id and a file path."
    )
    carries = actions.PushBlocked


class PushExited(Endpoint):
    method = "POST"
    path = "/push/exited"
    body = EXITED
    answers = (Answer(201, ACK, TOOK_IT + " finished; its gates are gone"), BAD_BODY)
    source = (APP + "push_exited", STATE)
    does = (
        "A workflow's process ended. The run is finished and holds no gates. An exit code that is absent or not a number "
        "leaves the run's earlier code as it was."
    )
    carries = actions.PushExited


ALL = (PushProgress, PushBlocked, PushExited)
