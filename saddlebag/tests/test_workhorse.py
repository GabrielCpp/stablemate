"""The `.workhorse/credential.json` contract."""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from saddlebag.models import AcquiredCredential, Credential, Lease
from saddlebag.workhorse import lease_id_of, read_credential, write_credential

ACQUIRED_AT = datetime(2026, 6, 30, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def acquired() -> AcquiredCredential:
    cred = Credential(id="cred-007", username="admin@staging.example.com",
                      env="staging", roles=("admin", "billing"),
                      features=("eu_region",), surface="checkout/login")
    lease = Lease(lease_id="abc123", credential_id="cred-007", run_id="run-42",
                  acquired_at=ACQUIRED_AT, expires_at=ACQUIRED_AT + timedelta(hours=2))
    return AcquiredCredential(credential=cred, lease=lease, password="hunter2")


def test_written_file_carries_the_password_and_the_lease(tmp_path: Path, acquired):
    path = write_credential(tmp_path / ".workhorse" / "credential.json", acquired)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["password"] == "hunter2"
    assert data["lease_id"] == "abc123"
    assert data["run_id"] == "run-42"
    assert data["roles"] == ["admin", "billing"]


def test_written_file_is_owner_only(tmp_path: Path, acquired):
    """The one file that holds a secret must never be group- or world-readable."""
    path = write_credential(tmp_path / "credential.json", acquired)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {mode:04o}"


def test_parent_directories_are_created(tmp_path: Path, acquired):
    path = write_credential(tmp_path / "deep" / "nested" / "cred.json", acquired)
    assert path.exists()


def test_overwriting_keeps_the_mode_and_drops_old_content(tmp_path: Path, acquired):
    path = tmp_path / "credential.json"
    path.write_text("stale, world-readable garbage", encoding="utf-8")
    path.chmod(0o644)

    write_credential(path, acquired)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert read_credential(path)["id"] == "cred-007"


def test_lease_id_of_reads_the_file(tmp_path: Path, acquired):
    path = write_credential(tmp_path / "credential.json", acquired)
    assert lease_id_of(path) == "abc123"


def test_lease_id_of_rejects_a_file_without_one(tmp_path: Path):
    path = tmp_path / "credential.json"
    path.write_text(json.dumps({"id": "cred-007"}), encoding="utf-8")
    with pytest.raises(ValueError, match="no lease_id"):
        lease_id_of(path)


def test_expires_at_is_iso_utc(tmp_path: Path, acquired):
    data = read_credential(write_credential(tmp_path / "c.json", acquired))
    assert data["expires_at"] == "2026-06-30T12:00:00Z"
