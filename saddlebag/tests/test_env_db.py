"""The environment tables: the CHECK invariant, NULL-aware scoping, and cascade."""

from __future__ import annotations

import sqlite3

import pytest

from saddlebag.db import Pool, PoolError
from saddlebag.models import (
    KIND_CONFIG,
    KIND_CREDENTIAL_REF,
    KIND_PENDING,
    KIND_SECRET,
    EnvironmentEntry,
)


@pytest.fixture
def web(pool: Pool):
    return pool.env_add(name="web-local", env="local", project="predykt",
                        target="web/.env.local")


# -- the invariant: the database itself refuses to hold a secret --------------


def test_the_check_constraint_rejects_a_value_on_a_secret_row(pool: Pool, web):
    """The fence that matters. A bug in a caller — or a caller not yet written —
    cannot quietly put a secret in the pool DB, because SQLite will not take it."""
    with pytest.raises(sqlite3.IntegrityError):
        pool._conn.execute(
            "INSERT INTO environment_entries (environment_id, key, kind, value) "
            "VALUES (?, 'API_KEY', 'secret', 'sk_live_oops')",
            (web.id,),
        )


def test_the_check_constraint_rejects_an_unknown_kind(pool: Pool, web):
    with pytest.raises(sqlite3.IntegrityError):
        pool._conn.execute(
            "INSERT INTO environment_entries (environment_id, key, kind) "
            "VALUES (?, 'K', 'plaintext')",
            (web.id,),
        )


def test_the_model_refuses_a_secret_with_a_value_before_the_db_ever_sees_it(pool: Pool):
    with pytest.raises(ValueError, match="cannot hold a value"):
        EnvironmentEntry(key="API_KEY", kind=KIND_SECRET, value="sk_live_oops")


# -- CRUD ---------------------------------------------------------------------


def test_add_mints_sequential_env_ids(pool: Pool):
    first = pool.env_add(name="web-local", env="local")
    second = pool.env_add(name="api-local", env="local")
    assert (first.id, second.id) == ("env-001", "env-002")


def test_a_duplicate_name_in_the_same_project_is_rejected(pool: Pool, web):
    with pytest.raises(PoolError, match="already exists"):
        pool.env_add(name="web-local", env="local", project="predykt")


def test_a_duplicate_name_is_rejected_even_when_unscoped(pool: Pool):
    """UNIQUE (project, name) does not catch this on its own — in SQL two NULLs are
    not equal — so the unscoped case is guarded in env_add."""
    pool.env_add(name="web-local", env="local")
    with pytest.raises(PoolError, match="already exists"):
        pool.env_add(name="web-local", env="local")


def test_the_same_name_in_two_projects_is_fine(pool: Pool, web):
    other = pool.env_add(name="web-local", env="local", project="other-repo")
    assert other.id != web.id


def test_env_by_name_finds_an_unscoped_environment(pool: Pool):
    """`project = NULL` is never true in SQL; the lookup uses `IS`, so this works."""
    pool.env_add(name="web-local", env="local")
    assert pool.env_by_name("web-local").id == "env-001"


def test_env_find_scopes_to_one_project(pool: Pool, web):
    pool.env_add(name="api-local", env="local", project="other-repo")
    assert [e.name for e in pool.env_find("predykt")] == ["web-local"]
    assert [e.name for e in pool.env_find(None)] == []
    assert len(pool.env_all()) == 2


def test_an_unknown_format_is_rejected(pool: Pool):
    with pytest.raises(PoolError, match="unknown format"):
        pool.env_add(name="web-local", env="local", format="toml")


def test_removing_an_environment_cascades_to_its_entries(pool: Pool, web):
    pool.env_put_entry(web.id, EnvironmentEntry(key="K", kind=KIND_CONFIG, value="v"))
    assert pool.env_remove(web.id) is True

    rows = pool._conn.execute("SELECT * FROM environment_entries").fetchall()
    assert rows == []


# -- entries ------------------------------------------------------------------


def test_entries_keep_their_render_order(pool: Pool, web):
    for key in ("C", "A", "B"):
        pool.env_put_entry(web.id, EnvironmentEntry(key=key, kind=KIND_CONFIG, value=key))
    assert [e.key for e in pool.env_get(web.id).entries] == ["C", "A", "B"]


def test_resupplying_a_value_does_not_reshuffle_the_file(pool: Pool, web):
    for key in ("A", "B", "C"):
        pool.env_put_entry(web.id, EnvironmentEntry(key=key, kind=KIND_PENDING))
    pool.env_put_entry(web.id, EnvironmentEntry(key="A", kind=KIND_CONFIG, value="now-set"))

    entries = pool.env_get(web.id).entries
    assert [e.key for e in entries] == ["A", "B", "C"]
    assert entries[0].kind == KIND_CONFIG


def test_a_pinned_position_is_honoured(pool: Pool, web):
    """Manifest import pins positions, so an imported file renders in manifest order."""
    pool.env_put_entry(web.id, EnvironmentEntry(key="LAST", kind=KIND_PENDING, position=9))
    pool.env_put_entry(web.id, EnvironmentEntry(key="FIRST", kind=KIND_PENDING, position=1))
    assert [e.key for e in pool.env_get(web.id).entries] == ["FIRST", "LAST"]


def test_an_entry_round_trips_through_the_db(pool: Pool, web):
    pool.env_put_entry(web.id, EnvironmentEntry(
        key="TEST_USER_PASSWORD", kind=KIND_CREDENTIAL_REF,
        cred_ref="cred-007:password", required=False, note="the leased QA user",
    ))
    entry = pool.env_get_entry(web.id, "TEST_USER_PASSWORD")
    assert entry.kind == KIND_CREDENTIAL_REF
    assert entry.cred_ref == "cred-007:password"
    assert entry.required is False
    assert entry.note == "the leased QA user"


def test_remove_entry(pool: Pool, web):
    pool.env_put_entry(web.id, EnvironmentEntry(key="K", kind=KIND_CONFIG, value="v"))
    assert pool.env_remove_entry(web.id, "K") is True
    assert pool.env_remove_entry(web.id, "K") is False


def test_needs_store_is_false_for_a_config_only_environment(pool: Pool, web):
    """The property §7 hangs on: this environment renders on a host with no keyring."""
    pool.env_put_entry(web.id, EnvironmentEntry(key="HOST", kind=KIND_CONFIG, value="localhost"))
    assert pool.env_get(web.id).needs_store is False

    pool.env_put_entry(web.id, EnvironmentEntry(key="API_KEY", kind=KIND_SECRET))
    assert pool.env_get(web.id).needs_store is True


# -- store keys ---------------------------------------------------------------


def test_the_store_key_is_project_qualified(pool: Pool, web):
    assert web.store_key("VITE_FIREBASE_API_KEY") == "predykt/env-001/VITE_FIREBASE_API_KEY"


def test_an_unscoped_environment_uses_a_bare_store_key(pool: Pool):
    environment = pool.env_add(name="web-local", env="local")
    assert environment.store_key("API_KEY") == "env-001/API_KEY"


def test_two_projects_minting_env_001_do_not_collide_in_the_store(tmp_path):
    """The whole reason keys are qualified: two per-project pools each restart the
    id sequence, so a bare key would clobber."""
    keys = []
    for project in ("repo-a", "repo-b"):
        with Pool(tmp_path / f"{project}.db") as p:
            keys.append(p.env_add(name="web", env="local", project=project).store_key("K"))
    assert keys == ["repo-a/env-001/K", "repo-b/env-001/K"]


# -- an old pool gains the tables ---------------------------------------------


def test_a_pool_predating_environments_simply_gains_the_tables(tmp_path):
    """CREATE TABLE IF NOT EXISTS: no migration entry needed, and no existing
    credential is touched."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE credentials (id TEXT PRIMARY KEY, username TEXT NOT NULL, "
        "env TEXT NOT NULL, roles TEXT NOT NULL DEFAULT '[]', "
        "features TEXT NOT NULL DEFAULT '[]', surface TEXT, last_used REAL, "
        "lease_id TEXT UNIQUE, run_id TEXT, acquired_at REAL, expires_at REAL);"
        "INSERT INTO credentials (id, username, env) VALUES ('cred-001', 'a@x.com', 'staging');"
    )
    conn.commit()
    conn.close()

    with Pool(path) as pool:
        assert pool.get("cred-001").username == "a@x.com"
        assert pool.env_all() == []
        assert pool.env_add(name="web-local", env="local").id == "env-001"
