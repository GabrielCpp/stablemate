"""The `author` distribution's composition root — nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.author.epic_edit import EpicEdit
from workhorse_workflows.author.epic_edit.nodes import blueprint as epic_edit_blueprint
from workhorse_workflows.author.epic_author import EpicAuthor
from workhorse_workflows.author.epic_author.nodes import blueprint as epic_author_blueprint
from workhorse_workflows.author.epic_split import EpicSplit
from workhorse_workflows.author.epic_split.nodes import blueprint as epic_split_blueprint
from workhorse_workflows.author.finalize import Finalize
from workhorse_workflows.author.main.flow import Author
from workhorse_workflows.author.main.nodes import blueprint
from workhorse_workflows.author.milestone import Milestone
from workhorse_workflows.author.milestone.nodes import blueprint as milestone_blueprint
from workhorse_workflows.author.parity_surveyor import ParitySurveyor
from workhorse_workflows.author.shared.survey.blueprint import blueprint as survey_blueprint
from workhorse_workflows.author.story_edit import StoryEdit
from workhorse_workflows.author.story_edit.nodes import blueprint as story_edit_blueprint
from workhorse_workflows.author.story_author import StoryAuthor
from workhorse_workflows.author.story_author.nodes import blueprint as story_author_blueprint
from workhorse_workflows.author.story_split import StorySplitFlow
from workhorse_workflows.author.story_split.nodes import blueprint as story_split_blueprint
from workhorse_workflows.author.surveyor import Surveyor

workflow = (
    Registry("author", package=__package__)
    .add_blueprints(
        blueprint,
        survey_blueprint,
        epic_edit_blueprint,
        story_edit_blueprint,
        milestone_blueprint,
        epic_split_blueprint,
        epic_author_blueprint,
        story_author_blueprint,
        story_split_blueprint,
    )
    .add_flows(
        surveyor=Surveyor,
        **{
            "parity-surveyor": ParitySurveyor,
            "epic-edit": EpicEdit,
            "story-edit": StoryEdit,
            "milestone": Milestone,
            "epic-split": EpicSplit,
            "epic-author": EpicAuthor,
            "story-split": StorySplitFlow,
            "story-author": StoryAuthor,
            "finalize": Finalize,
        },
    )
    .stub_agents(
        {
            "review-epics": {"status": "approved"},
            "build-milestone": {"status": "complete"},
            "review-epic-split": {"status": "approved"},
            "rework-epic-split": {"status": "complete"},
            "resolve-epic-split": {"decision": "answered"},
            "write-epic": {"status": "complete"},
            "split-stories": {"status": "complete"},
            "design-mockup": {"status": "skipped"},
            "write-story": {"status": "written"},
            "audit-story": {"status": "passed"},
            "review-coverage": {"status": "ok"},
            "resolve-operator": {"decision": "answered"},
            "resolve-integrity": {"decision": "answered"},
            "plan-units": {"status": "complete"},
            "assess-unit": {"status": "assessed"},
            "assess-parity-unit": {"status": "assessed"},
            "fix-record": {"status": "fixed"},
            "partition-findings": {"status": "complete"},
            "plan-epic-edit": {
                "status": "complete",
                "delete_epic": True,
            },
            "refine-epic-edit-plan": {
                "status": "complete",
                "delete_epic": True,
            },
            "review-epic-edit-plan": {"status": "approved"},
            "rewrite-epic-edit": {"status": "complete"},
        }
    )
)
main = console_script(workflow.entry_point(Author))

__all__ = ["Author", "main", "workflow"]
