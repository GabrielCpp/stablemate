"""`book_fixtures.resolved` walks the book's `fixture` nodes into the harness's
`context["book_fixtures"]` shape: steps, declared args/provides/secrets, and `needs`
bindings with their `name=value` args resolved to strings.

Secrets are the one field this module must never let leak past a NAME: a test here
asserts a declared secret comes back as a bare name, never a value.
"""

from __future__ import annotations

import json
from pathlib import Path

from ostler.model import load
from ostler.qa import book_fixtures

from conftest import write

SEEDED_ACME = """---
type: fixture
title: Seeded acme
---
# Seeded acme

- args: id
- provides:
  - id — the seeded account's id
- secrets:
  - API_TOKEN

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-acme.sh
- timeout: 45
"""

SEEDED_GLOBEX = """---
type: fixture
title: Seeded globex
---
# Seeded globex

- provides:
  - project_id — the seeded project's id
- needs:
  - [seeded-acme](seeded-acme.md) id=@seeded-acme.id

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-globex.sh
"""


def test_resolved_carries_steps_args_provides_and_secret_names(repo: Path) -> None:
    write(repo / "docs/features/acme/fixtures/seeded-acme.md", SEEDED_ACME)
    graph = load(repo)

    fixtures = book_fixtures.resolved(graph)

    acme = fixtures["seeded-acme"]
    assert acme["args"] == ["id"]
    assert acme["provides"] == ["id"]
    assert acme["secrets"] == ["API_TOKEN"]
    assert acme["needs"] == []
    [step] = acme["steps"]
    assert step["kind"] == "seed"
    assert step["command"] == "./scripts/seed-acme.sh"
    assert step["timeout"] == "45"
    assert step["cwd"] == str(repo.resolve())


def test_resolved_parses_a_needs_binding_with_its_args(repo: Path) -> None:
    write(repo / "docs/features/acme/fixtures/seeded-acme.md", SEEDED_ACME)
    write(repo / "docs/features/acme/fixtures/seeded-globex.md", SEEDED_GLOBEX)
    graph = load(repo)

    fixtures = book_fixtures.resolved(graph)

    [need] = fixtures["seeded-globex"]["needs"]
    assert need["fixture"] == "seeded-acme"
    assert need["args"] == {"id": "@seeded-acme.id"}


def test_resolved_never_carries_a_secret_value_anywhere_in_the_dict(repo: Path) -> None:
    write(repo / "docs/features/acme/fixtures/seeded-acme.md", SEEDED_ACME)
    graph = load(repo)

    fixtures = book_fixtures.resolved(graph)

    assert fixtures["seeded-acme"]["secrets"] == ["API_TOKEN"]
    dumped = json.dumps(fixtures)
    assert "API_TOKEN" in dumped
    # The name is expected to appear — what must never appear is a value for it, and
    # there is no value in this book to leak, which is the point: the grammar has no
    # slot for one.
