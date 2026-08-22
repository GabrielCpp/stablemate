"""The experiment that asks whether a declared check could have gone red."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import checks
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
        'json_path(path="policy.status", matches="Draft|Active")',
        'json_path(path="errors.premium", absent=false)',
        'json_path(path="detail.token", absent=true)',
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
