"""A restart promise in a book must be a seam the frozen QA can actually pull."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

DATA = Path(__file__).parents[1]
APPS = sorted(
    p.parent for p in (DATA / "apps").glob("*/agents.yml") if p.parent.is_dir()
)


def _promises_restart(app: Path) -> bool:
    features = app / "docs" / "features"
    return any(
        re.search(r"\brestarts?\b", doc.read_text(encoding="utf-8"))
        for doc in features.rglob("*.md")
    )


def _qa_tools(app: Path) -> list[str]:
    data = yaml.safe_load((app / "agents.yml").read_text(encoding="utf-8")) or {}
    return list((data.get("qa") or {}).get("tools") or [])


@pytest.mark.parametrize("app", APPS, ids=lambda p: p.name)
def test_a_restart_promise_has_its_tool_opted_in(app: Path) -> None:
    if not _promises_restart(app):
        pytest.skip(f"{app.name}'s book never promises restart survival")
    assert "docker" in _qa_tools(app), (
        f"{app.name}'s book promises restart survival, but agents.yml never opts its QA "
        "into `docker` — a frozen plan pulling the seam would refuse at run time, and an "
        "authored one could not write the observation at all"
    )


@pytest.mark.parametrize("app", APPS, ids=lambda p: p.name)
def test_a_frozen_persistence_plan_pulls_the_seam(app: Path) -> None:
    plans = sorted((app / "docs" / "specs").rglob("qa_plan.py"))
    if not plans:
        pytest.skip(f"{app.name} freezes no QA plans — its rounds author them per trial")
    owning = [p for p in plans if re.search(r"persistence", p.read_text(encoding="utf-8"))]
    if not owning:
        pytest.skip(f"{app.name}'s frozen plans cover no persistence obligation")
    for plan in owning:
        text = plan.read_text(encoding="utf-8")
        assert "qa.tool(" in text or "restart=[" in text, (
            f"{plan.relative_to(DATA)} covers a persistence obligation without ever "
            "calling `qa.tool(` or declaring `@scenario(restart=[...])` — every read is "
            "request-scoped, so the restart-survival promise is asserted against process "
            "memory and the P8-class variant passes"
        )


GREENFIELD = sorted(p.parent.parent for p in (DATA / "apps").glob("*/docs/decisions"))
PINNED = DATA / "configs" / "opencode.toml"
READERS = ("jq",)


def _promises_durability(app: Path) -> bool:
    """Does any standing decision record for this app promise an on-disk store?"""
    return any(
        re.search(r"\bon-disk\b|\bpersist(s|ed)\b|\bdurable\b", record.read_text(encoding="utf-8"))
        for record in (app / "docs" / "decisions").glob("*.md")
    )


@pytest.mark.parametrize("app", GREENFIELD, ids=lambda p: p.name)
def test_a_durability_decision_has_a_reader_in_the_pinned_config(app: Path) -> None:
    """The other side of the restart gate, for the fixtures that author their own plans."""
    if not _promises_durability(app):
        pytest.skip(f"{app.name}'s decisions promise no on-disk durability")
    defined = tomllib.loads(PINNED.read_text(encoding="utf-8")).get("qa_tools", {})
    assert any(tool in defined for tool in READERS), (
        f"{app.name}'s decisions make an on-disk durability promise, but the pinned "
        f"config {PINNED.relative_to(DATA)} defines none of {READERS} — a QA plan cannot "
        "read the store file directly, so the round can only block on a criterion the "
        "decision asked for and the harness withheld"
    )
