from datetime import date

from ostler.book import Journey, OwnerRefused

from ...teams.model import Team
from ..endpoints import ReadGatewayTeam


class TheTeamsServiceTurnsACallerAway(Journey):
    """A caller who asks for a team nobody added gets the teams service's refusal back from the gateway."""

    def steps(self, today: date):
        yield OwnerRefused(ReadGatewayTeam(Team(id="nobody-added-this")))
