"""What groom refuses, in its own words."""

from __future__ import annotations

from ostler.book import Rule

from ..fixtures import Look, Reply
from .state import Dashboard, GroomApp


def valid_cursor(cursor: str | None) -> bool:
    """A cursor is empty, or three fields apart by bars: a time, a rank and an id."""
    if not cursor:
        return True
    parts = cursor.split("|")
    if len(parts) != 3:
        return False
    try:
        float(parts[0])
        int(parts[1])
        int(parts[2])
    except ValueError:
        return False
    return True


bad_cursor = Rule[Look, GroomApp](
    "not a cursor of this run's records",
    lambda a, s, by: not valid_cursor(a.before),
    400,
    why="a page of records resumes from the cursor the page before it returned, so any other text is a mistake the caller made",
)

no_archive = Rule[Look, GroomApp](
    "no archived run {run_id}",
    lambda a, s, by: True,
    404,
    why="a run is archived once groom has its telemetry, and the book's groom is never sent any, so no run is archived",
)

no_entry = Rule[Look, GroomApp](
    "no such step or gate",
    lambda a, s, by: True,
    404,
    why="a step or a gate of a run is read from its stored telemetry, and the book's groom holds none",
)

no_turn = Rule[Look, GroomApp](
    "no such turn",
    lambda a, s, by: True,
    404,
    why="a turn is read from a run's stored telemetry, and the book's groom holds none",
)

no_queue = Rule[Look, GroomApp](
    "no such queue: {queue}",
    lambda a, s, by: True,
    404,
    why="a queue exists when the home config names it, and the book's groom runs in a home that names none",
)

workspace_unreachable = Rule[Reply, Dashboard](
    "unknown workspace volume for this container",
    lambda a, s, by: True,
    400,
    why="groom writes an answer into the gate file in the run's workspace, and a pushed run gives groom none",
)
