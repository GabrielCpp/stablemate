"""The `author` distribution's composition root — nothing else.

`workhorse-author` is bound here (`workflows/pyproject.toml`), and this module is what the
script imports: the registry that names the distribution, folds in the node blueprints,
lists the flows a caller can run by name, and declares what a `--dry-run` gets back from
each prompt. The graph a bare `run` starts is a flow package like the other four —
[`main/`](main) — so the five sit side by side and this file stays a table of contents.

The registry declares its own `package`, and that is load-bearing rather than tidy: it is
the root every prompt path renders against (`surveyor/prompts/assess-unit.md`) and the
name the repo-flavor lookup uses (`.agents/flavors/author/`). Inferred from the entry
class instead, both would follow `Author` into `main/` and every sibling flow's prompts
would fall outside the loader.
"""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.author.epic_edit import EpicEdit
from workhorse_workflows.author.epic_edit.nodes import blueprint as epic_edit_blueprint
from workhorse_workflows.author.main import Author
from workhorse_workflows.author.main.nodes import blueprint
from workhorse_workflows.author.parity_surveyor import ParitySurveyor
from workhorse_workflows.author.shared.survey.blueprint import blueprint as survey_blueprint
from workhorse_workflows.author.story_edit import StoryEdit
from workhorse_workflows.author.story_edit.nodes import blueprint as story_edit_blueprint
from workhorse_workflows.author.surveyor import Surveyor

workflow = (
    Registry("author", package=__package__)
    .add_blueprints(blueprint, survey_blueprint, epic_edit_blueprint, story_edit_blueprint)
    .add_flows(
        surveyor=Surveyor,
        **{
            "parity-surveyor": ParitySurveyor,
            "epic-edit": EpicEdit,
            "story-edit": StoryEdit,
        },
    )
    .stub_agents(
        {
            "review-epics": {"status": "approved"},
            "write-epic": {"status": "complete"},
            "split-stories": {"status": "complete"},
            "design-mockup": {"status": "skipped"},
            "write-story": {"status": "written"},
            "audit-story": {"status": "passed"},
            "review-coverage": {"status": "ok"},
            "resolve-operator": {"decision": "answered"},
            "resolve-integrity": {"decision": "answered"},
            # The sub-flows' turns. Keyed by prompt STEM, so every flow's own copy of an
            # envelope answers to one entry — `main/prompts/resolve-operator.md` and
            # `surveyor/prompts/resolve-operator.md` share the one above, and
            # `epic_edit/prompts/write-story.md` shares `write-story`. That is what they
            # want here: a stand-in reply is per *role*, and a copy that diverged far
            # enough to need its own would be a different role.
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
