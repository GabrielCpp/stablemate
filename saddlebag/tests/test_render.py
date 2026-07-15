"""Resolution, the credential-ref join with the lease machinery, and the --check gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saddlebag import envfile, render
from saddlebag.db import Pool, PoolError
from saddlebag.models import (
    KIND_CONFIG,
    KIND_CREDENTIAL_REF,
    KIND_PENDING,
    KIND_SECRET,
    EnvironmentEntry,
)


@pytest.fixture
def web(pool: Pool, tmp_path: Path):
    """A realistic environment: config, a secret, and a credential-ref."""
    environment = pool.env_add(name="web-local", env="local", project="acme",
                               target=str(tmp_path / ".env.local"))
    for entry in (
        EnvironmentEntry(key="PROJECT_ID", kind=KIND_CONFIG, value="acme"),
        EnvironmentEntry(key="API_KEY", kind=KIND_SECRET),
        EnvironmentEntry(key="TEST_USER_PASSWORD", kind=KIND_CREDENTIAL_REF,
                         cred_ref="cred-001:password"),
    ):
        pool.env_put_entry(environment.id, entry)
    return pool.env_get(environment.id)


@pytest.fixture
def seeded(pool: Pool, store, web):
    """The secret is in the store, and the referenced credential exists."""
    store.put(web.store_key("API_KEY"), "AIzaSy-REAL-KEY")
    cred = pool.add(username="qa@acme.example", env="local", project="acme",
                    credential_id="cred-001")
    store.put(cred.store_key, "hunter2")
    return web


def opener(store):
    return lambda: store


class ExplodingStore:
    """A store that fails the moment anything opens it — a host with no keyring."""

    name = "none"

    def __call__(self):
        raise AssertionError("the store must not be opened for a config-only environment")


# -- resolution ---------------------------------------------------------------


def test_resolve_reads_config_from_the_pool_secrets_from_the_store(pool, store, seeded):
    resolution = render.resolve(seeded, pool, opener(store))
    assert resolution.resolvable
    assert resolution.values == {
        "PROJECT_ID": "acme",
        "API_KEY": "AIzaSy-REAL-KEY",
        "TEST_USER_PASSWORD": "hunter2",
    }


def test_a_config_only_environment_never_opens_the_store(pool: Pool, tmp_path):
    """§7, and the whole reason config is first class: this must work on a container
    with no keyring, no Vault, and no configuration whatsoever."""
    environment = pool.env_add(name="cfg", env="local", target=str(tmp_path / ".env"))
    pool.env_put_entry(environment.id, EnvironmentEntry(key="HOST", kind=KIND_CONFIG,
                                                        value="127.0.0.1:9099"))

    resolution = render.resolve(pool.env_get(environment.id), pool, ExplodingStore())
    assert resolution.values == {"HOST": "127.0.0.1:9099"}


def test_a_pending_required_key_is_a_gap(pool: Pool, store, web):
    pool.env_put_entry(web.id, EnvironmentEntry(key="STRIPE_KEY", kind=KIND_PENDING))
    resolution = render.resolve(pool.env_get(web.id), pool, opener(store))

    assert not resolution.resolvable
    assert [g.key for g in resolution.gaps if g.reason == render.PENDING] == ["STRIPE_KEY"]


def test_a_secret_the_store_does_not_have_is_a_gap(pool, store, web):
    resolution = render.resolve(web, pool, opener(store))
    gap = next(g for g in resolution.gaps if g.key == "API_KEY")
    assert gap.reason == render.UNSET


def test_a_credential_ref_to_a_missing_credential_is_a_gap(pool, store, web):
    store.put(web.store_key("API_KEY"), "k")
    resolution = render.resolve(web, pool, opener(store))

    gap = next(g for g in resolution.gaps if g.key == "TEST_USER_PASSWORD")
    assert gap.reason == render.DANGLING
    assert "no such credential: cred-001" in gap.detail


def test_an_optional_key_with_no_value_is_omitted_not_a_gap(pool: Pool, store, seeded):
    pool.env_put_entry(seeded.id, EnvironmentEntry(key="SENTRY_DSN", kind=KIND_PENDING,
                                                   required=False))
    resolution = render.resolve(pool.env_get(seeded.id), pool, opener(store))

    assert resolution.resolvable
    assert "SENTRY_DSN" not in resolution.values


def test_resolution_preserves_render_order(pool, store, seeded):
    assert list(render.resolve(seeded, pool, opener(store)).values) == [
        "PROJECT_ID", "API_KEY", "TEST_USER_PASSWORD",
    ]


# -- the join with credentials ------------------------------------------------


def test_a_credential_ref_leases_the_credential_for_the_run(pool: Pool, store, seeded):
    resolution = render.resolve(seeded, pool, opener(store), run_id="run-42")

    assert resolution.leases["cred-001"]
    cred = pool.get("cred-001")
    assert cred.is_locked()
    assert cred.run_id == "run-42"

    # And the existing bookend cleans up after it, unchanged.
    assert pool.release_run("run-42") == 1
    assert not pool.get("cred-001").is_locked()


def test_username_and_password_refs_share_one_lease(pool: Pool, store, seeded):
    """Two entries, one identity — leasing per entry would collide with itself."""
    pool.env_put_entry(seeded.id, EnvironmentEntry(key="TEST_USER_EMAIL",
                                                   kind=KIND_CREDENTIAL_REF,
                                                   cred_ref="cred-001:username"))
    resolution = render.resolve(pool.env_get(seeded.id), pool, opener(store), run_id="run-42")

    assert resolution.values["TEST_USER_EMAIL"] == "qa@acme.example"
    assert list(resolution.leases) == ["cred-001"]


def test_rendering_twice_in_one_run_reuses_its_own_lease(pool: Pool, store, seeded):
    first = render.resolve(seeded, pool, opener(store), run_id="run-42")
    second = render.resolve(seeded, pool, opener(store), run_id="run-42")
    assert second.leases == first.leases


def test_a_credential_held_by_another_run_blocks_the_render(pool: Pool, store, seeded):
    pool.acquire("cred-001", run_id="someone-else")
    with pytest.raises(PoolError, match="already leased"):
        render.resolve(seeded, pool, opener(store), run_id="run-42")


def test_check_takes_no_lease(pool: Pool, store, seeded):
    """--check is a gate, not an action: a QA preflight must not lock an identity."""
    render.check(seeded, pool, opener(store))
    assert not pool.get("cred-001").is_locked()


def test_a_failed_lease_hands_back_the_ones_taken_beside_it(pool: Pool, store, seeded):
    """A render that cannot complete must not strand a lease behind it."""
    other = pool.add(username="b@x.com", env="local", project="acme")
    store.put(other.store_key, "pw")
    pool.env_put_entry(seeded.id, EnvironmentEntry(
        key="OTHER_PASSWORD", kind=KIND_CREDENTIAL_REF, cred_ref=f"{other.id}:password"))
    # cred-001 sorts first, so it is leased before cred-002 is found to be taken.
    pool.acquire(other.id, run_id="someone-else")

    with pytest.raises(PoolError):
        render.resolve(pool.env_get(seeded.id), pool, opener(store), run_id="run-42")

    assert not pool.get("cred-001").is_locked()


# -- formatting ---------------------------------------------------------------


def test_dotenv_output_round_trips_through_the_parser(tmp_path):
    """The writer is the exact inverse of the reader — a secret that reads back
    differently than it was written is a corrupted secret."""
    values = {
        "PLAIN": "abc",
        "SPACES": "s3kr#t with spaces",
        "HASH": "pa#ssword",
        "EMPTY": "",
        "QUOTED": '"already quoted"',
        "APOSTROPHE": "it's",
    }
    path = tmp_path / ".env"
    path.write_text(envfile.dumps(values), encoding="utf-8")
    assert envfile.parse(path) == values


def test_a_dotenv_value_with_a_newline_is_refused_not_mangled():
    with pytest.raises(ValueError, match="newline"):
        envfile.dumps({"KEY": "line1\nline2"})


def test_json_format_takes_what_dotenv_cannot(tmp_path):
    text = render.format_values({"KEY": "line1\nline2"}, "json")
    assert json.loads(text) == {"KEY": "line1\nline2"}


def test_read_keys_returns_names_and_discards_values(tmp_path):
    path = tmp_path / ".env.example"
    path.write_text("API_KEY=placeholder\n# comment\nPROJECT_ID=\n", encoding="utf-8")
    assert envfile.read_keys(path) == ["API_KEY", "PROJECT_ID"]


# -- check --------------------------------------------------------------------


def test_check_on_an_unrendered_target_reports_every_key_missing(pool, store, seeded):
    report = render.check(seeded, pool, opener(store))
    assert report.resolvable
    assert not report.target_exists
    assert report.missing == ["PROJECT_ID", "API_KEY", "TEST_USER_PASSWORD"]
    assert not report.ok


def test_check_is_in_sync_after_a_render(pool, store, seeded, tmp_path):
    resolution = render.resolve(seeded, pool, opener(store))
    Path(seeded.target).write_text(render.format_values(resolution.values, "dotenv"),
                                   encoding="utf-8")

    report = render.check(seeded, pool, opener(store))
    assert report.ok
    assert (report.missing, report.extra, report.drift) == ([], [], [])


def test_check_reports_drift_and_extra_keys_by_name_only(pool, store, seeded):
    Path(seeded.target).write_text(
        "PROJECT_ID=hand-edited\nAPI_KEY=AIzaSy-REAL-KEY\n"
        "TEST_USER_PASSWORD=hunter2\nLEFTOVER=x\n",
        encoding="utf-8",
    )
    report = render.check(seeded, pool, opener(store))

    assert report.drift == ["PROJECT_ID"]
    assert report.extra == ["LEFTOVER"]
    assert not report.in_sync
    # The report knows the values differ, but never carries either of them.
    assert "hand-edited" not in json.dumps(report.to_dict())
    assert "AIzaSy-REAL-KEY" not in json.dumps(report.to_dict())


def test_check_reports_gaps_without_touching_the_target(pool, store, web):
    report = render.check(web, pool, opener(store))
    assert not report.resolvable
    assert [g.key for g in report.gaps] == ["API_KEY", "TEST_USER_PASSWORD"]
    assert not Path(web.target).exists()
