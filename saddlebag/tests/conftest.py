"""Shared fixtures: an on-disk pool and an in-memory secret store.

Nothing here touches the real OS keyring — a test run must never write to the
developer's Keychain, and must pass on a headless CI box with no keyring at all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from saddlebag.db import Pool


class FakeStore:
    """An in-memory :class:`~saddlebag.store.SecretStore`."""

    name = "fake"

    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}

    def put(self, credential_id: str, password: str) -> None:
        self.secrets[credential_id] = password

    def get(self, credential_id: str) -> str | None:
        return self.secrets.get(credential_id)

    def delete(self, credential_id: str) -> None:
        self.secrets.pop(credential_id, None)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "pool.db"


@pytest.fixture
def pool(db_path: Path) -> Pool:
    with Pool(db_path) as p:
        yield p


@pytest.fixture
def populated(pool: Pool, store: FakeStore) -> Pool:
    """Two staging admins and one prod reader, with passwords in the fake store."""
    specs = [
        ("admin@staging.example.com", "staging", ("admin", "billing"),
         ("mfa_enabled", "eu_region"), "checkout/login"),
        ("plain@staging.example.com", "staging", ("admin",), (), "checkout/login"),
        ("reader@prod.example.com", "prod", ("reader",), (), "checkout/address"),
    ]
    for username, env, roles, features, surface in specs:
        cred = pool.add(username=username, env=env, roles=roles,
                        features=features, surface=surface)
        store.put(cred.id, f"pw-{cred.id}")
    return pool


@pytest.fixture
def frozen() -> datetime:
    """A fixed instant. Lease arithmetic is exercised against this, not wall time."""
    return datetime(2026, 6, 30, 10, 0, 0, tzinfo=UTC)
