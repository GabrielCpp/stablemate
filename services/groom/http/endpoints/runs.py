"""What an operator reads of one run beyond its row: the gate it waits on, its inbox, its cost,
its turns and its records, and the same reads over an archived run. groom answers these from
the telemetry it stored, and the book's groom stores none."""

from ostler.book import Answer, Bool, Endpoint, Field, Int, Map, Object, Str

from ...model import actions
from .shapes import (
    ACTIVITY,
    ANSWER_INPUT,
    ERROR,
    INBOX,
    MATCHES,
    MESSAGE_INPUT,
    NOTICE,
    OUTBOX,
    OVERVIEW,
    RECORDS,
    RUN_ID,
)

APP = "groom/groom/app.py::"
STORE = "groom/groom/store.py"
PICK = Object(run_id=Field(RUN_ID, does="the run's id, as the dashboard addresses it"))
NOT_ARCHIVED = Answer(404, ERROR, "no archived run has this id, so nothing is read")
FILES_GONE = Answer(410, ERROR, "the run is archived and its archive's files are gone")
SERVED = Map(Str())
ARCHIVE_SOURCE = (
    "groom/groom/archive.py",
    "groom/groom/history.py",
    "groom/groom/pools.py",
)
OVERVIEW_SOURCE = (
    "groom/groom/overview.py::run_overview",
    "groom/groom/figures.py",
    "groom/groom/flows.py",
    "groom/groom/norms.py",
    "groom/groom/medians.py",
    "groom/groom/banner.py",
    "groom/groom/problems.py",
    "groom/groom/prices.py",
    STORE,
)
ACTIVITY_SOURCE = (
    "groom/groom/activity.py",
    "groom/groom/churn.py",
    "groom/groom/flows.py",
    "groom/groom/live_history.py",
    "groom/groom/live_transcript.py",
    "groom/groom/transcript_parse.py",
    STORE,
)


class ReadOutbox(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/outbox"
    params = PICK
    answers = (Answer(200, OUTBOX, "the first gate the run waits on, or {found: false}"),)
    source = (APP + "outbox_get", "groom/groom/projection.py::reported_gates")
    does = "Reads the gate a run is parked on: its path, question and status. A run that is unknown or waits on nothing has none."
    carries = actions.ReadOutbox


class AnswerGate(Endpoint):
    method = "POST"
    path = "/api/run/{run_id}/outbox"
    params = PICK
    body = ANSWER_INPUT
    answers = (Answer(201, NOTICE, "{ok: false, message}: groom could not deliver the answer, and says why"),)
    source = (
        APP + "outbox_post",
        APP + "_answer",
        APP + "_answer_via_socket",
        "groom/groom/gates.py::answer_gate",
        "groom/groom/models.py",
        "groom/groom/docker_io.py",
        "groom/groom/localfs.py",
        "groom/groom/sidecar_hub.py",
    )
    does = (
        "Answers the gate a run waits on. groom delivers the answer over the run's control socket and falls back to "
        "writing the gate file in the run's workspace. A run groom never heard of is refused with {ok: false}, and so is "
        "a run whose workspace groom cannot reach, which every run the book pushes is."
    )
    carries = actions.AnswerGate


class ReadInbox(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/inbox"
    params = PICK
    query = Object(include_all=Field(Bool(), required=False, does="true adds the messages already replied to"))
    answers = (Answer(200, INBOX, "the run's outstanding messages"),)
    source = (APP + "inbox_get", "groom/groom/run_inbox.py::messages")
    does = "Reads the messages an operator left for the run: the unanswered ones, or every one with include_all."
    carries = actions.ReadInbox


class LeaveMessage(Endpoint):
    method = "POST"
    path = "/api/run/{run_id}/inbox"
    params = PICK
    body = MESSAGE_INPUT
    answers = (Answer(201, NOTICE, "{ok: false, message}: groom left no message, and says why"),)
    source = (APP + "inbox_post", "groom/groom/run_inbox.py::append")
    does = (
        "Leaves the operator's message in the run's inbox. A run groom never heard of, an empty message and a run with no "
        "directory yet are each refused with {ok: false}, in that order. An optional id names the message."
    )
    carries = actions.LeaveMessage


class ReadOverview(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/overview"
    params = PICK
    answers = (Answer(200, OVERVIEW, "the run's cost, its figures and its time per flow"),)
    source = (APP + "run_overview", *OVERVIEW_SOURCE)
    does = "Reads one run's cost so far and its time per flow, from its stored telemetry. A run with none reads as an empty overview."
    carries = actions.ReadOverview


class ReadActivity(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/activity"
    params = PICK
    query = Object(logs=Field(Int(), required=False, does="1 adds the run's info logs at their place in the timeline"))
    answers = (Answer(200, ACTIVITY, "the run's turns oldest first in rows, and the same turns grouped by work item, flow pass and visit in items"),)
    source = (APP + "run_activity", APP + "_timeline", APP + "_live_turns", APP + "_standing", *ACTIVITY_SOURCE)
    does = "Reads one run's agent turns oldest first in rows, and the same turns in items, grouped by work item, flow pass and visit with the steps, gates, retries and churn alerts around them; logs=1 adds its info logs at their place."
    carries = actions.ReadActivity


class ReadRecords(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/records"
    params = PICK
    query = Object(
        before=Field(Str(), required=False, does="the cursor the previous page returned"),
        limit=Field(Int(), required=False, does="how many records a page holds; a value under 1 holds none"),
        metrics=Field(Int(), required=False, does="1 adds the metric samples"),
    )
    answers = (
        Answer(200, RECORDS, "one page of the run's stored records, newest first"),
        Answer(400, ERROR, "the cursor is not one this run's records handed out"),
    )
    source = (APP + "run_records", APP + "_records", "groom/groom/records.py::page", STORE)
    does = "Reads one page of a run's stored records, newest first, from the cursor a previous page returned."
    carries = actions.ReadRecords


class SearchRun(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/search"
    params = PICK
    query = Object(q=Field(Str(), required=False, does="the text to find in the transcripts"))
    answers = (
        Answer(200, MATCHES, "the turns whose transcript says the query, each with its first matching line"),
        Answer(503, ERROR, "the transcripts could not be searched"),
    )
    source = (APP + "run_search", APP + "_search", "groom/groom/activity.py::search")
    does = "Searches the transcripts of one run for the text and answers the turns that say it."
    carries = actions.SearchRun


class ReadEntry(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/entry/{key}"
    params = Object("Entry", run_id=Field(RUN_ID), key=Field(Str(), does="the key of a step, gate, retry or churn alert"))
    answers = (Answer(200, SERVED, "the step or gate, in full"), Answer(404, ERROR, "the run has no step or gate under this key"))
    source = (APP + "run_entry", APP + "_entry", "groom/groom/activity.py::entry")
    does = "Reads one step, operator gate, backend retry or churn alert of the run in full."
    carries = actions.ReadEntry


class ReadTurn(Endpoint):
    method = "GET"
    path = "/api/run/{run_id}/activity/{slug}"
    params = Object("Turn", run_id=Field(RUN_ID), slug=Field(Str(), does="the slug of an agent turn"))
    answers = (
        Answer(200, SERVED, "the turn, with its messages and its tool calls"),
        Answer(404, ERROR, "the run has no turn with this slug"),
        Answer(503, ERROR, "the turn's transcript could not be read"),
    )
    source = (APP + "run_turn", APP + "_turn", "groom/groom/activity.py::turn", "groom/groom/turns.py")
    does = "Reads one agent turn: its head figures, its messages and its tool calls."
    carries = actions.ReadTurn


class ReadArchiveOverview(Endpoint):
    method = "GET"
    path = "/api/archive/{run_id}/overview"
    params = PICK
    answers = (Answer(200, OVERVIEW, "the archived run's overview"), NOT_ARCHIVED, FILES_GONE)
    source = (APP + "archive_overview", APP + "_archive_overview", *ARCHIVE_SOURCE, *OVERVIEW_SOURCE)
    does = "Reads one archived run's overview from its frozen archive, or from its stored summary when the files are gone."
    carries = actions.ReadArchive


class ReadArchiveActivity(Endpoint):
    method = "GET"
    path = "/api/archive/{run_id}/activity"
    params = PICK
    query = Object(logs=Field(Int(), required=False, does="1 adds the run's info logs at their place in the timeline"))
    answers = (Answer(200, ACTIVITY, "the archived run's turns"), NOT_ARCHIVED, FILES_GONE)
    source = (APP + "archive_activity", APP + "_in_archive", APP + "_archive_read", *ARCHIVE_SOURCE)
    does = "Reads one archived run's turns from its frozen file, on the archive pool."
    carries = actions.ReadArchive


class ReadArchiveRecords(Endpoint):
    method = "GET"
    path = "/api/archive/{run_id}/records"
    params = PICK
    query = Object(
        before=Field(Str(), required=False),
        limit=Field(Int(), required=False),
        metrics=Field(Int(), required=False),
    )
    answers = (Answer(200, RECORDS, "one page of the archived run's records"), NOT_ARCHIVED, FILES_GONE)
    source = (APP + "archive_records", *ARCHIVE_SOURCE)
    does = "Reads one page of an archived run's stored records, newest first, from its frozen file."
    carries = actions.ReadArchive


class SearchArchive(Endpoint):
    method = "GET"
    path = "/api/archive/{run_id}/search"
    params = PICK
    query = Object(q=Field(Str(), required=False))
    answers = (Answer(200, MATCHES, "the archived turns that say the query"), NOT_ARCHIVED, FILES_GONE)
    source = (APP + "archive_search", *ARCHIVE_SOURCE)
    does = "Searches the transcripts of one archived run for the text."
    carries = actions.ReadArchive


class ReadArchiveEntry(Endpoint):
    method = "GET"
    path = "/api/archive/{run_id}/entry/{key}"
    params = Object("ArchiveEntry", run_id=Field(RUN_ID), key=Field(Str()))
    answers = (Answer(200, SERVED, "the archived step, gate, retry or churn alert"), NOT_ARCHIVED, FILES_GONE)
    source = (APP + "archive_entry", *ARCHIVE_SOURCE)
    does = "Reads one step, gate, retry or churn alert of an archived run in full. Its workspace is gone, so a gate's answer reads as unavailable."
    carries = actions.ReadArchive


class ReadArchiveTurn(Endpoint):
    method = "GET"
    path = "/api/archive/{run_id}/activity/{slug}"
    params = Object("ArchiveTurn", run_id=Field(RUN_ID), slug=Field(Str()))
    answers = (Answer(200, SERVED, "the archived turn"), NOT_ARCHIVED, FILES_GONE)
    source = (APP + "archive_turn", *ARCHIVE_SOURCE)
    does = "Reads one agent turn of an archived run from the records its archive kept."
    carries = actions.ReadArchive


ALL = (
    ReadOutbox, AnswerGate, ReadInbox, LeaveMessage, ReadOverview, ReadActivity, ReadRecords, SearchRun, ReadEntry,
    ReadTurn, ReadArchiveOverview, ReadArchiveActivity, ReadArchiveRecords, SearchArchive, ReadArchiveEntry,
    ReadArchiveTurn,
)
