"""The gateway's one read and one write over the teams service, which speaks gRPC. Neither carries an action."""

from ostler.book import Answer, Endpoint, Field, Object, Passes, Reaches, Str

from ..teams.endpoints import GetTeam, RemoveTeam
from .foreign import AS_IS, labelled

ERROR = Object("Error", error=Field(Str(), does="the reason"))
NOT_FOUND = Answer(404, ERROR, "the teams service has no such team")
BY_ID = Object(id=Field(Str(), does="the team's id"))
LABELLED = Object("Labelled", id=Field(Str(), does="the team's id"), label=Field(Str(), does="the team's name"))


class ReadGatewayTeam(Endpoint):
    method = "GET"
    path = "/gateway/{id}"
    params = BY_ID
    answers = (Answer(200, LABELLED, "the team under a label"), NOT_FOUND)
    source = ("gateway::read",)
    does = "Reads one team from the teams service."
    carries = None
    passes = Passes(asks=lambda step: GetTeam(step.of), derived=labelled, refused=AS_IS)


class FinishFromGateway(Endpoint):
    method = "POST"
    path = "/gateway/{id}/done"
    params = BY_ID
    answers = (Answer(204, None, "the teams service removed the team"), NOT_FOUND)
    source = ("gateway::done",)
    does = "Removes one team, which the teams service does on its own call."
    carries = None
    reaches = Reaches(lambda step: RemoveTeam(step.of), refused=AS_IS)
