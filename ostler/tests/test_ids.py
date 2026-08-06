"""Id allocation: a per-repo prefix + a coordination-free, lexicographically-increasing ULID,
and the git-style short handle that abbreviates it."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ostler import ids
from ostler.model import load

_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")   # 26 uppercase Crockford Base32 chars


def _repo(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    return root


def _ulid_of(identifier: str) -> str:
    return identifier.split("-", 1)[1]


# ── prefix: unchanged, still tied to the repo name ───────────────────────────────────────

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
    # once minted the prefix is pinned — later allocations keep it, with no counter in the registry
    assert ids.allocate(load(root)).startswith("acme-")
    registry = json.loads((root / ".agents/ids.json").read_text())
    assert registry == {"prefix": "acme"}


# ── the ULID body: unique, sortable, coordination-free ───────────────────────────────────

def test_ids_are_unique_and_lexicographically_increasing(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    minted = [ids.allocate(load(root)) for _ in range(500)]
    assert len(set(minted)) == 500                 # no collisions
    assert minted == sorted(minted)                # strictly increasing in mint order (monotonic)


def test_new_ulid_is_monotonic_even_within_one_millisecond():
    burst = [ids.new_ulid() for _ in range(1000)]  # far more than fit in a ms → forces the tiebreak
    assert len(set(burst)) == 1000
    assert burst == sorted(burst)


def test_allocation_needs_no_counter_and_survives_concurrent_processes(tmp_path: Path):
    # No shared mutable counter, so two independent "processes" (fresh graph loads, as a subprocess
    # would have) never collide — the property the old counter could not give across worktrees.
    root = _repo(tmp_path, "acme")
    a = [ids.allocate(load(root)) for _ in range(50)]
    b = [ids.allocate(load(root)) for _ in range(50)]
    assert len(set(a) | set(b)) == 100


# ── short handle (git-style, over a hash so bursts stay short) ────────────────────────────

def test_handle_stays_short_for_a_burst_and_expands_round_trip(tmp_path: Path):
    root = _repo(tmp_path, "acme")
    minted = [ids.allocate(load(root)) for _ in range(20)]   # a same-ms burst (adjacent ULIDs)
    for ident in minted:
        handle = ids.abbreviate(ident, minted)
        # hashing decorrelates the near-identical burst ids, so handles hug the floor length
        assert len(handle.split("-", 1)[1]) <= ids.HANDLE_MIN + 2
        assert handle.startswith("ACME-")
        assert ids.expand(handle, minted) == ident           # resolves back uniquely


def test_handle_lengthens_when_fingerprints_collide(monkeypatch):
    # Hash collisions can't be hand-crafted, so drive _fingerprint to share the first 6 chars.
    a, b = "ACME-" + "0" * 26, "ACME-" + "1" * 26
    monkeypatch.setattr(ids, "_fingerprint",
                        lambda i: {a: "KKKKKKZZZZ000000", b: "KKKKKK9999999999"}.get(i, ""))
    ha = ids.abbreviate(a, [a, b])
    assert len(ha.split("-", 1)[1]) > ids.HANDLE_MIN         # grew past the 6-char floor
    assert ids.expand(ha, [a, b]) == a


def test_expand_is_none_when_ambiguous_or_unknown(monkeypatch):
    a, b = "ACME-" + "0" * 26, "ACME-" + "1" * 26
    monkeypatch.setattr(ids, "_fingerprint",
                        lambda i: {a: "KKKKKKZZZZ000000", b: "KKKKKK9999999999"}.get(i, ""))
    assert ids.expand("ACME-KKKKKK", [a, b]) is None         # matches both → ambiguous
    assert ids.expand("ACME-777777", [a, b]) is None         # matches none
    assert ids.expand(a, [a, b]) == a                        # a full id passes through


def test_legacy_counter_ids_still_work_as_opaque_strings():
    # An old ACME-42 has no ULID; abbreviate leaves it whole and expand still matches it exact.
    legacy = ["ACME-42", "ACME-7"]
    assert ids.abbreviate("ACME-42", legacy) == "ACME-42"
    assert ids.expand("ACME-42", legacy) == "ACME-42"
