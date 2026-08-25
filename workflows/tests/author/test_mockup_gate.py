"""The mockup gate, decided from seed tags rather than from a model turn.

`check_mockup_needed` is the whole of the decision, so the table below is the contract:
`frontend` present anywhere in the story's covered seeds mandates a design turn, an
explicit tag set without it skips one, and anything unknown fails closed.

Nothing is stubbed — the graph is a real ostler repo built through `crud`, which is also
what validates the layer vocabulary these tests write.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from ostler import Ostler

from workhorse_workflows.author.main.nodes.stories import check_mockup_needed

EPIC = "accounts"


def _epic(root: Path, seeds: dict[str, list[str]], covers: list[str]) -> None:
    """One epic, one story covering `covers`, with each seed tagged as given."""
    okf = Ostler(root)
    okf.create_epic(EPIC, "Accounts", prefix="acme")
    for seed_id, layers in seeds.items():
        meta = {"layers": layers, "services": ["api-service"]} if layers else {}
        res = okf.add_seed(EPIC, seed_id, status="researched", summary=seed_id, meta=meta)
        assert res.ok, res.message
    assert okf.create_story(EPIC, "01-sign-in", "Sign in", covers=covers).ok


@pytest.mark.parametrize(
    ("seeds", "required", "layers"),
    [
        ({"s1": ["frontend"]}, True, ["frontend"]),
        ({"s1": ["backend"]}, False, ["backend"]),
        ({"s1": ["backend", "infra"]}, False, ["backend", "infra"]),
        ({"s1": ["frontend", "backend"]}, True, ["frontend", "backend"]),
        # The union runs over every covered seed, so one frontend seed carries the story.
        ({"s1": ["backend"], "s2": ["frontend"]}, True, ["backend", "frontend"]),
        # Unclassified is unknown, not "no frontend": an untagged seed costs a wasted design
        # turn rather than silently dropping a screen nobody designed.
        ({"s1": []}, True, []),
        ({"s1": ["backend"], "s2": []}, True, ["backend"]),
    ],
)
def test_the_gate_is_the_union_of_the_covered_seeds_layers(
    logger: logging.Logger, repo: Path, seeds: dict[str, list[str]],
    required: bool, layers: list[str],
) -> None:
    _epic(repo, seeds, covers=list(seeds))

    gate = check_mockup_needed(logger, story_slug="01-sign-in", repo_dir=str(repo))

    assert gate.required is required, gate.evidence
    assert gate.layers == layers
    assert gate.evidence, "the decision must say which seeds drove it"


def test_a_story_the_graph_cannot_resolve_still_gets_a_mockup(
    logger: logging.Logger, repo: Path
) -> None:
    """Fail closed on absence. A missing story is not a backend story."""
    _epic(repo, {"s1": ["backend"]}, covers=["s1"])

    gate = check_mockup_needed(logger, story_slug="99-ghost", repo_dir=str(repo))

    assert gate.required is True
    assert "absent from the knowledge graph" in gate.evidence


def test_the_services_of_the_covered_seeds_travel_with_the_decision(
    logger: logging.Logger, repo: Path
) -> None:
    """The tags land in the checkpoint, so why a turn was skipped is legible after the run."""
    _epic(repo, {"s1": ["backend"]}, covers=["s1"])

    gate = check_mockup_needed(logger, story_slug="01-sign-in", repo_dir=str(repo))

    assert gate.services == ["api-service"]
