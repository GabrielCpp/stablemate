"""paddock, as ostler loads it."""

from __future__ import annotations

from ostler.book import App, Because, Environment, Service, Stack, Unseen

from .commands import ALL as ENDPOINTS, Look, SandboxRun
from .journeys import ALL as JOURNEYS
from .model import FileRecord, Root, Round
from .model.lifecycle import MATRICES
from .surface import PaddockCli

LOCAL = Environment("local", {})

service = Service[Root](
    name="paddock",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Root,
    surface=PaddockCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(Look(),),
    records=(FileRecord, Round),
    unseen=(
        Unseen(SandboxRun, "0", Because.OUTSIDE, "a call that passes every refusal starts docker, whose image and daemon the book's sandbox does not hold"),
        Unseen(SandboxRun, "inputs", Because.OUTSIDE, "every call the model accepts ends in docker, so no call the run saw succeed carries a class"),
    ),
    app=App(roots=("paddock/paddock",), verified="VERIFIED",
            ignore=("paddock/paddock/__init__.py", "paddock/paddock/README.md", "paddock/paddock/tasks/__init__.py",
                    "paddock/paddock/_vendor/*")),
)
