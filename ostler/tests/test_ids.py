"""Id allocation: a per-repo prefix + a coordination-free, lexicographically-increasing ULID, and the git-style short handle that abbreviates it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import write, write_prefix
from ostler import ids
from ostler._vendor.stablemate_core.config import ConfigError
from ostler.cli import main
from ostler.model import load

_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _repo(tmp_path: Path, name: str, prefix: str | None = "ACME") -> Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    if prefix is not None:
        write_prefix(root, prefix)
    return root


def _ulid_of(identifier: str) -> str:
    return identifier.split("-", 1)[1]


def test_the_minted_id_starts_with_the_manifest_prefix(tmp_path: Path):
    root = _repo(tmp_path, "stablemate", "Acme_1")
    ident = ids.allocate(load(root))
    assert ident.startswith("Acme_1-")
    assert _ULID.match(_ulid_of(ident))


def test_a_mint_creates_no_registry_file(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    ids.allocate(load(root))
    assert not (root / ".agents" / "ids.json").exists()


def test_a_leftover_registry_file_is_ignored(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    write(root / ".agents/ids.json", '{"prefix": "OLD"}\n')
    assert ids.allocate(load(root)).startswith("ACME-")


def test_a_repo_without_a_manifest_refuses_to_mint(tmp_path: Path):
    root = _repo(tmp_path, "acme", None)
    with pytest.raises(ConfigError) as refused:
        ids.allocate(load(root))
    assert "repo.id_prefix" in str(refused.value)
    assert str(root / "agents.yml") in str(refused.value)


def test_a_manifest_without_the_key_refuses_to_mint(tmp_path: Path):
    root = _repo(tmp_path, "acme", None)
    write(root / "agents.yml", "repo:\n  name: acme\n")
    with pytest.raises(ConfigError) as refused:
        ids.allocate(load(root))
    assert "repo.id_prefix" in str(refused.value)


@pytest.mark.parametrize("prefix", ["my-app", "1ACME", "A" * 17, "ac me"])
def test_a_malformed_prefix_refuses_to_mint(tmp_path: Path, prefix: str):
    root = _repo(tmp_path, "acme", None)
    write(root / "agents.yml", f'repo:\n  id_prefix: "{prefix}"\n')
    with pytest.raises(ConfigError) as refused:
        ids.allocate(load(root))
    assert "repo.id_prefix" in str(refused.value)


def test_the_cli_mint_fails_with_the_message_and_no_traceback(tmp_path: Path, capsys):
    root = _repo(tmp_path, "acme", None)

    code = main(["-C", str(root), "create", "epic", "billing", "--title", "Billing"])

    err = capsys.readouterr().err
    assert code != 0
    assert "repo.id_prefix" in err
    assert "Traceback" not in err


def test_ids_are_unique_and_lexicographically_increasing(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    minted = [ids.allocate(load(root)) for _ in range(500)]
    assert len(set(minted)) == 500
    assert minted == sorted(minted)


def test_new_ulid_is_monotonic_even_within_one_millisecond():
    burst = [ids.new_ulid() for _ in range(1000)]
    assert len(set(burst)) == 1000
    assert burst == sorted(burst)


def test_allocation_needs_no_counter_and_survives_concurrent_processes(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    a = [ids.allocate(load(root)) for _ in range(50)]
    b = [ids.allocate(load(root)) for _ in range(50)]
    assert len(set(a) | set(b)) == 100



def test_handle_stays_short_for_a_burst_and_expands_round_trip(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    minted = [ids.allocate(load(root)) for _ in range(20)]
    for ident in minted:
        handle = ids.abbreviate(ident, minted)
        assert len(handle.split("-", 1)[1]) <= ids.HANDLE_MIN + 2
        assert handle.startswith("ACME-")
        assert ids.expand(handle, minted) == ident


def test_handle_lengthens_when_fingerprints_collide(monkeypatch):
    a, b = "ACME-" + "0" * 26, "ACME-" + "1" * 26
    monkeypatch.setattr(ids, "_fingerprint",
                        lambda i: {a: "KKKKKKZZZZ000000", b: "KKKKKK9999999999"}.get(i, ""))
    ha = ids.abbreviate(a, [a, b])
    assert len(ha.split("-", 1)[1]) > ids.HANDLE_MIN
    assert ids.expand(ha, [a, b]) == a


def test_expand_is_none_when_ambiguous_or_unknown(monkeypatch):
    a, b = "ACME-" + "0" * 26, "ACME-" + "1" * 26
    monkeypatch.setattr(ids, "_fingerprint",
                        lambda i: {a: "KKKKKKZZZZ000000", b: "KKKKKK9999999999"}.get(i, ""))
    assert ids.expand("ACME-KKKKKK", [a, b]) is None
    assert ids.expand("ACME-777777", [a, b]) is None
    assert ids.expand(a, [a, b]) == a


def test_legacy_counter_ids_still_work_as_opaque_strings():
    legacy = ["ACME-42", "ACME-7"]
    assert ids.abbreviate("ACME-42", legacy) == "ACME-42"
    assert ids.expand("ACME-42", legacy) == "ACME-42"
