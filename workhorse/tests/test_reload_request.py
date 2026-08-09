"""The reload request file: written atomically, read once, never fatal to read."""

from __future__ import annotations

import json
from pathlib import Path

from workhorse import reload


def test_a_written_request_reads_back_with_its_flags(tmp_path: Path) -> None:
    reload.request(tmp_path, core=True)
    found = reload.pending(tmp_path)
    assert found is not None
    assert found.core is True
    assert found.at_boundary is False
    assert found.cuts_the_turn is True
    assert found.requested_at


def test_the_default_request_cuts_the_turn(tmp_path: Path) -> None:
    """The default reason for reloading is that the turn is broken, so the default cuts."""
    reload.request(tmp_path)
    found = reload.pending(tmp_path)
    assert found is not None and found.cuts_the_turn is True

    reload.request(tmp_path, at_boundary=True)
    found = reload.pending(tmp_path)
    assert found is not None and found.cuts_the_turn is False


def test_no_request_is_not_an_error(tmp_path: Path) -> None:
    assert reload.pending(tmp_path) is None
    assert reload.pending(None) is None
    assert reload.consume(tmp_path) is None


def test_an_unreadable_request_reads_as_no_request(tmp_path: Path) -> None:
    """The poll runs inside a live agent turn; a malformed file must not end the run."""
    (tmp_path / reload.REQUEST_FILE).write_text("{not json", encoding="utf-8")
    assert reload.pending(tmp_path) is None
    (tmp_path / reload.REQUEST_FILE).write_text("[]", encoding="utf-8")
    assert reload.pending(tmp_path) is None


def test_consuming_clears_it_so_one_request_is_one_reload(tmp_path: Path) -> None:
    reload.request(tmp_path, core=True)
    taken = reload.consume(tmp_path)
    assert taken is not None and taken.core is True
    assert reload.pending(tmp_path) is None
    assert not (tmp_path / reload.REQUEST_FILE).exists()


def test_a_second_request_overwrites_rather_than_queues(tmp_path: Path) -> None:
    """Two operators asking for a reload want one reload, with the newest flags."""
    reload.request(tmp_path, core=True)
    reload.request(tmp_path, core=False, at_boundary=True)
    found = reload.pending(tmp_path)
    assert found is not None and found.core is False and found.at_boundary is True
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_request_file_is_json_an_operator_can_read(tmp_path: Path) -> None:
    path = reload.request(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")).keys() == {
        "core",
        "at_boundary",
        "requested_at",
    }


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
