"""The teams service, which speaks gRPC: a record, the state that keeps it and the three things the service does."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ostler.book import Action, Actor, Code, Collection, Create, Delete, Fixture, Rule, Show, State, Transaction, Unique


@dataclass(frozen=True)
class TeamRecord:
    id: str
    name: str


@dataclass(frozen=True)
class TeamList:
    teams: tuple[TeamRecord, ...]


@dataclass(eq=False)
class Team(Fixture):
    name: str | None = None
    id: str | None = None

    def __str__(self) -> str:
        return self.name or "(unnamed)"


class Teaming(State):
    teams = Collection(TeamRecord, Unique("id"))

    def rows(self) -> tuple[TeamList, ...]:
        return (TeamList(tuple(self.teams)),)


not_found = Rule[Team, Teaming]("no such team", lambda a, s, by: a.id not in s.teams, Code.NOT_FOUND)


class AddTeam(Action[Team, Teaming]):
    accept = Team

    @staticmethod
    def reduce(a: Team, s: Teaming, by: Actor | None) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.teams, TeamRecord(a.id or "", a.name or "")))


class RemoveTeam(Action[Team, Teaming]):
    accept = Team
    rules = (not_found,)

    @staticmethod
    def reduce(a: Team, s: Teaming, by: Actor | None) -> Transaction:
        return Transaction(Delete(s.teams, a.id))


class ListTeams(Action[object, Teaming]):
    @staticmethod
    def reduce(a: object, s: Teaming, by: Actor | None) -> Show:
        return Show(TeamList(tuple(s.teams)))
