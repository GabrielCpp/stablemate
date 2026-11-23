from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look
from ..fixtures import nothing
from ..graph import (BuildIndex, CleanQaScratch, Doctor, EditRename, EditRenameUnknown, EnvCheck, EnvList, EnvListAll, EnvPrune, EnvSchema, EvictCache,
                     ListArtifactKinds, ListEpicRows, ListRepoStoryRows, ListStoryRows, ListUnknownRepoRows, NextEpic, NextStory, QueryCovering, SearchPlan,
                     ShowChecks)


class ReadThePlan(Journey):
    """A planner looks at the plan and changes nothing. They check its integrity, list its epics and stories and the stories of one repo, search it,
    build the index, ask which epic and which story come next and which stories cover a seed, read the checks a QA plan
    may use, preview a rename, and ask the stack commands what they hold. The files stay as they were."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            Look(),
            Doctor(nothing()),
            ListEpicRows(nothing()),
            ListStoryRows(nothing()),
            ListRepoStoryRows(nothing()),
            ListUnknownRepoRows(nothing()),
            SearchPlan(nothing()),
            BuildIndex(nothing()),
            QueryCovering(nothing()),
            NextEpic(nothing()),
            NextStory(nothing()),
            ShowChecks(nothing()),
            EvictCache(nothing()),
            EditRename(nothing()),
            EditRenameUnknown(nothing()),
            ListArtifactKinds(nothing()),
            CleanQaScratch(nothing()),
            EnvSchema(nothing()),
            EnvCheck(nothing()),
            EnvList(nothing()),
            EnvListAll(nothing()),
            EnvPrune(nothing()),
            Look(),
        )
