"""One matrix: a team is listed or it is not. The scene reaches it by adding one."""

from __future__ import annotations

from datetime import date

from ostler.book import Axes, Scene

from .endpoints import AddTeam
from .model import Team, Teaming, TeamRecord

TODAY = date(2026, 11, 4)

SCENES = (
    Scene("(none)", "no team is listed", lambda today: ()),
    Scene("listed", "'Ops' is listed", lambda today: (AddTeam(Team(name="Ops")),)),
)

MATRICES = (
    Axes[Teaming]("team", TODAY, SCENES, {}, lambda m: "listed" if len(m.teams) else "(none)",
                  state_of=lambda m, t: "listed" if isinstance(t, TeamRecord) else "(none)", entities=lambda m: m.teams),
)
