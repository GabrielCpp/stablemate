"""One story's mockup gate, and the operator's notes on it."""
from __future__ import annotations

import logging

from ostler import Ostler
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.kit import poll_run_inbox
from workhorse_workflows.author.shared.schemas.main import Feedback, MockupGate

MOCKUP_LAYER = "frontend"
MOCKUP_REQUIRED = "required"
MOCKUP_PRESERVE = "preserve"


@blueprint.node
def check_mockup_needed(
    logger: logging.Logger, story_slug: str = "", repo_dir: str = ""
) -> MockupGate:
    """Design a mockup only for new or materially changed visual behavior."""
    try:
        graph = Ostler(survey_repo_root(repo_dir)).graph
    except (OSError, ValueError, RuntimeError) as exc:
        return MockupGate(evidence=f"knowledge graph unavailable: {exc}")
    found = graph.find_story(story_slug.strip())
    if found is None:
        return MockupGate(evidence="story is absent from the knowledge graph")
    epic, story = found
    if not story.seed_items:
        return MockupGate(evidence="story has no covered seed evidence")

    seeds = {seed.id: seed for seed in epic.seeds}
    layers: list[str] = []
    services: list[str] = []
    untagged: list[str] = []
    required: list[str] = []
    preserved: list[str] = []
    unclassified_design: list[str] = []
    for seed_id in story.seed_items:
        seed = seeds.get(seed_id)
        if seed is None or not seed.layers:
            untagged.append(seed_id)
            continue
        layers += [t for t in seed.layers if t not in layers]
        services += [t for t in seed.services if t not in services]
        if MOCKUP_LAYER not in seed.layers:
            continue
        if seed.design == MOCKUP_REQUIRED:
            required.append(seed_id)
        elif seed.design == MOCKUP_PRESERVE:
            preserved.append(seed_id)
        else:
            unclassified_design.append(
                f"{seed_id} ({seed.design or 'missing'})"
            )

    if untagged:
        return MockupGate(
            layers=layers, services=services,
            evidence="covered seed(s) carry no `layers:`, so a frontend surface cannot be "
                     "ruled out: " + ", ".join(untagged),
        )
    if required:
        return MockupGate(
            layers=layers, services=services,
            evidence="frontend seed(s) require visual design: " + ", ".join(required),
        )
    if unclassified_design:
        return MockupGate(
            layers=layers, services=services,
            evidence="frontend seed(s) have no valid `design:` classification: "
                     + ", ".join(unclassified_design),
        )
    if preserved:
        logger.info(
            "story '%s' preserves existing frontend design (%s)", story_slug, ", ".join(preserved)
        )
        return MockupGate(
            required=False, layers=layers, services=services,
            evidence="frontend seed(s) preserve the existing visual contract: "
                     + ", ".join(preserved),
        )
    logger.info("story '%s' touches no frontend layer (%s)", story_slug, ", ".join(layers))
    return MockupGate(
        required=False, layers=layers, services=services,
        evidence=f"covered seeds are tagged {', '.join(layers)} only — no {MOCKUP_LAYER} work",
    )


@blueprint.node
def check_story_feedback(logger: logging.Logger, run_dir: str = "") -> Feedback:
    """Poll the operator's run-scoped inbox for un-consumed feedback."""
    polled = poll_run_inbox(run_dir, reply_text="folded into a story rework")
    if polled is None:
        logger.info("no outstanding inbox messages")
        return Feedback()
    content, scope = polled
    logger.info("feedback present (scope=%s)", scope)
    return Feedback(present=True, scope=scope, content=content)


__all__ = ["check_mockup_needed", "check_story_feedback"]
