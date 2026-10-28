"""The catalogue: records in an owner-only JSON file, and nothing that looks like a value."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from saddlebag.catalogue import Catalogue
from saddlebag.models import Secret
from saddlebag.store import StoreUnavailable


def test_a_record_round_trips_with_tags_and_fields(catalogue: Catalogue) -> None:
    secret = Secret("login", "gab", "A login", "LOGIN_PASSWORD", frozenset({("environment", "local")}), frozenset({"password"}))
    catalogue.put(secret)
    assert catalogue.get("login") == secret
    assert catalogue.names() == ["login"]


def test_an_absent_file_is_an_empty_catalogue(catalogue: Catalogue) -> None:
    assert catalogue.names() == []
    assert catalogue.get("login") is None
    assert not catalogue.path.exists()


def test_put_replaces_and_drop_forgets(catalogue: Catalogue) -> None:
    catalogue.put(Secret("b"))
    catalogue.put(Secret("a", username="one"))
    catalogue.put(Secret("a", username="two"))
    assert catalogue.names() == ["a", "b"]
    assert catalogue.get("a") == Secret("a", username="two")
    catalogue.drop("a")
    assert catalogue.names() == ["b"]


def test_the_file_is_owner_only(catalogue: Catalogue) -> None:
    catalogue.put(Secret("login"))
    assert stat.S_IMODE(catalogue.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(catalogue.path.parent.stat().st_mode) == 0o700
    assert [entry.name for entry in catalogue.path.parent.iterdir()] == ["catalogue.json"]


def test_a_value_looking_key_is_rejected(catalogue: Catalogue) -> None:
    catalogue.put(Secret("login"))
    payload = json.loads(catalogue.path.read_text())
    payload["secrets"][0]["password"] = "hunter2"
    catalogue.path.write_text(json.dumps(payload))
    with pytest.raises(StoreUnavailable, match=str(catalogue.path)):
        catalogue.names()


def test_unreadable_json_names_the_path(catalogue: Catalogue) -> None:
    catalogue.path.parent.mkdir(parents=True)
    catalogue.path.write_text("{not json")
    with pytest.raises(StoreUnavailable, match=str(catalogue.path)):
        catalogue.get("login")


def test_another_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps({"version": 2, "secrets": []}))
    with pytest.raises(StoreUnavailable, match=str(path)):
        Catalogue(path).names()


def test_a_record_round_trips_with_metadata(catalogue: Catalogue) -> None:
    secret = Secret("login", metadata={"phone": "+15555550100", "role": "admin"})
    catalogue.put(secret)
    assert catalogue.get("login") == secret
    assert json.loads(catalogue.path.read_text())["secrets"][0]["metadata"] == {"phone": "+15555550100", "role": "admin"}


def test_a_record_written_before_metadata_loads_empty(catalogue: Catalogue) -> None:
    catalogue.put(Secret("login", "gab"))
    payload = json.loads(catalogue.path.read_text())
    del payload["secrets"][0]["metadata"]
    catalogue.path.write_text(json.dumps(payload))
    assert catalogue.get("login") == Secret("login", "gab")


@pytest.mark.parametrize("metadata", [["a"], {"a": 1}, "x"])
def test_metadata_that_is_not_a_string_map_is_rejected(catalogue: Catalogue, metadata: object) -> None:
    catalogue.put(Secret("login"))
    payload = json.loads(catalogue.path.read_text())
    payload["secrets"][0]["metadata"] = metadata
    catalogue.path.write_text(json.dumps(payload))
    with pytest.raises(StoreUnavailable, match=str(catalogue.path)):
        catalogue.names()
