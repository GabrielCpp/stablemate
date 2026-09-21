"""okf-builder's result ledger — what a claim last ran against, not whether it passed."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ostler.provenance import checkout_for
from ostler.refs import parse_code_ref, strip_digest
from ostler.stamp import digest_file

_UNREADABLE = "unreadable"


def claim_fingerprint(
    code_refs: Sequence[str],
    fixture_texts: Mapping[str, str],
    claim_content: str,
    repo_root: Path,
    *,
    own_repository: str = "",
    checkouts: Mapping[str, Path] | None = None,
) -> str:
    """A fingerprint over what one claim's targeted re-run depends on."""
    digest = hashlib.sha256()
    digest.update(claim_content.encode())
    digest.update(b"\0")
    checkout_map = dict(checkouts) if checkouts else {}
    for ref in sorted({strip_digest(item) for item in code_refs}):
        try:
            parsed = parse_code_ref(ref)
            path, repository = parsed.path, parsed.repository
        except ValueError:
            path, repository = ref, ""
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(
            _cited_file_digest(repo_root, path, repository, own_repository, checkout_map).encode()
        )
        digest.update(b"\0")
    for node_id in sorted(fixture_texts):
        digest.update(node_id.encode())
        digest.update(b"\0")
        digest.update(fixture_texts[node_id].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _cited_file_digest(
    repo_root: Path,
    path: str,
    repository: str,
    own_repository: str,
    checkouts: dict[str, Path],
) -> str:
    """The byte digest of one cited, digest-stripped path, or a fixed sentinel when unreadable."""
    source_root = repo_root
    if repository and repository != own_repository:
        checkout = checkout_for(repository, checkouts, default=own_repository)
        if checkout is None:
            return _UNREADABLE
        source_root = checkout
    try:
        data = (source_root / path).read_bytes()
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
    """Record one claim's outcome against the fingerprint it ran under, and persist it."""
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
