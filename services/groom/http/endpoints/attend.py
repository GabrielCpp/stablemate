"""What the operator sees of the attendant: the runs waiting on it, its log, one attendance,
and the stop that hands a run back."""

from ostler.book import Answer, Endpoint, Field, Object

from ...model import actions
from .shapes import ATTEND_QUEUE, ATTEND_SESSION, ATTEND_SESSIONS, DONE, JOB_ID, SESSION_ID

APP = "groom/groom/app.py::"
ATTENDANT = (
    "groom/groom/attend.py",
    "groom/groom/attend_ledger.py",
    "groom/groom/attend_transcript.py",
    "groom/groom/settings.py",
    "groom/groom/procs.py",
)


class ReadAttendQueue(Endpoint):
    method = "GET"
    path = "/api/attend/queue"
    answers = (Answer(200, ATTEND_QUEUE, "the attendant's mode and every run waiting on it"),)
    source = (APP + "attend_queue", "groom/groom/attend.py::queue", "groom/groom/attend.py::mode", "groom/groom/prompts/attend-gate.md")
    does = "Reads every run currently waiting on an attendant, oldest first, with the attendant's mode."
    carries = actions.ReadAttendQueue


class ReadAttendSessions(Endpoint):
    method = "GET"
    path = "/api/attend/sessions"
    answers = (Answer(200, ATTEND_SESSIONS, "the attendant's mode and the latest 200 attendances"),)
    source = (APP + "attend_sessions", "groom/groom/attend_ledger.py::attend_recent")
    does = "Reads the attendance log, newest first."
    carries = actions.ReadAttendSessions


class ReadAttendSession(Endpoint):
    method = "GET"
    path = "/api/attend/sessions/{session_id}"
    params = Object(session_id=Field(SESSION_ID, does="the attendant's session id"))
    answers = (Answer(200, ATTEND_SESSION, "one attendance rendered as a conversation, with the command that resumes it"),)
    source = (APP + "attend_session", *ATTENDANT)
    does = "Reads one attendance as a conversation. A session with no transcript is still answered, with present false."
    carries = actions.ReadAttendSession


class StopAttendant(Endpoint):
    method = "POST"
    path = "/api/attend/sessions/{job_id}/stop"
    params = Object(job_id=Field(JOB_ID, does="the job's id"))
    answers = (Answer(201, DONE, "{ok: true} when a running attendant was killed, {ok: false} for a job that is not running"),)
    source = (APP + "attend_stop", "groom/groom/attend.py::stop")
    does = "Kills one attendant and hands its run back to the operator's own terminal."
    carries = actions.StopAttendant


ALL = (ReadAttendQueue, ReadAttendSessions, ReadAttendSession, StopAttendant)
