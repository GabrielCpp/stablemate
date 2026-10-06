"""A check written again under a second claim of the same node is reported; a check a list of claims shares once is not."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

_PAGE = "docs/features/acme/concepts/ledger.md"
_HEAD = "---\ntype: concept\ntitle: Ledger\n---\n# Ledger\n\n- code: `app.py`\n"
_COUNT = 'count(subject="ledger entries", equals=1)'


def _shared(repo: Path, body: str) -> list[str]:
    write(repo / _PAGE, _HEAD + body)
    write(repo / "app.py", "x = 1\n")
    return [f.message for f in doctor.run(load(repo)).findings if f.code == "shared-check"]


def test_one_check_written_under_two_claims_is_reported_once_naming_both(repo: Path):
    body = (f"- persistence: one entry is kept per payment\n- verify: {_COUNT}\n"
            f"- idempotency: a replayed payment adds no entry\n- verify: {_COUNT}\n")

    [message] = _shared(repo, body)

    assert "`persistence:1`" in message and "`idempotency:1`" in message


def test_a_check_spelled_with_its_arguments_reordered_is_the_same_check(repo: Path):
    body = (f"- persistence: one entry is kept per payment\n- verify: {_COUNT}\n"
            "- idempotency: a replayed payment adds no entry\n"
            '- verify: count(equals=1, subject="ledger entries")\n')

    assert len(_shared(repo, body)) == 1


def test_a_list_of_claims_sharing_its_one_check_is_not_reported(repo: Path):
    body = ("- persistence: all\n  - one entry is kept per payment\n  - the entry keeps its amount\n"
            f"- verify: {_COUNT}\n")

    assert _shared(repo, body) == []


def test_each_claim_with_its_own_check_is_not_reported(repo: Path):
    body = (f"- persistence: one entry is kept per payment\n- verify: {_COUNT}\n"
            "- idempotency: a replayed payment adds no entry\n"
            '- verify: count(subject="ledger entries after a replay", equals=1)\n')

    assert _shared(repo, body) == []
