from datetime import date

from ostler.book import Journey, Needs

from ..endpoints import ReadGatewayTeam
from ..foreign import TEAM


class ATeamIsAtTheGateway(Journey):
    """Ops is a team. The gateway reads it from the teams service under a label."""

    team = Needs(TEAM, "listed")
    given = (team,)

    def steps(self, today: date):
        yield ReadGatewayTeam(self.team)
