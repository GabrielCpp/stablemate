from datetime import date

from ostler.book import Journey, Needs

from ..endpoints import FinishFromGateway
from ..foreign import TEAM


class ATeamIsFinishedFromTheGateway(Journey):
    """Ops is finished from the gateway. The teams service then holds no such team."""

    team = Needs(TEAM, "listed")
    given = (team,)

    def steps(self, today: date):
        yield FinishFromGateway(self.team)
