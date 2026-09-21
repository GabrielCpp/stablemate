"""`PythonDriver` builds `context["book_fixtures"]` once per driver, not once per scenario."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.model import Graph
from ostler.qa.drivers import PythonDriver
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


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8"
    )
    session = QaSession.create(spec, "qa-cache-1", "story-1", {})
    return PythonDriver(session, "api", {"driver": "python"}, root=repo, variables={})


def test_resolved_book_fixtures_is_built_once_and_reused(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(repo / "docs/features/acme/fixtures/seeded-acme.md", FIXTURE)
    driver = _driver(repo)

    from ostler.qa import drivers as drivers_mod

    calls: list[Path] = []
    real_load_graph = drivers_mod.load_graph

    def _counting_load_graph(root: Path, *, root_overrides: dict[str, str] | None = None) -> Graph:
        calls.append(root)
        return real_load_graph(root, root_overrides=root_overrides)

    monkeypatch.setattr(drivers_mod, "load_graph", _counting_load_graph)

    first = driver._resolved_book_fixtures()
    second = driver._resolved_book_fixtures()

    assert len(calls) == 1
    assert first is second
    assert "seeded-acme" in first
