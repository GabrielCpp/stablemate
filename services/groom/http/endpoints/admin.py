"""What groom does about itself: lists the checkouts it can read, reads the live runs and the
history, rescans for runs, and tells its sidecars to reload."""

from ostler.book import Answer, Bool, Endpoint, Enum, Field, Int, List, Num, Object, Str

from ...model import actions
from ...model.records import STATES
from .shapes import DONE, HISTORY, REFRESHED, LIVE_RUN, RELOADED, RUN_ID

APP = "groom/groom/app.py::"
CHECKOUT = Object("Checkout", repo=Field(Str(), does="the checkout's folder, empty for a volume that holds one repo"), label=Field(Str()))
REPO = Object(
    "RepoGroup",
    container=Field(Str(), does="the run's container id"),
    name=Field(Str()),
    state=Field(Enum(STATES)),
    type=Field(Str()),
    type_hue=Field(Int()),
    repos=Field(List(CHECKOUT), does="one entry per checkout found on the volume, or one empty entry when none is found"),
)
LIVE_ROW = Object(
    "LiveRow",
    run_id=Field(LIVE_RUN),
    workflow=Field(Str()),
    run_dir=Field(Str()),
    node=Field(Str()),
    node_elapsed_s=Field(Num()),
    turn_active=Field(Bool(), nullable=True),
    turn_elapsed_s=Field(Num()),
    turn_idle_s=Field(Num()),
    wait_kind=Field(Str()),
    wait_elapsed_s=Field(Num()),
    gas=Field(Num(), nullable=True),
    last_beat_ts=Field(Num()),
    alive=Field(Bool()),
)


class ReadRepos(Endpoint):
    method = "GET"
    path = "/repos"
    answers = (Answer(200, List(REPO, unordered="the groups follow the order groom discovered its containers"), "one group per container with a workspace volume"),)
    source = (APP + "repos", "groom/groom/projection.py::repo_entries", "groom/groom/localfs.py", "groom/groom/docker_io.py")
    does = "Lists every container's checkouts for the terminal client's repo view: one group per container with a workspace volume, each with the checkouts found there. The page does not read it."
    carries = actions.ReadRepos


class ReadLive(Endpoint):
    method = "GET"
    path = "/api/live"
    query = Object(run=Field(RUN_ID, required=False, does="keeps the one run"))
    answers = (Answer(200, List(LIVE_ROW, unordered="the rows of every live run groom received telemetry from"), "where each live run is right now"),)
    source = (APP + "api_live", "groom/groom/alerts.py", "groom/groom/overview.py")
    does = "Reads where each live run is right now: the rows behind groom status. A run groom has no telemetry of has no row."
    carries = actions.ReadLive


class ReadHistory(Endpoint):
    method = "GET"
    path = "/api/history"
    query = Object(archives=Field(Int(), required=False, does="1 adds every archived summary, whatever its age"))
    answers = (Answer(200, HISTORY, "the runs that ended, newest first, with the totals above the table"),)
    source = (APP + "api_history", "groom/groom/history.py::listing", "groom/groom/history.py::totals", "groom/groom/medians.py")
    does = "Reads the runs that ended in the retention window, newest first, from their stored summaries."
    carries = actions.ReadHistory


class RetryHistory(Endpoint):
    method = "POST"
    path = "/api/history/{run_id}/retry"
    params = Object(run_id=Field(RUN_ID))
    answers = (Answer(201, DONE, "{ok: true} when an archive's unreadable summary is queued to be read again, {ok: false} for any other run"),)
    source = (APP + "history_retry", "groom/groom/history.py::retry")
    does = "Asks for an archive whose summary could not be read to be read again."
    carries = actions.RetryHistory


class Refresh(Endpoint):
    method = "POST"
    path = "/refresh"
    answers = (Answer(201, REFRESHED, "{ok: true, count}: the scan ran and found count workflows"),)
    source = (APP + "refresh", APP + "_reconcile", "groom/groom/discovery.py", "groom/groom/checkpoints.py")
    does = "Runs the discovery scan again: upserts every workflow found and prunes the ones whose container is gone, unless docker is unreachable."
    carries = actions.Refresh


class Reload(Endpoint):
    method = "POST"
    path = "/reload"
    query = Object(container_id=Field(RUN_ID, required=False, does="reloads this container's sidecar only; every sidecar when absent"))
    answers = (Answer(201, RELOADED, "{ok: true, reloaded}: how many connected sidecars were told"),)
    source = (APP + "reload", "groom/groom/sidecar_hub.py")
    does = "Tells the connected sidecars to reload. A container with no sidecar counts for nothing."
    carries = actions.Reload


ALL = (ReadRepos, ReadLive, ReadHistory, RetryHistory, Refresh, Reload)
