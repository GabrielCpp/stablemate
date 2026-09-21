"""Suite-wide gate: every inline book a workflows test builds must be legal OKF."""

from __future__ import annotations

import pytest
from ostler import testsupport

UNKNOWN_BULLET_ALLOWED_TESTS: frozenset[str] = frozenset()


@pytest.fixture(autouse=True)
def _inline_books_are_legal_okf(request: pytest.FixtureRequest):
    start = len(testsupport.CONSTRUCTED_UI_NODES)
    yield
    nodes = testsupport.CONSTRUCTED_UI_NODES[start:]
    if not nodes or request.node.nodeid in UNKNOWN_BULLET_ALLOWED_TESTS:
        return
    violations = testsupport.unknown_bullet_violations(nodes)
    assert not violations, (
        f"{request.node.nodeid} builds a book `unknown-bullet` would flag on a real run — the "
        f"fixture is written against a grammar these types no longer declare: {violations}"
    )
