"""A restart promise in a book must be a seam the frozen QA can actually pull.

`policy-desk`'s P8 is the defect this gate exists for: the book promises an accepted
write "survives a restart", the seeded variant satisfies every request-scoped read, and
the only observation that tells them apart is a real restart between the accepted write
and the re-read. That observation needs two opt-ins that live in different files and rot
independently:

* the app's `agents.yml` must allowlist a restart-capable QA tool (`docker`), because
  `ostler.qa.tools` is fail-closed — a plan that calls `qa.tool("docker")` in a repo that
  never opted in refuses at run time, which in a scored round arrives as an
  `inconclusive` trial rather than as this test failing;
* where the app freezes its plans, the plan covering the persistence obligation must
  actually pull the seam — a `covers=[...persistence...]` proven only by request-scoped
  reads is green against the P8 variant, and the answer key reports that as the *plan*
  missing rather than the fixture lying.

Prose is the trigger deliberately: the books are the spec of record, and "restart" in a
feature doc is the promise a defect row can be seeded against. An app whose book never
makes the promise owes neither opt-in and is skipped, not failed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BENCHMARKS = Path(__file__).parents[1]
APPS = sorted(
    p.parent for p in (BENCHMARKS / "apps").glob("*/agents.yml") if p.parent.is_dir()
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
        assert "qa.tool(" in plan.read_text(encoding="utf-8"), (
            f"{plan.relative_to(BENCHMARKS)} covers a persistence obligation without ever "
            "calling `qa.tool(` — every read is request-scoped, so the restart-survival "
            "promise is asserted against process memory and the P8-class variant passes"
        )
