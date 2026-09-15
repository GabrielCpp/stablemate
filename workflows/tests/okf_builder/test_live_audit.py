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

import json
import logging
from pathlib import Path

import pytest
from ostler.model import UINode
from ostler.qa.plan import load_plan, resolve_spec_dir

from workhorse_workflows.okf_builder.live_audit.flow import (
    _fixture_texts_for, _node_text, audit_one_spec,
)
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

    # The compiled claim content is the scenario's own rendered fields (id, covers,
    # mechanism, ...), not the bare id — reloading the same plan the flow read gives the
    # exact dict `audit_one_spec` serializes, rather than guessing its shape by hand.
    resolved_spec_dir = resolve_spec_dir(
        Path("docs/specs/story-1") / "qa_plan.py", Path("docs/specs/story-1"), docs_root,
    )
    document, problems = load_plan(
        Path("docs/specs/story-1") / "qa_plan.py", resolved_spec_dir, docs_root,
    )
    assert document is not None, problems
    [scenario_data] = document.data["scenarios"]
    claim_content = json.dumps(scenario_data, sort_keys=True, default=str)

    # What the fingerprint must be if `own_repository` were resolved correctly (matches
    # `charge_is_covered`'s own repository) vs. what it would be if `audit_one_spec` had
    # forgotten to pass it (the ledger's own default, which folds the repository-qualified
    # ref into the unreadable sentinel because `REPOSITORY != ""`).
    correct = claim_fingerprint(
        scenario.code_refs, {}, claim_content, repo_root, own_repository=REPOSITORY,
    )
    wrong = claim_fingerprint(scenario.code_refs, {}, claim_content, repo_root)

    assert scenario.fingerprint == correct
    assert scenario.fingerprint != wrong


def test_claim_content_change_moves_the_fingerprint(
    logger: logging.Logger, two_root_book: tuple[Path, Path]
) -> None:
    """A book-only edit to the scenario's own asserted content moves the fingerprint.

    Ruling 1's whole point: a claim's own compiled content changing must not be invisible
    just because the cited file and fixtures did not change. Two otherwise identical plans,
    one with an edited scenario docstring (`ScenarioDecl.objective`, part of the serialized
    scenario this test's fingerprint is built from), must fingerprint differently.
    """
    docs_root, repo_root = two_root_book
    baseline = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )

    edited_plan = QA_PLAN.replace(
        '"""The charge concept is exercised."""',
        '"""The charge concept is exercised, and now says something different."""',
    )
    assert edited_plan != QA_PLAN
    (docs_root / "docs/specs/story-1/qa_plan.py").write_text(edited_plan, encoding="utf-8")

    edited = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )

    assert edited.scenarios[0].code_refs == baseline.scenarios[0].code_refs
    assert edited.scenarios[0].fingerprint != baseline.scenarios[0].fingerprint


def test_node_text_renders_ordered_bullets() -> None:
    node = UINode(
        type="fixture", kind="section", id="seed-org", path=Path("docs/features/x.md"),
        bullet_order=[("run", "seed-org.sh", 10), ("provides", "org_id", 11)],
    )
    assert _node_text(node) == "run: seed-org.sh\nprovides: org_id"


def test_fixture_texts_for_resolves_declared_fixtures_by_name() -> None:
    fixture_node = UINode(
        type="fixture", kind="section", id="seed-org", path=Path("docs/features/x.md"),
        bullet_order=[("run", "seed-org.sh", 10)],
    )
    obligations_by_id = {
        "okf:x:contract": {"fixturesDeclared": [{"name": "seed-org", "args": []}]},
    }
    texts = _fixture_texts_for(
        ["okf:x:contract"], obligations_by_id, {"seed-org": fixture_node},
    )
    assert texts == {"seed-org": "run: seed-org.sh"}

    # A change to the fixture node's own bullets is a change to the text this function
    # returns, which `claim_fingerprint` folds in independent of any cited code file.
    fixture_node.bullet_order = [("run", "seed-org-v2.sh", 10)]
    changed = _fixture_texts_for(
        ["okf:x:contract"], obligations_by_id, {"seed-org": fixture_node},
    )
    assert changed["seed-org"] != texts["seed-org"]
