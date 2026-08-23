"""The experiment that asks whether a declared check could have gone red."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import checks, model
from ostler.qa import sensitivity


def _trial(text: str) -> sensitivity.Trial:
    call = checks.parse_check(text)
    assert isinstance(call, checks.CheckCall), call
    return sensitivity.trial(call)


@pytest.mark.parametrize(
    "call",
    [
        'http_status(code=200, path="/policies")',
        'http_status(code=401, title="Unauthorized")',
        'json_path(path="claim.amount_cents", equals="125000")',
        'json_path(path="claim.amount_cents", equals=125000)',
        'json_path(path="claim.paid", equals=true)',
        'json_path(path="policy.status", matches="Draft|Active")',
        'json_path(path="errors.premium", absent=false)',
        'json_path(path="detail.token", absent=true)',
        """json_path(path="people[?(@.who=='ana')].total_cents", equals=4200)""",
        'json_path(path="people[*].id", absent=true)',
        'json_path(path="items[*].kind", matches="^trip$")',
        'count(subject="people[*].trips[*]", equals=3)',
        'omits(subject="people[?(@.who==\'ana\')].note", text="secret")',
        'unchanged(subject="ledger", except_fields=["updated_at"])',
        'keys_unchanged(subject="ledger")',
        'count(subject="policies", equals=3)',
        'absent(subject="the cancelled policy")',
        'created(subject="the policy")',
        'removed(subject="the policy")',
        'visible(locator="text=Draft", text="Draft")',
        'persists(subject="the policy")',
        'emitted(event="policy.created", count=1)',
        'omits(subject="detail", matches="eyJ[A-Za-z0-9_-]{6,}")',
        'conflict_on_stale(subject="the policy")',
    ],
)
def test_every_check_in_the_vocabulary_has_a_witness_and_a_defect(call: str) -> None:
    """A check the harness cannot witness reports every book that uses it unmeasured."""
    trial = _trial(call)
    assert trial.witnessed, trial.note
    assert trial.sensitive, f"no mutation of {call} went red"


def test_a_filter_witness_is_the_smallest_document_the_selector_is_satisfied_by() -> None:
    """The witness carries the key the filter selects on beside the value the claim reads, so
    a mutation of that value is noticed through the selector and not around it."""
    path = "people[?(@.who=='ana')].total_cents"
    assert sensitivity._set_path({}, path, 4200) == {"people": [{"who": "ana", "total_cents": 4200}]}
    assert sensitivity._collection("people[*].trips[*]", 2) == {"people": [{"trips": [{"i": 0}, {"i": 1}]}]}
    trial = _trial(f'json_path(path="{path}", equals=4200)')
    assert trial.witnessed
    assert trial.flipped == ("the field holds something else", "the field is not there at all")


def test_a_presence_assertion_is_not_asked_to_notice_a_changed_value() -> None:
    """`absent=false` claims the field is there and claims nothing about what it holds."""
    trial = _trial('json_path(path="errors.premium", absent=false)')
    assert trial.flipped == ("the field the claim requires is missing",)
    assert not trial.survived


def test_a_check_nothing_could_falsify_is_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property under test is the harness's own: a rubber stamp has to read as one."""
    monkeypatch.setitem(
        sensitivity._VERIFIERS, "visible", lambda observed, args: (True, {}, {})
    )
    trial = _trial('visible(locator="text=Draft", text="Draft")')
    assert trial.witnessed and not trial.sensitive
    assert trial.survived and not trial.flipped


@pytest.mark.parametrize(
    "call",
    [
        'json_path(path="claim.status", matches=".*")',
        'json_path(path="claim.status", matches=".")',
    ],
)
def test_a_pattern_that_admits_any_value_is_insensitive(call: str) -> None:
    """The shape a lax rule blesses: a stamp rescued by the mutation it was not written for.

    Both patterns parse, and both notice the field going missing — which is enough for an
    `any(flipped)` rule to call them discriminating. Neither can tell one value from
    another, so the mutation that matters survives, and that is what has to disqualify them.
    """
    trial = _trial(call)
    assert trial.witnessed
    assert trial.flipped == ("the field is not there at all",)
    assert trial.survived == ("the field holds something else",)
    assert not trial.sensitive


def test_a_pattern_no_string_can_be_invented_for_is_unwitnessed_not_green() -> None:
    """Reporting a guess as a witness would credit sensitivity the experiment never showed."""
    trial = _trial(r'omits(subject="detail", matches="(?=x)(?!x)")')
    assert not trial.witnessed
    assert "no leaking value" in trial.note


def test_a_synthesized_witness_is_a_member_of_the_language() -> None:
    assert sensitivity._matching("eyJ[A-Za-z0-9_-]{6,}") == "eyJ------"
    assert sensitivity._matching("Draft|Active") == "Draft"
    assert sensitivity._matching(r"Bearer \w+") == "Bearer a"


def test_the_benchmark_corpus_declares_no_check_that_cannot_go_red() -> None:
    """The calibration set: every catch the seeded-defect books earned survives the mutations."""
    apps = Path(__file__).resolve().parents[2] / "paddock" / "data" / "apps"
    for app in sorted(apps.iterdir()):
        if not (app / "docs").is_dir():
            continue
        outcome = sensitivity.cmd_sensitivity(app)
        assert outcome.ok, f"{app.name}: {outcome.message}"


def _book(tmp_path: Path, endpoint: str) -> Path:
    docs = tmp_path / "docs" / "features"
    docs.mkdir(parents=True)
    (docs / "api.md").write_text(
        "---\ntype: server\nslug: api\ntitle: API\n---\n# API\n\n"
        "## Endpoints\n\n### post-policies\n\n" + endpoint,
        encoding="utf-8",
    )
    return tmp_path


def test_a_claim_no_check_observes_is_counted_undeclared_not_dropped(tmp_path: Path) -> None:
    """The denominator is every claim the book mints, not every claim that declares a check.

    Dropping the unobserved ones lets a book raise its score by deleting an assertion instead
    of strengthening one, which is the opposite of what the metric is for.
    """
    root = _book(tmp_path, (
        "- errors: `409` when the policy number is already on the books\n"
        '- verify: http_status(409, path="/api/policies")\n'
        "- errors: `422` when a field does not validate\n"
    ))
    rows = {row.claim: row.status for row in sensitivity.report(model.load(root))}
    assert rows["docs/features/api.md#post-policies:errors:1"] == "sensitive"
    assert rows["docs/features/api.md#post-policies:errors:2"] == "undeclared"


def test_an_unobserved_claim_does_not_fail_the_command_but_is_named(tmp_path: Path) -> None:
    """`doctor` refuses an unasserted claim; this command grades the assertions that exist.

    Two refusals for one defect teaches the author to silence whichever complains first, so
    the report says the number out loud and leaves the gate where it already was.
    """
    root = _book(tmp_path, "- errors: `422` when a field does not validate\n")
    outcome = sensitivity.cmd_sensitivity(root)
    assert outcome.ok
    assert "0 insensitive" in outcome.message
    assert "unobserved" in outcome.message
    unobserved = [row["claim"] for row in outcome.data["claims"] if row["status"] == "undeclared"]
    assert "docs/features/api.md#post-policies:errors:1" in unobserved
