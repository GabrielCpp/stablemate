"""Pool metadata, matching semantics and lease lifecycle."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

import platformdirs

from saddlebag.db import Pool, PoolError, _dt, default_db_path
from saddlebag.models import Requirement


def test_default_db_path_honours_the_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SADDLEBAG_DB", str(tmp_path / "custom.db"))
    assert default_db_path() == tmp_path / "custom.db"


def test_default_db_path_uses_the_platform_data_dir(monkeypatch):
    """No hard-coded ~/.local/share: the location follows each OS's convention
    (Application Support on macOS, %LOCALAPPDATA% on Windows, XDG on Linux)."""
    monkeypatch.delenv("SADDLEBAG_DB", raising=False)
    path = default_db_path()
    assert path.name == "pool.db"
    assert path.parent == Path(platformdirs.user_data_dir("saddlebag"))


def test_epoch_zero_round_trips_as_an_instant_not_none():
    """Regression: epoch 0 is falsy. A truthiness check silently turned an expired
    lease into 'no lease', so `doctor` under-reported stale leases while `expire`
    (which compares in SQL) reclaimed them."""
    assert _dt(0.0) is not None
    assert _dt(0.0).year == 1970
    assert _dt(None) is None


def test_a_lease_expiring_at_epoch_zero_reads_as_stale(populated: Pool):
    populated.acquire("cred-001")
    populated._conn.execute("UPDATE credentials SET expires_at = 0 WHERE id = 'cred-001'")

    cred = populated.get("cred-001")
    assert cred.is_stale() is True
    assert cred.is_locked() is False


def test_ids_are_minted_sequentially(pool: Pool):
    first = pool.add(username="a@x.com", env="staging")
    second = pool.add(username="b@x.com", env="staging")
    assert (first.id, second.id) == ("cred-001", "cred-002")


def test_ids_resume_after_a_gap(pool: Pool):
    pool.add(username="a@x.com", env="staging", credential_id="cred-007")
    assert pool.add(username="b@x.com", env="staging").id == "cred-008"


def test_pool_never_stores_a_password(pool: Pool, db_path: Path):
    pool.add(username="a@x.com", env="staging")
    columns = {r[1] for r in pool._conn.execute("PRAGMA table_info(credentials)")}
    assert "password" not in columns
    assert not any("password" in c for c in columns)


def test_roles_match_as_a_superset(populated: Pool):
    # cred-001 holds {admin, billing}; cred-002 holds {admin}.
    both = populated.find(Requirement(roles=("admin", "billing")))
    assert [c.id for c in both] == ["cred-001"]

    admin_only = populated.find(Requirement(roles=("admin",)))
    assert [c.id for c in admin_only] == ["cred-001", "cred-002"]


def test_features_match_as_a_superset(populated: Pool):
    found = populated.find(Requirement(features=("eu_region",)))
    assert [c.id for c in found] == ["cred-001"]


def test_env_and_surface_match_exactly(populated: Pool):
    assert [c.id for c in populated.find(Requirement(env="prod"))] == ["cred-003"]
    assert populated.find(Requirement(env="prod", surface="checkout/login")) == []


def test_project_is_stored_and_filters_exactly(pool: Pool):
    pool.add(username="a@x.com", env="staging", project="checkout-web")
    pool.add(username="b@x.com", env="staging", project="billing-api")
    pool.add(username="c@x.com", env="staging")  # no project

    assert pool.get("cred-001").project == "checkout-web"
    assert [c.id for c in pool.find(Requirement(project="checkout-web"))] == ["cred-001"]
    # A project filter excludes credentials with no project.
    assert [c.id for c in pool.find(Requirement(project="billing-api"))] == ["cred-002"]
    # No project filter returns all three.
    assert len(pool.find(Requirement())) == 3


def test_project_composes_with_other_filters(pool: Pool):
    pool.add(username="a@x.com", env="staging", project="checkout-web", roles=("admin",))
    pool.add(username="b@x.com", env="prod", project="checkout-web", roles=("admin",))

    found = pool.find(Requirement(project="checkout-web", env="staging", roles=("admin",)))
    assert [c.id for c in found] == ["cred-001"]


def test_a_pool_without_the_project_column_is_migrated_on_open(db_path):
    """An old pool.db predates `project`; opening it with a current Pool must add
    the column additively, not error, and existing rows read project as None."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        "CREATE TABLE credentials ("
        "  id TEXT PRIMARY KEY, username TEXT NOT NULL, env TEXT NOT NULL,"
        "  roles TEXT NOT NULL DEFAULT '[]', features TEXT NOT NULL DEFAULT '[]',"
        "  surface TEXT, last_used REAL, lease_id TEXT UNIQUE, run_id TEXT,"
        "  acquired_at REAL, expires_at REAL);"
        "INSERT INTO credentials (id, username, env) VALUES ('cred-001', 'old@x.com', 'staging');"
    )
    conn.commit()
    conn.close()

    with Pool(db_path) as pool:
        cred = pool.get("cred-001")
        assert cred is not None
        assert cred.project is None
        # And the migrated pool now accepts a project on new rows.
        pool.add(username="new@x.com", env="staging", project="checkout-web")
        assert pool.get("cred-002").project == "checkout-web"


def test_unconstrained_find_returns_everything(populated: Pool):
    assert len(populated.find(Requirement())) == 3


def test_acquire_locks_and_excludes_from_find(populated: Pool):
    lease = populated.acquire("cred-001")
    assert lease.credential_id == "cred-001"

    assert [c.id for c in populated.find(Requirement(roles=("admin",)))] == ["cred-002"]
    assert populated.get("cred-001").is_locked()


def test_second_acquire_of_a_leased_credential_is_refused(populated: Pool):
    populated.acquire("cred-001")
    with pytest.raises(PoolError, match="already leased"):
        populated.acquire("cred-001")


def test_acquire_unknown_credential_says_so(populated: Pool):
    with pytest.raises(PoolError, match="no such credential"):
        populated.acquire("cred-999")


def test_acquire_rejects_nonpositive_ttl(populated: Pool):
    with pytest.raises(PoolError, match="ttl must be positive"):
        populated.acquire("cred-001", ttl=0)


def test_expired_lease_can_be_reacquired_without_release(populated: Pool, frozen):
    populated.acquire("cred-001", ttl=60, now=frozen)
    later = frozen + timedelta(seconds=61)

    # The credential is stale, not locked: the TTL is the backstop that makes a
    # leaked lease self-healing.
    cred = populated.get("cred-001")
    assert cred.is_stale(later) and not cred.is_locked(later)

    lease = populated.acquire("cred-001", now=later)
    assert lease.credential_id == "cred-001"


def test_release_by_lease_id(populated: Pool):
    lease = populated.acquire("cred-001")
    assert populated.release_lease(lease.lease_id) == 1
    assert not populated.get("cred-001").is_locked()


def test_release_by_lease_id_is_scoped_to_that_lease(populated: Pool):
    lease = populated.acquire("cred-001")
    populated.acquire("cred-002")
    populated.release_lease(lease.lease_id)
    assert populated.get("cred-002").is_locked()


def test_release_by_run_id_frees_every_credential_in_the_run(populated: Pool):
    populated.acquire("cred-001", run_id="run-42")
    populated.acquire("cred-003", run_id="run-42")
    populated.acquire("cred-002", run_id="run-99")

    assert populated.release_run("run-42") == 2
    assert not populated.get("cred-001").is_locked()
    assert not populated.get("cred-003").is_locked()
    assert populated.get("cred-002").is_locked()


def test_release_of_an_unknown_lease_frees_nothing(populated: Pool):
    assert populated.release_lease("nope") == 0


def test_expire_reclaims_only_stale_leases(populated: Pool, frozen):
    populated.acquire("cred-001", ttl=60, now=frozen)
    populated.acquire("cred-002", ttl=7200, now=frozen)

    later = frozen + timedelta(seconds=61)
    assert populated.expire(now=later) == 1
    assert not populated.get("cred-001").is_locked(later)
    assert populated.get("cred-002").is_locked(later)


def test_expire_on_a_clean_pool_is_a_noop(populated: Pool):
    assert populated.expire() == 0


def test_remove_deletes_the_row(populated: Pool):
    assert populated.remove("cred-001") is True
    assert populated.get("cred-001") is None
    assert populated.remove("cred-001") is False


def test_leases_lists_outstanding_checkouts(populated: Pool):
    populated.acquire("cred-001", run_id="run-42")
    leases = populated.leases()
    assert len(leases) == 1
    assert leases[0].credential_id == "cred-001"
    assert leases[0].run_id == "run-42"


def test_pool_survives_reopen(db_path: Path):
    with Pool(db_path) as first:
        first.add(username="a@x.com", env="staging", roles=("admin",))
    with Pool(db_path) as second:
        cred = second.get("cred-001")
        assert cred.roles == ("admin",)


def test_duplicate_explicit_id_is_refused(pool: Pool):
    pool.add(username="a@x.com", env="staging", credential_id="cred-007")
    with pytest.raises(PoolError, match="already exists"):
        pool.add(username="b@x.com", env="staging", credential_id="cred-007")
