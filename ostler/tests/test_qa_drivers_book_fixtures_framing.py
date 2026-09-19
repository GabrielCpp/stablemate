"""The book-fixture tier is framed against the QA context packet, not the checkout root.

`self.root` is the checkout; the book a compiled plan speaks about can live anywhere else
in the tree, named by the packet's `featuresRoot`. A fixture declared only in that other
book has to resolve — and a run whose packet cannot say where the book is has to refuse
once, up front, rather than dying once per scenario deep inside a subprocess.
"""

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


def _driver(repo: Path, *, features_root: str | None) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    if features_root is not None:
        (spec / "qa-okf-context.json").write_text(
            json.dumps({"featuresRoot": features_root}), encoding="utf-8"
        )
    session = QaSession.create(spec, "qa-frame-1", "story-1", {})
    return PythonDriver(session, "api", {"driver": "python"}, root=repo, variables={})


def test_book_fixtures_resolve_against_the_packets_frame_not_self_root(repo: Path) -> None:
    """The checkout's own book (`repo`'s `docs/features`) declares no fixture: mirroring a
    real repo whose book lives elsewhere, this fixture is only under `other-book/`."""
    write(repo / "other-book/docs/features/acme/fixtures/seeded-acme.md", FIXTURE)
    driver = _driver(repo, features_root="other-book/docs/features")

    fixtures = driver._resolved_book_fixtures()

    assert "seeded-acme" in fixtures


def test_start_blocks_once_when_the_packet_is_missing(repo: Path) -> None:
    write(repo / "other-book/docs/features/acme/fixtures/seeded-acme.md", FIXTURE)
    driver = _driver(repo, features_root=None)

    with pytest.raises(DriverBlocked) as excinfo:
        driver.start()

    assert "qa-okf-context.json" in str(excinfo.value)
