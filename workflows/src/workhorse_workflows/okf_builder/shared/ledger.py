"""okf-builder's result ledger — what a claim last ran against, not whether it passed.

Modeled on `shared/worklist.py`'s persistence: one JSON file per service, loaded, mutated
in memory, and written back whole. Keyed by claim id (`context.py`'s `obligation["id"]`),
each record holds a fingerprint of what the claim's targeted re-run depends on — the actual
bytes of its cited files and the fixture text its preconditions reach — so a caller can tell
whether a re-run would exercise anything different from what already ran.

Pass/fail is deliberately not a concept this module has an opinion about: `record_result`
stores whatever verdict vocabulary its caller uses, and only the fingerprint comparison in
`needs_rerun` is this module's own logic. Known-defect marking is book content and belongs
to the plan's later slice on repair-side selection, not to run state kept here.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ostler.refs import parse_code_ref
from ostler.stamp import digest_file

#: What a cited file's bytes hash to when the file cannot be read (missing, a repository- or
#: checkout-relative path this module has no root for, a permission error). Fixed rather than
#: empty so a citation that never resolves still contributes *something* stable to the
#: fingerprint — the point is only that it must never be mistaken for real file content, and it
#: must never silently equal `digest_file(b"")`, which a genuinely empty cited file would.
_UNREADABLE = "unreadable"


def claim_fingerprint(
    code_refs: Sequence[str],
    fixture_texts: Mapping[str, str],
    claim_content: str,
    repo_root: Path,
) -> str:
    """A fingerprint over what one claim's targeted re-run depends on.

    `code_refs` are the claim's own `code:` citations (`ostler.refs.code_refs`), each
    optionally carrying a stamped `@digest` that this function does not read: a stamp is a
    copy of a hash the book kept, not the thing itself, and either a stale stamp (nothing
    re-reads the file behind it) or a bare, unstamped citation (nothing to read at all)
    would make a real code change invisible to the fingerprint. Instead each ref is stripped
    to its bare path (`ostler.refs.parse_code_ref`, the same digest-stripping the doctor's own
    citation grouping uses) and resolved against `repo_root`, and the fingerprint hashes the
    file's own bytes at that path (`ostler.stamp.digest_file`) — the actual content a targeted
    re-run would execute against, not any copy of it the book happens to be carrying. A file
    that cannot be read (moved, deleted, a repository-qualified ref this checkout does not
    have) folds in a fixed sentinel instead of raising, so a broken citation still produces a
    stable fingerprint rather than crashing the caller.

    `fixture_texts` is each fixture node's own text the claim's preconditions reach, keyed by
    node id, so a change to a fixture's setup steps changes the fingerprint without any code
    change at all. `claim_content` is a canonical serialization of the claim's own compiled
    obligation or plan step — whatever slice 6 actually executes — supplied by the caller:
    this module has no opinion on what that shape is, only that a book-side repair (an edited
    expected value, a rewritten step) must move the fingerprint even when no cited file or
    fixture changed. `repo_root` is the checkout the caller already resolved `code_refs`
    against — a plain filesystem read, not an ostler/context extraction concern, so this
    module still reaches into no compile/registry internals of its own.

    Two claims that cite the same files and fixtures in a different order still fingerprint
    equal — the set is what changed re-execution cares about, not the order a caller happened
    to list it in.
    """
    digest = hashlib.sha256()
    digest.update(claim_content.encode())
    digest.update(b"\0")
    for ref in sorted(set(code_refs)):
        try:
            path = parse_code_ref(ref).path
        except ValueError:
            path = ref
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(_cited_file_digest(repo_root, path).encode())
        digest.update(b"\0")
    for node_id in sorted(fixture_texts):
        digest.update(node_id.encode())
        digest.update(b"\0")
        digest.update(fixture_texts[node_id].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _cited_file_digest(repo_root: Path, path: str) -> str:
    """The byte digest of one cited, digest-stripped path, or a fixed sentinel when unreadable."""
    try:
        data = (repo_root / path).read_bytes()
    except OSError:
        return _UNREADABLE
    return digest_file(data)


def load_ledger(path: Path) -> dict[str, Any]:
    """Load the persisted ledger, or an empty one when none exists yet or it cannot be read."""
    if not path.exists():
        return {"claims": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"claims": {}}
    if not isinstance(data, dict) or not isinstance(data.get("claims"), dict):
        return {"claims": {}}
    return data


def needs_rerun(ledger: Mapping[str, Any], claim_id: str, fingerprint: str) -> bool:
    """Whether a targeted re-run must execute this claim: no record, or its fingerprint moved."""
    record = ledger.get("claims", {}).get(claim_id)
    return not isinstance(record, dict) or record.get("fingerprint") != fingerprint


def record_result(
    path: Path,
    ledger: dict[str, Any],
    claim_id: str,
    fingerprint: str,
    verdict: str,
    **extra: Any,
) -> dict[str, Any]:
    """Record one claim's outcome against the fingerprint it ran under, and persist it.

    `verdict` and `extra` are the caller's own vocabulary — the ledger stores whatever a
    live audit turn reports; it does not interpret pass/fail itself. Returns `ledger` so a
    caller can chain further writes before the next persist, the same shape
    `shared/worklist.py`'s `record` returns its own mutated `data`.
    """
    claims = ledger.setdefault("claims", {})
    claims[claim_id] = {"fingerprint": fingerprint, "verdict": verdict, **extra}
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger


__all__ = [
    "claim_fingerprint",
    "load_ledger",
    "needs_rerun",
    "record_result",
]
