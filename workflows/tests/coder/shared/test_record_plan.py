"""A plan that names no service takes the services its story declares."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from workhorse_workflows.coder.shared.plan import build_dispatch_list, record_plan
from workhorse_workflows.kit import resolve_workspace

SPEC = "spec"
SERVICES = {
    "api": {"path": "api", "type": "go"},
    "web": {"path": "web", "type": "ts"},
}
NAMED = {
    "services": [{"repo": "acme", "path": "web", "type": "ts", "plan_file": "plan.md"}],
    "implementation_order": [],
}
WARNING = "the plan named no service; using the story's declared services: "


@pytest.fixture
def acme(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    write(repo / "agents.yml", yaml.safe_dump({"repo": {"name": "acme"}, "services": SERVICES}))
    for entry in SERVICES.values():
        (repo / entry["path"]).mkdir()
    write(repo / SPEC / "plan.md", "# Plan\n")
    return repo


def record(logger: logging.Logger, acme: Path, plan: dict, story_services: list[str] | None):
    return record_plan(
        logger, plan, SPEC, repo_dir=str(acme), story_services=story_services
    )


def test_an_empty_plan_takes_the_one_service_its_story_declares(
    logger: logging.Logger, acme: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)

    result = record(logger, acme, {}, ["api"])

    assert result.status == "valid", result.errors
    (service,) = result.document["services"]
    assert (service["repo"], service["path"], service["type"]) == ("acme", "api", "go")
    dispatch = build_dispatch_list(
        result.document, resolve_workspace("", str(acme)), fallback=True
    )
    assert [entry["service"] for entry in dispatch] == ["acme::api"]
    assert dispatch[0]["service_path"] == "api"
    assert WARNING + "api" in caplog.text


def test_an_empty_plan_takes_two_declared_services_in_the_storys_order(
    logger: logging.Logger, acme: Path
) -> None:
    result = record(logger, acme, {}, ["web", "api"])

    assert [svc["path"] for svc in result.document["services"]] == ["web", "api"]


def test_a_declared_name_that_does_not_resolve_is_left_out_and_warned_about(
    logger: logging.Logger, acme: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)

    result = record(logger, acme, {}, ["api", "ghost"])

    assert [svc["path"] for svc in result.document["services"]] == ["api"]
    assert "ghost" in caplog.text


def test_when_no_declared_name_resolves_the_record_is_the_empty_one(
    logger: logging.Logger, acme: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    before = record(logger, acme, {}, None)

    after = record(logger, acme, {}, ["ghost"])

    assert after == before
    assert after.document["services"] == []
    assert "ghost" in caplog.text


def test_a_plan_that_names_its_services_is_recorded_unchanged(
    logger: logging.Logger, acme: Path
) -> None:
    result = record(logger, acme, NAMED, ["api", "web"])

    assert result.document == record(logger, acme, NAMED, None).document
    assert [svc["path"] for svc in result.document["services"]] == ["web"]
