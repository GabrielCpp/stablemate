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
import subprocess
from pathlib import Path
from typing import Literal

import pytest
from ostler.model import UINode
from ostler.qa.plan import load_plan, resolve_spec_dir

from workhorse_workflows.okf_builder.live_audit import flow as live_audit_flow
from workhorse_workflows.okf_builder.live_audit.flow import (
    BOOK_TARGET, _fixture_texts_for, _node_text, audit_one_spec,
)
from workhorse_workflows.okf_builder.shared.ledger import claim_fingerprint
from workhorse_workflows.qa.schemas import QaPlanRun, StackStatus

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


def _fake_stack_ready() -> StackStatus:
    return StackStatus(ready="unneeded", notes="The book serves nothing.")


def _fake_run(
    status: Literal["passed", "failed", "blocked", "invalid"],
    *, assertions: int = 1, failures: int = 0,
) -> QaPlanRun:
    return QaPlanRun(
        status=status,
        notes=f"Ostler QA run returned {status}.",
        ostler={
            "scenarios": {
                "charge-is-covered": {
                    "status": status, "assertions": assertions, "failures": failures,
                    "message": "ok" if status == "passed" else "assertion failed",
                },
            },
        },
    )


def test_blocked_when_no_stack_runbook(
    logger: logging.Logger, two_root_book: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A book with a served surface but no stack runbook blocks before running anything.

    `ensure_stack` itself already returns this — this pins that `audit_one_spec` surfaces
    it as `status="blocked"` rather than trying to run the plan against nothing.
    """
    docs_root, repo_root = two_root_book
    monkeypatch.setattr(
        live_audit_flow, "ensure_stack",
        lambda *a, **k: StackStatus(ready="none", notes="no stack runbook"),
    )

    def _fail_if_run(*args: object, **kwargs: object) -> QaPlanRun:
        raise AssertionError("run_qa_plan must not run when the stack is blocked")

    monkeypatch.setattr(live_audit_flow, "run_qa_plan", _fail_if_run)

    report = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )
    assert report.status == "blocked"
    assert report.scenarios == ()


def test_skip_on_unchanged_fingerprint_surfaces_carried_result(
    logger: logging.Logger, two_root_book: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second pass over an untouched plan carries the recorded verdict, not a re-run."""
    docs_root, repo_root = two_root_book
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())
    monkeypatch.setattr(live_audit_flow, "run_qa_plan", lambda *a, **k: _fake_run("passed"))

    baseline = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )
    assert baseline.scenarios[0].source == "fresh"
    assert baseline.scenarios[0].status == "passed"

    def _fail_if_run(*args: object, **kwargs: object) -> QaPlanRun:
        raise AssertionError("an unchanged fingerprint must not be re-run")

    monkeypatch.setattr(live_audit_flow, "run_qa_plan", _fail_if_run)

    carried = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )
    assert carried.scenarios[0].source == "carried"
    assert carried.scenarios[0].status == "passed"
    assert carried.scenarios[0].changed is False
    assert carried.scenarios[0].fingerprint == baseline.scenarios[0].fingerprint


def test_rerun_when_cited_file_changes(
    logger: logging.Logger, two_root_book: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing the cited source file moves the fingerprint and forces a real re-run."""
    docs_root, repo_root = two_root_book
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())
    monkeypatch.setattr(live_audit_flow, "run_qa_plan", lambda *a, **k: _fake_run("passed"))

    baseline = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )
    assert baseline.scenarios[0].source == "fresh"

    (repo_root / REPOSITORY / "service.py").write_text(
        '"""The billing service, now different."""\n\n\ndef charge(amount):\n    return amount\n',
        encoding="utf-8",
    )

    ran_only: list[object] = []

    def _record_only(*args: object, only: list[str] | None = None, **kwargs: object) -> QaPlanRun:
        ran_only.append(only)
        return _fake_run("passed")

    monkeypatch.setattr(live_audit_flow, "run_qa_plan", _record_only)

    rerun = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )
    assert rerun.scenarios[0].source == "fresh"
    assert rerun.scenarios[0].changed is True
    assert rerun.scenarios[0].fingerprint != baseline.scenarios[0].fingerprint
    assert ran_only == [["charge-is-covered"]]


def test_failing_scenario_is_overwritten_by_a_later_passing_run(
    logger: logging.Logger, two_root_book: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later pass over the same (changed) plan replaces the ledger record, not appends."""
    docs_root, repo_root = two_root_book
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())
    monkeypatch.setattr(
        live_audit_flow, "run_qa_plan",
        lambda *a, **k: _fake_run("failed", assertions=1, failures=1),
    )

    failing = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )
    assert failing.scenarios[0].status == "failed"
    ledger_path = docs_root / "docs/specs/story-1" / live_audit_flow.LEDGER_FILE
    assert json.loads(ledger_path.read_text())["claims"]["charge-is-covered"]["verdict"] == "failed"

    # rerun_all=True forces a fresh execution even though the fingerprint has not moved,
    # for the case the failure is a flake and the operator wants the ledger corrected.
    monkeypatch.setattr(live_audit_flow, "run_qa_plan", lambda *a, **k: _fake_run("passed"))
    passing = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
        rerun_all=True,
    )
    assert passing.scenarios[0].status == "passed"
    assert passing.scenarios[0].source == "fresh"
    record = json.loads(ledger_path.read_text())["claims"]
    assert len(record) == 1
    assert record["charge-is-covered"]["verdict"] == "passed"


# --- Book-as-plan-source: no authored `qa_plan.py`, the compiled path -----------------

FIXTURE_NODE = """---
type: fixture
title: Seeded thing
---
# Seeded thing

- provides:
  - id — the seeded thing's id

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-thing.sh
"""

FIXTURE_PATH = "docs/features/app/fixtures/seeded-thing.md"

#: One gap-free obligation (`get-thing`: GET, a fixture declared, a plain `http_status`
#: check, no unresolved template variable) and one obligation that gaps (`create-thing`:
#: checks declared but no `fixture:` at all, so `compile_plan_gaps` reports
#: `unresolved-precondition: no fixture arranged for this obligation` — see
#: `ostler/ostler/qa/compile.py`). `compile_plan` groups obligations into one scenario
#: per *source file*, so the two live in separate files — otherwise the gap-free
#: obligation would be folded into the same scenario function as the gapped one and
#: excluded along with it, rather than compiling and running on its own.
GET_NODE = """---
type: endpoint
title: App things read
---
# App things read

## Invocations

### get-thing

- route: `GET /api/things`
- does: a thing is fetched.
- fixture: seeded-thing
- verify: http_status(code=200)
- code: app/service.py::get_thing
"""

GET_PATH = "docs/features/app/server-read.md"

CREATE_NODE = """---
type: endpoint
title: App things write
---
# App things write

## Invocations

### create-thing

- route: `POST /api/things`
- does: a thing is created.
- verify: http_status(code=201)
- code: app/service.py::create_thing
"""

CREATE_PATH = "docs/features/app/server-write.md"

#: Phase 2h reads a target's `base_url` off the book instead of a fixed CLI default, so a
#: surface with obligations needs a `server` node stating `entry-url:` or every obligation
#: gaps as `undeclared-entry-url` regardless of what else it declares.
SERVER_NODE = """---
type: server
title: App server
---
# App server

- launch: `python -m app.service`
- entry-url: http://localhost:8000
- walkthrough: true
"""

SERVER_PATH = "docs/features/app/server.md"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


@pytest.fixture
def compiled_book(tmp_path: Path) -> Path:
    """A single-root book (docs and source share a git worktree) with no authored plan.

    `book_context` diffs `EMPTY_TREE_SHA..WORKTREE`, which needs a git repository but no
    commit at all — the empty-tree object is present in every repository already.
    """
    root = tmp_path / "book"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    (root / FIXTURE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / FIXTURE_PATH).write_text(FIXTURE_NODE, encoding="utf-8")
    (root / GET_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / GET_PATH).write_text(GET_NODE, encoding="utf-8")
    (root / CREATE_PATH).write_text(CREATE_NODE, encoding="utf-8")
    (root / SERVER_PATH).write_text(SERVER_NODE, encoding="utf-8")
    (root / "app/service.py").parent.mkdir(parents=True, exist_ok=True)
    (root / "app/service.py").write_text(
        "def get_thing():\n    return 'thing'\n\n\ndef create_thing():\n    return 'thing'\n",
        encoding="utf-8",
    )
    return root


def test_compiled_book_reports_blocked_obligations_with_gap_details(
    logger: logging.Logger, compiled_book: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A book with no authored plan uses `compile_plan_gaps`, and reports every gap.

    Before this slice, `discover_spec_dirs()` on a book like this returned `[]`, `LiveAudit`
    reported zero specs, and the operator gate's `any(...)` over an empty list passed
    silently — nothing ran and nothing was said. This pins the fix: the compiled path
    reports the gap, by obligation id and kind, with the compiler's own detail line.
    """
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())
    monkeypatch.setattr(live_audit_flow, "run_qa_plan", lambda *a, **k: _fake_run("passed"))

    report = audit_one_spec(
        logger, BOOK_TARGET, docs_path=str(compiled_book), repo_dir=str(compiled_book),
    )

    assert report.gaps, "the gapped create-thing obligation must be reported"
    gap_ids = {g["obligation_id"] for g in report.gaps}
    assert any("create-thing" in gid for gid in gap_ids)
    for gap in report.gaps:
        assert gap["kind"] and gap["detail"]


def test_compiled_book_runs_a_gap_free_obligation_for_real(
    logger: logging.Logger, compiled_book: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one obligation that compiles clean is actually executed as a real scenario.

    `get-thing` (GET, fixture declared, plain `http_status`) must reach `run_qa_plan`,
    get fingerprinted, and gain a ledger row — the gapped `create-thing` must not.
    """
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())

    ran_only: list[object] = []

    def _record_and_run(*args: object, only: list[str] | None = None, **kwargs: object) -> QaPlanRun:
        ran_only.append(only)
        assert only is not None
        return QaPlanRun(
            status="passed",
            notes="Ostler QA run returned passed.",
            ostler={
                "scenarios": {
                    sid: {"status": "passed", "assertions": 1, "failures": 0, "message": "ok"}
                    for sid in only
                },
            },
        )

    monkeypatch.setattr(live_audit_flow, "run_qa_plan", _record_and_run)

    report = audit_one_spec(
        logger, BOOK_TARGET, docs_path=str(compiled_book), repo_dir=str(compiled_book),
    )

    assert report.status == "ran"
    assert len(report.scenarios) == 1
    scenario = report.scenarios[0]
    assert "create-thing" not in scenario.id
    assert scenario.status == "passed"
    assert ran_only and ran_only[0]

    ledger_path = compiled_book / live_audit_flow._COMPILED_RUN_ROOT / "book" / live_audit_flow.LEDGER_FILE
    ledger = json.loads(ledger_path.read_text())["claims"]
    assert len(ledger) == 1
    assert scenario.id in ledger


def test_compiled_gaps_never_ledgered_and_re_report_every_pass(
    logger: logging.Logger, compiled_book: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Condition 3: a compile gap is not a result — it is never fingerprinted or ledgered.

    A gapped obligation has no scenario to run, so it never becomes a `ScenarioResult`
    (blocked and failed are distinct — condition 2) and never gains a ledger row (the
    ledger only records an executed claim's verdict). Because nothing about the gap is
    ever recorded, re-running reports the identical gap every single pass — there is no
    ledger-based suppression of book debt the way a passing scenario's fingerprint would
    suppress a re-run.
    """
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())
    monkeypatch.setattr(live_audit_flow, "run_qa_plan", lambda *a, **k: _fake_run("passed"))

    first = audit_one_spec(
        logger, BOOK_TARGET, docs_path=str(compiled_book), repo_dir=str(compiled_book),
    )
    second = audit_one_spec(
        logger, BOOK_TARGET, docs_path=str(compiled_book), repo_dir=str(compiled_book),
    )

    assert first.gaps and second.gaps
    assert {g["obligation_id"] for g in first.gaps} == {g["obligation_id"] for g in second.gaps}

    # No `ScenarioResult` for the gapped obligation, on either pass.
    for report in (first, second):
        assert not any("create-thing" in s.id for s in report.scenarios)

    ledger_path = compiled_book / live_audit_flow._COMPILED_RUN_ROOT / "book" / live_audit_flow.LEDGER_FILE
    ledger = json.loads(ledger_path.read_text())["claims"]
    assert len(ledger) == 1
    assert not any("create-thing" in claim_id for claim_id in ledger)


def test_strict_mode_violation_is_a_book_gap_not_a_failed_scenario(
    logger: logging.Logger, two_root_book: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 8: a Playwright strict-mode violation is book debt, never a failed check.

    `compile.py` emits an author's `selector:` locator as-is and never guesses a `.first`
    on their behalf — `selector:` is unique by intent, not by construction. When that
    intent is wrong, Playwright's own strict mode raises, and by the time it reaches this
    flow it is folded into the scenario's `message` as a traceback
    (`ostler_qa.py`'s `_run`: `except BaseException: ... traceback.format_exc()`). That is
    attributable to the book, never to the app, so `audit_one_spec` must report it as a
    `gaps` entry (kind `unresolved-precondition`, keyed to the scenario's own covered
    obligation id) rather than as a failing `ScenarioResult` or a ledger row a later,
    unchanged pass would carry forward as a false failure.
    """
    docs_root, repo_root = two_root_book
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())

    traceback_text = (
        "Traceback (most recent call last):\n"
        '  File "qa_plan.py", line 12, in charge_is_covered\n'
        '    qa.verify("visible", qa.page.locator("span.field-error"))\n'
        "playwright._impl._errors.Error: strict mode violation: "
        'locator("span.field-error") resolved to 6 elements:\n'
        '    1) <span class="field-error">…</span>\n'
    )
    monkeypatch.setattr(
        live_audit_flow, "run_qa_plan",
        lambda *a, **k: QaPlanRun(
            status="failed",
            notes="Ostler QA run returned failed.",
            ostler={
                "scenarios": {
                    "charge-is-covered": {
                        "status": "failed", "assertions": 1, "failures": 1,
                        "message": traceback_text,
                    },
                },
            },
        ),
    )

    report = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )

    # No failing scenario — the strict-mode-violation outcome is reclassified entirely.
    assert report.scenarios == ()
    assert len(report.gaps) == 1
    [gap] = report.gaps
    assert gap["kind"] == "unresolved-precondition"
    assert gap["obligation_id"] == "okf:docs/features/acme/concepts/charge.md:contract"
    assert "strict mode violation" in gap["detail"]

    # Never ledgered: a later pass with the same (unmoved) fingerprint must re-attempt it,
    # not silently carry a failure forward the way a genuine failed assertion would.
    ledger_path = docs_root / "docs/specs/story-1" / live_audit_flow.LEDGER_FILE
    assert not ledger_path.exists() or not json.loads(ledger_path.read_text())["claims"]


def test_authored_plan_takes_precedence_over_the_compiled_book(
    logger: logging.Logger, two_root_book: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authored `qa_plan.py` wins even when the book itself could also compile a plan.

    `two_root_book`'s spec dir authors a `qa_plan.py`; if the compiled path were ever
    reached instead, `book_context` would be called against `two_root_book`'s split
    docs/checkout layout, which `_book_context_or_note` explicitly cannot support (see
    its own docstring) and would return a blocked report naming that gap. Getting a real
    `status="ran"` result with the authored scenario's own id proves the authored path,
    not the compiled one, ran.
    """
    docs_root, repo_root = two_root_book
    monkeypatch.setattr(live_audit_flow, "ensure_stack", lambda *a, **k: _fake_stack_ready())
    monkeypatch.setattr(live_audit_flow, "run_qa_plan", lambda *a, **k: _fake_run("passed"))

    def _fail_if_book_context_used(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("the compiled book_context path must not run when a plan is authored")

    monkeypatch.setattr(live_audit_flow, "book_context", _fail_if_book_context_used)

    report = audit_one_spec(
        logger, "docs/specs/story-1", docs_path=str(docs_root), repo_dir=str(repo_root),
    )

    assert report.status == "ran"
    assert report.scenarios[0].id == "charge-is-covered"
