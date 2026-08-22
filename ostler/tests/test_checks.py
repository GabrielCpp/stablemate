"""The `verify:` check vocabulary: what parses, what is refused, and how it renders."""

from __future__ import annotations

import pytest

from ostler import checks, registry
from ostler.qa.harness_host import load_harness_module


def test_positional_and_keyword_arguments_bind_to_the_declared_params() -> None:
    call = checks.parse_check('http_status(409, title="Manifest Conflict")')
    assert isinstance(call, checks.CheckCall)
    assert call.name == "http_status"
    assert call.args == {"code": 409, "title": "Manifest Conflict"}


def test_text_is_identity_not_display() -> None:
    """Two spellings of one call render the same string, or the binding check refuses on
    whitespace and argument order instead of on substance."""
    one = checks.parse_check('http_status(title="Conflict",   code=409)')
    two = checks.parse_check('http_status(409, title="Conflict")')
    assert isinstance(one, checks.CheckCall) and isinstance(two, checks.CheckCall)
    assert one.text() == two.text() == 'http_status(code=409, title="Conflict")'


def test_list_arguments_round_trip() -> None:
    call = checks.parse_check('unchanged(subject="manifest", except_fields=["pages.a.fr.slug"])')
    assert isinstance(call, checks.CheckCall)
    assert call.text() == 'unchanged(subject="manifest", except_fields=["pages.a.fr.slug"])'


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("Test_Service_Publish_ShouldConflict", "not a check call"),
        # A test reference is the mistake this vocabulary replaced, so its refusal says where
        # the reference belongs rather than only that a call was expected.
        ("api/publish.go::Publish", "Put it on `tests:`"),
        ("a sentence about the manifest", "not a check call"),
        ("http_status()", "requires `code: int`"),
        ('http_status(409, reason="x")', "has no argument `reason`"),
        ("http_status(409, code=500)", "given twice"),
        ('http_status("409")', "`code` is int, got str"),
        ("count(subject=\"pages\", equals=true)", "`equals` is int, got bool"),
        ("manifest_unchanged_except(page='a')", "is not a known check"),
        ('http_status(code=int("409"))', "must be literals"),
        # An assertion that cannot go red, refused where it is written: a `json_path` with
        # no comparison observes only that the path resolved.
        ('json_path(path="$.item.id")', "needs one of `equals`, `matches`, `absent`"),
        # Same rule on the one check whose whole job is negative: without a thing it must
        # not carry, `omits` reads the subject and objects to nothing in it.
        ('omits(subject="$.detail")', "needs one of `text`, `matches`"),
        ("", "empty"),
    ],
)
def test_refusals_say_what_is_wrong(value: str, fragment: str) -> None:
    result = checks.parse_check(value)
    assert isinstance(result, str)
    assert fragment in result


def test_canonical_text_parses_back_to_the_same_call() -> None:
    """`text()` is fed to authors and to refusal messages; a rendering the parser then rejects
    would send someone to fix a bullet by copying a spelling that cannot be written."""
    for value in (
        'json_path(path="$.error.title", absent=false)',
        'unchanged(subject="manifest", except_fields=["a", "b"])',
        'conflict_on_stale(subject="manifest", token="etag")',
    ):
        first = checks.parse_check(value)
        assert isinstance(first, checks.CheckCall)
        again = checks.parse_check(first.text())
        assert isinstance(again, checks.CheckCall)
        assert again == first


def test_every_spec_names_the_defect_it_excludes() -> None:
    """`excludes:` is the sentence a refusal quotes and the test of whether a check earns a
    place in the vocabulary at all — a check that excludes nothing is prose with parentheses."""
    for spec in checks.CHECKS:
        assert spec.excludes.strip()
        assert spec.params, f"{spec.name} observes nothing in particular"


def test_a_lifecycle_claim_is_expressible_as_a_paired_observation() -> None:
    """`created` / `removed` exist so "it was created" is writable without collapsing into
    "it is there now" — the after-only spelling passes identically on a no-op."""
    for value in ('created(subject="the seat A1 booking")', 'removed(subject="the hold")'):
        call = checks.parse_check(value)
        assert isinstance(call, checks.CheckCall)
        assert call.text() == value
        again = checks.parse_check(call.text())
        assert again == call


def test_a_lifecycle_check_names_its_subject() -> None:
    """A creation with no subject is the unfalsifiable form the check was added to replace."""
    result = checks.parse_check("created()")
    assert isinstance(result, str)
    assert "requires `subject: str`" in result
    assert checks.expected_form("created()") == "created(subject: str)"


def test_every_declarable_check_is_observable_by_the_harness() -> None:
    """The two tables are spelled twice on purpose — `ostler.checks` says what may be
    declared, the stdlib-only harness says what observing it means — so nothing but a test
    stops them drifting. A name in one and not the other is a bullet that parses in the book
    and dies at the call, or a verifier no author can reach."""
    harness = load_harness_module("ostler_qa")
    assert set(harness.VERIFIERS) == {spec.name for spec in checks.CHECKS}


def test_verify_is_a_check_key_on_the_normative_types() -> None:
    for node_type in ("flow", "interaction", "invocation", "method"):
        assert registry.check_keys(node_type) == ("verify",)


def test_every_type_that_states_claims_can_say_what_observing_one_looks_like() -> None:
    """A type with claims and no check key is covered unconditionally: `checksDeclared` is
    empty by construction, so whatever the scenario happened to assert fulfils it. `endpoint`
    and `component` were in that state while their books wrote `verify:` bullets nobody read,
    and `environment` was in it while a stack's provider pin went missing under a plan that
    could not be held to it."""
    for node_type in registry.NORMATIVE_KEYS_BY_TYPE:
        assert registry.check_keys(node_type) == ("verify",), node_type
    assert registry.check_keys("environment") == ("verify",)


def test_a_runbook_step_verify_stays_a_reference() -> None:
    """Same word, different job: a boot step's `verify:` says how to tell the *step* ran."""
    assert registry.check_keys("step") == ()
    assert registry.UI_TYPES_BY_NAME["step"].bullet_by_key["verify"].link


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('absent(locator="the row")', "absent(subject: str)"),
        ('emitted(subject="page.published")', "emitted(event: str, count: int = …)"),
    ],
)
def test_the_expected_form_is_the_failing_checks_own_signature(value: str, expected: str) -> None:
    """The counter-case is a canned example: an author shown `http_status(code=…)` after
    mis-calling `absent` learns nothing about `absent`, and guesses again on the next lap."""
    assert isinstance(checks.parse_check(value), str)
    assert checks.expected_form(value) == expected


def test_the_expected_form_falls_back_to_the_whole_vocabulary() -> None:
    """No name recovered means no check chosen yet, so the answer is the menu."""
    form = checks.expected_form("api/publish.go::Publish")
    for spec in checks.CHECKS:
        assert spec.signature() in form


def test_the_one_of_rule_holds_on_both_sides_of_the_binding() -> None:
    """`parse_check` reads the book's bullet and `bind` reads the plan's recovered call. A
    rule applied on one side only would refuse a plan that invokes exactly what was declared,
    so the refusal lives in the shared tail and both spellings feel it identically."""
    assert isinstance(checks.bind("json_path", {"path": "$.item.id"}), str)
    for args in ({"equals": "abc"}, {"matches": "^a"}, {"absent": True}):
        assert isinstance(checks.bind("json_path", {"path": "$.item.id", **args}), checks.CheckCall)


def test_a_one_of_spec_shows_the_choice_in_its_signature() -> None:
    """The signature is what a refusal offers an author as the shape that would be accepted,
    and an optional-looking argument list does not say that one of them is mandatory."""
    assert "one of equals, matches, absent" in checks.CHECK_BY_NAME["json_path"].signature()


def test_omits_is_the_vocabularys_one_negative_observation() -> None:
    """Every other check asserts what a subject holds, and a clause about what a response may
    *not* contain has no positive form — so a book stating one had nothing to declare."""
    call = checks.parse_check('omits(subject="$.detail", matches="eyJ[A-Za-z0-9]+")')
    assert isinstance(call, checks.CheckCall)
    assert call.args == {"subject": "detail", "matches": "eyJ[A-Za-z0-9]+"}
    assert "credential it rejected" in checks.CHECK_BY_NAME["omits"].excludes


def test_a_path_argument_is_the_same_call_with_or_without_the_root_token() -> None:
    """`$` is not a key — every resolver in the harness drops it before walking. Identity
    between a declared check and an invoked one is textual, so leaving the sigil in would make
    a plan spelling `$.policy.id` fail to assert a bullet spelling `policy.id`, and vice versa."""
    declared = checks.parse_check('json_path(path="$.policy.id", equals="pn-1001")')
    invoked = checks.bind("json_path", {"path": "policy.id", "equals": "pn-1001"})
    assert isinstance(declared, checks.CheckCall) and isinstance(invoked, checks.CheckCall)
    assert declared.text() == invoked.text()


def test_a_prose_argument_keeps_a_leading_sigil() -> None:
    """Only a path is walked. `count`'s subject is prose the report quotes back."""
    call = checks.bind("count", {"subject": "$ spent", "equals": 2})
    assert isinstance(call, checks.CheckCall)
    assert call.args["subject"] == "$ spent"
