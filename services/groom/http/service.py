"""groom's HTTP API, as ostler loads it."""

from __future__ import annotations

from ostler.book import App, Because, Diverges, Environment, Refusal, Refusals, Service, Unseen

from .. import fixtures
from ..model.state import GroomApp, Off
from ..stack import PORT, stack
from . import endpoints as e
from .endpoints import ALL as ENDPOINTS
from .endpoints import PushBlocked, PushExited, PushProgress, ReadAttend, ReadFleet, ReadWorker, SetAttend
from .health import TheFleetAnswers
from .journeys import ALL as JOURNEYS
from .lifecycle import MATRICES
from .surface import GroomApi
from .unseen import UNSEEN as GAPS

PUSH_FIELDS = {
    PushProgress: ("container_id", "name", "repo_name", "repo_branch", "current_node"),
    PushBlocked: ("container_id", "file_path", "question", "name", "repo_name", "repo_branch"),
    PushExited: ("container_id", "exit_code", "name", "repo_name", "repo_branch"),
}

NO_INPUT_BASE = "the book's groom refuses every call of this endpoint the same way, so no call succeeds for an input class to vary"
NO_TELEMETRY = "the book's groom is never sent telemetry, which its OTLP receivers take as protobuf the book cannot write"
ARCHIVE_ENDPOINTS = (
    e.ReadArchiveOverview, e.ReadArchiveActivity, e.ReadArchiveRecords, e.SearchArchive, e.ReadArchiveEntry, e.ReadArchiveTurn,
)

DIVERGES = (
    *(
        Diverges(endpoint, f"{field} {kind}", why=f"groom reads {field} with data.get and keeps going, so a {kind} value is not refused")
        for endpoint, fields in PUSH_FIELDS.items()
        for field in fields
        for kind in ("wrong type", "null")
        if not (field == "name" and kind == "wrong type" and endpoint is not PushProgress)
    ),
    *(
        Diverges(ep, f"{field} {kind}", why=f"groom turns {field} into text with str(), so a {kind} value is not refused")
        for ep, fields in ((e.AnswerGate, ("file_path", "answer")), (e.LeaveMessage, ("body",)))
        for field in fields
        for kind in ("wrong type", "null")
    ),
    *(
        Diverges(SetAttend, f"enabled {kind}", why="groom turns the body into a truth value, so any value answers 201")
        for kind in ("wrong type", "null")
    ),
)

NEVER_PUSHED = "a pushed run carries none of the telemetry a workhorse sidecar adds to its row"

UNSEEN = (
    *GAPS,
    *(Unseen(ep, "inputs", Because.NEVER_FILLED, NO_INPUT_BASE) for ep in (*ARCHIVE_ENDPOINTS, e.ReadEntry, e.ReadTurn, e.Enqueue)),
    *(Unseen(ep, "200", Because.NEVER_FILLED, NO_TELEMETRY) for ep in (*ARCHIVE_ENDPOINTS, e.ReadEntry, e.ReadTurn)),
    *(Unseen(ep, "410", Because.NEVER_FILLED, "no run is archived, so no archive has lost its files") for ep in ARCHIVE_ENDPOINTS),
    Unseen(e.ReadTurn, "503", Because.NEVER_FILLED, NO_TELEMETRY),
    Unseen(e.SearchRun, "503", Because.NEVER_FILLED, NO_TELEMETRY),
    Unseen(e.Enqueue, "201", Because.NEVER_FILLED, "the home of the book's groom names no dispatch queue"),
    *(
        Unseen(endpoint, "400", Because.RUNTIME, "the 400 is the framework's answer to a body that is not an object, which the runtime does not send")
        for endpoint in (PushProgress, PushBlocked, PushExited)
    ),
    *(
        Unseen(ReadFleet, f"200: {field}", Because.NEVER_FILLED, NEVER_PUSHED)
        for field in (
            "runs[].type", "runs[].wait_kind", "runs[].turn_active", "runs[].mini", "runs[].clock", "runs[].activity",
            "runs[].question", "runs[].pid", "runs[].figures", "runs[].ended", "attention[].terminal",
        )
    ),
    Unseen(ReadFleet, "200: store.last_error", Because.NEVER_FILLED, "the book's database never fails"),
    Unseen(ReadFleet, "200: attend.by_run", Because.NEVER_FILLED, "no attendant job exists while the attendant has nothing to answer"),
    *(
        Unseen(ReadWorker, f"200: {field}", Because.NEVER_FILLED, NEVER_PUSHED)
        for field in (
            "gates[].kind", "running.wait_kind", "strip.wait_kind", "strip.idle_since_ts", "strip.beat_ts", "strip.norm",
            "ended", "head.type", "head.pid", "head.cli", "head.activity", "head.worktree", "head.checkout",
            "metrics.cells", "metrics.alerts", "metrics.run_dir", "logs", "history",
        )
    ),
    Unseen(ReadAttend, "200: deny", Because.NEVER_FILLED, "the book sets no deny list for the attendant"),
    Unseen(SetAttend, "400", Because.RUNTIME, "the 400 is the framework's answer to a body that is not an object, which the runtime does not send"),
    Unseen(SetAttend, "201: deny", Because.NEVER_FILLED, "the book sets no deny list for the attendant"),
)

IGNORE = (
    "groom/groom/__init__.py",
    "groom/groom/README.md",
    "groom/groom/assets/*",
    "groom/groom/templates/*",
    "groom/groom/tui/*",
    "groom/groom/cli.py",
    "groom/groom/export.py",
    "groom/groom/wait.py",
    "groom/groom/channel.py",
    "groom/groom/ws_url.py",
    "groom/groom/digest.py",
    "groom/groom/notify.py",
    "groom/groom/otlp.py",
    "groom/groom/sidecar_turns.py",
)

LOCAL = Environment("local", {"api": f"http://127.0.0.1:{PORT}"})

service = Service[GroomApp](
    name="api",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Off,
    surface=GroomApi,
    journeys=JOURNEYS,
    health=(TheFleetAnswers,),
    stack=stack,
    app=App(roots=("groom/groom",), verified="VERIFIED", ignore=IGNORE),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(),
    diverges=DIVERGES,
    unseen=UNSEEN,
    refusals=Refusals(
        malformed=Refusal("JSON is malformed: invalid character (byte 0)", 400),
        unknown_id=Refusal("Validation failed", 400),
        wrong_kind=Refusal("Validation failed", 400),
        missing=Refusal("Validation failed", 400),
    ),
    words={**{e.__name__: e for e in ENDPOINTS}, **{name: getattr(fixtures, name) for name in fixtures.__all__}},
)
