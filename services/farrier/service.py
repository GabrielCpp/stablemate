"""farrier, as ostler loads it."""

from __future__ import annotations

from ostler.book import App, Environment, Service, Stack

from .commands import ALL as ENDPOINTS, Look
from .journeys import ALL as JOURNEYS
from .model import FileRecord, Repo
from .model.lifecycle import MATRICES
from .surface import FarrierCli

LOCAL = Environment("local", {})

service = Service[Repo](
    name="farrier",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Repo,
    surface=FarrierCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(Look(),),
    records=(FileRecord,),
    app=App(roots=("farrier/farrier",), verified="VERIFIED", ignore=("farrier/farrier/__init__.py", "farrier/farrier/README.md", "farrier/farrier/_vendor/*")),
)
