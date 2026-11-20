from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import LayoutApply, Look, PathEpic
from ..events import CopyInAnOldEpic
from ..fixtures import nothing, path_epic


class MoveAnOldShelf(Journey):
    """A planner copies in an epic from a shelf in the old layout, folder 0004-legacy with its story folder named by
    slug. ostler refuses to read the plan and names the command that fixes it. They run `ostler layout apply`, which
    records the epic's slug and renames both folders to their ids. The epic's slug and its old name then both find its
    id folder, and a second apply finds nothing to move."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CopyInAnOldEpic(),
            Look(),
            PathEpic(path_epic("legacy")),
            LayoutApply(nothing()),
            Look(),
            PathEpic(path_epic("legacy")),
            PathEpic(path_epic("0004-legacy")),
            LayoutApply(nothing()),
        )
