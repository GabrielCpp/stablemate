"""Pinning `audit_one_spec` threads `own_repository` into every ledger call it makes.

`ledger.claim_fingerprint` defaults `own_repository` to `""`; a caller that forgets to
pass the book's own repository folds every repository-qualified citation — same-repo ones
included — into the unreadable-file sentinel, silently making every fingerprint look
identical regardless of what the cited file actually says. `audit_one_spec` resolves it
the same way `doctor.py` does (`book_repository(features_root_of(graph))`), but nothing
exercised that path end to end before this test: the existing ledger tests call
`claim_fingerprint` directly, never through the flow that is supposed to feed it.

The book here (docs) and the source it cites (a separate checkout) are deliberately two
different directories, so a fingerprint that came out right could only have come from a
real `own_repository`/`repo_root` resolution, not from the two roots being the same
directory by accident.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from workhorse_workflows.okf_builder.live_audit.flow import audit_one_spec
from workhorse_workflows.okf_builder.shared.ledger import claim_fingerprint

REPOSITORY = "acme"
REF = f"repo://{REPOSITORY}/{REPOSITORY}/service.py::charge"

CONCEPT = f"""---
type: concept
slug: charge
title: Charge
---
# Charge

- code: `{REF}`

Charging.
"""

QA_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["okf:docs/features/acme/concepts/charge.md:contract"])
def charge_is_covered(qa: Qa) -> None:
    """The charge concept is exercised."""
    qa.check("charge holds", True, covers=["okf:docs/features/acme/concepts/charge.md:contract"])
'''


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test.okf_builder.live_audit")


@pytest.fixture
def two_root_book(tmp_path: Path) -> tuple[Path, Path]:
    """A docs root and a source checkout that are genuinely separate directories.

    Only a book naming its own repository (`docs/features/repository.txt`) and a
    citation qualified with `repo://<that repository>/...` exercises the code path this
    test pins — a bare, unqualified citation would resolve against `repo_root` either way
    and would not tell an `own_repository=""` bug from a correct resolution.
    """
    repo_root = tmp_path / "checkout"
    (repo_root / REPOSITORY).mkdir(parents=True)
    (repo_root / REPOSITORY / "service.py").write_text(
        '"""The billing service."""\n\n\ndef charge(amount):\n    return amount\n',
        encoding="utf-8",
    )

    docs_root = tmp_path / "book"
    features = docs_root / "docs/features"
    features.mkdir(parents=True)
    (features / "repository.txt").write_text(REPOSITORY, encoding="utf-8")
    (features / "acme/concepts").mkdir(parents=True)
    (features / "acme/concepts/charge.md").write_text(CONCEPT, encoding="utf-8")

    spec = docs_root / "docs/specs/story-1"
    spec.mkdir(parents=True)
    (spec / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")

    return docs_root, repo_root


def test_live_audit_resolves_the_books_own_repository(
    logger: logging.Logger, two_root_book: tuple[Path, Path]
) -> None:
    docs_root, repo_root = two_root_book

    report = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )

    assert report.status == "ran"
    assert len(report.scenarios) == 1
    scenario = report.scenarios[0]
    assert scenario.code_refs == (REF,)

    # What the fingerprint must be if `own_repository` were resolved correctly (matches
    # `charge_is_covered`'s own repository) vs. what it would be if `audit_one_spec` had
    # forgotten to pass it (the ledger's own default, which folds the repository-qualified
    # ref into the unreadable sentinel because `REPOSITORY != ""`).
    correct = claim_fingerprint(
        scenario.code_refs, {}, scenario.id, repo_root, own_repository=REPOSITORY,
    )
    wrong = claim_fingerprint(scenario.code_refs, {}, scenario.id, repo_root)

    assert scenario.fingerprint == correct
    assert scenario.fingerprint != wrong
