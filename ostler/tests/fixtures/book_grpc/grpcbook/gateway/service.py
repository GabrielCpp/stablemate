"""The gateway, as a test loads it: a service that stores nothing and answers from the teams service. Its surface is built
by the test around the owner it is given, so the service holds none."""

from ostler.book import BookError, Environment, Service, Stack, Surface

from .endpoints import FinishFromGateway, ReadGatewayTeam
from .journeys import ALL as JOURNEYS
from .model import Gatewaying

LOCAL = Environment("local", {"gateway": "http://gateway.local"})


def surface(environment: Environment) -> Surface:
    raise BookError("the gateway answers in the process of the test, which builds its surface around the owner")


service = Service[Gatewaying](
    name="gateway",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Gatewaying,
    surface=surface,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=(ReadGatewayTeam, FinishFromGateway),
    words={"ReadGatewayTeam": ReadGatewayTeam, "FinishFromGateway": FinishFromGateway},
)
