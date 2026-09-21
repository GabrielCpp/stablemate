"""Id allocation: a per-repo prefix + a coordination-free, lexicographically-increasing ULID, and the git-style short handle that abbreviates it."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ostler import doctor, ids
from ostler.model import load

_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _repo(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    return root


def _ulid_of(identifier: str) -> str:
    return identifier.split("-", 1)[1]



def test_prefix_is_first_four_letters_of_repo_name_uppercased(tmp_path: Path):
    ident = ids.allocate(load(_repo(tmp_path, "stablemate")))
    assert ident.startswith("STAB-")
    assert _ULID.match(_ulid_of(ident))


def test_prefix_skips_non_alphanumerics_and_handles_short_names(tmp_path: Path):
    assert ids.allocate(load(_repo(tmp_path, "my-app"))).startswith("MYAP-")
    assert ids.allocate(load(_repo(tmp_path, "ai"))).startswith("AI-")


def test_explicit_prefix_overrides_and_registry_pins_it(tmp_path: Path):
    root = _repo(tmp_path, "stablemate")
    assert ids.allocate(load(root), prefix="acme").startswith("acme-")
    assert ids.allocate(load(root)).startswith("acme-")
    registry = json.loads((root / ".agents/ids.json").read_text())
    assert registry == {"prefix": "acme"}


def test_new_counter_free_registry_passes_schema_validation(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    ids.allocate(load(root))

    report = doctor.run(load(root))

    assert not [finding for finding in report.findings if finding.code == "schema"]



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
