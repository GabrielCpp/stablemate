"""Suite-wide gate: every inline book a workflows test builds must be legal OKF.

A `UINode` a test constructs is a book nothing in this suite reads for grammar the way a real
book is read by `doctor`, so a fixture written against a grammar its node type no longer declares
sits here with no witness — which is how `test_live_audit.py`'s `type: endpoint` file root and its
`- route:` bullet survived until `07ab6d23`. The recorder and the violation check are shared
plumbing in `ostler.testsupport`; this file carries only what is this suite's own — its autouse
fixture and its own allow-set, keyed by this suite's nodeids.
"""

from __future__ import annotations

import pytest
from ostler import testsupport

#: Tests that build a book with an undeclared, load-bearing bullet key *on purpose*. Empty today:
#: no workflows test exists to prove what an undeclared key does — that check is ostler's, and it
#: is exercised there. Add to this set only for a test whose own assertions read the report for
#: what an undeclared key does, never to silence a failure this gate raises for a fixture nobody
#: meant to write that way.
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
