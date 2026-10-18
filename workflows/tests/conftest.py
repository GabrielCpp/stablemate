"""Suite-wide gate: every inline book a workflows test builds must be legal OKF."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from ostler import testing

UNKNOWN_BULLET_ALLOWED_TESTS: frozenset[str] = frozenset()


@pytest.fixture(autouse=True)
def _artifacts_dir_is_per_test(tmp_path_factory, monkeypatch):
    """Specs live in the user's artifacts folder, so no test may resolve to the real one."""
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(tmp_path_factory.mktemp("artifacts")))


@pytest.fixture(autouse=True)
def _inline_books_are_legal_okf(request: pytest.FixtureRequest):
    start = len(testing.CONSTRUCTED_UI_NODES)
    yield
    nodes = testing.CONSTRUCTED_UI_NODES[start:]
    if not nodes or request.node.nodeid in UNKNOWN_BULLET_ALLOWED_TESTS:
        return
    violations = testing.unknown_bullet_violations(nodes)
    assert not violations, (
        f"{request.node.nodeid} builds a book `unknown-bullet` would flag on a real run — the "
        f"fixture is written against a grammar these types no longer declare: {violations}"
    )


TOOL_CACHE = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")


@pytest.fixture(autouse=True)
def _no_real_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", TOOL_CACHE)
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path_factory.mktemp("stablemate-cache")))
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
