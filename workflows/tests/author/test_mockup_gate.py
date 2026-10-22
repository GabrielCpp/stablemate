"""The mockup gate, decided from the story's services rather than from a model turn."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from ostler import Ostler
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.author.story_author.nodes.mockup import check_mockup_needed
from workhorse_workflows.author.story_split.nodes.services import derive_story_services

EPIC = "accounts"


def _books(root: Path) -> None:
    screens = root / "docs/services/web-app/gui/screens"
    screens.mkdir(parents=True)
    (screens / "sign-in.md").write_text(
        "---\ntype: screen\nslug: sign-in\ntitle: Sign in\n---\n# Sign in\n\n"
        "- route: `/sign-in`\n- requires: none\n- params: none\n\n"
        "## Screen states\n\n### Loaded\n- shows: none\n",
        encoding="utf-8",
    )
    ops = root / "docs/services/web-app/ops"
    ops.mkdir(parents=True)
    (ops / "stack.md").write_text(
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: web\n- entry-url: http://localhost:3000\n"
        "- surfaces: [sign-in](../gui/screens/sign-in.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `serve`\n",
        encoding="utf-8",
    )
    (root / "docs/services/api-service").mkdir(parents=True)


def _epic(
    logger: logging.Logger, root: Path, seeds: dict[str, list[str]], covers: list[str]
) -> None:
    _books(root)
    okf = Ostler(root)
    okf.create_epic(EPIC, "Accounts", prefix="acme")
    for seed_id, services in seeds.items():
        meta: dict[str, object] = {"services": services} if services else {}
        res = okf.add_seed(EPIC, seed_id, status="researched", summary=seed_id, meta=meta)
        assert res.ok, res.message
    assert okf.create_story(EPIC, "01-sign-in", "Sign in", covers=covers).ok
    epic = str(Ostler(root).list("epic")[0]["name"])
    derive_story_services(logger, epic, repo_dir=str(root))


@pytest.mark.parametrize(
    ("seeds", "required", "services"),
    [
        ({"s1": ["web-app"]}, True, ["web-app"]),
        ({"s1": ["api-service"]}, False, ["api-service"]),
        ({"s1": ["web-app", "api-service"]}, True, ["api-service", "web-app"]),
        ({"s1": ["api-service"], "s2": ["web-app"]}, True, ["api-service", "web-app"]),
        ({"s1": []}, False, []),
    ],
)
def test_the_gate_is_the_union_of_the_covered_seeds_services(
    logger: logging.Logger, repo: Path, seeds: dict[str, list[str]],
    required: bool, services: list[str],
) -> None:
    _epic(logger, repo, seeds, covers=list(seeds))

    gate = check_mockup_needed(logger, story_slug="01-sign-in", repo_dir=str(repo))

    assert gate.required is required, gate.evidence
    assert gate.services == services
    assert gate.evidence, "the decision must say which services drove it"


def test_a_story_the_graph_cannot_resolve_fails_the_run(
    logger: logging.Logger, repo: Path
) -> None:
    _epic(logger, repo, {"s1": ["api-service"]}, covers=["s1"])

    with pytest.raises(WorkflowFailed, match="absent from the knowledge graph"):
        check_mockup_needed(logger, story_slug="99-ghost", repo_dir=str(repo))


def test_an_api_only_story_needs_no_mockup_whatever_the_seed_says(
    logger: logging.Logger, repo: Path
) -> None:
    _epic(logger, repo, {"worker": ["api-service"]}, covers=["worker"])
    Ostler(repo).add_seed(
        EPIC, "worker", status="researched", summary="worker",
        meta={"services": ["api-service"], "design": "required", "layers": ["frontend"]},
    )

    gate = check_mockup_needed(logger, story_slug="01-sign-in", repo_dir=str(repo))

    assert gate.required is False, gate.evidence
