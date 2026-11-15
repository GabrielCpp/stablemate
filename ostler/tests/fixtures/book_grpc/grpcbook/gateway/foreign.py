"""The team as the gateway knows it: a record the teams service owns, and the one way the gateway reads its answer."""

from __future__ import annotations

from typing import Any

from ostler.book import Code, Foreign

from ..teams.model import TeamRecord

TEAM = Foreign(TeamRecord, owner="grpcbook.teams", reads=("id", "name"))

AS_IS = {Code.NOT_FOUND: 404, Code.PERMISSION_DENIED: 403}


def labelled(read: Any) -> dict[str, Any]:
    """the team the owner reads, under its id and its name as a label"""
    return {"id": read["id"], "label": read["name"]}
