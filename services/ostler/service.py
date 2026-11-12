"""ostler, as ostler loads it."""

from __future__ import annotations

from ostler.book import Environment, Service, Stack

from .commands import ALL as ENDPOINTS, Look
from .journeys import ALL as JOURNEYS
from .model import FileRecord, Plan
from .model.lifecycle import MATRICES
from .surface import OstlerCli

LOCAL = Environment("local", {})

service = Service[Plan](
    name="ostler",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Plan,
    surface=OstlerCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(Look(),),
    records=(FileRecord,),
)
