"""Whether one story needs a visual mockup before it is written."""
from __future__ import annotations

import logging

from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.story_author.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import MockupGate


@blueprint.node
def check_mockup_needed(
    logger: logging.Logger, story_id: str = "", repo_dir: str = ""
) -> MockupGate:
    """A story needs a mockup exactly when one of its services is a UI book."""
    story_ref = story_id.strip()
    try:
        okf = Ostler(survey_repo_root(repo_dir))
        found = okf.graph.find_story(story_ref)
        if found is None:
            raise WorkflowFailed(f"story id '{story_ref}' is absent from the knowledge graph")
        _, story = found
        ui = sorted(okf.ui_services(story.services))
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkflowFailed(
            f"cannot decide whether story id '{story_ref}' needs a mockup: {exc}"
        ) from exc
    services = list(story.services)
    if ui:
        logger.info("story id '%s' changes the UI service(s) %s", story_ref, ", ".join(ui))
        return MockupGate(
            services=services,
            evidence="the story changes the UI service(s): " + ", ".join(ui),
        )
    logger.info("story id '%s' changes no UI service (%s)", story_ref, ", ".join(services))
    return MockupGate(
        required=False,
        services=services,
        evidence=f"the story's services are {', '.join(services) or 'none'}: no UI service",
    )


__all__ = ["check_mockup_needed"]
