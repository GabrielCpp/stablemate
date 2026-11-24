from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look
from ..fixtures import nothing
from ..graph import (BacklogAdopt, BacklogAdd, BacklogDropWithoutReason, BacklogList, BacklogPrune, CreateMilestone, CreateSpec,
                     CreateSpecOfUnknownStory, MilestoneEpicsBoth, MilestoneEpicsFirst, MilestoneEpicsUnknown,
                     MilestoneSourceItem, ScaffoldArtifact, TemplateApply, TemplateDelete, TemplateFind, TemplateNew, VetArtifact)


class WriteTheDocuments(Journey):
    """A planner writes the documents around the plan. They open a milestone, list its epics and the backlog items it owns,
    file a record on the Register and close it, file a decision, type a story's spec and scaffold its artifact, and declare
    a template, apply it and delete it. Each command that finds its document already there is refused or reports it."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            MilestoneEpicsFirst(nothing()),
            CreateMilestone(nothing()),
            CreateMilestone(nothing()),
            MilestoneEpicsFirst(nothing()),
            Look(),
            MilestoneEpicsUnknown(nothing()),
            MilestoneEpicsBoth(nothing()),
            MilestoneSourceItem(nothing()),
            Look(),
            BacklogList(nothing()),
            BacklogPrune(nothing()),
            BacklogAdd(nothing()),
            BacklogAdd(nothing()),
            BacklogList(nothing()),
            BacklogDropWithoutReason(nothing()),
            BacklogPrune(nothing()),
            BacklogPrune(nothing()),
            BacklogList(nothing()),
            Look(),
            BacklogAdopt(nothing()),
            BacklogAdopt(nothing()),
            CreateSpecOfUnknownStory(nothing()),
            CreateSpec(nothing()),
            CreateSpec(nothing()),
            VetArtifact(nothing()),
            ScaffoldArtifact(nothing()),
            ScaffoldArtifact(nothing()),
            VetArtifact(nothing()),
            Look(),
            TemplateFind(nothing()),
            TemplateApply(nothing()),
            TemplateNew(nothing()),
            TemplateNew(nothing()),
            TemplateFind(nothing()),
            TemplateApply(nothing()),
            Look(),
            TemplateDelete(nothing()),
            TemplateDelete(nothing()),
            Look(),
        )
