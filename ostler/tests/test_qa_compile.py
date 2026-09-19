"""What a plan compiled from the book alone may and may not claim.

A plan an author writes while reading the implementation tests what the code already does.
These pin the alternative: the book's own `verify:` grammar, compiled into assertions with
no source file opened — and, just as load-bearing, what the compiler refuses to invent when
the book is silent.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from ostler import checks
from ostler.qa.compile import (
    Gap,
    DriverSpec,
    MAESTRO,
    PLAYWRIGHT,
    PYTHON,
    _BUILT_TARGETS,
    _DISPATCH_TABLE,
    _OBSERVE_ROW,
    _dispatch_target,
    _unobservable_gap,
    annotate_deferred_obligations as _annotate_deferred_obligations,
    book_digest,
    cmd_compile_plan as _cmd_compile_plan,
    compile_plan as _compile_plan,
    compile_plan_gaps as _compile_plan_gaps,
    deferred_obligations as _deferred_obligations,
)
from ostler.qa.outcome import QaOutcome


#: Phase 2h reads each target's `base_url` off `context["navigation"][surface]["entryUrl"]`,
#: falling back to `--base-url` only for a surface stating none, and never at all for an
#: obligation with no `surface:` — that shape is the http/api side's, which has no notion of
#: "surface" to look navigation up by. Every test in this file that isn't itself about
#: entry-url resolution just wants a plan that compiles, so `compile_plan`/`compile_plan_gaps`/
#: `cmd_compile_plan` below wrap the real ones with this as the `--base-url` fallback, exactly
#: as if every call in this file had passed it on the command line. The handful of tests
#: pinning entry-url resolution itself (undeclared-entry-url, per-surface base_url) call the
#: real, unwrapped functions instead, imported above with a leading underscore.
_BASE_URL = "http://localhost:8000"


def compile_plan(
    context: dict,
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = _BASE_URL,
) -> str:
    return _compile_plan(context, story=story, run_id=run_id, base_url=base_url)


def compile_plan_gaps(
    context: dict,
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = _BASE_URL,
) -> tuple[str, list[Gap]]:
    return _compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)


def cmd_compile_plan(
    spec_dir: Path,
    *,
    out: Path | None = None,
    story: str = "",
    run_id: str | None = None,
    base_url: str | None = _BASE_URL,
) -> QaOutcome:
    return _cmd_compile_plan(spec_dir, out=out, story=story, run_id=run_id, base_url=base_url)


def _obligation(oid: str, **extra: object) -> dict:
    # GET, not POST: most tests here are about check compilation, gap kinds, digests, and
    # coverage bookkeeping — none of it about request bodies. A POST default would make every
    # one of them arrange a body it has no reason to care about, since there is still no book
    # grammar to arrange one with (`unarranged-request-body`, compile.py's `_scenario_body`).
    # The handful of tests actually about POST/body behavior override this explicitly.
    base = {
        "id": oid,
        "source": "docs/features/demo/api.md",
        "nodeType": "endpoint",
        "requirement": "writes the record and answers with it",
        "required": True,
        "locators": {"route": ["GET /api/things"]},
        "checksDeclared": [],
    }
    base.update(extra)
    return base


def _context(*obligations: dict) -> dict:
    # D1's dispatch table keys on `(nodeType, driver)` — every obligation these tests build
    # defaults to `nodeType: "endpoint"` (`_obligation`) or `"interaction"` (`_page_obligation`),
    # and each surface those obligations name (the default "" surface here, others via
    # `navigation=`) needs its own `driver:` for the table to resolve at all, the same as a
    # real book's `runbook` node states one. Tests about the dispatch table itself, or that
    # replace `navigation` outright, override this.
    return {"story": "demo-story", "obligations": list(obligations), "navigation": {"": {"driver": "http"}}}


def _covers(source: str) -> set[str]:
    """Every id the compiled plan claims coverage of, read out of its own syntax tree."""
    claimed: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "covers" and isinstance(keyword.value, ast.List):
                claimed.update(
                    element.value
                    for element in keyword.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
    return claimed


def test_a_compiled_plan_is_valid_python() -> None:
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:1",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                {"call": "the record", "name": "json_path", "args": {"path": "thing.status", "equals": "Draft"}},
            ],
        )
    )
    source = compile_plan(context, story="demo-story")
    ast.parse(source)
    assert "qa.http.get" in source
    assert "expect_status=201" in source


def test_a_compiled_plan_carries_the_books_own_digest() -> None:
    """`plan(book=...)` names the obligation id set this compile pass read, so a run against
    a book that has since changed can tell it apart from one still current."""
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:1",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        )
    )
    source = compile_plan(context, story="demo-story")
    assert f'book="{book_digest(context)}"' in source


def test_the_books_digest_ignores_order_and_context_only_obligations() -> None:
    """Stable under a rewalk that visits the same ids in a different order, and blind to a
    `required: False` obligation — the plan never owed that one a scenario in the first place,
    so its coming or going is not a reason to call the plan stale."""
    a = _obligation("okf:docs/features/demo/api.md#post-things:does:1")
    b = _obligation("okf:docs/features/demo/api.md#post-things:does:2")
    context_only = _obligation("okf:docs/features/demo/api.md#post-things:does:3", required=False)
    assert book_digest(_context(a, b)) == book_digest(_context(b, a))
    assert book_digest(_context(a, b)) == book_digest(_context(a, b, context_only))


def test_the_books_digest_changes_with_the_obligation_set() -> None:
    a = _obligation("okf:docs/features/demo/api.md#post-things:does:1")
    b = _obligation("okf:docs/features/demo/api.md#post-things:does:2")
    assert book_digest(_context(a)) != book_digest(_context(a, b))


def test_a_boolean_argument_compiles_to_python_not_json() -> None:
    """`absent: false` is the book's spelling and a `NameError` in a plan."""
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:1",
            checksDeclared=[
                {"call": "the draft", "name": "absent", "args": {"absent": False, "of": "thing"}},
            ],
        )
    )
    source = compile_plan(context, story="demo-story")
    ast.parse(source)
    assert "absent=False" in source
    assert "absent=false" not in source


def test_an_obligation_with_no_declared_check_is_book_debt_not_coverage() -> None:
    """Claiming an id the body never asserts would read as covered in every report."""
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:1",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
        _obligation("okf:docs/features/demo/api.md#post-things:does:2"),
    )
    source = compile_plan(context, story="demo-story")
    assert _covers(source) == {"okf:docs/features/demo/api.md#post-things:does:1"}
    assert "# Book debt." in source
    assert "#   okf:docs/features/demo/api.md#post-things:does:2" in source


def test_a_source_document_owing_nothing_observable_emits_no_scenario() -> None:
    context = _context(_obligation("okf:docs/features/demo/api.md#post-things:does:1"))
    source = compile_plan(context, story="demo-story")
    ast.parse(source)
    assert "@scenario(" not in source
    assert "# Book debt." in source


def test_an_obligation_the_change_does_not_owe_is_not_compiled() -> None:
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:9",
            required=False,
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200, "path": "/api/things"}}],
        )
    )
    assert _covers(compile_plan(context, story="demo-story")) == set()


def test_a_check_needing_a_subject_the_book_never_gave_compiles_to_a_marker() -> None:
    """`unchanged` observes a before and an after. The book names neither, so nothing is invented."""
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:persistence:1",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                {"call": "the ledger", "name": "unchanged", "args": {"of": "thing.version"}},
            ],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    # Nothing invented, and nothing half-claimed either: the sibling `http_status` row compiles,
    # but the two bullets are one claim, so the obligation withdraws whole and stands as its gap.
    oid = "okf:docs/features/demo/api.md#post-things:persistence:1"
    assert "needs-snapshot" in _gap_kinds(gaps, oid)
    assert oid not in _covers(source)
    assert "qa.verify(" not in source


def test_the_command_writes_the_plan_and_reports_the_debt(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            _context(
                _obligation(
                    "okf:docs/features/demo/api.md#post-things:does:1",
                    checksDeclared=[
                        {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                    ],
                ),
                _obligation("okf:docs/features/demo/api.md#post-things:does:2"),
            )
        ),
        encoding="utf-8",
    )
    out = spec / "qa_plan.py"
    result = cmd_compile_plan(spec, out=out)
    assert result.ok
    assert result.data["owed"] == 2
    assert result.data["declared"] == 1
    assert result.data["debt"] == ["okf:docs/features/demo/api.md#post-things:does:2"]
    ast.parse(out.read_text(encoding="utf-8"))


def test_the_command_reports_gaps_in_doctors_own_finding_shape(tmp_path: Path) -> None:
    """`compile_plan_gaps`'s `Gap` list surfaces in `cmd_compile_plan`'s JSON output as
    doctor-shaped dicts — a caller reads `severity`/`code`/`message`/`ref` the same way it
    would read a `doctor.Finding`, without re-parsing the compiled plan's Python."""
    oid = "okf:docs/features/demo/api.md#post-things:does:1"
    context = _context(_obligation(
        oid,
        locators={"route": ["POST /api/things"]},
        checksDeclared=[{"call": "created", "name": "http_status", "args": {"code": 201}}],
        fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
    ))
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
    result = cmd_compile_plan(spec)
    assert result.ok
    [gap] = result.data["gaps"]
    assert gap == {
        "severity": "error",
        "code": "unarranged-request-body",
        "message": "the book carries no request body",
        "ref": oid,
    }


def test_the_command_refuses_to_overwrite_an_authored_plan(tmp_path: Path) -> None:
    """It cannot tell an author's arrangement from its own last output, so it declines."""
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text(json.dumps(_context()), encoding="utf-8")
    out = spec / "qa_plan.py"
    out.write_text("# hours of arrangement\n", encoding="utf-8")
    result = cmd_compile_plan(spec, out=out)
    assert not result.ok
    assert out.read_text(encoding="utf-8") == "# hours of arrangement\n"


def test_a_missing_packet_is_a_problem_not_a_traceback(tmp_path: Path) -> None:
    result = cmd_compile_plan(tmp_path, out=tmp_path / "qa_plan.py")
    assert not result.ok
    assert result.status == "invalid"


def _check(**args: object) -> dict:
    return {"call": "created", "name": "http_status",
            "args": {"code": 201, "path": "/api/things", **args}}


def test_the_book_arrangement_compiles_to_the_call_and_the_precondition() -> None:
    """Both halves of a `fixture:` bullet land, in the two places a plan keeps them.

    The name and its arguments become the `qa.fixture(...)` the scenario opens with; the prose
    after the em dash becomes the precondition. The alternative was a `TODO(arrange)` marker an
    author filled in by reading the code — which is the contamination this whole compiler exists
    to remove, arriving through the one door it had left open.
    """
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:1",
            checksDeclared=[_check()],
            fixturesDeclared=[
                {"name": "seeded-ledger", "args": ["2", "draft"],
                 "provides": "two draft policies on file"},
            ],
        )
    )
    source = compile_plan(context, story="demo-story")
    assert 'qa.fixture("seeded-ledger", "2", "draft")' in source
    assert '"two draft policies on file"' in source
    assert "preconditions=[]" not in source
    ast.parse(source)


def test_one_state_two_claims_is_arranged_once() -> None:
    """Two claims documented in the same seeded ledger name one arrangement between them.

    Running it twice would be a second ledger rather than the one both claims are about, so the
    dedup is not tidiness — it is the difference between the state the book described and a
    state nothing described.
    """
    ledger = {"name": "seeded-ledger", "args": ["2"], "provides": "two policies on file"}
    context = _context(
        _obligation("okf:docs/features/demo/api.md#post-things:does:1",
                    checksDeclared=[_check()], fixturesDeclared=[ledger]),
        _obligation("okf:docs/features/demo/api.md#post-things:does:2",
                    checksDeclared=[_check()], fixturesDeclared=[ledger]),
    )
    source = compile_plan(context, story="demo-story")
    assert source.count('qa.fixture("seeded-ledger", "2")') == 1

    # Two that differ in an argument are two states, and both are reached.
    other = {"name": "seeded-ledger", "args": ["5"], "provides": "five policies on file"}
    context["obligations"][1]["fixturesDeclared"] = [other]
    source = compile_plan(context, story="demo-story")
    assert source.count('qa.fixture("seeded-ledger"') == 2


def test_a_book_that_arranges_nothing_still_says_so_out_loud() -> None:
    """Silence in the book is plan debt, and it stays visible as a marker rather than becoming
    an empty `preconditions=[]` a reader would take for a considered answer."""
    context = _context(
        _obligation("okf:docs/features/demo/api.md#post-things:does:1", checksDeclared=[_check()])
    )
    assert "preconditions=[],  # TODO(arrange)" in compile_plan(context, story="demo-story")


def _gap_kinds(gaps: list[Gap], oid: str) -> list[str]:
    return [g.kind for g in gaps if g.obligation_id == oid]


def test_no_fixture_arranged_is_an_unresolved_precondition() -> None:
    oid = "okf:docs/features/demo/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["unresolved-precondition"]


def test_a_missing_request_body_is_an_unarranged_request_body() -> None:
    """`json_body={}` against an endpoint that needs a real one gets refused by the app (422) —
    a false failure against code that did nothing wrong. Unlike an unresolved path reference or
    template variable, there is no partial request to send, so the call is withheld entirely and
    the obligation is never covered, not just annotated with a TODO on a call that still runs.
    """
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["POST /api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["unarranged-request-body"]
    assert oid not in _covers(source)


def _body_act(field: str, value: object) -> dict:
    return {"call": f"body(field={field!r}, value={value!r})", "name": "body",
            "args": {"field": field, "value": value}}


def test_an_arranged_request_body_compiles_to_json_body() -> None:
    """`arrange: body(field=..., value=...)` under the arm fills what `_check`'s bare POST
    otherwise withholds — the whole reason `body` exists as an act rather than a new key."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["POST /api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
            actsDeclared=[_body_act("name", "Widget A"), _body_act("quantity", 3)],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == []
    assert oid in _covers(source)
    assert 'json_body={"name": "Widget A", "quantity": 3}' in source


def test_a_half_arranged_request_body_is_still_withheld() -> None:
    """One act the HTTP driver cannot perform poisons the whole body, the same all-or-nothing
    rule `_performed_lines` already applies to `fill`/`click` — a request half the book
    declared is neither the body it wrote nor no body."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["POST /api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
            actsDeclared=[
                _body_act("name", "Widget A"),
                {"call": 'click(locator="#submit")', "name": "click", "args": {"locator": "#submit"}},
            ],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["unarranged-request-body"]
    assert oid not in _covers(source)


def test_an_unparsed_act_is_still_an_unarranged_request_body() -> None:
    """A bullet under `arrange:` that failed to parse is the same absent body as none at all —
    a compiler that emitted `json_body={}` around it would be filling in for a mistake it
    never saw, not for what the author actually wrote."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["POST /api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
            actsDeclared=[_body_act("name", "Widget A")],
            actsUnparsed=[{"value": "body(field=)", "kind": "bad-arguments", "problem": "malformed"}],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["unarranged-request-body"]
    assert oid not in _covers(source)


def test_an_unresolved_path_template_variable_is_an_unresolved_precondition() -> None:
    oid = "okf:docs/features/demo/globex.md#get-thing:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things/{id}"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, oid)
    assert any("template variable" in g.detail for g in gaps if g.obligation_id == oid)


def test_a_reference_in_the_path_is_an_unresolved_precondition() -> None:
    """`@node.key`/`$name` are static syntax `compile_plan` cannot resolve without running the
    plan — a gap, not a compile-time crash, and the same grammar `fixture:`/`needs:` share."""
    oid = "okf:docs/features/demo/globex.md#get-thing:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things/@seeded-thing.id"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, oid)
    assert any("seeded-thing" in g.detail for g in gaps if g.obligation_id == oid)


def test_a_verify_argument_reference_is_an_unresolved_precondition() -> None:
    oid = "okf:docs/features/demo/globex.md#post-thing:does:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[{"call": "ok", "name": "json_path", "args": {"path": "$captured"}}],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, oid)


def test_no_route_at_all_is_an_uncompilable_claim() -> None:
    """No `route:` to act on is a book that gives QA nothing to observe — a different repair
    from a fixture-shaped gap, so it earns its own kind rather than folding into the other."""
    oid = "okf:docs/features/demo/globex.md#note:does:1"
    context = _context(
        _obligation(
            oid,
            locators={},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]


def test_an_unrecognized_method_is_an_invalid_http_method_not_uncompilable() -> None:
    """A `method:` that does not spell a recognized HTTP verb is undetermined, not absent — a
    different repair (fix the spelling) from `uncompilable-claim` (state a `route:` at all), so
    it earns its own gap kind naming the value that failed, and it must not fall through to
    `unarranged-request-body` either (that code is about a method that parsed but has no body)."""
    oid = "okf:docs/features/demo/globex.md#weird-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"method": ["FROB"], "path": ["/api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["invalid-http-method"]
    assert oid not in _covers(source)
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "FROB" in gap.detail


def test_a_subject_pair_check_wanting_a_snapshot_is_a_named_gap() -> None:
    """`unchanged` wants a before and an after this compiler has no snapshot mechanism to
    take — a named `needs-snapshot` gap, not the generic `uncompilable-claim`."""
    oid = "okf:docs/features/demo/globex.md#post-things:persistence:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                {"call": "the ledger", "name": "unchanged", "args": {"of": "thing.version"}},
            ],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "needs-snapshot" in _gap_kinds(gaps, oid)


@pytest.mark.parametrize("verb", ["created", "removed", "keys_unchanged"])
def test_every_snapshot_needing_verb_gets_the_named_gap(verb: str) -> None:
    oid = "okf:docs/features/demo/globex.md#post-things:persistence:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                {"call": "the ledger", "name": verb, "args": {"subject": "thing.version"}},
            ],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "needs-snapshot" in _gap_kinds(gaps, oid)


@pytest.mark.parametrize("verb", ["persists", "emitted"])
def test_every_out_of_band_verb_gets_the_named_gap(verb: str) -> None:
    oid = "okf:docs/features/demo/globex.md#post-things:persistence:1"
    args = {"subject": "thing.version"} if verb == "persists" else {"event": "thing.updated"}
    context = _context(
        _obligation(
            oid,
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                {"call": "the ledger", "name": verb, "args": args},
            ],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "needs-out-of-band-observation" in _gap_kinds(gaps, oid)


@pytest.mark.parametrize("verb,args", [
    ("count", {"subject": "pages", "equals": 2}),
    ("absent", {"subject": "the deleted thing"}),
    ("exit_status", {"code": 0}),
])
def test_every_single_observation_verb_compiles_for_real(verb: str, args: dict) -> None:
    """`count`/`absent`/`exit_status` are read once, after the action, from what the scenario
    already holds — they compile to a real `qa.verify(...)` call, not a gap."""
    oid = "okf:docs/features/demo/globex.md#get-things:persistence:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[
                {"call": "ok", "name": "http_status", "args": {"code": 200}},
                {"call": "the outcome", "name": verb, "args": args},
            ],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == []
    assert f'qa.verify("{verb}"' in source


def test_checkpoints_and_forbid_scaffolding_never_appear_in_the_gap_report() -> None:
    """`checkpoints=[]`/`forbid=[]` are unconditional TODO scaffolding, not a fact discovered
    about any one obligation — so they stay plain source comments, outside the structured
    report `doctor` reads."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(_obligation(oid, checksDeclared=[_check()]))
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "checkpoints=[],  # TODO" in source
    assert "forbid=[],  # TODO" in source
    assert {g.kind for g in gaps} <= {"unresolved-precondition", "uncompilable-claim"}


def test_a_reference_to_a_fixture_key_arranged_in_the_same_obligation_is_resolved() -> None:
    """A fixture arranged for this obligation arranges before it verifies — so a reference to a
    key that fixture's own `provides:` declares resolves, and is not a gap."""
    oid = "okf:docs/features/acme/api.md#get-thing:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things/@seeded-acme.id"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists",
                               "providesKeys": ["seeded-acme.id"]}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == []


def test_only_the_literal_a_reference_was_found_in_is_wrapped_in_resolve() -> None:
    """`qa.resolve(...)` is the harness's one explicit substitution entry point (Fix 2) — the
    compiler wraps a literal in it only where `references.find_references` actually found a
    `@node.key`/`$name`, and leaves every other literal, including one that merely starts with
    `$` in a way that is not a reference, exactly as it read it.
    """
    oid = "okf:docs/features/acme/api.md#get-thing:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things/@seeded-acme.id"]},
            checksDeclared=[{"call": "ok", "name": "http_status",
                              "args": {"code": 200, "path": "thing.id"}}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists",
                               "providesKeys": ["seeded-acme.id"]}],
        )
    )
    source = compile_plan(context, story="demo-story")
    assert 'qa.http.get(qa.resolve("/api/things/@seeded-acme.id"), expect_status=200)' in source
    assert 'path="thing.id"' in source
    assert 'qa.resolve("thing.id")' not in source


def test_a_capture_resolves_a_reference_on_a_strictly_later_obligation() -> None:
    """`$name` names a fact an earlier `capture:` bullet left behind — an obligation after the
    one that captures it may reference it with no gap."""
    capturing = "okf:docs/features/acme/api.md#post-thing:does:1"
    referencing = "okf:docs/features/acme/api.md#get-thing:does:1"
    context = _context(
        _obligation(
            capturing,
            checksDeclared=[_check()],
            capturesDeclared=[{"name": "captured", "from": "$.thing.id"}],
        ),
        _obligation(
            referencing,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "json_path", "args": {"path": "$captured"}}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists"}],
        ),
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, referencing) == []


def test_a_dollar_capture_with_no_route_credits_nothing_and_still_gaps() -> None:
    """No `route:` means `observed_N` compiles to `None` — nothing was ever requested to read a
    `$.`-rooted capture off of. Crediting `produced_captures` anyway would let a later `$name`
    resolve against a capture that can never run, and the emitted call would blow up on
    `None.json()` with no fault record. This must fall through to the same TODO + gap scaffolding
    a UI-locator capture gets: no emitted call, no credit."""
    capturing = "okf:docs/features/demo/globex.md#note:does:1"
    referencing = "okf:docs/features/acme/api.md#get-thing:does:1"
    context = _context(
        _obligation(
            capturing,
            locators={},
            checksDeclared=[_check()],
            capturesDeclared=[{"name": "captured", "from": "$.thing.id"}],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        ),
        _obligation(
            referencing,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "json_path", "args": {"path": "$captured"}}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists"}],
        ),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "qa.capture_field(" not in source
    assert "unresolved-precondition" in _gap_kinds(gaps, referencing)


def test_a_capture_declared_only_on_a_later_obligation_is_still_a_gap() -> None:
    """The same-obligation exception generalises to ordering: a reference does not see into the
    future, so a capture the book only produces afterward leaves the earlier reference a gap."""
    referencing = "okf:docs/features/acme/api.md#get-thing:does:1"
    capturing = "okf:docs/features/acme/api.md#post-thing:does:1"
    context = _context(
        _obligation(
            referencing,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "json_path", "args": {"path": "$captured"}}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists"}],
        ),
        _obligation(
            capturing,
            checksDeclared=[_check()],
            capturesDeclared=[{"name": "captured", "from": "$.thing.id"}],
        ),
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, referencing)


def test_a_reference_to_an_unarranged_fixtures_key_is_a_gap() -> None:
    """`@node.key` names a fact only that fixture's own arrangement produces — a scenario that
    never arranges it leaves the reference unresolved regardless of what else it did arrange."""
    oid = "okf:docs/features/acme/api.md#get-thing:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things/@seeded-globex.id"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists",
                               "providesKeys": ["seeded-acme.id"]}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, oid)


def test_a_key_reached_only_through_needs_is_resolved() -> None:
    """`seeded-globex` `needs:` `seeded-acme` — arranging the former also arranges the latter, so
    a reference to a key only `seeded-acme` declares under `provides:` still resolves."""
    oid = "okf:docs/features/acme/api.md#get-thing:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["GET /api/things/@seeded-acme.id"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
            fixturesDeclared=[{"name": "seeded-globex", "args": [], "provides": "a project exists",
                               "providesKeys": ["seeded-globex.project_id", "seeded-acme.id"]}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == []


def test_the_producer_walk_follows_document_order_not_alphabetical_id_order() -> None:
    """A node written `returns:` (captures `account_id`) before `raises:` (reads `$account_id`)
    resolves cleanly — even though `raises` sorts before `returns` alphabetically, and
    `_sort_key` is what orders `obligations` on the way in here. The walk has to use each
    obligation's stamped `docPosition`, not the order it arrives in, to get this right."""
    ledger = {"name": "seeded-ledger", "args": [], "provides": "an account exists"}
    returns = _obligation(
        "okf:docs/features/acme/api.md#post-thing:returns:1",
        docPosition=[10, 1],
        locators={"route": ["GET /api/things"]},
        checksDeclared=[_check(path="/api/things")],
        capturesDeclared=[{"name": "account_id", "from": "$.thing.id"}],
        fixturesDeclared=[ledger],
    )
    raises = _obligation(
        "okf:docs/features/acme/api.md#post-thing:raises:1",
        docPosition=[10, 2],
        locators={"route": ["GET /api/things"]},
        checksDeclared=[{"call": "ok", "name": "json_path", "args": {"path": "$account_id"}}],
        fixturesDeclared=[ledger],
    )
    # Arrives alphabetically sorted, `raises` before `returns` — the order `_sort_key` produces
    # and the opposite of the book's own document order stamped in `docPosition` above.
    context = _context(raises, returns)
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, raises["id"]) == []


def test_the_producer_walk_still_gaps_a_reference_that_precedes_its_producer() -> None:
    """The mirror of the case above: `raises:` written *before* `returns:` in the book still
    leaves the reference a gap, because the capture it needs has not happened yet at that point
    in document order — regardless of what the two obligations' ids alphabetize to."""
    ledger = {"name": "seeded-ledger", "args": [], "provides": "an account exists"}
    raises = _obligation(
        "okf:docs/features/acme/api.md#post-thing:raises:1",
        docPosition=[10, 1],
        locators={"route": ["GET /api/things"]},
        checksDeclared=[{"call": "ok", "name": "json_path", "args": {"path": "$account_id"}}],
        fixturesDeclared=[ledger],
    )
    returns = _obligation(
        "okf:docs/features/acme/api.md#post-thing:returns:1",
        docPosition=[10, 2],
        locators={"route": ["GET /api/things"]},
        checksDeclared=[_check(path="/api/things")],
        capturesDeclared=[{"name": "account_id", "from": "$.thing.id"}],
        fixturesDeclared=[ledger],
    )
    context = _context(raises, returns)
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, raises["id"])


def test_a_checkless_obligation_never_reaches_the_scenario_body() -> None:
    """The dead `TODO(undeclared)` branch removed from `_scenario_body`: a checkless obligation
    is book debt, filtered out before the body is ever asked to render one — no scenario is
    emitted for it, but it is not a silent drop either: the same code that declined to compile
    it is the code that gaps it, so it still lands in `{emitted, gap}` like every owed id."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:2"
    context = _context(_obligation(oid))
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["no-verify-declared"]
    assert "# Book debt." in source
    assert f"#   {oid}" in source


# --- Screen page-scenario compilation (slice 4) -----------------------------------------------
#
# A screen's `visible(...)` bullets are addressed by navigating there, not by parsing its
# `route:` as an HTTP verb+path — see `compile.py`'s module-level comment above `_ROUTE` and
# `_compile_page_scenarios`'s docstring for the full partitioning this drives (Amendment 3).
# These fixtures mirror the shape `ostler.qa.context._navigation`/`_locators` actually produce
# (confirmed against paddock's policy-desk fixture, `docs/features/policy/gui/screens/*.md`),
# rather than reconstructing it from the ruling set alone.

_SCREEN = "docs/features/policy/gui/screens/policy-list.md"


def _page_obligation(oid: str, node: str, *, surface: str = "policy",
                      source: str = _SCREEN, locators: dict | None = None,
                      checks: list[dict] | None = None, kind: str | None = None,
                      requirement: str = "shows what the screen promises",
                      fixtures: list[dict] | None = None,
                      acts: list[dict] | None = None) -> dict:
    obligation = {
        "id": oid,
        "node": node,
        "nodeType": "interaction",
        "source": source,
        "surface": surface,
        "requirement": requirement,
        "required": True,
        "locators": locators or {},
        "checksDeclared": checks if checks is not None else [
            {"call": "it", "name": "visible", "args": {"locator": "irrelevant"}},
        ],
    }
    if kind is not None:
        obligation["kind"] = kind
    if fixtures is not None:
        obligation["fixturesDeclared"] = fixtures
    if acts is not None:
        obligation["actsDeclared"] = acts
    return obligation


def _act(name: str, node: str, locators: dict[str, list[str]], **args: str) -> dict:
    """One `actsDeclared` row shaped the way `qa context` writes it: the canonical call text,
    its bound arguments, and the resolved book node each locator argument names.
    """
    call = f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
    return {"call": call, "name": name, "args": dict(args),
            "locates": {"locator": {"node": node, "locators": locators}}}


def _visible(locator: str) -> dict:
    return {"call": "it", "name": "visible", "args": {"locator": locator}}


def _navigation_context(*obligations: dict, navigation: dict,
                        screen_routes: dict[str, str] | None = None) -> dict:
    ctx = _context(*obligations)
    ctx["navigation"] = navigation
    # A real packet carries each screen file's `route:` — `qa context` reads it off the book
    # with the same function the vet driver compares a URL against. Without one the compiler
    # cannot say a photographed page is the screen it names, and withholds the vet; these
    # fixtures are about what a plan compiles, so every screen they mention states a plain one.
    ctx["screenRoutes"] = (
        _screen_routes(navigation) if screen_routes is None else dict(screen_routes)
    )
    return ctx


def _screen_routes(navigation: dict) -> dict[str, str]:
    """A literal `route:` for every screen file the navigation map names."""
    routes: dict[str, str] = {}
    for surface in navigation.values():
        documents = [surface.get("start", "")]
        documents.extend(surface.get("routes") or {})
        documents.extend(surface.get("unreachable") or [])
        documents.extend(surface.get("undeclared") or [])
        for document in documents:
            if document:
                routes[document] = "/" + document.rsplit("/", 1)[-1].removesuffix(".md")
    return routes


def _arrival_navigation(source: str = _SCREEN, surface: str = "policy", *,
                         unreachable: list[str] | None = None,
                         undeclared: list[str] | None = None) -> dict:
    """One surface, one screen, reachable with an empty hop list (it is the route's own root)."""
    return {
        surface: {
            "start": source,
            "surface": surface,
            "driver": "web",
            "rootPath": "/",
            "entryUrl": _BASE_URL,
            "counts": {"screens": 1, "reachable": 1, "unreachable": 0, "undeclared": 0, "nav_edges": 0},
            "routes": {} if source in (unreachable or []) else {source: []},
            "unreachable": unreachable or [],
            "undeclared": undeclared or [],
        }
    }


def test_exclusive_with_pairing_never_shares_a_scenario() -> None:
    """`empty-register-notice`/`policy-table` (real policy-desk bullets) must never land in the
    same compiled scenario — the amendment reads `exclusive-with:` as symmetric even though only
    one side of this real pair writes the bullet. `empty-register-notice`'s real `role: paragraph`
    carries no `name:`, which after Finding 7 is no longer an addressable subject on its own, so
    a `selector:` is added here to keep this test about partitioning rather than about locator
    constructibility (covered separately)."""
    table = f"{_SCREEN}#policy-table"
    notice = f"{_SCREEN}#empty-register-notice"
    context = _navigation_context(
        _page_obligation("okf:policy-list:policy-table:visible:1", table,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        _page_obligation("okf:policy-list:empty-register-notice:visible:1", notice,
                          locators={"role": ["paragraph"],
                                    "selector": ["p.empty-register-notice"],
                                    "exclusiveWith": ["[policy-table](#policy-table)"]},
                          checks=[_visible("text=No policies are on file yet")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    scenarios = source.split("@scenario(")[1:]
    scenario_with = [s for s in scenarios if "text=No policies are on file yet" in s]
    scenario_without = [s for s in scenarios if "table:Policies on file" in s and "verify" in s]
    assert len(scenario_with) == 1
    assert "table:Policies on file" not in scenario_with[0]
    assert len(scenario_without) == 1
    assert "No policies are on file yet" not in scenario_without[0]
    assert _gap_kinds(gaps, "okf:policy-list:empty-register-notice:visible:1") == []


def test_a_page_scenario_with_no_root_path_gaps_uncompilable_claim_not_a_fabricated_root() -> None:
    """A driver with no path grammar (`routes.is_path_addressed` says no) states no `rootPath`
    at all — `reach.root_path` now returns `(None, None)` for it rather than the app root. The
    catch-all this compiler used to own, `nav.get("rootPath") or "/"`, is gone: a screen on such
    a surface gaps `uncompilable-claim` naming the missing root, instead of opening a scenario
    on a fabricated `qa.goto("/")` that claims an address the book never stated."""
    oid = "okf:policy-list:policy-table:visible:1"
    node = f"{_SCREEN}#policy-table"
    nav = _arrival_navigation()
    nav["policy"]["rootPath"] = None
    context = _navigation_context(
        _page_obligation(oid, node, locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=nav,
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]
    detail = next(g.detail for g in gaps if g.obligation_id == oid)
    assert "states no root path" in detail
    assert "qa.goto(" not in source


def test_an_unarranged_states_claim_produces_a_gap_not_a_scenario() -> None:
    """A `states:` bullet mints its own obligation (`kind == "states"`) separate from the node's
    `role:`/`name:` claim. With no fixture arranging it, it compiles to nothing — no scenario,
    arrival or otherwise — only an `unarranged-state` gap quoting its own requirement text
    verbatim. Its non-state sibling on the same node is unaffected: it still gets a real
    scenario, because a `states:` bullet no longer withholds the whole node (Finding a)."""
    node = f"{_SCREEN}#coverage-type-select"
    oid = "okf:new-policy:coverage-type-select:visible:1"
    state_oid = "okf:new-policy:coverage-type-select:states:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["combobox"], "name": ["Coverage type"]},
                          checks=[_visible("combobox:Coverage type")]),
        _page_obligation(state_oid, node, kind="states",
                          requirement="opens on `auto`.",
                          locators={"role": ["combobox"], "name": ["Coverage type"]},
                          checks=[]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "combobox:Coverage type" in source
    assert _gap_kinds(gaps, oid) == []
    assert _gap_kinds(gaps, state_oid) == ["unarranged-state"]
    [gap] = [g for g in gaps if g.obligation_id == state_oid]
    assert "opens on `auto`." in gap.detail


def test_a_fully_arranged_states_claim_compiles_its_own_scenario() -> None:
    """A `states:` obligation that declares both a check and a fixture compiles into its own
    dedicated scenario, with `preconditions=[...]` quoting the arranging fixture's own words —
    it is not merged into the node's plain arrival scenario, and it is not gapped."""
    node = f"{_SCREEN}#widget-table"
    oid = "okf:widget-list:widget-table:visible:1"
    state_oid = "okf:widget-list:widget-table:states:2"
    fixture = {"name": "seeded-loading", "args": [], "provides": "the widget list is loading"}
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["table"], "name": ["Widgets"]},
                          checks=[_visible("table:Widgets")]),
        _page_obligation(state_oid, node, kind="states",
                          requirement="shows a loading indicator while widgets are fetched.",
                          locators={"role": ["table"], "name": ["Widgets"]},
                          checks=[_visible("status:Loading")],
                          fixtures=[fixture]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, state_oid) == []
    assert "status:Loading" in source
    assert 'qa.fixture("seeded-loading")' in source
    assert '"the widget list is loading"' in source


def test_states_no_longer_withholds_exclusive_with_on_the_same_node() -> None:
    """`vehicle-vin-field` in the real `new-policy.md` fixture carries *both* `states:` and
    `exclusive-with:`. The two are now separate obligations: the `states:` one is gapped on its
    own id (unarranged), and the `exclusive-with:` claim still compiles into its own isolated
    scenario — a `states:` bullet no longer blocks a sibling claim from compiling at all."""
    node = f"{_SCREEN}#vehicle-vin-field"
    oid = "okf:new-policy:vehicle-vin-field:visible:1"
    state_oid = "okf:new-policy:vehicle-vin-field:states:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["textbox"], "name": ["Vehicle VIN"],
                                    "exclusiveWith": ["[property-address-field](#property-address-field)"]},
                          checks=[_visible("textbox:Vehicle VIN")]),
        _page_obligation(state_oid, node, kind="states",
                          requirement="present only while the coverage type is `auto`.",
                          locators={"role": ["textbox"], "name": ["Vehicle VIN"],
                                    "exclusiveWith": ["[property-address-field](#property-address-field)"]},
                          checks=[]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "textbox:Vehicle VIN" in source
    assert "@scenario(" in source
    assert _gap_kinds(gaps, oid) == []
    assert _gap_kinds(gaps, state_oid) == ["unarranged-state"]


def test_unarranged_state_reaches_the_same_gap_on_every_driver() -> None:
    """A check-less `states:` obligation on a `component` node dispatches to a different
    builder per surface driver (D1: `component` x `driver`, `_OBSERVE_ROW`) — web to the
    page builder, cli and http to their own. All three owe it the same verdict: gapped
    `unarranged-state`, never `no-verify-declared`, and never dropped. Three packets
    identical but for the driver, reproducing the defect where the cli arm re-derived
    "declares no check" by re-filtering `checksDeclared` (mislabeling the gap) and the
    http arm dropped the obligation on the floor (tripping the totality assert at the
    close of `compile_plan_gaps` on a legitimate book)."""
    requirement = "opens on `auto`."

    node = f"{_SCREEN}#coverage-type-select"
    web_oid = "okf:new-policy:coverage-type-select:states:web"
    web_obligation = _page_obligation(web_oid, node, kind="states", requirement=requirement,
                                       locators={"role": ["combobox"], "name": ["Coverage type"]},
                                       checks=[])
    web_obligation["nodeType"] = "component"
    web_context = _navigation_context(web_obligation, navigation=_arrival_navigation())
    web_source, web_gaps = compile_plan_gaps(web_context, story="demo-story")
    ast.parse(web_source)
    assert _gap_kinds(web_gaps, web_oid) == ["unarranged-state"]

    cli_oid = "okf:new-policy:coverage-type-select:states:cli"
    cli_context = _context(
        _obligation(cli_oid, nodeType="component", kind="states", requirement=requirement)
    )
    cli_context["navigation"][""]["driver"] = "cli"
    cli_source, cli_gaps = compile_plan_gaps(cli_context, story="demo-story")
    ast.parse(cli_source)
    assert _gap_kinds(cli_gaps, cli_oid) == ["unarranged-state"]

    http_oid = "okf:new-policy:coverage-type-select:states:http"
    http_context = _context(
        _obligation(http_oid, nodeType="component", kind="states", requirement=requirement)
    )
    http_context["navigation"][""]["driver"] = "http"
    http_source, http_gaps = compile_plan_gaps(http_context, story="demo-story")
    ast.parse(http_source)
    assert _gap_kinds(http_gaps, http_oid) == ["unarranged-state"]


def test_an_interactions_assertion_never_lands_on_the_arrival_scenario() -> None:
    """A `## Interactions` row's `visible(...)` asserts state *after* the interaction — it must
    never be emitted as an arrival assertion on the screen's own page-load scenario. The
    interaction row itself carries no `role`/`name`/`selector` of its own (only `on`/`trigger`/
    `does`), so per Finding 1 its `visible(...)` claim has no addressable subject and is gapped
    as `uncompilable-claim` rather than silently asserting on `qa.page`/the document body — and
    since that is this fixture's only interaction obligation, nothing survives to claim, so the
    interaction scenario itself is not emitted at all (a `covers=[]` scenario is a hole in the
    plan wearing a function signature, never the compiled output)."""
    button = f"{_SCREEN}#create-policy-button"
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:visible:1"
    context = _navigation_context(
        _page_obligation("okf:new-policy:create-policy-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy... navigates to its detail screen"]},
                          checks=[_visible("heading:Policy PN-1001")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    scenarios = source.split("@scenario(")[1:]
    arrival = [s for s in scenarios if "_arrival(" in s]
    interactions = [s for s in scenarios if "submit_new_policy(" in s]
    assert len(arrival) == 1
    assert "heading:Policy PN-1001" not in arrival[0]
    # No addressable subject for the interaction's own `visible(...)` claim, so it is gapped as
    # `uncompilable-claim` rather than compiled against a guessed operand — and since that is
    # this scenario's only obligation, nothing survives to claim, so the scenario itself is not
    # emitted (an emitted `covers=[]` scenario is a hole in the plan wearing a function
    # signature, never the compiled output).
    assert len(interactions) == 0
    # Two independent gaps land on this id: the trigger itself is an unverified scaffold click
    # (`unresolved-precondition`, minted unconditionally for every interaction obligation — see
    # `_interaction_scenario`), and its `visible(...)` claim has no addressable subject of its
    # own (`uncompilable-claim`). Both are real, neither supersedes the other.
    assert sorted(_gap_kinds(gaps, interaction_oid)) == ["uncompilable-claim", "unresolved-precondition"]


def test_a_subject_only_verb_on_a_page_obligation_is_a_gap_not_a_silent_drop() -> None:
    """`unchanged` observes a subject (a before/after pair), not the rendered page — a
    Playwright driver cannot serve it. Before the fix this row was dropped with a bare
    `continue`: no call, no gap, no note. It must now surface as a real `uncompilable-claim`
    gap naming the verb — and the obligation goes uncovered, because its `verify:` bullets
    are a conjunction and the `visible(...)` row is only half of what it claims."""
    node = f"{_SCREEN}#policy-table"
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  {"call": "the count", "name": "unchanged", "args": {"of": "policy.count"}}]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    kinds = _gap_kinds(gaps, oid)
    assert "uncompilable-claim" in kinds
    [gap] = [g for g in gaps if g.obligation_id == oid and g.kind == "uncompilable-claim"]
    assert "unchanged" in gap.detail
    assert "not observable from the playwright driver" in gap.detail


def test_a_body_observing_verb_on_a_page_obligation_names_driver_and_channel_differently() -> None:
    """`json_path` observes a `body` — a channel Playwright *can* see, unlike `unchanged`'s
    `subject`. So the gap is not "this driver is blind to it" but "a browser makes many
    requests and this claim did not say which one": `json_path`'s own `path=` is a path into
    the payload, never a route. The message must name the driver, the channel, and the bullet
    that would settle it."""
    node = f"{_SCREEN}#policy-table"
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  {"call": "the status field", "name": "json_path",
                                   "args": {"path": "$.status", "equals": "active"}}]),
        navigation=_arrival_navigation(),
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    [gap] = [g for g in gaps if g.obligation_id == oid and g.kind == "uncompilable-claim"]
    assert "json_path" in gap.detail
    assert "an HTTP body" in gap.detail
    assert "playwright driver " in gap.detail and "can see" in gap.detail
    assert 'http_status(method="' in gap.detail and '", path="' in gap.detail


def test_a_driver_with_no_declared_channels_gaps_every_claim_and_crashes_on_none() -> None:
    """Acceptance criterion 3: a driver declaring no capability at all must turn every
    claim shape routed through `_unobservable_gap` into a gap — never an exception, and
    never a silently compiled (falsely passing) assertion."""
    empty = DriverSpec("empty", frozenset())
    for observes_shape in ("response", "body", "page", "subject", "subject-pair", None):
        name = {
            "response": "http_status", "body": "json_path", "page": "visible",
            "subject": "count", "subject-pair": "unchanged", None: "not_a_real_check",
        }[observes_shape]
        gap = _unobservable_gap("okf:some:obligation:1", name, empty)
        assert gap.kind == "uncompilable-claim"
        assert "empty driver" in gap.detail


def test_playwright_and_maestro_declare_disjoint_but_overlapping_capabilities() -> None:
    """Maestro is nameable from the compiler via its own capability declaration — it
    declares `page` and `subject`, not the HTTP channels Playwright can see, and not the
    same page/HTTP mix Playwright declares either. Playwright alone also declares
    `keyboard`: a real keypress it can dispatch at the page, which Maestro's touch UI has
    no notion of."""
    assert PLAYWRIGHT.observes == frozenset({"page", "response", "body", "keyboard"})
    assert MAESTRO.observes == frozenset({"page", "subject"})
    assert PYTHON.observes == frozenset({"response", "body", "subject"})


def test_a_reachable_screen_with_no_declared_preconditions_is_undeclared_not_silent() -> None:
    """Amendment 2: reachable, but the screen's `requires:`/`params:` bullets are literally
    absent — a third outcome, distinct from `unreachable`, with its own gap kind, and emitted
    once per screen rather than once per obligation (a live-audit gate renders one line per
    gap; multiplying this by obligation count would not add information)."""
    node = f"{_SCREEN}#policy-table"
    context = _navigation_context(
        _page_obligation("okf:policy-list:policy-table:visible:1", node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        _page_obligation("okf:policy-list:policy-table:visible:2", node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(undeclared=[_SCREEN]),
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    undeclared_gaps = [g for g in gaps if g.kind == "screen-preconditions-undeclared"]
    assert len(undeclared_gaps) == 1
    # One gap per screen (documented exception to Amendment 1's per-obligation rule), but it
    # must still carry a real, known obligation id — never the screen's source path — so the
    # live-audit lane's `covers`/`gapped_ids` intersection can filter on it (Finding 2). The
    # first (sorted) obligation id on the screen stands in for the screen-level fact.
    assert undeclared_gaps[0].obligation_id == "okf:policy-list:policy-table:visible:1"


def test_an_unreachable_screen_is_a_finding_not_a_compile_target() -> None:
    """Correction 5': an unreachable screen is a finding, not a scenario. `unreachable-screen`
    is doctor's own existing code for this fact (the same one its `reach`-based check mints),
    reused here rather than collapsing it into the generic `uncompilable-claim`."""
    node = f"{_SCREEN}#policy-table"
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(unreachable=[_SCREEN]),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "@scenario(" not in source
    assert "web = target(" not in source or "table:Policies on file" not in source
    kinds = _gap_kinds(gaps, oid)
    assert kinds == ["unreachable-screen"]


def test_a_zero_screen_book_grows_no_playwright_target() -> None:
    """Condition 1: a book with no screen nodes on any surface never grows a `web` target, even
    if a stray page-checked obligation somehow reached the compiler."""
    node = "docs/features/policy/http/policy-desk-api.md#note"
    context = _navigation_context(
        _page_obligation("okf:note:visible:1", node, surface="policy",
                          source="docs/features/policy/http/policy-desk-api.md",
                          checks=[_visible("text=irrelevant")]),
        navigation={
            "policy": {
                "start": "", "surface": "policy", "driver": "web", "entryUrl": _BASE_URL,
                "counts": {"screens": 0, "reachable": 0, "unreachable": 0, "undeclared": 0, "nav_edges": 0},
                "routes": {}, "unreachable": [], "undeclared": [],
            }
        },
    )
    source, _gaps = compile_plan_gaps(context, story="demo-story")
    assert 'target("web"' not in source
    assert "@scenario(" not in source


def test_navigation_is_keyed_by_surface_even_for_a_single_surface_book() -> None:
    """Amendment 1: `navigation` is keyed by surface, no special-casing a one-surface book —
    pinned here with two surfaces so a screen on one never resolves against the other's route."""
    policy_screen = "docs/features/policy/gui/screens/policy-list.md"
    claims_screen = "docs/features/claims/gui/screens/claims-list.md"
    policy_node = f"{policy_screen}#policy-table"
    claims_node = f"{claims_screen}#claims-table"
    context = _navigation_context(
        _page_obligation("okf:policy-list:policy-table:visible:1", policy_node,
                          surface="policy", source=policy_screen,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        _page_obligation("okf:claims-list:claims-table:visible:1", claims_node,
                          surface="claims", source=claims_screen,
                          locators={"role": ["table"], "name": ["Claims on file"]},
                          checks=[_visible("table:Claims on file")]),
        navigation={
            **_arrival_navigation(source=policy_screen, surface="policy"),
            **_arrival_navigation(source=claims_screen, surface="claims"),
        },
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "table:Policies on file" in source
    assert "table:Claims on file" in source
    assert gaps == []


# --- Locator constructibility (Findings 1, 4-7) ------------------------------------------------
#
# A compiled `qa.verify(...)`/`qa.by_role(...)`/`qa.by_css(...)` call is only as good as the
# string arguments the book handed it — Playwright raises at *runtime*, not compile time, when
# they are wrong, so these are read straight out of the compiled plan's own syntax tree rather
# than by running a browser.

try:
    from playwright._impl._api_structures import AriaRole as _AriaRole
    from typing import get_args as _get_args
    _KNOWN_ARIA_ROLES = frozenset(_get_args(_AriaRole))
except ImportError:  # pragma: no cover - exercised only when the `qa` extra is installed
    _KNOWN_ARIA_ROLES = frozenset()

_UNMATCHABLE_ROLES = frozenset({"generic", "none", "presentation"})


def _call_kwargs(call: ast.Call) -> dict[str, str | None]:
    """Every keyword argument of *call* whose value is a string literal, by name."""
    out: dict[str, str | None] = {}
    for kw in call.keywords:
        if kw.arg is not None and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            out[kw.arg] = kw.value.value
    return out


def _call_attr(call: ast.Call) -> str:
    """The attribute name of *call*'s callee, e.g. `"by_role"` for `qa.by_role(...)`."""
    assert isinstance(call.func, ast.Attribute), f"expected an attribute call, got {ast.dump(call.func)}"
    return call.func.attr


def _locator_calls(source: str) -> list[ast.Call]:
    """Every `qa.by_role(...)` / `qa.by_css(...)` call in the compiled plan."""
    calls = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("by_role", "by_css")):
            calls.append(node)
    return calls


def _string_args(call: ast.Call) -> list[str]:
    args = [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    args += [v for v in _call_kwargs(call).values() if v is not None]
    return args


def test_a_compiled_plan_never_hands_playwright_an_unconstructible_locator() -> None:
    """Five ways a compiled `by_role`/`by_css` call can be wrong and only fail at runtime, all
    pinned against one plan compiled from bullets that provoke each of them:

    1. a code-span-wrapped value (`` `button` ``) reaching Playwright with its backticks still
       on, which raises `InvalidSelectorError` (Finding 6);
    2. a `role=` value outside Playwright's matchable `AriaRole` set (Finding 5);
    3. a `role=` value inside `{"generic","none","presentation"}` — real ARIA roles that never
       match anything via `get_by_role` (Finding 5's correction);
    4. a `name=` value equal to the literal string `"none"` — the book's sentinel for "no
       accessible name," never a name to search for (Finding 4);
    5. a bare `by_role(...)` call with no accompanying `name=` — ambiguous and, unlike a
       boolean check, one Playwright's strict mode *raises* on rather than failing quietly
       (Finding 7).
    """
    screen = "docs/features/policy/gui/screens/policy-list.md"
    context = _navigation_context(
        # (1) backtick-wrapped role and name.
        _page_obligation("okf:policy-list:backticked:visible:1", f"{screen}#backticked",
                          locators={"role": ["`button`"], "name": ["`Cancel policy`"]},
                          checks=[_visible("button:Cancel policy")]),
        # (2) an unrecognized role string, falling through to a backtick-wrapped selector.
        _page_obligation("okf:policy-list:bad-role:visible:1", f"{screen}#bad-role",
                          locators={"role": ["widget-nonexistent"], "name": ["Something"],
                                    "selector": ["`.something`"]},
                          checks=[_visible("something")]),
        # (3) `role: generic` paired with the `name: none` sentinel and a selector fallback.
        _page_obligation("okf:policy-list:generic-role:visible:1", f"{screen}#generic-role",
                          locators={"role": ["generic"], "name": ["none"], "selector": ["dl"]},
                          checks=[_visible("generic")]),
        # (4)+(5) role-only, no name and no selector: no addressable subject at all -> gap,
        # never a bare `by_role("table")` call.
        _page_obligation("okf:policy-list:role-only:visible:1", f"{screen}#role-only",
                          locators={"role": ["table"]},
                          checks=[_visible("table")]),
        navigation=_arrival_navigation(source=screen),
    )
    source, _gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)

    calls = _locator_calls(source)
    assert calls, "expected at least one by_role/by_css call to check"
    for call in calls:
        for value in _string_args(call):
            assert "`" not in value, f"a code-span backtick reached a compiled locator argument: {value!r}"
        kwargs = _call_kwargs(call)
        attr = _call_attr(call)
        role = kwargs.get("role") if attr == "by_role" else None
        # A `by_role` call's first positional argument is the role.
        if attr == "by_role" and call.args:
            first = call.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                role = first.value
        if role is not None:
            assert not _KNOWN_ARIA_ROLES or role in _KNOWN_ARIA_ROLES, (
                f"{role!r} is not a role Playwright's `get_by_role` can match"
            )
            assert role not in _UNMATCHABLE_ROLES, (
                f"{role!r} is a real ARIA role that never matches anything via `get_by_role`"
            )
        name = kwargs.get("name")
        if name is not None:
            assert name.lower() != "none", "the book's `name: none` sentinel leaked in as a literal name"
        if attr == "by_role":
            assert "name" in kwargs, f"bare `by_role({role!r})` call with no `name=` is ambiguous " \
                "under Playwright's strict mode"


def test_an_unavailable_role_set_degrades_to_a_selector_never_to_skipped_validation(monkeypatch) -> None:
    """Finding 9: when Playwright's `AriaRole` set cannot be derived (the `qa` extra missing, or
    a future playwright release moving the private module), `_MATCHABLE_ROLES` is `None` — and
    that must never be read as "validation is optional." `role: generic` must still not compile
    to `by_role("generic")`; it must fall through to `selector:` exactly as when the role set is
    known and `generic` is excluded from it."""
    import ostler.qa.compile as compile_mod

    monkeypatch.setattr(compile_mod, "_MATCHABLE_ROLES", None)
    screen = "docs/features/policy/gui/screens/policy-list.md"
    context = _navigation_context(
        _page_obligation("okf:policy-list:generic-role:visible:1", f"{screen}#generic-role",
                          locators={"role": ["generic"], "name": ["Summary"], "selector": ["dl"]},
                          checks=[_visible("generic")]),
        navigation=_arrival_navigation(source=screen),
    )
    source, _gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert 'by_role("generic"' not in source
    assert 'by_css("dl")' in source


def _located(locator: str, node: str, locators: dict) -> dict:
    """A `visible(locator=...)` row the packet already resolved to a declared component."""
    row = _visible(locator)
    row["locates"] = {"locator": {"node": node, "locators": locators}}
    return row


def test_a_check_is_pointed_at_the_component_its_locator_names() -> None:
    """The claim is the form's; the thing that shows the refusal is a span declared beside it.

    Before `locates`, the operand came from the obligation's *own* node — so the assertion
    looked at the form rather than at the span the check names. The `locator=` argument still
    rides along: resolving a reference into an operand does not repeat the claim, and the
    claim is what `ostler qa validate` matches against the `verify:` bullet.
    """
    oid = "okf:new-policy:submit:does:1"
    error_span = f"{_SCREEN}#name-error"
    context = _navigation_context(
        _page_obligation(
            oid, f"{_SCREEN}#new-policy-form",
            locators={"role": ["form"], "name": ["New policy"]},
            checks=[_located("#name-error", error_span, {"selector": ["`#name-error`"]})],
        ),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "#name-error" in source
    assert 'name="New policy"' not in source
    # The declared argument still stands beside the operand: it is the claim's own statement
    # of its subject, and `visible` marks `locator` required.
    assert 'locator="#name-error"' in source
    assert _gap_kinds(gaps, oid) == []


def test_a_check_locator_that_names_no_component_compiles_to_nothing() -> None:
    """`doctor` refuses this book; `compile_plan` is not `doctor`'s downstream and still sees it.

    The failure to avoid is an assertion emitted against the obligation's own node, which would
    pass on a screen that never renders the thing the check was written about.
    """
    oid = "okf:new-policy:submit:does:1"
    row = _visible("#no-such-thing")
    row["locates"] = {"locator": {"node": "", "locators": {}}}
    context = _navigation_context(
        _page_obligation(
            oid, f"{_SCREEN}#new-policy-form",
            locators={"role": ["form"], "name": ["New policy"]},
            checks=[row],
        ),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "@scenario(" not in source
    assert _gap_kinds(gaps, oid) == ["undeclared-check-locator"]


def test_a_named_component_with_no_addressable_locator_is_an_uncompilable_claim() -> None:
    """The book says what to look at and not how to address it — a gap, not a body fallback."""
    oid = "okf:new-policy:submit:does:1"
    context = _navigation_context(
        _page_obligation(
            oid, f"{_SCREEN}#new-policy-form",
            locators={"role": ["form"], "name": ["New policy"]},
            checks=[_located("#name-error", f"{_SCREEN}#name-error", {"role": ["paragraph"]})],
        ),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]


def test_an_undetermined_claim_combiner_emits_no_code_at_all() -> None:
    """A claim whose siblings may be alternatives is undetermined, and undetermined never runs.

    The check above the list either observes this child or refutes it, and the book does not
    say which — so the compiler gaps it rather than picking the reading (`all`) that the flat
    grammar happens to produce, which is the one that files a refutation as a proof.
    """
    oid = "okf:docs/features/demo/api.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            claimCombiner="unstated",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/x"}},
            ],
        )
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _covers(source) == set()
    assert _gap_kinds(gaps, oid) == ["unstated-claim-combiner"]


def test_an_interactions_check_is_pointed_at_the_component_it_names() -> None:
    """An interaction's claim is observed by whatever the check names, not by the interaction.

    An interaction row declares `on`/`trigger`/`does` and nothing addressable of its own, so
    before the `(locator)` argument every one of its `visible(...)` claims was uncompilable. The
    claim was never unobservable — the book said which component shows the outcome, and the
    compiler was pointing at the wrong node and passing the right one through as a string.
    """
    button = f"{_SCREEN}#create-policy-button"
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    context = _navigation_context(
        _page_obligation("okf:new-policy:create-policy-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    interactions = [s for s in source.split("@scenario(")[1:] if "submit_new_policy(" in s]
    assert len(interactions) == 1
    assert 'qa.by_role("table", name="Policies on file")' in interactions[0]
    assert 'locator="#policy-table"' in interactions[0]
    # The claim is observed; the trigger is still a scaffold click, and that gap is unrelated.
    assert _gap_kinds(gaps, interaction_oid) == ["unresolved-precondition"]
    assert interaction_oid in _covers(source)


def test_an_interaction_with_no_on_locator_emits_no_assertion() -> None:
    """A click with nowhere real to land is not a weaker version of the interaction — it is not
    the interaction at all, so nothing it would have proven is emitted.

    `unresolved-precondition` ordinarily stands beside a real, compiled assertion on purpose
    (`_ARRANGEMENT_GAPS`): the claim is genuine even though the state was reached by a scaffold.
    But when `on:` names a component the book gives no locator at all, the compiled click falls
    back to `qa.page.locator('body')` — not a scaffolded trigger, no trigger. An assertion after
    it would be observing whatever the page already looked like on arrival, a check that can
    only fail and reads as the app's defect rather than the book's undeclared locator.
    """
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    context = _navigation_context(
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "submit_new_policy(" not in source
    assert 'qa.by_role("table", name="Policies on file")' not in source
    assert interaction_oid not in _covers(source)
    assert _gap_kinds(gaps, interaction_oid) == ["unresolved-precondition"]


def test_the_scaffold_click_gap_does_not_claim_does_is_unresolved() -> None:
    """The generic `unresolved-precondition` gap here only ever established one fact: the
    trigger compiles to a scaffold click, not a verified action. `does:` is quoted as a
    comment and never parsed or resolved (own docstring), so a node whose `does:` genuinely
    does resolve — via its own check's cross-file target, the real `open-new-widget` shape —
    must not have this branch's message assert the opposite about it. Say only what was
    checked; a node whose `does:` truly does not resolve needs its own check to say so.
    """
    button = f"{_SCREEN}#create-policy-button"
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    context = _navigation_context(
        _page_obligation("okf:new-policy:create-policy-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    _, gaps = compile_plan_gaps(context, story="demo-story")
    details = [g.detail for g in gaps if g.obligation_id == interaction_oid]
    assert len(details) == 1
    assert "scaffold click" in details[0]
    assert "does:" not in details[0]


def test_a_gapped_but_covered_obligation_is_not_deferred() -> None:
    """The `open-new-widget` shape: a real `covers=[...]` claim stands beside its own gap on
    purpose (`_ARRANGEMENT_GAPS`). `deferred_obligations` must not name this id — a real plan
    can be held to the same coverage standard the reference compiler itself met.
    """
    button = f"{_SCREEN}#create-policy-button"
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    context = _navigation_context(
        _page_obligation("okf:new-policy:create-policy-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    deferred = _deferred_obligations(context, story="demo-story")
    assert interaction_oid not in deferred


def test_a_gapped_and_uncovered_obligation_is_deferred_with_its_gap() -> None:
    """The mirror: a `submit-new-policy` with nowhere real to land compiles no assertion at
    all (`test_an_interaction_with_no_on_locator_emits_no_assertion`) — its whole gap is that
    the reference compiler produced no evidence for it, so it must be named as deferred.
    """
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    context = _navigation_context(
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    deferred = _deferred_obligations(context, story="demo-story")
    assert interaction_oid in deferred
    assert deferred[interaction_oid].kind == "unresolved-precondition"


def test_annotate_deferred_obligations_stamps_the_packets_own_obligations() -> None:
    """The producer half: the packet handed to `write_context` carries the reason inline,
    so a consumer (`validate_v2`) reads it off the obligation rather than recompiling.
    """
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    context = _navigation_context(
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    _annotate_deferred_obligations(context, story="demo-story")
    stamped = next(o for o in context["obligations"] if o["id"] == interaction_oid)
    assert stamped["deferred"]["kind"] == "unresolved-precondition"


def test_interaction_arms_with_an_unarranged_when_emit_no_assertion() -> None:
    """The real `globex` `new-widget.md` shape: a happy arm and its `extends:`-linked refusal
    arm share one resolved `on:` button and no fixture that fills the form either declares.

    Both arms compile to the identical scaffold up to their assertions — `goto` → click the
    same button. With no fixture arranging `name`/`quantity`, the unarranged page is always
    literally the empty-form state, which happens to be the refusal arm's own precondition:
    the happy arm's assertion fails for a real reason, and the refusal arm's three assertions
    pass vacuously, not because the scenario arranged a refusal but because the unarranged
    world already is one. Suppressing only the failing arm would leave the refusal arm's
    obligation marked discharged by a scenario that never established its `when:` — 2t's
    failure mode arriving through 2q's door. A condition under which a claim holds is part of
    the claim, so both arms — each carrying its own `when:` — withhold their assertion and
    surface as `unarranged-interaction-precondition` alike; which one would have passed by
    accident is not the property being tested for.
    """
    button = f"{_SCREEN}#submit-widget-button"
    submit_oid = "okf:new-widget:submit-new-widget:does:1"
    refuse_oid = "okf:new-widget:refuse-new-widget:does:1"
    context = _navigation_context(
        _page_obligation("okf:new-widget:submit-widget-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Add widget"]},
                          checks=[_visible("button:Add widget")]),
        _page_obligation(submit_oid, f"{_SCREEN}#submit-new-widget",
                          locators={"on": ["[submit-widget-button](#submit-widget-button)"],
                                    "trigger": ["click"],
                                    "when": ["`name` non-empty and `quantity` a non-negative "
                                             "number"],
                                    "does": ["the browser navigates to widget-list"]},
                          checks=[_located("widget-list.md#widget-table",
                                            "docs/features/globex/gui/screens/widget-list.md"
                                            "#widget-table", {"role": ["table"]})]),
        _page_obligation(refuse_oid, f"{_SCREEN}#refuse-new-widget",
                          locators={"on": ["[submit-widget-button](#submit-widget-button)"],
                                    "trigger": ["click"],
                                    "when": ["`name` empty, or `quantity` missing or negative"],
                                    "does": ["the field error spans are populated"]},
                          checks=[_located("#name-error", f"{_SCREEN}#name-error",
                                            {"selector": ["`#name-error`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "#widget-table" not in source
    assert "#name-error" not in source
    assert submit_oid not in _covers(source)
    assert refuse_oid not in _covers(source)
    assert _gap_kinds(gaps, submit_oid) == ["unarranged-interaction-precondition"]
    assert _gap_kinds(gaps, refuse_oid) == ["unarranged-interaction-precondition"]


def test_an_arranged_interaction_arm_performs_its_acts_and_compiles_its_assertion() -> None:
    """The same two arms, with the happy one declaring the acts its `when:` needs.

    `fixture:` cannot make this arm's `when:` true — no out-of-process command can type into a
    form — so the arm declares `arrange: fill(...)` instead, and the compiler performs them
    after arrival and before the trigger. That is the window in which they are preconditions of
    the interaction rather than part of it: the observation window opens at the click, so what
    it holds afterward is still evidence about this interaction alone.

    The arm's claim is then observed in the state the book named, so the assertion compiles and
    the `unarranged-interaction-precondition` gap goes. The refusal arm arranges nothing and is
    unchanged, which is the point — the gap is per arm, not per interaction.
    """
    button = f"{_SCREEN}#submit-widget-button"
    submit_oid = "okf:new-widget:submit-new-widget:does:1"
    refuse_oid = "okf:new-widget:refuse-new-widget:does:1"
    context = _navigation_context(
        _page_obligation("okf:new-widget:submit-widget-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Add widget"]},
                          checks=[_visible("button:Add widget")]),
        _page_obligation(submit_oid, f"{_SCREEN}#submit-new-widget",
                          locators={"on": ["[submit-widget-button](#submit-widget-button)"],
                                    "trigger": ["click"],
                                    "when": ["`name` non-empty and `quantity` a non-negative "
                                             "number"],
                                    "does": ["the browser navigates to widget-list"]},
                          acts=[_act("fill", f"{_SCREEN}#name-field",
                                     {"selector": ["`input[name=\"name\"]`"]},
                                     locator="#name-field", value="Widget A"),
                                _act("fill", f"{_SCREEN}#quantity-field",
                                     {"selector": ["`input[name=\"quantity\"]`"]},
                                     locator="#quantity-field", value="3")],
                          checks=[_located("#saved-banner", f"{_SCREEN}#saved-banner",
                                            {"selector": ["`#saved-banner`"]})]),
        _page_obligation(refuse_oid, f"{_SCREEN}#refuse-new-widget",
                          locators={"on": ["[submit-widget-button](#submit-widget-button)"],
                                    "trigger": ["click"],
                                    "when": ["`name` empty, or `quantity` missing or negative"],
                                    "does": ["the field error spans are populated"]},
                          checks=[_located("#name-error", f"{_SCREEN}#name-error",
                                            {"selector": ["`#name-error`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    lines = source.splitlines()
    fills = [i for i, line in enumerate(lines) if ".fill(" in line]
    clicks = [i for i, line in enumerate(lines) if "# trigger:" in line]
    assert len(fills) == 2, source
    assert lines[fills[0]].strip() == (
        'qa.by_css("input[name=\\"name\\"]").fill("Widget A")'
        "  # arrange: fill(locator='#name-field', value='Widget A')")
    assert lines[fills[1]].strip() == (
        'qa.by_css("input[name=\\"quantity\\"]").fill("3")'
        "  # arrange: fill(locator='#quantity-field', value='3')")
    # Both fills precede every trigger click, and the arranging arm's own click is the first.
    assert fills[1] < clicks[0]
    assert "unarranged-interaction-precondition" not in _gap_kinds(gaps, submit_oid)
    assert submit_oid in _covers(source)
    assert "#saved-banner" in source
    # The condition itself is the precondition, named in the book's own words.
    assert "`name` non-empty and `quantity` a non-negative number" in source
    # The arm that arranges nothing is untouched.
    assert _gap_kinds(gaps, refuse_oid) == ["unarranged-interaction-precondition"]
    assert refuse_oid not in _covers(source)


def test_an_act_whose_subject_has_no_locator_withholds_the_whole_arrangement() -> None:
    """A `when:` is arranged by the whole sequence the book wrote, so half of it is not a
    weaker arrangement — it is a state no arm declares, neither the documented precondition
    nor the page's accidental default. An act whose subject the book gives no locator for
    withholds every act beside it, and the arm keeps the gap that says so, which is true.
    """
    button = f"{_SCREEN}#submit-widget-button"
    submit_oid = "okf:new-widget:submit-new-widget:does:1"
    context = _navigation_context(
        _page_obligation("okf:new-widget:submit-widget-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Add widget"]},
                          checks=[_visible("button:Add widget")]),
        _page_obligation(submit_oid, f"{_SCREEN}#submit-new-widget",
                          locators={"on": ["[submit-widget-button](#submit-widget-button)"],
                                    "trigger": ["click"],
                                    "when": ["`name` non-empty and `quantity` a non-negative "
                                             "number"],
                                    "does": ["the browser navigates to widget-list"]},
                          acts=[_act("fill", f"{_SCREEN}#name-field",
                                     {"selector": ["`input[name=\"name\"]`"]},
                                     locator="#name-field", value="Widget A"),
                                _act("fill", f"{_SCREEN}#quantity-field", {},
                                     locator="#quantity-field", value="3")],
                          checks=[_located("#saved-banner", f"{_SCREEN}#saved-banner",
                                            {"selector": ["`#saved-banner`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert ".fill(" not in source
    assert _gap_kinds(gaps, submit_oid) == ["unarranged-interaction-precondition"]
    assert submit_oid not in _covers(source)


def test_an_arms_acts_reach_the_builder_from_the_bullet_that_declares_no_check() -> None:
    """The shape a real packet produces, and the one the two tests above do not write.

    `arrange:` binds to the normative bullet above it, and in every book that bullet is
    `when:` — a condition, not an observation, so the obligation it mints declares no check
    and is filed as book debt long before the page builders see it. An arrangement is a
    property of the arm it arranges, not of whichever sibling bullet happens to carry a
    check, so the acts have to reach the builder from the check-less obligation or they
    reach nowhere: the arm compiles its assertion against an unfilled form.
    """
    button = f"{_SCREEN}#submit-widget-button"
    interaction = f"{_SCREEN}#submit-new-widget"
    when_oid = "okf:new-widget:submit-new-widget:when:1"
    does_oid = "okf:new-widget:submit-new-widget:does:1"
    locators = {"on": ["[submit-widget-button](#submit-widget-button)"],
                "trigger": ["click"],
                "when": ["`name` non-empty and `quantity` a non-negative number"],
                "does": ["the browser navigates to widget-list"]}
    acts = [_act("fill", f"{_SCREEN}#name-field",
                 {"selector": ["`input[name=\"name\"]`"]},
                 locator="#name-field", value="Widget A"),
            _act("fill", f"{_SCREEN}#quantity-field",
                 {"selector": ["`input[name=\"quantity\"]`"]},
                 locator="#quantity-field", value="3")]
    context = _navigation_context(
        _page_obligation("okf:new-widget:submit-widget-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Add widget"]},
                          checks=[_visible("button:Add widget")]),
        _page_obligation(when_oid, interaction, locators=locators, checks=[], acts=acts),
        _page_obligation(does_oid, interaction, locators=locators, acts=acts,
                          checks=[_located("#saved-banner", f"{_SCREEN}#saved-banner",
                                            {"selector": ["`#saved-banner`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    lines = source.splitlines()
    fills = [i for i, line in enumerate(lines) if ".fill(" in line]
    clicks = [i for i, line in enumerate(lines) if "# trigger:" in line]
    assert len(fills) == 2, source
    assert fills[1] < clicks[0]
    assert "unarranged-interaction-precondition" not in _gap_kinds(gaps, does_oid)
    assert does_oid in _covers(source)


def test_a_journey_step_performs_its_own_acts_before_it_triggers_it() -> None:
    """The performer of a step is the only actor that can establish state on the surface it
    performs on, and a journey performs this step itself — so the step's `arrange:` bullets
    are performed here, in the same window `_interaction_scenario` uses when it compiles the
    same interaction alone. A journey is a separate builder, so threading the acts into the
    interaction scenario does not reach it, and a journey through a form would otherwise
    click submit on an empty one and land on the refusal the empty form earns.
    """
    oid = f"okf:{_FLOW}:end-state"
    open_thing = f"{_SCREEN}#open-thing"
    save_thing = f"{_SCREEN}#save-thing"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="policy",
            steps=[_step(open_thing, "interaction", "policy"),
                   _step(save_thing, "interaction", "policy")],
            checks=[_located_visible(f"{_SCREEN}#things-table",
                                     {"selector": ["#things-table"]})],
        ),
        _page_obligation(f"{open_thing}:carrier", open_thing,
                         locators={"on": ["[open-link](#open-link)"], "trigger": ["click"]},
                         checks=[]) | {"required": False},
        _page_obligation(f"{save_thing}:carrier", save_thing,
                         locators={"on": ["[save-button](#save-button)"], "trigger": ["click"],
                                   "when": ["`name` is non-empty"]},
                         checks=[],
                         acts=[_act("fill", f"{_SCREEN}#name-field",
                                    {"selector": ["#name-field"]},
                                    locator="#name-field", value="Widget A")],
                         ) | {"required": False},
        _page_obligation(f"{_SCREEN}#open-link:carrier", f"{_SCREEN}#open-link",
                         locators={"selector": ["#open-link"]}, checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#save-button:carrier", f"{_SCREEN}#save-button",
                         locators={"selector": ["#save-button"]}, checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#name-field:carrier", f"{_SCREEN}#name-field",
                         locators={"selector": ["#name-field"]}, checks=[]) | {"required": False},
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source), [g for g in gaps if g.obligation_id == oid]
    journey = source.split("@scenario(")[-1]
    first = journey.index('"#open-link"')
    fill = journey.index('.fill("Widget A")')
    second = journey.index('"#save-button"')
    # The step that arranges performs its acts after arriving through the step before it, and
    # before its own trigger — the state the click needs exists exactly when the click happens.
    assert first < fill < second


def test_a_wrapped_book_bullet_still_compiles_to_valid_python() -> None:
    """A `does:`/`trigger:` value that wrapped across lines in the book source is still just one
    string by the time `qa context` hands it here — nothing marks where the line broke. Embedding
    that embedded newline raw, as a `#`-comment or inside a `\"\"\"`-docstring, ends the comment or
    (for a stray `\"\"\"`-free case) the line mid-token and turns the wrapped remainder into code;
    `py_compile`-worthy output is the property under test, not the comment text.
    """
    button = f"{_SCREEN}#create-policy-button"
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = "okf:new-policy:submit-new-policy:does:1"
    wrapped_trigger = "submit the new policy form\nwith every required field filled in"
    wrapped_does = "adds a policy and\nnavigates to its detail screen"
    context = _navigation_context(
        _page_obligation("okf:new-policy:create-policy-button:visible:1", button,
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": [wrapped_trigger],
                                    "does": [wrapped_does]},
                          checks=[_located("#policy-table", f"{_SCREEN}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
    )
    source, _gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    interactions = [s for s in source.split("@scenario(")[1:] if "submit_new_policy(" in s]
    assert len(interactions) == 1
    assert "with every required field filled in" in interactions[0]
    assert "navigates to its detail screen" in interactions[0]


def _verify_calls(source: str) -> list[tuple[str, dict]]:
    """Every `qa.verify(name, operand, **args)` the plan emits, as `checks.bind` reads it."""
    calls: list[tuple[str, dict]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "verify" or not node.args:
            continue
        name = node.args[0]
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            continue
        args = {}
        for keyword in node.keywords:
            if keyword.arg is None or keyword.arg == "covers":
                continue
            try:
                args[keyword.arg] = ast.literal_eval(keyword.value)
            except ValueError:
                args[keyword.arg] = "<computed>"
        calls.append((name.value, args))
    return calls


def test_every_emitted_assertion_is_legal_against_the_checks_own_signature() -> None:
    """A compiled call the check vocabulary refuses is a plan `ostler qa validate` rejects.

    The regression this pins was legal Python and illegal in the artifact: the compiler had
    resolved `locator=` into an operand and then dropped the argument, so every emitted
    `visible` call was missing a parameter its own `CheckSpec` marks required — and the
    declared-versus-invoked matcher, which compares the book's call to the plan's, could no
    longer see that the plan had made the observation at all. Neither the suite nor the
    interpreter noticed; only a real run of `qa validate` did.
    """
    oid = "okf:new-policy:submit:does:1"
    context = _navigation_context(
        _page_obligation(
            oid, f"{_SCREEN}#new-policy-form",
            locators={"role": ["form"], "name": ["New policy"]},
            checks=[_located("#name-error", f"{_SCREEN}#name-error",
                             {"selector": ["`#name-error`"]})],
        ),
        navigation=_arrival_navigation(),
    )
    source, _ = compile_plan_gaps(context, story="demo-story")
    emitted = _verify_calls(source)
    assert emitted
    for name, args in emitted:
        bound = checks.bind(name, args)
        assert not isinstance(bound, str), f"qa.verify({name!r}, ...) is illegal: {bound}"


def _vetted(source: str) -> list[str]:
    """Every screen document the plan photographs, in the order it photographs them."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "vet" or not node.args:
            continue
        screen = node.args[0]
        if isinstance(screen, ast.Constant) and isinstance(screen.value, str):
            found.append(screen.value)
    return found


def test_an_arrival_photographs_the_screen_it_arrived_at() -> None:
    """Presence is what a role locator proves; placement is what it cannot.

    `ostler qa validate` refuses a UI scenario that vets no screen, so a plan compiled
    without one is a plan that cannot run — and the refusal exists because every assertion
    in the run that motivated it was true of a page crushed against one margin.
    """
    oid = "okf:new-policy:form:role:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#new-policy-form",
                          locators={"role": ["form"], "name": ["New policy"]},
                          checks=[_visible("form:New policy")]),
        navigation=_arrival_navigation(),
    )
    source, _ = compile_plan_gaps(context, story="demo-story")
    assert _vetted(source) == [_SCREEN]


def test_an_interaction_photographs_the_screen_its_checks_name() -> None:
    """The state an interaction's claims are about is the one the trigger produced.

    `does:` is not resolved to a target screen, so the documents the checks themselves name
    are the only evidence of where the run ended up — vetting the screen the claim was
    *authored* on would file the photograph under the wrong book.
    """
    interaction = f"{_SCREEN}#submit-new-policy"
    interaction_oid = f"okf:{interaction}:does:1"
    elsewhere = "docs/features/demo/gui/screens/policy-list.md"
    context = _navigation_context(
        _page_obligation("okf:new-policy:button:role:1", f"{_SCREEN}#create-policy-button",
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(interaction_oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the new policy form"],
                                    "does": ["adds a policy and shows it"]},
                          checks=[_located("#policy-table", f"{elsewhere}#policy-table",
                                           {"role": ["table"], "name": ["Policies on file"]})]),
        navigation=_arrival_navigation(),
        # `elsewhere` is reached by the trigger rather than by a nav hop, so it is absent from
        # the navigation map and its `route:` has to be stated here for the vet to be compiled.
        screen_routes={_SCREEN: "/new-policy", elsewhere: "/policies"},
    )
    source, _ = compile_plan_gaps(context, story="demo-story")
    interactions = [s for s in source.split("@scenario(")[1:] if "submit_new_policy(" in s]
    assert len(interactions) == 1
    # Read off the fragment, not its tree: a scenario split from its decorator is not a
    # parseable module, and what is being pinned is which screen this function photographs.
    assert re.findall(r"qa\.vet\(\"(.+?)\"\)", interactions[0]) == [elsewhere]
    # …and the click comes first: a photograph taken before the trigger is of the wrong state.
    assert interactions[0].index(".click()") < interactions[0].index("qa.vet(")


def test_an_obligation_half_of_whose_checks_compile_is_claimed_by_nobody() -> None:
    """A claim whose refusal is visible on screen *and* leaves a stored count alone is one
    claim, and `unchanged` observes a `subject` no browser can see.

    The failure this pins is a green filed against an app that renders the error span and
    moves the count: the scenario reported the span, the count was gapped as unobservable,
    and the obligation was claimed anyway on the strength of the row that compiled. `ostler
    qa validate` sees it from the other side — the declared call no assertion invokes,
    against an id the plan says it covers.
    """
    interaction = f"{_SCREEN}#submit-new-policy"
    oid = f"okf:{interaction}:does:2"
    context = _navigation_context(
        _page_obligation("okf:new-policy:button:role:1", f"{_SCREEN}#create-policy-button",
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the form with no name"],
                                    "does": ["refuses and says why"]},
                          checks=[_located("#name-error", f"{_SCREEN}#name-error",
                                           {"selector": ["`#name-error`"]}),
                                  {"call": "the count", "name": "unchanged",
                                   "args": {"of": "policy.count"}}]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    assert "#name-error" not in source
    assert "uncompilable-claim" in _gap_kinds(gaps, oid)


# --- Per-surface `base_url` (Phase 2h) ----------------------------------------------------------
#
# `ostler qa compile-plan` used to grow every target's `base_url` from one CLI flag. A book with
# two services on two ports made that flag a lie for whichever surface didn't get it — these pin
# the replacement: each surface's own `entry-url:`, read off `navigation[surface]["entryUrl"]`
# (`reach.entry_origin`, by way of `qa.context._navigation`), with `--base-url` only as the
# fallback for a surface stating none, and `undeclared-entry-url` the gap when neither exists.
# The two below call the *real*, unwrapped `compile_plan`/`compile_plan_gaps` — the module-level
# wrapper above exists so the rest of this file doesn't have to care about entry-url resolution;
# these two are the tests that do.


def test_a_two_surface_book_compiles_two_different_base_urls() -> None:
    """The `api` target's address comes from the http obligation's own surface, and the `web`
    target's from the page obligation's — a book with two services on two ports must not see
    either one's address bleed onto the other's target line."""
    api_oid = "okf:docs/features/acme/api.md#post-things:does:1"
    page_oid = "okf:new-policy:button:role:1"
    context = _navigation_context(
        _obligation(
            api_oid,
            surface="api-service",
            locators={"route": ["GET /api/things"]},
            checksDeclared=[
                {"call": "the response", "name": "http_status", "args": {"code": 200, "path": "/api/things"}},
            ],
            fixturesDeclared=[{"name": "seeded-thing", "args": [], "provides": "a thing exists"}],
        ),
        _page_obligation(page_oid, f"{_SCREEN}#create-policy-button", surface="web-app",
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        navigation={
            "api-service": {"driver": "http", "entryUrl": "http://localhost:18101"},
            "web-app": {**_arrival_navigation(surface="web-app")["web-app"],
                        "entryUrl": "http://localhost:18102"},
        },
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert gaps == []
    assert 'api_service_api = target("api_service_api", driver="python", ' \
        'base_url="http://localhost:18101")' in source
    assert 'web_app_web = target("web_app_web", driver="playwright", ' \
        'base_url="http://localhost:18102")' in source


def test_two_surfaces_sharing_one_driver_kind_each_keep_their_own_address() -> None:
    """Two http surfaces — not one http surface and one page surface — land in the *same*
    `http_owed` partition (both are `_is_page_obligation` false), which is exactly the case
    the old `known[0]` alphabetic-first fallback used to collapse onto one address. Each
    surface's own scenario must reference its own target, not a neighbour's."""
    alpha_oid = "okf:docs/features/acme/alpha.md#post-things:does:1"
    zulu_oid = "okf:docs/features/acme/zulu.md#post-things:does:1"
    context = _navigation_context(
        _obligation(
            alpha_oid,
            source="docs/features/acme/alpha.md",
            surface="alpha-service",
            locators={"route": ["GET /api/things"]},
            checksDeclared=[
                {"call": "the response", "name": "http_status", "args": {"code": 200, "path": "/api/things"}},
            ],
            fixturesDeclared=[{"name": "seeded-alpha-thing", "args": [], "provides": "a thing exists"}],
        ),
        _obligation(
            zulu_oid,
            source="docs/features/acme/zulu.md",
            surface="zulu-service",
            locators={"route": ["GET /api/things"]},
            checksDeclared=[
                {"call": "the response", "name": "http_status", "args": {"code": 200, "path": "/api/things"}},
            ],
            fixturesDeclared=[{"name": "seeded-zulu-thing", "args": [], "provides": "a thing exists"}],
        ),
        navigation={
            "alpha-service": {"driver": "http", "entryUrl": "http://localhost:18201"},
            "zulu-service": {"driver": "http", "entryUrl": "http://localhost:18202"},
        },
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert gaps == []
    assert 'alpha_service_api = target("alpha_service_api", driver="python", ' \
        'base_url="http://localhost:18201")' in source
    assert 'zulu_service_api = target("zulu_service_api", driver="python", ' \
        'base_url="http://localhost:18202")' in source
    # Each surface's own scenario references its own target, not the other surface's.
    assert "    target=alpha_service_api,\n" in source
    assert "    target=zulu_service_api,\n" in source


def test_a_surface_with_no_entry_url_and_no_fallback_gaps_instead_of_guessing() -> None:
    """No `--base-url` and no book-stated `entry-url:` on this obligation's surface: the compiler
    drops it as `undeclared-entry-url` rather than compiling it against an address nobody wrote
    down — the failure mode Phase 2h exists to replace (one CLI default applied to every surface,
    right or wrong)."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            surface="api-service",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
    )
    # `driver:` (D1's dispatch table) and `entry-url:` are two separate facts a runbook states —
    # this test is about the second one being absent, so the surface still states a driver
    # (otherwise the dispatch table itself gaps the obligation first, as `uncompilable-claim`,
    # before ever reaching the entry-url check this test targets).
    context["navigation"] = {"api-service": {"driver": "http"}}
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    assert "qa.http.post" not in source
    assert _gap_kinds(gaps, oid) == ["undeclared-entry-url"]
    # The obligation was dropped before target emission, so nothing compiles a target for it.
    assert "target(" not in source


def test_a_checkless_obligation_on_a_surface_with_no_entry_url_is_book_debt_not_undeclared_entry_url() -> None:
    """A bucket that names a performer cannot also carry the things nothing performs: a
    check-less obligation has no claim for any driver to dispatch, so an unrelated surface with
    no `entry-url:` must not decide its gap kind. It is `no-verify-declared` regardless of
    whether the surface's address ever resolved."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    context = _context(
        _obligation(oid, surface="api-service"),
    )
    context["navigation"] = {"api-service": {"driver": "http"}}
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    assert _gap_kinds(gaps, oid) == ["no-verify-declared"]
    assert "undeclared-entry-url" not in {g.kind for g in gaps}
    assert "# Book debt." in source
    assert f"#   {oid}" in source


def _conflicting_origin_context(oid: str) -> dict:
    """A surface whose sources disagreed about its address: `qa context` caught
    `reach.ConflictingEntryOrigin`, left `entryUrl` unset and recorded why."""
    context = _context(
        _obligation(
            oid,
            surface="api-service",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
    )
    context["navigation"] = {"api-service": {
        "driver": "http",
        "entryUrlError": "surface 'api-service' has conflicting entry origins: "
                         "docs/features/acme/api.md says http://localhost:18101; "
                         "docs/features/acme/ops/run.md says http://localhost:18999",
    }}
    return context


def test_a_surface_whose_sources_disagree_gaps_the_conflict_not_an_absence() -> None:
    """Two stated addresses is a different defect from none stated, and it takes a different
    remedy — so it may not be reported as `undeclared-entry-url`, whose message would send the
    author looking for a bullet that is already written twice."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    source, gaps = _compile_plan_gaps(_conflicting_origin_context(oid), story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["conflicting-entry-origin"]
    assert "18101" in gaps[0].detail
    assert "18999" in gaps[0].detail
    assert "target(" not in source


def test_a_base_url_does_not_adjudicate_between_two_addresses_the_book_states() -> None:
    """`--base-url` answers a book that states no address. A book that states two has already
    answered, twice, and an operator flag is not an adjudication between them — falling back
    here would compile a plan against a third address nobody wrote down at all."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    source, gaps = _compile_plan_gaps(_conflicting_origin_context(oid), story="demo-story",
                                      base_url="http://localhost:8000")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["conflicting-entry-origin"]
    assert "8000" not in source


def _conflicting_driver_context(oid: str) -> dict:
    """A surface whose runbooks disagreed about what drives it: `qa context` caught
    `reach.ConflictingSurfaceDriver`, left `driver` unset and recorded why."""
    context = _context(
        _obligation(
            oid,
            surface="api-service",
            nodeType="endpoint",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
    )
    context["navigation"] = {"api-service": {
        "driver": None,
        "driverError": "surface 'api-service' has conflicting drivers: "
                       "docs/features/acme/ops/run.md says http; "
                       "docs/features/acme/ops/qa.md says playwright",
    }}
    return context


def test_a_surface_whose_runbooks_disagree_gaps_the_conflict_not_an_absence() -> None:
    """Two stated drivers is a different defect from none stated, and it takes a different remedy
    — write a `driver:` versus settle which of two already written is right — so it may not be
    reported as `uncompilable-claim`, whose message asserts the book states no `driver:` at all
    and sends the author looking for a bullet that is there twice."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    source, gaps = compile_plan_gaps(_conflicting_driver_context(oid), story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["conflicting-surface-driver"]
    assert "run.md" in gaps[0].detail and "qa.md" in gaps[0].detail


def _undeclared_walkthrough_context(oid: str) -> dict:
    """A surface covered by several runbooks with different drivers, none marked
    `walkthrough: true`: `qa context` caught `reach.UndeclaredWalkthroughRunbook`, left `driver`
    unset and recorded why, plus which kind of disagreement it was."""
    context = _context(
        _obligation(
            oid,
            surface="api-service",
            nodeType="endpoint",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
    )
    context["navigation"] = {"api-service": {
        "driver": None,
        "driverError": "surface 'api-service' is covered by several runbooks and none is marked "
                       "`walkthrough: true`: docs/features/acme/ops/run.md drives it with http; "
                       "docs/features/acme/ops/qa.md drives it with playwright",
        "driverErrorKind": "undeclared-walkthrough-runbook",
    }}
    return context


def test_a_surface_with_no_walkthrough_marked_gaps_the_ambiguity_not_a_conflict() -> None:
    """`conflicting-surface-driver` and `undeclared-walkthrough-runbook` are different defects
    with different remedies — settle a disagreement between two marked runbooks, versus mark
    the one that exercises the surface — so this shape, which `driverErrorKind` distinguishes
    from `_conflicting_driver_context` above, may not be reported under the other kind, nor as
    `uncompilable-claim`."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    source, gaps = compile_plan_gaps(_undeclared_walkthrough_context(oid), story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["undeclared-walkthrough-runbook"]
    assert "run.md" in gaps[0].detail and "qa.md" in gaps[0].detail
    assert "walkthrough" in gaps[0].detail


def test_a_surface_stating_no_driver_at_all_still_gaps_the_absence() -> None:
    """Non-vacuity for the test above: the same context with the conflict record removed — the
    only difference — keeps the kind it always had, so a `conflicting-surface-driver` verdict
    there is a verdict on the disagreement and not on the missing driver both books share."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    context = _conflicting_driver_context(oid)
    del context["navigation"]["api-service"]["driverError"]
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]
    assert "states no `driver:`" in gaps[0].detail


def test_a_selector_the_census_cannot_read_still_compiles_one_whole_scenario() -> None:
    """Phase 3p': a compile-time gap is a statement about the plan being compiled, and vet's
    render census is a different observer.

    `[data-state="booked"]` is a selector `placement.is_addressable` rejects, so `ostler vet`'s
    screen census can never confirm the component present. That is a real finding — and it is
    doctor's `unaddressable-selector` check, made against the book. It is *not* a gap, because
    a gap says "this obligation went unobserved by the compiled plan", and this obligation is
    observed: `qa.by_css` compiles the selector fine and the assertion runs against the live
    page. Emitting both put the obligation in `covers=[...]` and in the unobserved gap list at
    once, which is exactly what `compile_plan`'s own mirror assert forbids."""
    oid = "okf:docs/features/policy/gui/screens/policy-list.md#seat-grid:verify:1"
    context = _navigation_context(
        _page_obligation(
            oid, "seat-grid",
            locators={"selector": ['[data-state="booked"]']},
            checks=[_visible('[data-state="booked"]')],
        ),
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    # The selector reaches the emitted check verbatim: it is compiled, not dropped.
    assert r'locator="[data-state=\"booked\"]"' in source


# --- HTTP exchanges a page scenario made (Phase 2l) ---------------------------------------------
#
# `DriverSpec.PLAYWRIGHT` has always declared `response` and `body`, and the browser harness has
# always recorded every response the page fetched. What was missing between them was an
# *arrangement*: a page scenario has as many responses as the page chose to request, so the
# operand of an HTTP claim is a selection, and a selection needs a selector and a bound. The
# selector is `http_status(path=…)` — the one bullet in the vocabulary carrying a route — read
# once per obligation, because an obligation is one claim. The bound is `qa.window()`, emitted
# immediately before the scenario's action, because a response recorded before the click is not
# an observation of the click.


def _scenarios(source: str) -> list[str]:
    return source.split("@scenario(")[1:]


def _http_status(code: int, path: str) -> dict[str, object]:
    return {"call": f'http_status(code={code}, path="{path}")', "name": "http_status",
            "args": {"code": code, "path": path}}


def test_a_page_claim_about_the_response_its_click_provoked_compiles_whole() -> None:
    """The globex shape: submitting the form is refused, the error span appears, and the
    page's own POST answered 400. All three rows are one claim and all three compile — the
    two HTTP rows against the exchange the book named, the page row against the DOM."""
    interaction = f"{_SCREEN}#submit-new-policy"
    oid = f"okf:{interaction}:does:2"
    context = _navigation_context(
        _page_obligation("okf:new-policy:button:role:1", f"{_SCREEN}#create-policy-button",
                          locators={"role": ["button"], "name": ["Create policy"]},
                          checks=[_visible("button:Create policy")]),
        _page_obligation(oid, interaction,
                          locators={"on": ["[create-policy-button](#create-policy-button)"],
                                    "trigger": ["submit the form with no name"],
                                    "does": ["refuses and says why"]},
                          checks=[_located("#name-error", f"{_SCREEN}#name-error",
                                           {"selector": ["`#name-error`"]}),
                                  _http_status(400, "/api/policies"),
                                  {"call": "the reason", "name": "json_path",
                                   "args": {"path": "detail", "equals": "name is required"}}]),
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source)
    # (`unresolved-precondition` is this fixture's own, and orthogonal: it is about reaching
    # the screen, not about what the claim observes once there.)
    assert "uncompilable-claim" not in _gap_kinds(gaps, oid)
    # The response check is handed the selected exchange; the body check, its parsed payload.
    assert 'qa.verify("http_status", exchanges.response_for("/api/policies")' in source
    assert 'qa.verify("json_path", exchanges.response_for("/api/policies").json()' in source
    # …and the window opens before the action, or it would span the arrival's own requests too.
    interactions = [s for s in _scenarios(source) if ".click()" in s]
    assert len(interactions) == 1
    assert interactions[0].index("qa.window()") < interactions[0].index(".click()")


def test_an_arrival_claim_about_a_response_opens_its_window_before_the_navigation() -> None:
    """An arrival scenario's action is `qa.goto`, so the same rule puts the window first —
    a response recorded before the page was asked for is not an observation of the arrival."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  _http_status(200, "/api/policies")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    [arrival] = [s for s in _scenarios(source) if "qa.goto(" in s]
    assert arrival.index("qa.window()") < arrival.index("qa.goto(")


def test_an_obligation_naming_two_routes_is_two_claims_and_emits_nothing_executable() -> None:
    """Undetermined ⇒ do not emit executable code. One obligation carrying `http_status` on
    two different routes has not said which exchange its body check is about, and the
    compiler has no basis to pick — so it gaps rather than defaulting to either."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  _http_status(200, "/api/policies"),
                                  _http_status(200, "/api/agents")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    assert "uncompilable-claim" in _gap_kinds(gaps, oid)
    assert "response_for(" not in source
    assert "qa.window()" not in source


def test_a_page_scenario_with_no_http_claim_binds_no_window() -> None:
    """The window is emitted because a row needs it, not because the scenario is a page one —
    a plan that reads no exchange should not carry a name nothing reads."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
    )
    source, _gaps = _compile_plan_gaps(context, story="demo-story")
    assert "qa.window()" not in source


def test_a_node_nobody_performs_is_observed_by_the_driver_of_its_own_surface() -> None:
    """A `flow` orders steps that are performed; a `component` and a `screen` are places a claim
    is true. None of the three is a step, so there is no action to cross with a driver — only a
    check, run by whatever drives the surface the claim's subject lives on. That makes them a
    single row (`_OBSERVE_ROW`), not a table: every driver can observe, which is why an `http`
    driver lands a target here while `_DISPATCH_TABLE` deliberately leaves `interaction`x`http`
    empty — it cannot *perform* an interaction, but it can assert a status on a journey that
    ends at an endpoint."""
    for node_type in ("flow", "component", "screen"):
        assert _dispatch_target(node_type, "web") == ("playwright", "", "")
        assert _dispatch_target(node_type, "http") == ("http", "", "")
        assert _dispatch_target(node_type, "cli") == ("cli", "", "")
        # `maestro` is a real cell this compiler does not build: a named target plus a detail,
        # never "no row for this type."
        target, detail, kind = _dispatch_target(node_type, "mobile")
        assert target == "maestro" and "builds no maestro path yet" in detail
        assert kind == "needs-target-backend"
    # The performed half is unchanged — the blank cell is still blank.
    target, detail, kind = _dispatch_target("interaction", "http")
    assert target is None and "names no target" in detail
    assert kind == "uncompilable-claim"


def _located_visible(node: str, locators: dict) -> dict:
    """A `visible(locator=…)` whose reference the packet already resolved to *node*."""
    row = _visible(node)
    row["locates"] = {"locator": {"node": node, "locators": locators}}
    return row


def _step(ref: str, node_type: str, surface: str) -> dict:
    return {"ref": ref, "href": ref.split("#")[-1], "nodeType": node_type, "surface": surface}


def _flow_obligation(oid: str, *, source: str, surface: str, steps: list[dict],
                     checks: list[dict], fixtures: list[dict] | None = None) -> dict:
    # Arranged by default, because every test below is about the *walk* and a journey that
    # arranges nothing compiles to no scenario at all (`unarranged-journey`). Pass
    # `fixtures=[]` to write the unarranged case on purpose.
    row = {
        "id": oid,
        "node": f"{source}#flow",
        "nodeType": "flow",
        "source": source,
        "surface": surface,
        "requirement": "the journey leaves the world it promises",
        "required": True,
        "locators": {},
        "checksDeclared": checks,
        "steps": steps,
    }
    declared = [{"name": "seeded-ledger", "args": [], "provides": "a ledger"}] \
        if fixtures is None else fixtures
    if declared:
        row["fixturesDeclared"] = declared
    return row


def _step_node(node: str, locators: dict) -> dict:
    """A step's own node, carried by the packet for its locators and owing nothing itself."""
    return {"id": f"{node}:carrier", "node": node, "nodeType": "endpoint",
            "source": node.split("#")[0], "surface": "api", "required": False,
            "locators": locators, "checksDeclared": []}


_API = "docs/features/demo/http/api.md"
_FLOW = "docs/features/demo/flows/add-a-thing.md"


def _api_navigation(surface: str = "api") -> dict:
    return {surface: {"start": _API, "surface": surface, "driver": "http",
                      "entryUrl": _BASE_URL, "counts": {}, "routes": {}, "unreachable": [],
                      "undeclared": []}}


def test_a_flow_that_names_no_steps_has_no_walk_to_compile() -> None:
    """A flow's claim is about what its `steps:` did, so a flow that names none states a claim
    about a journey nobody wrote down. It gaps rather than being handed to the place-scoped
    builders, which would address the end-state at the node it names and assert it on arrival —
    a check that passes in a world where the journey did not happen."""
    oid = "okf:docs/features/policy/flows/file-a-policy.md:end-state"
    context = _navigation_context(
        _obligation(oid, nodeType="flow", surface="policy",
                    source="docs/features/policy/flows/file-a-policy.md",
                    locators={}, checksDeclared=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "`steps:`" in gap.detail and "names no steps to walk" in gap.detail
    # Nothing executable, and in particular no arrival scenario standing in for the journey.
    assert oid not in _covers(source)
    assert "qa.goto(" not in source


def test_a_journeys_claim_is_observed_where_its_last_step_left_the_world() -> None:
    """The steps are performed in the order the book wrote them, and the flow's own `verify:`
    is asserted against the *last* step's response — the only world this scenario actually
    produced. The steps' own claims are not restated here; they are compiled where they live."""
    oid = f"okf:{_FLOW}:end-state"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api"),
                   _step(f"{_API}#get-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                                   "path": "/api/things"}}],
        ),
        # DELETE, not POST: a journey step whose route needs a request body and arranges none
        # gets withheld entirely (`unarranged-request-body`, compile.py's `_http_journey`) — see
        # `test_a_journey_step_sends_the_body_its_node_arranges` for the arranged case. This test
        # is about step ordering across two distinct methods, not about bodies, so both steps use
        # body-exempt verbs.
        _step_node(f"{_API}#post-things", {"route": ["DELETE /api/things"]}),
        _step_node(f"{_API}#get-things", {"route": ["GET /api/things"]}),
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source)
    post = source.index('observed_1 = qa.http.delete("/api/things"')
    get = source.index('observed_2 = qa.http.get("/api/things")')
    assert post < get
    # Asserted on the response the walk ended on, not on the one the first step produced.
    assert 'qa.verify("http_status", observed_2' in source
    assert 'qa.verify("http_status", observed_1' not in source
    assert _gap_kinds(gaps, oid) == []


def test_a_journey_step_sends_the_body_its_node_arranges() -> None:
    """Node-level, unlike the arm-level read in `_scenario_body`'s own tests: a journey step
    names a node, not an arm, so `_http_journey` reads `acts_by_node` the same way a step's
    `fill:` acts already are — merged across every obligation sharing that node."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    post_node["actsDeclared"] = [_body_act("name", "Widget A"), _body_act("quantity", 3)]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        post_node,
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    assert 'json_body={"name": "Widget A", "quantity": 3}' in source


def test_a_journey_step_with_a_contradictory_body_is_unarranged() -> None:
    """Phase 1's limitation, named explicitly: two arms of the same node stating different
    values for the same field merge to a contradiction, not a body any request could carry, so
    the step withholds the whole request exactly as a half-performable one already does."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    post_node["actsDeclared"] = [_body_act("name", "Widget A")]
    other_arm = _step_node(f"{_API}#post-things", {})
    other_arm["id"] = f"{_API}#post-things:carrier-2"
    other_arm["actsDeclared"] = [_body_act("name", "Widget B")]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        post_node,
        other_arm,
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["unarranged-request-body"]
    assert oid not in _covers(source)


def test_a_journey_step_ignores_its_nodes_refusal_arm_arrangement() -> None:
    """A journey's steps causally chain, so it can only ever be walking the arm that leaves
    something for the next step to read back — never the refusal arm (`errors:`/`error:`,
    `registry.refusal_keys`). The refusal arm's own `arrange: body(...)` states a contradictory
    value on purpose: if it reached the merge, `_http_body` would refuse the contradiction and
    this step would gap `unarranged-request-body` instead of compiling."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    post_node["actsDeclared"] = [_body_act("name", "Widget A"), _body_act("quantity", 3)]
    refusal_arm = _step_node(f"{_API}#post-things", {})
    refusal_arm["id"] = f"{_API}#post-things:carrier-2"
    refusal_arm["kind"] = "errors"
    refusal_arm["actsDeclared"] = [_body_act("name", "Widget B")]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        post_node,
        refusal_arm,
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    assert 'json_body={"name": "Widget A", "quantity": 3}' in source


def test_a_journey_step_whose_node_only_declares_a_refusal_arm_is_unarranged() -> None:
    """A node whose only declared arm is the refusal arm merges to no acts at all once that arm
    is excluded — not "nothing declared" the way a step that genuinely needs no body would read,
    so it withholds the request and gaps exactly as an unbuildable body already does, rather than
    silently sending `json_body={}`."""
    oid = f"okf:{_FLOW}:end-state"
    refusal_only = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    refusal_only["kind"] = "errors"
    refusal_only["actsDeclared"] = [_body_act("name", "Widget B")]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        refusal_only,
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["unarranged-request-body"]
    assert oid not in _covers(source)


def test_a_journey_step_with_an_unrecognized_method_is_an_invalid_http_method() -> None:
    """The node-level check mirrors `_scenario_body`'s: a step whose node states a `method:`
    that does not parse as an HTTP verb is undetermined, so `_http_journey` withholds the whole
    journey rather than falling through to `unarranged-request-body`."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"method": ["FROB"], "path": ["/api/things"]})
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        post_node,
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["invalid-http-method"]
    assert oid not in _covers(source)


def test_a_check_naming_another_steps_path_is_not_about_this_journeys_end() -> None:
    """A journey's claim is about the world its last step left. A check naming some other route
    is a claim about a request this journey did not end on — pointing the driver at the response
    it does hold would answer a question nobody asked, so it gaps instead."""
    oid = f"okf:{_FLOW}:end-state"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api"),
                   _step(f"{_API}#get-health", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        # DELETE, not POST: see the comment on the sibling test above — this one is about a
        # check naming a route other than the journey's last step, not about bodies.
        _step_node(f"{_API}#post-things", {"route": ["DELETE /api/things"]}),
        _step_node(f"{_API}#get-health", {"route": ["GET /healthz"]}),
        navigation=_api_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    assert "uncompilable-claim" in _gap_kinds(gaps, oid)
    [gap] = [g for g in gaps if g.obligation_id == oid and g.kind == "uncompilable-claim"]
    assert "/healthz" in gap.detail and "its last step left" in gap.detail


def test_a_journey_across_two_targets_has_no_scenario_shape_to_fit_into() -> None:
    """A target is the pairing of a driver with a service, and `@scenario(target=...)` binds
    exactly one. The reason says that — a fact about the harness — rather than claiming no
    builder exists, because after this row one does. The *kind* says it too: a journey the
    harness cannot shape is not a claim an author can go and fix, so it does not share
    `uncompilable-claim` with the books that really are underspecified."""
    oid = f"okf:{_FLOW}:end-state"
    navigation = _api_navigation()
    navigation.update(_arrival_navigation())
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api"),
                   _step(f"{_SCREEN}#open-thing", "interaction", "policy")],
            checks=[_visible("table:Things on file")],
        ),
        _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]}),
        navigation=navigation,
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["needs-multi-target-runtime"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "binds one driver to one service" in gap.detail
    assert "http on 'api'" in gap.detail and "playwright on 'policy'" in gap.detail
    assert oid not in _covers(source)


def test_a_mobile_step_is_a_backend_nobody_built_not_a_book_nobody_finished() -> None:
    """D1's table names `maestro` for an interaction on a mobile surface, and this compiler
    builds no maestro path. The book that wrote that step is finished and correct — nothing in
    it would change if someone repaired it — so the gap says the harness ran out, not the
    author. `uncompilable-claim` would have aimed an okf-builder repair turn at a good page."""
    oid = f"okf:{_SCREEN}#open-thing:does:1"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    context = _navigation_context(
        _obligation(oid, nodeType="interaction", source=_SCREEN, surface="policy",
                    checksDeclared=[_visible("table:Things on file")]),
        navigation=navigation,
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["needs-target-backend"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "builds no maestro path yet" in gap.detail
    assert oid not in _covers(source)


def test_a_step_whose_driver_the_book_never_states_is_still_the_books_to_fix() -> None:
    """The other side of the same branch, and the reason the two need different kinds: with no
    `driver:` on the surface the table cannot be read at all, and that *is* something an author
    goes and writes. It keeps `uncompilable-claim`, and a repair turn is the right destination
    for it."""
    oid = f"okf:{_SCREEN}#open-thing:does:1"
    navigation = _arrival_navigation()
    del navigation["policy"]["driver"]
    context = _navigation_context(
        _obligation(oid, nodeType="interaction", source=_SCREEN, surface="policy",
                    checksDeclared=[_visible("table:Things on file")]),
        navigation=navigation,
    )
    _source, gaps = _compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]


def test_a_journey_walked_entirely_on_an_unbuilt_target_says_so() -> None:
    """Every step dispatches to one target, so there is no crossing to report — the single
    target is one this compiler has no backend for. The journey reports the backend, not the
    crossing, because the two are fixed by building different things."""
    oid = f"okf:{_FLOW}:end-state"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="policy",
            steps=[_step(f"{_SCREEN}#open-thing", "interaction", "policy")],
            checks=[_visible("table:Things on file")],
        ),
        navigation=navigation,
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["needs-target-backend"]
    assert oid not in _covers(source)


def test_a_web_journey_arrives_then_clicks_every_step_in_order() -> None:
    """The journey walks to the screen its first step lives on and performs each `interaction`
    in document order; the flow's own `verify:` is observed after the last click, where the walk
    left the page."""
    oid = f"okf:{_FLOW}:end-state"
    open_thing = f"{_SCREEN}#open-thing"
    save_thing = f"{_SCREEN}#save-thing"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="policy",
            steps=[_step(open_thing, "interaction", "policy"),
                   _step(save_thing, "interaction", "policy")],
            checks=[_located_visible(f"{_SCREEN}#things-table",
                                     {"selector": ["#things-table"]})],
        ),
        _page_obligation(f"{open_thing}:carrier", open_thing,
                         locators={"on": ["[open-link](#open-link)"], "trigger": ["click"]},
                         checks=[]) | {"required": False},
        _page_obligation(f"{save_thing}:carrier", save_thing,
                         locators={"on": ["[save-button](#save-button)"], "trigger": ["click"]},
                         checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#open-link:carrier", f"{_SCREEN}#open-link",
                         locators={"selector": ["#open-link"]}, checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#save-button:carrier", f"{_SCREEN}#save-button",
                         locators={"selector": ["#save-button"]}, checks=[]) | {"required": False},
        navigation=_arrival_navigation(),
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source), [g for g in gaps if g.obligation_id == oid]
    goto = source.index("qa.goto(")
    first = source.index('"#open-link"')
    second = source.index('"#save-button"')
    assert goto < first < second
    # The claim is observed after the walk, never before it.
    assert second < source.rindex("#things-table")


def test_a_web_journey_with_no_root_path_gaps_uncompilable_claim_not_a_fabricated_root() -> None:
    """The journey side of the same catch-all removal: a driver with no path grammar states no
    `rootPath`, so the journey gaps `uncompilable-claim` naming the missing root instead of
    opening on a fabricated `qa.goto("/")` — no step is compiled and no claim is asserted in a
    world the walk never actually reached."""
    oid = f"okf:{_FLOW}:end-state"
    open_thing = f"{_SCREEN}#open-thing"
    save_thing = f"{_SCREEN}#save-thing"
    nav = _arrival_navigation()
    nav["policy"]["rootPath"] = None
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="policy",
            steps=[_step(open_thing, "interaction", "policy"),
                   _step(save_thing, "interaction", "policy")],
            checks=[_located_visible(f"{_SCREEN}#things-table",
                                     {"selector": ["#things-table"]})],
        ),
        _page_obligation(f"{open_thing}:carrier", open_thing,
                         locators={"on": ["[open-link](#open-link)"], "trigger": ["click"]},
                         checks=[]) | {"required": False},
        _page_obligation(f"{save_thing}:carrier", save_thing,
                         locators={"on": ["[save-button](#save-button)"], "trigger": ["click"]},
                         checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#open-link:carrier", f"{_SCREEN}#open-link",
                         locators={"selector": ["#open-link"]}, checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#save-button:carrier", f"{_SCREEN}#save-button",
                         locators={"selector": ["#save-button"]}, checks=[]) | {"required": False},
        navigation=nav,
    )
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]
    detail = next(g.detail for g in gaps if g.obligation_id == oid)
    assert "root path a journey can open from" in detail
    assert "qa.goto(" not in source


def _unarranged_journey_context(**flow_extra: object) -> tuple[str, dict]:
    oid = f"okf:{_FLOW}:end-state"
    listed = f"{_API}#list-things"
    flow = _flow_obligation(
        oid, source=_FLOW, surface="api",
        steps=[_step(listed, "endpoint", "api")],
        checks=[{"call": "it", "name": "http_status",
                 "args": {"status": 200, "path": "/api/things"}}],
        fixtures=[],
    ) | flow_extra
    return oid, _navigation_context(
        flow,
        _step_node(listed, {"route": ["GET /api/things"]}),
        navigation=_api_navigation(),
    )


def test_a_journey_that_arranges_nothing_compiles_to_no_scenario() -> None:
    """A journey's claims are about the world its steps left, and the world its steps left is
    the world they started in plus the walk. With nothing arranging the start, the end-state
    assertion observes whatever the scenario before it happened to leave — so a red says
    nothing about the app. The gap removes the case rather than routing it: no scenario is
    emitted, and the obligation is reported unmet with the reason."""
    oid, context = _unarranged_journey_context()
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["unarranged-journey"]
    assert oid not in _covers(source)


def test_a_journey_that_says_it_needs_no_arrangement_compiles() -> None:
    """The author who decided the journey holds in whatever world it finds can say so, and
    that is a different packet from the author who never looked — which is the whole reason
    `arrangesNothing` is carried beside `fixturesDeclared` rather than folded into it."""
    oid, context = _unarranged_journey_context(arrangesNothing=True)
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == []
    assert oid in _covers(source)
    assert "    preconditions=[\n    ],\n" in source


def test_a_scenario_ending_on_a_parameterised_route_vets_nothing() -> None:
    """A screen addressed by `/links/:id/edit` names a family of pages, not one page.

    The driver decides which screen it is looking at by comparing the page's URL against the
    book's `route:`, so a route that cannot be compared leaves the vet grading a render nothing
    established as this screen's. The verdicts would still be filed under it, and a pass filed
    against an unestablished subject is worse than no pass at all — so the call is withheld and
    the plan says why, on every obligation the scenario claims.
    """
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
        screen_routes={_SCREEN: "/policies/:id/edit"},
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _vetted(source) == []
    unidentifiable = [gap for gap in gaps if gap.kind == "unidentifiable-screen"]
    assert [gap.obligation_id for gap in unidentifiable] == [oid]
    assert "/policies/:id/edit" in unidentifiable[0].detail
    # The claim itself is still observed — what was withheld is the placement grading.
    assert f'covers=["{oid}"]' in source


def test_a_screen_the_book_states_no_route_for_vets_nothing() -> None:
    """Silence and ambiguity reach the compiler the same way: absent from the packet's map.

    `qa context` omits a screen file that states no `route:` and one that states two, because
    neither gives a reader of a rendered page anything to compare. The scenario is the same in
    both cases — it ends somewhere it cannot name — so it reports the same gap.
    """
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
        screen_routes={},
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _vetted(source) == []
    detail = next(gap.detail for gap in gaps if gap.kind == "unidentifiable-screen")
    assert "no single `route:`" in detail


def test_a_route_that_is_not_a_path_is_reported_as_one_not_as_a_pattern() -> None:
    """A book reverse-engineered from a framework writes the route's *name* in this bullet.

    `route: app_bundle_user_home` is a fact about the source, not an address, and telling its
    author it "names a family of pages" sends them to remove a parameter that is not there.
    Three unreadable shapes, three repairs, so the gap says which one it read.
    """
    oid = "okf:policy-list:policy-table:visible:1"

    def detail_for(route: str) -> str:
        context = _navigation_context(
            _page_obligation(oid, f"{_SCREEN}#policy-table",
                              locators={"role": ["table"], "name": ["Policies on file"]},
                              checks=[_visible("table:Policies on file")]),
            navigation=_arrival_navigation(),
            screen_routes={_SCREEN: route},
        )
        _, gaps = compile_plan_gaps(context, story="demo-story")
        return next(gap.detail for gap in gaps if gap.kind == "unidentifiable-screen")

    assert "is not a path a browser could show" in detail_for("app_bundle_user_home")
    assert "names a family of pages" in detail_for("/policies/{id}")


def test_a_fixture_bullet_that_did_not_parse_is_not_the_journey_that_arranges_nothing() -> None:
    """A rejected `fixture:` bullet and an absent one are not the same state of the book.

    Downstream of the packet both were an empty `fixturesDeclared`, which is how a flow whose
    bullet had a typo in it came to be gapped `unarranged-journey` — *"add a `fixture:` naming
    the arrangement, or `fixture: none, because ...`"* — at an author who had added one, and
    the advice was to do the thing already done. The packet now carries the value the parser
    rejected together with the parser's own sentence, and the obligation is partitioned out
    before any builder sees it: the state this claim is documented in is undetermined, and
    nothing executable comes out of an undetermined arrangement.
    """
    oid = f"okf:{_FLOW}:end-state"
    obligation = _flow_obligation(
        oid, source=_FLOW, surface="api",
        steps=[_step(f"{_API}#post-things", "endpoint", "api")],
        checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                               "path": "/api/things"}}],
        fixtures=[],
    )
    obligation["fixturesUnparsed"] = [
        {"value": "Seeded Ledger", "problem": "`Seeded` is not a fixture name"},
    ]
    context = _navigation_context(obligation, _step_node(f"{_API}#post-things", {}),
                                  navigation=_api_navigation())

    source, gaps = _compile_plan_gaps(context, story="demo-story")

    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["unparsed-fixture"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "Seeded Ledger" in gap.detail and "is not a fixture name" in gap.detail
    # Not the undecided case's code, and nothing compiled against a state nobody established.
    assert "unarranged-journey" not in {g.kind for g in gaps}
    assert oid not in _covers(source)


def test_a_fixture_providing_a_fact_of_undetermined_source_compiles_nothing() -> None:
    """A `provides:` entry stating neither `from:`/`read:` nor `is:` is an undetermined arrangement.

    The harness extracts every declared fact eagerly, before any check asks for one, so an entry
    whose source the book left open aborts the whole scenario — not the one assertion that cites
    it, and not only when something cites it at all. Left in `owed`, this obligation compiles
    into a scenario that dies at run time with a message about JSON parsing, three services away
    from the book that is actually wrong. So the gap is raised here, against the fixture, where
    the author can act on it.
    """
    oid = f"okf:{_FLOW}:end-state"
    obligation = _flow_obligation(
        oid, source=_FLOW, surface="api",
        steps=[_step(f"{_API}#post-things", "endpoint", "api")],
        checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                               "path": "/api/things"}}],
        fixtures=[],
    )
    obligation["fixturesDeclared"] = [
        {"name": "seeded-ledger", "args": [], "provides": "a ledger exists",
         "providesKeys": ["seeded-ledger.id", "seeded-ledger.total"],
         "providesUndetermined": ["seeded-ledger.total"]},
    ]
    context = _navigation_context(obligation, _step_node(f"{_API}#post-things", {}),
                                  navigation=_api_navigation())

    source, gaps = _compile_plan_gaps(context, story="demo-story")

    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["undetermined-provided-fact"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "seeded-ledger" in gap.detail and "seeded-ledger.total" in gap.detail
    assert oid not in _covers(source)


def test_a_fixture_whose_provided_facts_all_state_a_source_compiles() -> None:
    """The same arrangement with every source stated is not gapped — the key is undetermined-ness."""
    oid = f"okf:{_FLOW}:end-state"
    obligation = _flow_obligation(
        oid, source=_FLOW, surface="api",
        steps=[_step(f"{_API}#post-things", "endpoint", "api")],
        checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                               "path": "/api/things"}}],
        fixtures=[],
    )
    obligation["fixturesDeclared"] = [
        {"name": "seeded-ledger", "args": [], "provides": "a ledger exists",
         "providesKeys": ["seeded-ledger.id", "seeded-ledger.total"]},
    ]
    context = _navigation_context(obligation, _step_node(f"{_API}#post-things", {}),
                                  navigation=_api_navigation())

    _, gaps = _compile_plan_gaps(context, story="demo-story")

    assert "undetermined-provided-fact" not in {g.kind for g in gaps}


def test_a_verify_bullet_the_parser_refused_is_not_a_node_that_declared_no_check() -> None:
    """The gap said the book declares no check, to an author who declared one and misspelled it.

    `_parse_checks` kept the rows that parsed and dropped the rest, so downstream an obligation
    whose `verify:` bullet nobody could read and one with no `verify:` at all arrived the same
    way — with no `checksDeclared` — and fell through to `no-verify-declared`. `ostler doctor`
    refuses that bullet by name, which is what makes the fall-through a disagreement in writing
    rather than a gap: two readers of one bullet, and the one deciding whether to emit code held
    the wrong account of it. The packet now carries the refusal, and the obligation is
    partitioned out before any builder sees it — an observation nobody could read is not one.
    """
    oid = f"okf:{_SCREEN}#policy-table:contract"
    obligation = _page_obligation(oid, f"{_SCREEN}#policy-table",
                                  locators={"role": ["table"], "name": ["Policies on file"]},
                                  checks=[])
    obligation["checksUnparsed"] = [
        {"value": "visble(table:Policies on file)", "kind": "unknown-check",
         "problem": "names no check in the vocabulary"},
    ]
    context = _navigation_context(obligation, navigation=_arrival_navigation())

    source, gaps = _compile_plan_gaps(context, story="demo-story")

    ast.parse(source)
    assert _gap_kinds(gaps, oid) == ["unparsed-check-bullet"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "visble(table:Policies on file)" in gap.detail
    assert "names no check in the vocabulary" in gap.detail
    # Not the advice to declare what is already declared, and nothing asserted on its behalf.
    assert "no-verify-declared" not in {g.kind for g in gaps}
    assert oid not in _covers(source)


def test_a_capture_bullet_the_parser_refused_gaps_where_it_was_written() -> None:
    """A refused `capture:` costs this claim nothing and costs a later `$name` everything.

    Unlike the two kinds above, the obligation is not partitioned out: its own check is still
    stated and still emittable, and withholding it would be a second wrong answer. What was
    lost is the *fact* the bullet would have minted — and without this gap, the only thing said
    about it is an `unresolved-precondition` on whatever later bullet spells `$claim_id`, whose
    author wrote it correctly. The gap goes on the bullet that is actually wrong.
    """
    oid = f"okf:{_SCREEN}#policy-table:contract"
    obligation = _page_obligation(oid, f"{_SCREEN}#policy-table",
                                  locators={"role": ["table"], "name": ["Policies on file"]},
                                  checks=[_visible("table:Policies on file")])
    obligation["capturesUnparsed"] = [
        {"value": "claim_id $.id", "problem": "names no source"},
    ]
    context = _navigation_context(obligation, navigation=_arrival_navigation())

    source, gaps = _compile_plan_gaps(context, story="demo-story")

    ast.parse(source)
    [gap] = [g for g in gaps if g.kind == "unparsed-capture-bullet"]
    assert gap.obligation_id == oid
    assert "claim_id $.id" in gap.detail
    assert "names no source" in gap.detail
    # The claim itself is still proven — the refusal is about the capture, not about the check.
    assert oid in _covers(source)


def test_a_capture_no_builder_can_emit_stands_beside_the_claim_rather_than_against_it() -> None:
    """A UI-locator capture on a routed obligation: the assertion compiles, the binding does not.

    Both halves are true at once, and before `uncaptured-declaration` existed the compiler said
    so in a vocabulary that made them contradict — an `uncompilable-claim` gap ("nobody looked")
    minted against an id the same run compiled a real `covers=[...]` for. It survived only
    because no book in the corpus declares a non-empty `capture:`; the mirror assert in
    `compile_plan_gaps` would have caught it the day one did.
    """
    oid = "okf:docs/features/acme/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[_check(path="/api/things")],
            capturesDeclared=[{"name": "widget_id", "from": "#widget-id"}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists"}],
        )
    )
    covered: set[str] = set()
    source, gaps = _compile_plan_gaps(
        context, story="demo-story", base_url=_BASE_URL, covered_ids=covered)

    assert _gap_kinds(gaps, oid) == ["uncaptured-declaration"]
    assert oid in covered
    assert "qa.capture_field(" not in source
    assert "widget_id" in source  # the TODO says what went unbound, so it is not silent


def test_a_declared_capture_that_no_builder_accounts_for_is_refused() -> None:
    """The guard, exercised by removing the thing it guards.

    The defect is not that one builder cannot bind a page value — it is that a builder which
    cannot has nothing forcing it to *say so*, and a declaration read by nobody is
    indistinguishable from one the book never wrote. So the assert is aimed at the silence, and
    the only honest way to test it is to put the silence back.
    """
    oid = "okf:docs/features/acme/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[_check(path="/api/things")],
            capturesDeclared=[{"name": "widget_id", "from": "#widget-id"}],
            fixturesDeclared=[{"name": "seeded-acme", "args": [], "provides": "an account exists"}],
        )
    )
    import ostler.qa.compile as compile_mod

    with pytest.raises(AssertionError, match="neither emitted nor gapped"):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(compile_mod, "_decline_captures", lambda *a, **k: None)
            compile_plan_gaps(context, story="demo-story")


def test_a_capture_on_an_obligation_nobody_observed_goes_with_its_obligation() -> None:
    """One silence, reported once. A checkless obligation is already gapped as book debt — a
    second gap saying its capture went unbound grades the same nothing twice, and would send a
    repair agent after a `capture:` bullet when the missing thing is the `verify:`."""
    oid = "okf:docs/features/acme/api.md#get-things:does:1"
    context = _context(
        _obligation(oid, capturesDeclared=[{"name": "widget_id", "from": "#widget-id"}])
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["no-verify-declared"]


# --- D1 registry tripwire: every target named by the dispatch table is accounted for --------
#
# `_BUILT_TARGETS` is a claim, not an observation: it says "this compiler emits a scenario for
# an obligation dispatched here." Direction 1 below checks the claim is *complete* — no target
# `_DISPATCH_TABLE`/`_OBSERVE_ROW` can name falls through both `_BUILT_TARGETS` and an explicit,
# reasoned exclusion. Direction 2 checks the harder half: that every member of `_BUILT_TARGETS`
# is *true* — driving the compiler at each one and reading the emitted plan, not re-asserting a
# second hardcoded list of "targets that work" beside the first.

#: Targets D1's table names that this compiler does not build a scenario for, on purpose, each
#: with the reason and the condition that retires the entry. Anything reachable from
#: `_DISPATCH_TABLE`/`_OBSERVE_ROW` that is neither in `_BUILT_TARGETS` nor named here is an
#: undecided cell — a target added to the table with no decision recorded — and fails
#: `test_every_reachable_dispatch_target_is_built_or_named_as_an_exclusion` below.
_ACKNOWLEDGED_UNBUILT_TARGETS: dict[str, str] = {
    "maestro": (
        "D1's table names `maestro` for an `interaction` on a `mobile`-driven surface, and "
        "`_OBSERVE_ROW` names it for a `flow`/`component`/`screen` on one too, but this "
        "compiler builds no maestro path — `_dispatch_target` reports it as "
        "`needs-target-backend` (measured against the globex fixture: 8 such gaps, "
        "\"...but this compiler builds no maestro path yet\"). Remove this entry when a "
        "maestro scenario builder lands."
    ),
    "in-process": (
        "D1's table names `in-process` for every `method`/`invocation` obligation on every "
        "driver, but this compiler builds no in-process path either — the same "
        "`needs-target-backend` gap `maestro` gets. Remove this entry when an in-process "
        "scenario builder lands."
    ),
}


def test_every_reachable_dispatch_target_is_built_or_named_as_an_exclusion() -> None:
    """Completeness: nothing D1's table can dispatch to falls through the floor.

    A target that shows up in `_DISPATCH_TABLE` or `_OBSERVE_ROW` with no entry in either
    `_BUILT_TARGETS` or `_ACKNOWLEDGED_UNBUILT_TARGETS` is a decision nobody recorded — this
    fails the moment one is added, rather than waiting for a book that exercises it to surface
    a silent gap nobody meant to ship.
    """
    reachable = {
        target
        for row in _DISPATCH_TABLE.values()
        for target in ([row] if isinstance(row, str) else row.values())
        if target
    }
    reachable |= set(_OBSERVE_ROW.values())
    accounted = _BUILT_TARGETS | set(_ACKNOWLEDGED_UNBUILT_TARGETS)
    undecided = reachable - accounted
    assert not undecided, (
        f"{sorted(undecided)} named by D1's table but neither built ({sorted(_BUILT_TARGETS)}) "
        f"nor recorded as an acknowledged gap ({sorted(_ACKNOWLEDGED_UNBUILT_TARGETS)}) — decide "
        "one way or the other"
    )
    assert _BUILT_TARGETS.isdisjoint(_ACKNOWLEDGED_UNBUILT_TARGETS), (
        "a target cannot claim both a builder and an acknowledged absence of one"
    )


def _built_target_probe_playwright() -> tuple[dict, str]:
    """The smallest obligation D1 dispatches to `playwright`: an `interaction` on a
    `web`-driven surface, reachable from an arrival with nothing else to arrange."""
    oid = "okf:built-target-probe:playwright:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#probe",
                          locators={"role": ["table"], "name": ["Things on file"]},
                          checks=[_visible("table:Things on file")]),
        navigation=_arrival_navigation(),
    )
    return context, oid


def _built_target_probe_http() -> tuple[dict, str]:
    """The smallest obligation D1 dispatches to `http`: an `endpoint` on the default
    `http`-driven surface, fully arranged so nothing else could withhold the scenario."""
    oid = "okf:built-target-probe:http:does:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[_check()],
            fixturesDeclared=[
                {"name": "seeded-ledger", "args": [], "provides": "a ledger"},
            ],
        )
    )
    return context, oid


def _built_target_probe_cli() -> tuple[dict, str]:
    """The smallest obligation D1 dispatches to `cli`: a `command` on a `cli`-driven surface,
    with a real check (`exit_status`), a fixture arranged, and a `run:` (`ostler.acts`'s
    `invoke`) for the check to bind to — so nothing about this obligation is missing except a
    builder that reads it."""
    oid = "okf:built-target-probe:cli:exit-status:1"
    context = _context(
        _obligation(
            oid,
            nodeType="command",
            checksDeclared=[{"call": "it", "name": "exit_status", "args": {"code": 0}}],
            fixturesDeclared=[
                {"name": "seeded-ledger", "args": [], "provides": "a ledger"},
            ],
            actsDeclared=[
                {"call": 'invoke(argv=["import"])', "name": "invoke",
                 "args": {"argv": ["import"]}},
            ],
        )
    )
    context["navigation"][""]["driver"] = "cli"
    context["cliBinaries"] = {"docs/features/demo/api.md": "tally"}
    return context, oid


def test_a_run_with_no_owning_binary_is_uncompilable() -> None:
    """`argv` names only the arguments — the executable is the owning `cli` file node's own
    `binary:` bullet, resolved from `context["cliBinaries"]` by the obligation's shared `source`
    path. A `cli` node with no `binary:` value (its `source` absent from that dict, exactly what
    `context.py`'s `_cli_binaries` produces when the bullet is empty) leaves a well-formed
    `run:` with nothing to name as the executable — that is uncompilable, not a guess at
    `argv[0]`."""
    oid = "okf:built-target-probe:cli:exit-status:no-binary:1"
    context = _context(
        _obligation(
            oid,
            nodeType="command",
            checksDeclared=[{"call": "it", "name": "exit_status", "args": {"code": 0}}],
            actsDeclared=[
                {"call": 'invoke(argv=["import"])', "name": "invoke",
                 "args": {"argv": ["import"]}},
            ],
        )
    )
    context["navigation"][""]["driver"] = "cli"
    context["cliBinaries"] = {}  # the owning `cli` node declares no `binary:`

    _source, gaps = compile_plan_gaps(context, story="demo-story")

    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]
    (gap,) = [g for g in gaps if g.obligation_id == oid]
    assert "declares no `binary:`" in gap.detail
    assert "cannot name the executable this `run:` invokes" in gap.detail


def test_an_empty_argv_is_a_legal_bare_invocation() -> None:
    """`argv=[]` is a real, empty argument list — a bare invocation of the binary with no
    arguments — not indistinguishable from "no `run:` at all". It must compile to a call with no
    arguments, never gap as `uncompilable-claim`."""
    oid = "okf:built-target-probe:cli:exit-status:empty-argv:1"
    context = _context(
        _obligation(
            oid,
            nodeType="command",
            checksDeclared=[{"call": "it", "name": "exit_status", "args": {"code": 0}}],
            fixturesDeclared=[
                {"name": "seeded-ledger", "args": [], "provides": "a ledger"},
            ],
            actsDeclared=[
                {"call": "invoke(argv=[])", "name": "invoke", "args": {"argv": []}},
            ],
        )
    )
    context["navigation"][""]["driver"] = "cli"
    context["cliBinaries"] = {"docs/features/demo/api.md": "tally"}

    source, gaps = compile_plan_gaps(context, story="demo-story")

    assert _gap_kinds(gaps, oid) == []
    assert 'qa.tool("tally").run()' in source


#: One minimal-obligation builder per member of `_BUILT_TARGETS` — the harness direction 2
#: needs, not a second copy of the claim under test. `test_every_built_target_has_a_probe`
#: below fails loudly if `_BUILT_TARGETS` ever grows a member this dict has no entry for, so a
#: newly built target cannot silently skip the behavioural check by having nothing to drive it.
_BUILT_TARGET_PROBES = {
    "playwright": _built_target_probe_playwright,
    "http": _built_target_probe_http,
    "cli": _built_target_probe_cli,
}

#: `_BUILT_TARGETS` members direction 2 has *measured* to have no working builder, each with the
#: reason and the exit condition. This is the known-defect record the brief asks for.
#: `strict=True` on the xfail this drives means an entry fails the suite the day its target
#: starts passing, which is the point: nobody can leave a stale "known gap" behind once the fix
#: lands. `cli` had an entry here — every `cli`-dispatched obligation reached
#: `_gap_cli_obligations` unconditionally, which appended an `uncompilable-claim` gap and
#: emitted no scenario — and it is gone now that `_cli_scenario_body` (compile.py) compiles a
#: `command` obligation that declares a `run:` into `qa.tool(...).run(...)`.
_KNOWN_BUILT_TARGET_GAPS: dict[str, str] = {}


def test_every_built_target_has_a_probe() -> None:
    """The probe table direction 2 drives must cover `_BUILT_TARGETS` exactly — a target added
    there with no probe written is untested, not passing, and this is where that shows up."""
    assert set(_BUILT_TARGET_PROBES) == _BUILT_TARGETS


@pytest.mark.parametrize(
    "target",
    [
        pytest.param(
            name,
            marks=(
                [pytest.mark.xfail(strict=True, reason=_KNOWN_BUILT_TARGET_GAPS[name])]
                if name in _KNOWN_BUILT_TARGET_GAPS else []
            ),
        )
        for name in sorted(_BUILT_TARGETS)
    ],
)
def test_every_built_target_actually_emits_a_scenario(target: str) -> None:
    """Direction 2, behavioural: `_BUILT_TARGETS` says this compiler emits a scenario for an
    obligation dispatched to *target* — so drive the compiler with one and read the plan it
    hands back, rather than re-asserting a second hardcoded "targets that work" list beside the
    one under test. A gap where a scenario was claimed is exactly the defect this test exists
    to catch; a target with a genuinely absent builder is recorded above as a strict xfail
    instead of weakening this assertion.
    """
    context, oid = _BUILT_TARGET_PROBES[target]()
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid in _covers(source), (
        f"{target!r} is in _BUILT_TARGETS but the compiler emitted no scenario covering "
        f"{oid!r} — gaps recorded instead: {_gap_kinds(gaps, oid)}"
    )
    assert _gap_kinds(gaps, oid) == []
