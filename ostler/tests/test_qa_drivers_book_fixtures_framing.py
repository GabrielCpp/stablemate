"""The book-fixture tier is framed against the QA context packet, not the checkout root."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.qa.drivers import DriverBlocked, PythonDriver
from ostler.qa.session import QaSession

from conftest import write

FIXTURE = """---
type: fixture
title: Seeded acme
---
# Seeded acme

- provides:
  - id — the seeded account's id

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-acme.sh
"""


def _driver(repo: Path, *, services_root: str | None) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    if services_root is not None:
        (spec / "qa-okf-context.json").write_text(
            json.dumps({"servicesRoot": services_root}), encoding="utf-8"
        )
    session = QaSession.create(spec, "qa-frame-1", "story-1", {})
    return PythonDriver(session, "api", {"driver": "python"}, root=repo, variables={})


def test_book_fixtures_resolve_against_the_packets_frame_not_self_root(repo: Path) -> None:
    """The checkout's own book (`repo`'s `docs/services`) declares no fixture: mirroring a real repo whose book lives elsewhere, this fixture is only under `other-book/`."""
    write(repo / "other-book/docs/services/acme/fixtures/seeded-acme.md", FIXTURE)
    driver = _driver(repo, services_root="other-book/docs/services")

    fixtures = driver._resolved_book_fixtures()

    assert "seeded-acme" in fixtures


def test_start_blocks_once_when_the_packet_is_missing(repo: Path) -> None:
    write(repo / "other-book/docs/services/acme/fixtures/seeded-acme.md", FIXTURE)
    driver = _driver(repo, services_root=None)

    with pytest.raises(DriverBlocked) as excinfo:
        driver.start()

    assert "qa-okf-context.json" in str(excinfo.value)
