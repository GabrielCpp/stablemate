"""The `verify:` check vocabulary: what parses, what is refused, and how it renders."""

from __future__ import annotations

import re
from pathlib import Path

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


def test_a_soft_wrapped_bullet_parses_as_markdown_renders_it() -> None:
    """Books wrap bullets at a column; the break is a space to every reader but Python's
    grammar, so a wrapped `subject="…"` must bind as the one-line call it renders as."""
    call = checks.parse_check('persists(subject="the id resolved for a known,\n  verified email")')
    assert isinstance(call, checks.CheckCall)
    assert call.text() == 'persists(subject="the id resolved for a known, verified email")'
    refused = checks.parse_check('persists(subject="a,\n  b", nope=1)')
    assert isinstance(refused, checks.Refusal)
    assert refused.form == checks.CHECK_BY_NAME["persists"].signature()


def test_is_check_expression_is_the_one_test_for_a_check_shaped_value() -> None:
    """The single predicate `doctor` and `runbook` both call to tell a check call apart from a
    shell command — see `check-expression-as-command`. A value that fails to parse (a plain
    command, an empty string) is not a check expression; one that does is, regardless of
    whether it names a declared check."""
    assert checks.is_check_expression('http_status(200, path="/healthz")') is True
    assert checks.is_check_expression("curl -fsS http://localhost:8080/healthz") is False
    assert checks.is_check_expression("docker compose up -d --wait") is False
    assert checks.is_check_expression("") is False


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
    assert isinstance(result, checks.Refusal)
    assert fragment in result.message


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


def test_every_spec_declares_what_it_observes() -> None:
    """`observes` is what a compiler dispatches on to pick an operand and to know whether a
    given driver (HTTP, Playwright) can serve the check at all — every check names one, and
    the six values are the whole vocabulary a compiler needs to handle. `subject` is read
    once, after the action; `subject-pair` only means anything as a before-and-after;
    `keyboard` is a real keypress dispatched at the page, not a read of it."""
    expected = {
        "http_status": "response",
        "conflict_on_stale": "response",
        "json_path": "body",
        "visible": "page",
        "actionable": "page",
        "inert": "page",
        "focusable": "keyboard",
        "unchanged": "subject-pair",
        "keys_unchanged": "subject-pair",
        "count": "subject",
        "absent": "subject",
        "created": "subject-pair",
        "removed": "subject-pair",
        "persists": "subject-pair",
        "emitted": "subject",
        "omits": "response",
        "exit_status": "subject",
    }
    assert {spec.name: spec.observes for spec in checks.CHECKS} == expected
    assert {spec.observes for spec in checks.CHECKS} == {
        "response", "body", "page", "subject", "subject-pair", "keyboard",
    }


def test_out_of_band_is_declared_independently_of_shape() -> None:
    """`out_of_band` and `observes` vary independently: `emitted` is single-observation and
    out-of-band, `persists` is paired-observation and out-of-band — a compiler reading both
    fields off the spec never needs to know either check by name."""
    out_of_band = {spec.name for spec in checks.CHECKS if spec.out_of_band}
    assert out_of_band == {"emitted", "persists"}
    assert checks.CHECK_BY_NAME["emitted"].observes == "subject"
    assert checks.CHECK_BY_NAME["persists"].observes == "subject-pair"


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
    assert isinstance(result, checks.Refusal)
    assert result.kind == "bad-arguments"
    assert "requires `subject: str`" in result.message
    assert result.form == "created(subject*=<str>)"


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


def test_every_graded_key_is_a_declared_bullet() -> None:
    """The drift this closes: `status:`/`errors:`/`auth:` were graded on an endpoint for as
    long as the mapper existed and declared nowhere, so `fmt` could not place them and a
    `verify:` written under one bound to the `does:` above. A graded key is a bullet key."""
    for node_type, keys in registry.NORMATIVE_KEYS_BY_TYPE.items():
        declared = registry.UI_TYPES_BY_NAME[node_type].bullet_by_key
        for key in keys:
            assert key in declared, (node_type, key)
            assert declared[key].normative, (node_type, key)


def test_normative_table_is_derived_from_the_registry() -> None:
    """One flag, not two tables: every `normative=True` bullet is graded, nothing else is."""
    for uitype in registry.UI_TYPES:
        flagged = tuple(b.key for b in uitype.bullet_keys if b.normative)
        assert registry.NORMATIVE_KEYS_BY_TYPE.get(uitype.name, ()) == flagged, uitype.name
        assert set(registry.normative_keys(uitype.name)) == (
            set(flagged) | set(registry.SHARED_NORMATIVE_KEYS))
        assert set(flagged) <= registry.declared_keys(uitype.name)
    # The keys that drove the change, declared where they are graded.
    for node_type in ("endpoint", "invocation"):
        assert {"status", "errors", "auth"} <= set(registry.NORMATIVE_KEYS_BY_TYPE[node_type])
    assert {"errors", "exits"} <= set(registry.NORMATIVE_KEYS_BY_TYPE["command"])


def test_a_load_bearing_key_is_one_some_type_instruments() -> None:
    """`verify:` and `code:` are the keys an author expects machinery behind; `meaning:` is
    nobody's, and `parent:`/`detail:` are resolved on every type alike with no locator use, so
    neither is in the set. `on:` *is* — it resolves like any relation, but a `qa/context.py`
    planner also reads it off the obligation as a control's locator, so excluding it here
    would leave `unknown-bullet` blind on the same undeclared-type reads that fix closes."""
    assert {"verify", "code", "does", "status", "fixture", "on"} <= registry.LOAD_BEARING_KEYS
    assert not {"meaning", "parent", "detail"} & registry.LOAD_BEARING_KEYS


def test_an_alias_is_declared_but_never_stubbed() -> None:
    endpoint = registry.UI_TYPES_BY_NAME["endpoint"].bullet_by_key
    assert endpoint["error"].alias and endpoint["error"].normative
    assert not endpoint["errors"].alias


def test_no_alias_is_a_spelling_no_book_writes() -> None:
    """An alias exists for the books that wrote it, so one nobody wrote is not an alias.

    `statuses` was declared on `endpoint` and `invocation` and written in none of the three
    trees this format is exercised against. A second name the grammar answers for with no
    claim behind it is a spelling kept for nobody, and `scaffold` never stubs it, so nothing
    would ever have started writing it either.
    """
    for name in ("endpoint", "invocation"):
        assert "statuses" not in registry.UI_TYPES_BY_NAME[name].bullet_by_key


def test_a_runbook_step_verify_stays_a_reference() -> None:
    """Same word, different job: a boot step's `verify:` says how to tell the *step* ran."""
    assert registry.check_keys("step") == ()
    assert registry.UI_TYPES_BY_NAME["step"].bullet_by_key["verify"].link


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('absent(locator="the row")', "absent(subject*=<str>)"),
        ('emitted(subject="page.published")', "emitted(event*=<str>, count=<int>)"),
    ],
)
def test_the_expected_form_is_the_failing_checks_own_signature(value: str, expected: str) -> None:
    """The counter-case is a canned example: an author shown `http_status(code=…)` after
    mis-calling `absent` learns nothing about `absent`, and guesses again on the next lap."""
    refused = checks.parse_check(value)
    assert isinstance(refused, checks.Refusal)
    assert refused.form == expected


def test_a_signature_says_which_kind_of_string_an_argument_is() -> None:
    """`str` is three different obligations here — free prose, a path into the observed
    document, the anchor of a declared component — and an author writing a call has to know
    which. The reference page names the tool as the authority on that, so the rendering the
    tool prints is what has to carry it."""
    assert checks.CHECK_BY_NAME["json_path"].signature().startswith("json_path(path*=<str> (path)")
    assert "locator*=<str> (locator)" in checks.CHECK_BY_NAME["visible"].signature()
    assert "text=<str>)" in checks.CHECK_BY_NAME["visible"].signature()


def test_a_signature_is_an_example_before_it_is_a_type() -> None:
    """The separator is the whole finding. An author reads the signature as the call to copy,
    so rendering `code: int*` — the annotation spelling — put a colon where the call puts `=`,
    and bullets in one real book copied it verbatim (`exit_status(code: 1)`). `*` and `<…>`
    cannot be mistaken for a value; a colon in call position can, because there it is one."""
    for spec in checks.CHECKS:
        rendered = spec.signature().split(" — ")[0]
        assert ": " not in rendered, rendered
        for param in spec.params:
            star = "*" if param.required else ""
            assert f"{param.name}{star}=<{param.type}>" in rendered


def test_a_call_whose_arguments_do_not_parse_is_still_a_named_check() -> None:
    """The name is recovered from the text, not from the parse — the parse is the thing that
    just failed, so a name read only out of a successful parse is unavailable in exactly the
    case that needs it, and every such author was handed all sixteen checks to re-choose."""
    for value, name in (("exit_status(code: 1)", "exit_status"),
                        ('count(subject: "x", equals: 2)', "count"),
                        ('persists(subject: "x")', "persists")):
        refused = checks.parse_check(value)
        assert isinstance(refused, checks.Refusal)
        assert refused.kind == "bad-arguments"
        assert refused.form == checks.CHECK_BY_NAME[name].signature()
        assert "name=value" in refused.message


def test_an_unparseable_call_naming_no_known_check_is_not_recovered() -> None:
    """The guard on the recovery. A name nothing declares is not a check the author chose, so
    the answer stays the menu; and a test reference still reaches its own arm, because no test
    id is spelled `<a known check>(`."""
    for value, kind in (("nope(a: 1)", "not-a-call"),
                        ("api/publish.go::Publish", "misfiled-test-ref")):
        refused = checks.parse_check(value)
        assert isinstance(refused, checks.Refusal)
        assert refused.kind == kind


def test_only_a_refusal_that_named_no_check_falls_back_to_the_vocabulary() -> None:
    """No name recovered means no check chosen yet, so the answer is the menu — and *only*
    then. A value that named a check gets that check's signature, and a value that is a test
    reference gets the key it belongs under, because both of those are narrower answers the
    refusal is in a position to give."""
    unnamed = checks.parse_check("nope(a=1)")
    assert isinstance(unnamed, checks.Refusal)
    for spec in checks.CHECKS:
        assert spec.signature() in unnamed.form


def test_the_one_of_rule_holds_on_both_sides_of_the_binding() -> None:
    """`parse_check` reads the book's bullet and `bind` reads the plan's recovered call. A
    rule applied on one side only would refuse a plan that invokes exactly what was declared,
    so the refusal lives in the shared tail and both spellings feel it identically."""
    assert isinstance(checks.bind("json_path", {"path": "$.item.id"}), checks.Refusal)
    for args in ({"equals": "abc"}, {"matches": "^a"}, {"absent": True}):
        assert isinstance(checks.bind("json_path", {"path": "$.item.id", **args}), checks.CheckCall)


def test_an_unparsable_pattern_is_refused_at_bind_not_at_the_harness() -> None:
    """`matches=` is a regular expression, not free prose, and the two checks that declare it
    are the only ones the grammar marks that way. An author's typo used to reach `re.error` at
    whichever consumer compiled it first; it now surfaces as `bad-arguments` where the call is
    bound, on both sides of the binding check."""
    for name, args in (
        ("json_path", {"path": "$.item.id", "matches": "[a-z"}),
        ("omits", {"subject": "$.detail", "matches": "[a-z"}),
    ):
        refused = checks.bind(name, args)
        assert isinstance(refused, checks.Refusal)
        assert refused.kind == "bad-arguments"


def test_a_pattern_that_compiles_still_binds() -> None:
    call = checks.bind("json_path", {"path": "$.item.id", "matches": "^[a-z]+$"})
    assert isinstance(call, checks.CheckCall)
    assert call.args == {"path": "item.id", "matches": "^[a-z]+$"}


def test_only_a_declared_pattern_argument_is_compiled() -> None:
    """The flag, not the name, is what gates the compile: `omits`' `text=` is plain prose and
    must bind even though `[` alone is not a parsable regular expression."""
    call = checks.bind("omits", {"subject": "$.detail", "text": "an id like [redacted]"})
    assert isinstance(call, checks.CheckCall)
    assert call.args == {"subject": "detail", "text": "an id like [redacted]"}


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


def test_exit_status_binds_the_code_a_command_ends_with() -> None:
    """A tool's output is not its verdict: `created` and `json_path` can read what a process
    printed and never notice it printed it on the way to a non-zero exit."""
    call = checks.parse_check("exit_status(code=0)")
    assert isinstance(call, checks.CheckCall)
    assert call.args == {"code": 0}
    assert call.text() == "exit_status(code=0)"
    assert "only read its output" in checks.CHECK_BY_NAME["exit_status"].excludes
    assert isinstance(checks.parse_check("exit_status()"), checks.Refusal)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ('json_path(path="claim.amount_cents", equals=8250)', 8250),
        ('json_path(path="claim.paid", equals=true)', True),
        ('json_path(path="claim.ratio", equals=0.5)', 0.5),
        ('json_path(path="claim.id", equals="abc")', "abc"),
    ],
)
def test_json_path_equals_is_a_json_scalar(text: str, value: object) -> None:
    """The declared value keeps its JSON type through parse, bind and the canonical
    rendering, so a book's `equals=8250` reaches the harness as a number and reads back as
    the same bullet."""
    declared = checks.parse_check(text)
    assert isinstance(declared, checks.CheckCall), declared
    assert declared.args["equals"] == value
    assert type(declared.args["equals"]) is type(value)
    assert checks.parse_check(declared.text()) == declared
    bound = checks.bind("json_path", {"path": "claim.x", "equals": value})
    assert isinstance(bound, checks.CheckCall)


def test_a_filter_segment_survives_the_declaration_gate_and_the_canonical_rendering() -> None:
    """The quote and the `==` inside a filter live inside the quoted `path=` string, which the
    `ast`-based parser reads as one literal — and the canonical text reads back as itself."""
    text = """json_path(path="$.people[?(@.who=='ana')].total_cents", equals=4200)"""
    declared = checks.parse_check(text)
    assert isinstance(declared, checks.CheckCall), declared
    assert declared.args["path"] == "people[?(@.who=='ana')].total_cents"
    assert checks.parse_check(declared.text()) == declared
    wild = checks.parse_check('count(subject="people[*].trips[*]", equals=3)')
    assert isinstance(wild, checks.CheckCall), wild


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


def test_owning_keys_include_code_on_every_type_and_only_the_flagged_others() -> None:
    """`qa context` maps a diff through `owning_keys`; `code:` owns everywhere (a flow cites
    the code it is grounded in whether or not its profile lists the key), and the only other
    owners are the bullets the registry flags — a schema or a fixture file under its own
    name. `tests:` and `binary:` never own."""
    for uitype in registry.UI_TYPES:
        keys = registry.owning_keys(uitype.name)
        assert keys[0] == "code", uitype.name
        flagged = {b.key for b in uitype.bullet_keys if b.owns}
        assert set(keys) == flagged | {"code"}, uitype.name
        assert not {"tests", "binary"} & set(keys), uitype.name
    assert "openapi" in registry.owning_keys("endpoint")
    assert "openapi" in registry.owning_keys("server")
    assert "file" in registry.owning_keys("format")
    assert registry.owning_keys("untyped") == ("code",)



def test_a_regex_argument_parses_without_a_python_escape_warning():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        call = checks.parse_check(r'json_path(path="$.id", matches="^\d+$")')
    assert isinstance(call, checks.CheckCall)


def test_a_check_written_as_a_markdown_code_span_is_a_check() -> None:
    """Books render a call as code, and the backticks are the rendering. Reading them as
    content refuses a call the book got right — 12 of them in one real book — and the author
    is sent to fix a bullet that was already correct."""
    call = checks.parse_check('`json_path(path="$.result", equals="ok")`')
    assert isinstance(call, checks.CheckCall)
    assert call == checks.parse_check('json_path(path="$.result", equals="ok")')


def test_a_value_holding_two_code_spans_is_not_unwrapped_to_its_middle() -> None:
    """The closing run has to match the opening one and nothing may sit outside it. Stripping
    the first and last backtick instead would hand the parser `a` and `b` — a value the book
    never wrote, and a refusal quoting text that appears nowhere in it."""
    refused = checks.parse_check("`a` and `b`")
    assert isinstance(refused, checks.Refusal)
    assert "`a` and `b`" in refused.message


def test_a_backticked_test_reference_reaches_the_test_reference_arm() -> None:
    """The silent half of the same defect, and the larger one: the suffix test read ``ts` ``
    rather than `ts`, so 16 misfiled paths were reported as unrecognisable values instead of
    as values on the wrong key."""
    refused = checks.parse_check("`docs-app/app/lib/parse.test.ts`")
    assert isinstance(refused, checks.Refusal)
    assert refused.kind == "misfiled-test-ref"
    assert refused.bullet("verify") == "- tests: docs-app/app/lib/parse.test.ts"


def test_the_suggestion_cannot_contradict_the_message_it_travels_with() -> None:
    """The regression this row exists for. The message said *put this on `tests:`* while the
    suggestion beside it listed all sixteen checks, for 317 bullets in one real book, because
    each was produced by a separate classification of the same value. One refusal now carries
    both, so a kind that relocates a value cannot also advertise the vocabulary."""
    for value in ("docs/a.test.ts::describe > it", "`svc/x_test.go`", "api/publish.go::Publish"):
        refused = checks.parse_check(value)
        assert isinstance(refused, checks.Refusal)
        assert refused.relocates_to == "tests"
        assert "Put it on `tests:`" in refused.message
        assert refused.bullet("verify").startswith("- tests: ")
        assert "http_status(" not in refused.bullet("verify")


def test_the_reference_page_prints_the_signatures_the_tool_prints() -> None:
    """The page hard-codes all sixteen as headings and calls this module the authority on
    them, and until now nothing joined the two: the headings kept the annotation spelling for
    as long as the code had it, and then for one commit longer. A reference that can disagree
    with the thing it describes is a second source, and the author copies whichever they read.
    """
    page = Path(__file__).resolve().parents[2] / (
        "base-library/library/skills/ostler/okf/references/check-vocabulary.md")
    headings = re.findall(r"^### `(.+)`$", page.read_text(), re.M)
    assert headings, "check-vocabulary.md no longer lists the checks as headings"
    assert headings == [spec.signature() for spec in checks.CHECKS]
