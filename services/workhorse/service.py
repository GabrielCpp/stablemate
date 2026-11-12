"""The workhorse loop runner as a service the book can play."""

from __future__ import annotations

from ostler.book import Because, Environment, Service, Stack, Unseen

from .events import FinishARun, ParkARun
from .commands import ALL as ENDPOINTS, Look, Replay
from .journeys import ALL as JOURNEYS
from .model import FileRecord, Runs
from .model.lifecycle import MATRICES
from .surface import WorkhorseCli

LOCAL = Environment("local", {})

service = Service[Runs](
    name="workhorse",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Runs,
    surface=WorkhorseCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(Look(),),
    records=(FileRecord,),
    outside=(ParkARun, FinishARun),
    unseen=(
        Unseen(
            Replay,
            "inputs",
            Because.RUNTIME,
            "A replay that succeeds re-runs a recorded agent turn against a live backend, which the sandbox does not provide, so only its refusals are played.",
        ),
    ),
)
