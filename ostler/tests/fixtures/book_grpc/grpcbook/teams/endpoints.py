"""The teams service's calls, one Rpc class each."""

from ostler.book import Answer, Code, Field, Id, List, Object, Rpc, STATUS, Str

from .model import AddTeam as AddTeamAction, ListTeams as ListTeamsAction, RemoveTeam as RemoveTeamAction, TeamRecord

TEAM = Object("Team", id=Field(Id(TeamRecord, Str()), does="assigned by the service"), name=Field(Str()))
NEW = Object("NewTeam", name=Field(Str()))
BY_ID = Object("TeamId", id=Field(Id(TeamRecord, Str())))
TEAMS = Object("Teams", teams=Field(List(TEAM), does="every team, in the order they were added"))
NOT_FOUND = Answer(Code.NOT_FOUND, STATUS, "no such team")


class AddTeam(Rpc):
    rpc = "acme.Teams/Add"
    body = NEW
    answers = (Answer(Code.OK, TEAM, "the team, with the id the service gave it", creates="id"),)
    source = ("fake_grpcurl::add",)
    does = "Adds one team."
    carries = AddTeamAction


class GetTeam(Rpc):
    rpc = "acme.Teams/Get"
    body = BY_ID
    answers = (Answer(Code.OK, TEAM, "the team"), NOT_FOUND)
    source = ("fake_grpcurl::get",)
    does = "Reads one team."
    carries = None


class RemoveTeam(Rpc):
    rpc = "acme.Teams/Remove"
    body = BY_ID
    answers = (Answer(Code.OK, None, "the team is gone"), NOT_FOUND)
    source = ("fake_grpcurl::remove",)
    does = "Removes one team."
    carries = RemoveTeamAction


class ListTeams(Rpc):
    rpc = "acme.Teams/List"
    answers = (Answer(Code.OK, TEAMS, "every team"),)
    source = ("fake_grpcurl::listing",)
    does = "Lists every team."
    carries = ListTeamsAction


class Reset(Rpc):
    rpc = "acme.Teams/Reset"
    answers = (Answer(Code.OK, None, "no team is kept"),)
    source = ("fake_grpcurl::reset",)
    does = "Puts the service back to no teams, for a test."
    carries = None


ALL = (AddTeam, GetTeam, RemoveTeam, ListTeams, Reset)
