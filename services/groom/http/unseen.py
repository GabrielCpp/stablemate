"""The answers and fields no play of the book can reach, with the reason for each."""

from ostler.book import Because, Unseen

from ..model import actions as a
from . import endpoints as e

NO_TELEMETRY = "the book's groom is never sent telemetry, which its OTLP receivers take as protobuf the book cannot write"
NO_WORKSPACE = "no run the book pushes has a workspace volume or a sidecar, which a push cannot create"
NO_ATTENDANT = "no gate the book pushes belongs to a native run, and only a native run's gate gets an attendant"
NO_QUEUE = "the home of the book's groom names no dispatch queue"
FRAMEWORK = "the framework adds extra to a refusal of a query parameter's type, which the runtime does not send"
NO_NATIVE = "groom lists a container with a workspace volume, and only a run it discovers on docker or on disk has one"

ARCHIVES = (
    e.ReadArchiveOverview, e.ReadArchiveActivity, e.ReadArchiveRecords, e.SearchArchive, e.ReadArchiveEntry, e.ReadArchiveTurn,
)
EXTRA = ("extra", "extra[].message", "extra[].key", "extra[].source")

OVERVIEW_FIELDS = (
    "cost.usd", "cost.est_usd", "cost.backends", "figures.cost_usd", "figures.items_done", "figures.items_total",
    "figures.est_usd", "figures.backends", "flows", "nodes", "compare", "items", "clock", "models", "sessions",
    "facts.started_ts", "facts.branch", "facts.run_dir", "as_of_ts", "ending",
)
LIVE_FIELDS = (
    "run_id", "workflow", "run_dir", "node", "node_elapsed_s", "turn_active", "turn_elapsed_s", "turn_idle_s",
    "wait_kind", "wait_elapsed_s", "gas", "last_beat_ts", "alive",
)

GAPS = (
    (e.ReadInbox, "200", ("messages",), "a run's inbox is a file in its run directory, which a pushed run has none of"),
    (e.ReadOverview, "200", OVERVIEW_FIELDS, NO_TELEMETRY),
    (e.ReadActivity, "200", ("rows", "items"), NO_TELEMETRY),
    (e.ReadRecords, "200", ("records", "next"), NO_TELEMETRY),
    (e.SearchRun, "200", ("matches",), NO_TELEMETRY),
    (e.ReadFiles, "200", ("paths", "repos"), NO_WORKSPACE),
    (e.ReadFile, "200", ("content",), NO_WORKSPACE),
    (e.ReadDiff, "200", ("diff", "untracked", "repos", "based", "base", "base_ref", "base_branch", "base_reason"), NO_WORKSPACE),
    (e.ReadAttendQueue, "200", ("jobs",), NO_ATTENDANT),
    (e.ReadAttendSessions, "200", ("sessions",), NO_ATTENDANT),
    (e.ReadAttendSession, "200", ("entries", "record", "attempts"), NO_ATTENDANT),
    (e.ReadQueues, "200", ("queues",), NO_QUEUE),
    (e.ReadQueueItems, "200", ("items",), NO_QUEUE),
    (e.ReadHistory, "200", ("runs", "medians"), NO_TELEMETRY),
    (
        e.ReadRepos, "200",
        ("[].container", "[].name", "[].state", "[].type", "[].type_hue", "[].repos", "[].repos[].repo", "[].repos[].label"),
        NO_NATIVE,
    ),
    (e.ReadLive, "200", tuple(f"[].{name}" for name in LIVE_FIELDS), NO_TELEMETRY),
)

NO_PLAY = "groom refuses every call of this action the same way, so no play has the model accept the call"
NEVER_ACCEPTED = (a.ReadEntry, a.ReadTurn, a.ReadArchive, a.Enqueue)

UNSEEN = (
    *(Unseen(action, Because.RUNTIME, NO_PLAY) for action in NEVER_ACCEPTED),
    *(Unseen(ep, f"{status}: {field}", Because.NEVER_FILLED, why) for ep, status, fields, why in GAPS for field in fields),
    *(Unseen(ep, f"{status}: {field}", Because.RUNTIME, FRAMEWORK) for ep, status in (
        (e.ReadRecords, "400"), (e.ReadEntry, "404"), (e.ReadTurn, "404"), *((ep, "404") for ep in ARCHIVES),
    ) for field in EXTRA),
)
