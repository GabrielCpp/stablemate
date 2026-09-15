"""okf-builder's result ledger — what a claim last ran against, not whether it passed.

Modeled on `shared/worklist.py`'s persistence: one JSON file per service, loaded, mutated
in memory, and written back whole. Keyed by claim id (`context.py`'s `obligation["id"]`),
each record holds a fingerprint of what the claim's targeted re-run depends on — its cited
`code:` refs and the fixture text its preconditions reach — so a caller can tell whether a
re-run would exercise anything different from what already ran.

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


def claim_fingerprint(
    code_refs: Sequence[str], fixture_texts: Mapping[str, str], claim_content: str
) -> str:
    """A fingerprint over what one claim's targeted re-run depends on.

    `code_refs` are the claim's own `code:` citations, already rendered with their
    `@digest` stamp (`ostler.refs.code_refs`) — the digest doctor's `stale-citation` check
    already keeps current, so this never re-reads the cited files itself. `fixture_texts`
    is each fixture node's own text the claim's preconditions reach, keyed by node id, so a
    change to a fixture's setup steps changes the fingerprint without any code change at all.
    `claim_content` is a canonical serialization of the claim's own compiled obligation or
    plan step — whatever slice 6 actually executes — supplied by the caller: this module has
    no opinion on what that shape is, only that a book-side repair (an edited expected value,
    a rewritten step) must move the fingerprint even when no cited file or fixture changed.

    Two claims that cite the same files and fixtures in a different order still fingerprint
    equal — the set is what changed re-execution cares about, not the order a caller happened
    to list it in.
    """
    digest = hashlib.sha256()
    digest.update(claim_content.encode())
    digest.update(b"\0")
    for ref in sorted(set(code_refs)):
        digest.update(ref.encode())
        digest.update(b"\0")
    for node_id in sorted(fixture_texts):
        digest.update(node_id.encode())
        digest.update(b"\0")
        digest.update(fixture_texts[node_id].encode())
        digest.update(b"\0")
    return digest.hexdigest()


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
