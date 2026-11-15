"""The teams service, as ostler loads it."""

from ostler.book import Environment, Service, Stack

from .endpoints import ALL, ListTeams
from .lifecycle import MATRICES
from .model import Teaming
from .surface import TeamsSurface

LOCAL = Environment("local", {"teams": "teams.local:50051"})

service = Service[Teaming](
    name="teams",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Teaming,
    surface=TeamsSurface,
    journeys=(),
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ALL,
    matrices=MATRICES,
    watch=(ListTeams(),),
    words={e.__name__: e for e in ALL},
)
