"""The `verify:` check vocabulary: what parses, what is refused, and how it renders."""

from __future__ import annotations

import pytest

from ostler import checks, registry


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
        ("api/publish.go::Publish", "not a check call"),
        ("http_status()", "requires `code: int`"),
        ('http_status(409, reason="x")', "has no argument `reason`"),
        ("http_status(409, code=500)", "given twice"),
        ('http_status("409")', "`code` is int, got str"),
        ("count(subject=\"pages\", equals=true)", "`equals` is int, got bool"),
        ("manifest_unchanged_except(page='a')", "is not a known check"),
        ('http_status(code=int("409"))', "must be literals"),
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


def test_verify_is_a_check_key_on_the_normative_types() -> None:
    for node_type in ("flow", "interaction", "invocation", "method"):
        assert registry.check_keys(node_type) == ("verify",)


def test_a_runbook_step_verify_stays_a_reference() -> None:
    """Same word, different job: a boot step's `verify:` says how to tell the *step* ran."""
    assert registry.check_keys("step") == ()
    assert registry.UI_TYPES_BY_NAME["step"].bullet_by_key["verify"].link
