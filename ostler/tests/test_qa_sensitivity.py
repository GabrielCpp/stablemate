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


#: One declared call per check in the vocabulary, plus a second where an optional argument
#: changes which mutations the call is meant to catch.
_WITNESSED_CALLS = [
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
    'exit_status(code=0)',
    'exit_status(code=2)',
    'actionable(locator="#save")',
    'inert(locator="#save")',
    'focusable(locator="#save")',
    'focusable(locator="#save", activates="Enter")',
]


def test_the_witness_table_covers_the_whole_check_vocabulary() -> None:
    """The vocabulary and the witness table are two spellings of one list, and nothing else
    relates them: `focusable` reached the books with no branch in `_plan`, so every book that
    used it reported `unwitnessed-check` and the fallback marked `pragma: no cover` was the
    only thing that ran. This is the artifact that relates them, so the next check added to
    `CHECKS` fails here rather than in a downstream app's doctor."""
    exercised = set()
    for text in _WITNESSED_CALLS:
        call = checks.parse_check(text)
        assert isinstance(call, checks.CheckCall), call
        exercised.add(call.name)
    assert exercised == {spec.name for spec in checks.CHECKS}


@pytest.mark.parametrize("call", _WITNESSED_CALLS)
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


def test_an_index_rooted_path_witnesses_in_a_list_not_a_dict() -> None:
    """A path whose first step is an index needs a list root, the same as any other index
    step: `[0].kind` used to hand the root dict to `cursor.append`, which does not exist."""
    path = "[0].kind"
    assert sensitivity._set_path({}, path, "policy") == [{"kind": "policy"}]
    trial = _trial(f'json_path(path="{path}", equals="policy")')
    assert trial.witnessed
    assert trial.sensitive


def test_a_filter_rooted_path_witnesses_in_a_list_not_a_dict() -> None:
    """The same root-picking rule as a leading index: a filter as the first step still needs
    a list to select into, not the dict every call starts from."""
    path = "[?(@.who=='ana')].total_cents"
    assert sensitivity._set_path({}, path, 4200) == [{"who": "ana", "total_cents": 4200}]
    trial = _trial(f'json_path(path="{path}", equals=4200)')
    assert trial.witnessed
    assert trial.sensitive


def test_an_empty_path_witnesses_the_whole_document_not_a_container() -> None:
    """`json_path(path="")` asserts on the whole body: `resolve_path` treats an empty path as
    naming the document itself, so the witness is `value` and the drop mutation is `None`,
    not a step walk over zero steps (which used to overrun `zip(..., strict=True)`)."""
    assert sensitivity._set_path({}, "", "policy") == "policy"
    assert sensitivity._drop_path("policy", "") is None
    trial = _trial('json_path(path="", equals="policy")')
    assert trial.witnessed
    assert trial.sensitive


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
        'json_path(path="claim.status", matches=".+")',
        'json_path(path="claim.status", matches=".")',
    ],
)
def test_a_pattern_that_admits_any_value_gets_no_value_mutation(call: str) -> None:
    """A pattern loose enough to accept `_OTHER` is a presence assertion, not a value one.

    `absent=false` is only defeated by absence, and a `matches=` pattern that would still
    match whatever the field-changed mutation writes is the same claim in different syntax:
    listing that mutation here would score the call sensitive or insensitive on a
    perturbation its own comparison never rejected, which is not a fact about the check.
    `doctor._rubber_stamp` reports this shape as `weak-check` instead.
    """
    trial = _trial(call)
    assert trial.witnessed
    assert trial.flipped == ("the field is not there at all",)
    assert not trial.survived
    assert trial.sensitive


@pytest.mark.parametrize(
    "call",
    [
        'json_path(path="claim.status", matches="^(INFO|DEBUG|TRACE)$")',
        'json_path(path="claim.status", equals="INFO")',
    ],
)
def test_a_discriminating_check_still_gets_the_value_mutation(call: str) -> None:
    """A pattern (or an `equals=`) that rejects `_OTHER` is a real value assertion, and the
    mutation that would falsify it stays in the experiment."""
    trial = _trial(call)
    assert trial.witnessed
    assert trial.flipped == ("the field holds something else", "the field is not there at all")
    assert not trial.survived
    assert trial.sensitive


def test_a_denial_of_emission_is_not_asked_to_notice_its_own_claim() -> None:
    """`emitted(count=0)` claims nothing was emitted, so "nothing was emitted" is the claim
    itself, not a defect it forbids: listing it as a mutation used to make the check survive
    by construction and report `insensitive-check` on a working denial."""
    trial = sensitivity.trial(checks.CheckCall("emitted", {"event": "x", "count": 0}))
    assert trial.witnessed
    assert trial.flipped == ("one more was emitted",)
    assert not trial.survived
    assert trial.sensitive


def test_a_positive_emission_count_still_gets_both_mutations() -> None:
    """A `count=` above zero is still falsified by silence, so `emitted`'s narrowing must not
    drop "nothing was emitted" for anything but the `count=0` denial."""
    trial = sensitivity.trial(checks.CheckCall("emitted", {"event": "x", "count": 2}))
    assert trial.witnessed
    assert trial.flipped == ("nothing was emitted", "one more was emitted")
    assert not trial.survived
    assert trial.sensitive


def test_an_emitted_check_with_no_declared_count_is_unchanged() -> None:
    """No `count=` argument means only the implicit `want = 1`, which is still a positive
    count: it must keep getting the "nothing was emitted" mutation, same as before this
    check's `count=0` denial was given its own case."""
    trial = sensitivity.trial(checks.CheckCall("emitted", {"event": "x"}))
    assert trial.witnessed
    assert trial.flipped == ("nothing was emitted",)
    assert not trial.survived
    assert trial.sensitive


def test_a_pattern_no_string_can_be_invented_for_is_unwitnessed_not_green() -> None:
    """Reporting a guess as a witness would credit sensitivity the experiment never showed."""
    trial = _trial(r'omits(subject="detail", matches="(?=x)(?!x)")')
    assert not trial.witnessed
    assert "no leaking value" in trial.note


def test_a_claim_no_trial_could_witness_has_no_result_rather_than_a_bad_one() -> None:
    """`unwitnessed` is the absence of a result, not a weaker `insensitive`.

    A two-armed rule has to call this something, and the only arm left is the one that
    says the check stayed green through a perturbation — which never ran. That reading
    aims a repair at the check, and the one edit that would satisfy it is a looser
    pattern: the harness would then witness the claim and report it genuinely insensitive.
    """
    report = sensitivity.ClaimReport(
        claim="okf:policies.md#issue:returns:1",
        path="docs/policies.md",
        line=12,
        trials=(_trial(r'omits(subject="detail", matches="(?=x)(?!x)")'),),
    )
    assert not any(t.witnessed for t in report.trials)
    assert report.status == "unwitnessed"


def test_one_witnessed_survivor_makes_the_claim_insensitive_not_unwitnessed() -> None:
    """A result beats a missing one: a perturbation did run, and the check did survive it."""
    stamp = sensitivity.Trial(
        call='visible(locator="text=Draft", text="Draft")',
        witnessed=True, flipped=(), survived=("the element is not on the page",),
    )
    report = sensitivity.ClaimReport(
        claim="okf:policies.md#issue:returns:1",
        path="docs/policies.md",
        line=12,
        trials=(
            _trial(r'omits(subject="detail", matches="(?=x)(?!x)")'),
            stamp,
        ),
    )
    assert report.status == "insensitive"


@pytest.mark.parametrize("pattern", [".*", ".+", ".", "^.{0,4000}$"])
def test_matches_admits_other_is_true_for_a_vacuous_pattern(pattern: str) -> None:
    assert sensitivity.matches_admits_other(pattern)


@pytest.mark.parametrize(
    "pattern", ["^(INFO|DEBUG|TRACE)$", r"^\d+$", "Draft|Active", r"eyJ[A-Za-z0-9_-]{6,}"]
)
def test_matches_admits_other_is_false_for_a_discriminating_pattern(pattern: str) -> None:
    assert not sensitivity.matches_admits_other(pattern)


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
