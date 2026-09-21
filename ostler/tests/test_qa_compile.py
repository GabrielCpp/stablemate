"""What a plan compiled from the book alone may and may not claim."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

from ostler import checks
from ostler.qa.compile import (
    Gap,
    DriverSpec,
    MAESTRO,
    PLAYWRIGHT,
    PYTHON,
    Plan,
    Refusal,
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
) -> tuple[str | None, list[Gap]]:
    result = _compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)
    if isinstance(result, Refusal):
        return None, result.gaps
    return result.source, result.gaps


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
    base = {
        "id": oid,
        "source": "docs/features/demo/api.md",
        "nodeType": "endpoint",
        "requirement": "writes the record and answers with it",
        "required": True,
        "locators": {"route": ["GET /api/things"]},
        "checksDeclared": [],
        "arrangesNothing": True,
    }
    base.update(extra)
    return base


def _context(*obligations: dict) -> dict:
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
    """`plan(book=...)` names the obligation id set this compile pass read, so a run against a book that has since changed can tell it apart from one still current."""
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
    """Stable under a rewalk that visits the same ids in a different order, and blind to a `required: False` obligation — the plan never owed that one a scenario in the first place, so its coming or going is not a reason to call the plan stale."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)


def test_an_obligation_the_change_does_not_owe_is_not_compiled() -> None:
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:9",
            required=False,
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200, "path": "/api/things"}}],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert result.gaps == []


def test_a_check_needing_a_subject_the_book_never_gave_compiles_to_a_marker() -> None:
    """`unchanged` observes a before and an after."""
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:persistence:1",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
                {"call": "the ledger", "name": "unchanged", "args": {"of": "thing.version"}},
            ],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    oid = "okf:docs/features/demo/api.md#post-things:persistence:1"
    assert isinstance(result, Refusal)
    assert "needs-snapshot" in _gap_kinds(result.gaps, oid)


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
    """`compile_plan_gaps`'s `Gap` list surfaces in `cmd_compile_plan`'s JSON output as doctor-shaped dicts — a caller reads `severity`/`code`/`message`/`ref` the same way it would read a `doctor.Finding`, without re-parsing the compiled plan's Python."""
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
    assert not result.ok
    [gap] = result.data["gaps"]
    assert gap == {
        "severity": "error",
        "code": "unarranged-request-body",
        "message": "the book carries no request body",
        "ref": oid,
    }


def test_the_command_writes_no_file_when_nothing_compiled(tmp_path: Path) -> None:
    """A `Refusal` is not a plan with nothing in it — writing an empty or comment-only file over `out` would let a later run believe a plan already exists there, when what actually happened is that nothing here compiled to one at all."""
    oid = "okf:docs/features/demo/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            arrangesNothing=False,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
        )
    )
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
    out = spec / "qa_plan.py"
    result = cmd_compile_plan(spec, out=out)
    assert not result.ok
    assert not out.exists()


def test_the_command_reports_the_ledger_even_on_a_refusal(tmp_path: Path) -> None:
    """`owed`/`declared`/`debt`/`gaps` are the same ledger a caller reads on a success — a `Refusal` still owes a reader the count of what the book asked for and what it declared, not just the gaps that explain why none of it reached a scenario."""
    oid = "okf:docs/features/demo/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            arrangesNothing=False,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
        )
    )
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
    result = cmd_compile_plan(spec)
    assert not result.ok
    assert result.data["owed"] == 1
    assert result.data["declared"] == 1
    assert result.data["debt"] == []
    [gap] = result.data["gaps"]
    assert gap["code"] == "unarranged-scenario"
    assert gap["ref"] == oid


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
    """Both halves of a `fixture:` bullet land, in the two places a plan keeps them."""
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
    """Two claims documented in the same seeded ledger name one arrangement between them."""
    ledger = {"name": "seeded-ledger", "args": ["2"], "provides": "two policies on file"}
    context = _context(
        _obligation("okf:docs/features/demo/api.md#post-things:does:1",
                    checksDeclared=[_check()], fixturesDeclared=[ledger]),
        _obligation("okf:docs/features/demo/api.md#post-things:does:2",
                    checksDeclared=[_check()], fixturesDeclared=[ledger]),
    )
    source = compile_plan(context, story="demo-story")
    assert source.count('qa.fixture("seeded-ledger", "2")') == 1

    other = {"name": "seeded-ledger", "args": ["5"], "provides": "five policies on file"}
    context["obligations"][1]["fixturesDeclared"] = [other]
    source = compile_plan(context, story="demo-story")
    assert source.count('qa.fixture("seeded-ledger"') == 2


def test_a_book_that_says_it_needs_nothing_arranged_gets_an_empty_precondition_list() -> None:
    """`fixture: none, because ...` is an answer, and the plan states it as one."""
    context = _context(
        _obligation("okf:docs/features/demo/api.md#post-things:does:1", checksDeclared=[_check()])
    )
    source = compile_plan(context, story="demo-story")
    assert "preconditions=[]," in source
    assert "preconditions=[],  # TODO(arrange)" not in source


def _gap_kinds(gaps: list[Gap], oid: str) -> list[str]:
    return [g.kind for g in gaps if g.obligation_id == oid]


def test_a_scenario_that_arranges_nothing_and_says_nothing_compiles_to_nothing() -> None:
    """Neither an arrangement nor a stated need for none is the one answer nothing may compile."""
    oid = "okf:docs/features/demo/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            arrangesNothing=False,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-scenario"]
    assert isinstance(result, Refusal)


def test_a_refusal_carries_every_gap_and_is_never_also_a_plan() -> None:
    """`Refusal` and `Plan` are a sum, not two views of the same result — a caller that gets a `Refusal` back must never find a `Plan` underneath it, and the gap that explains why nothing compiled must be the whole of what `compile_plan_gaps` hands back, not a value alongside a `source` a caller could read instead of asking which case it has."""
    oid = "okf:docs/features/demo/api.md#get-things:does:1"
    context = _context(
        _obligation(
            oid,
            arrangesNothing=False,
            locators={"route": ["GET /api/things"]},
            checksDeclared=[{"call": "ok", "name": "http_status", "args": {"code": 200}}],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(result, Refusal)
    assert not isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-scenario"]


def test_a_compiling_context_yields_a_plan_whose_source_declares_a_scenario() -> None:
    """`Plan.source` is a plan file the plan format admits — at least one `@scenario(` — never the empty, decorator-free module `compile_plan_gaps` used to hand back for "nothing compiled"."""
    context = _context(
        _obligation(
            "okf:docs/features/demo/api.md#post-things:does:1",
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(result, Plan)
    assert "@scenario(" in result.source


def test_a_missing_request_body_is_an_unarranged_request_body() -> None:
    """`json_body={}` against an endpoint that needs a real one gets refused by the app (422) — a false failure against code that did nothing wrong."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"route": ["POST /api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-request-body"]


def _body_act(field: str, value: object) -> dict:
    return {"call": f"body(field={field!r}, value={value!r})", "name": "body",
            "args": {"field": field, "value": value}}


def test_an_arranged_request_body_compiles_to_json_body() -> None:
    """`arrange: body(field=..., value=...)` under the arm fills what `_check`'s bare POST otherwise withholds — the whole reason `body` exists as an act rather than a new key."""
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
    assert source is not None
    assert _gap_kinds(gaps, oid) == []
    assert oid in _covers(source)
    assert 'json_body={"name": "Widget A", "quantity": 3}' in source


def test_a_half_arranged_request_body_is_still_withheld() -> None:
    """One act the HTTP driver cannot perform poisons the whole body, the same all-or-nothing rule `_performed_lines` already applies to `fill`/`click` — a request half the book declared is neither the body it wrote nor no body."""
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
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-request-body"]


def test_an_unparsed_act_is_still_an_unarranged_request_body() -> None:
    """A bullet under `arrange:` that failed to parse is the same absent body as none at all — a compiler that emitted `json_body={}` around it would be filling in for a mistake it never saw, not for what the author actually wrote."""
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
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-request-body"]


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
    """`@node.key`/`$name` are static syntax `compile_plan` cannot resolve without running the plan — a gap, not a compile-time crash, and the same grammar `fixture:`/`needs:` share."""
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
    """No `route:` to act on is a book that gives QA nothing to observe — a different repair from a fixture-shaped gap, so it earns its own kind rather than folding into the other."""
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
    """A `method:` that does not spell a recognized HTTP verb is undetermined, not absent — a different repair (fix the spelling) from `uncompilable-claim` (state a `route:` at all), so it earns its own gap kind naming the value that failed, and it must not fall through to `unarranged-request-body` either (that code is about a method that parsed but has no body)."""
    oid = "okf:docs/features/demo/globex.md#weird-things:does:1"
    context = _context(
        _obligation(
            oid,
            locators={"method": ["FROB"], "path": ["/api/things"]},
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["invalid-http-method"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "FROB" in gap.detail


def test_a_subject_pair_check_wanting_a_snapshot_is_a_named_gap() -> None:
    """`unchanged` wants a before and an after this compiler has no snapshot mechanism to take — a named `needs-snapshot` gap, not the generic `uncompilable-claim`."""
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
    """`count`/`absent`/`exit_status` are read once, after the action, from what the scenario already holds — they compile to a real `qa.verify(...)` call, not a gap."""
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
    assert source is not None
    assert _gap_kinds(gaps, oid) == []
    assert f'qa.verify("{verb}"' in source


def test_checkpoints_and_forbid_scaffolding_never_appear_in_the_gap_report() -> None:
    """`checkpoints=[]`/`forbid=[]` are unconditional TODO scaffolding, not a fact discovered about any one obligation — so they stay plain source comments, outside the structured report `doctor` reads."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(_obligation(oid, checksDeclared=[_check()]))
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    assert "checkpoints=[],  # TODO" in source
    assert "forbid=[],  # TODO" in source
    assert {g.kind for g in gaps} <= {"unresolved-precondition", "uncompilable-claim"}


def test_a_reference_to_a_fixture_key_arranged_in_the_same_obligation_is_resolved() -> None:
    """A fixture arranged for this obligation arranges before it verifies — so a reference to a key that fixture's own `provides:` declares resolves, and is not a gap."""
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
    """`qa.resolve(...)` is the harness's one explicit substitution entry point (Fix 2) — the compiler wraps a literal in it only where `references.find_references` actually found a `@node.key`/`$name`, and leaves every other literal, including one that merely starts with `$` in a way that is not a reference, exactly as it read it."""
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
    """`$name` names a fact an earlier `capture:` bullet left behind — an obligation after the one that captures it may reference it with no gap."""
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
    """No `route:` means `observed_N` compiles to `None` — nothing was ever requested to read a `$.`-rooted capture off of."""
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
    assert source is not None
    assert "qa.capture_field(" not in source
    assert "unresolved-precondition" in _gap_kinds(gaps, referencing)


def test_a_capture_declared_only_on_a_later_obligation_is_still_a_gap() -> None:
    """The same-obligation exception generalises to ordering: a reference does not see into the future, so a capture the book only produces afterward leaves the earlier reference a gap."""
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
    """`@node.key` names a fact only that fixture's own arrangement produces — a scenario that never arranges it leaves the reference unresolved regardless of what else it did arrange."""
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
    """`seeded-globex` `needs:` `seeded-acme` — arranging the former also arranges the latter, so a reference to a key only `seeded-acme` declares under `provides:` still resolves."""
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
    """A node written `returns:` (captures `account_id`) before `raises:` (reads `$account_id`) resolves cleanly — even though `raises` sorts before `returns` alphabetically, and `_sort_key` is what orders `obligations` on the way in here."""
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
    context = _context(raises, returns)
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, raises["id"]) == []


def test_the_producer_walk_still_gaps_a_reference_that_precedes_its_producer() -> None:
    """The mirror of the case above: `raises:` written *before* `returns:` in the book still leaves the reference a gap, because the capture it needs has not happened yet at that point in document order — regardless of what the two obligations' ids alphabetize to."""
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
    """The dead `TODO(undeclared)` branch removed from `_scenario_body`: a checkless obligation is book debt, filtered out before the body is ever asked to render one — no scenario is emitted for it, but it is not a silent drop either: the same code that declined to compile it is the code that gaps it, so it still lands in `{emitted, gap}` like every owed id."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:2"
    context = _context(_obligation(oid))
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["no-verify-declared"]


def test_a_when_guarded_checkless_obligation_is_not_book_debt() -> None:
    """`when:` states a condition the node's other claims hold under, not a claim of its own — there is nothing for a check to prove, so a check-less `when:` obligation is not the same defect `no-verify-declared` names ("the book declares no check for this obligation to prove"), which would send an author looking for a check nothing could ever fail."""
    oid = "okf:docs/features/demo/globex.md#submit-widget:when:1"
    context = _context(_obligation(oid, kind="when"))
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["precondition-discharged-by-arrangement"]


def test_a_when_guarded_checkless_obligation_is_left_out_of_the_book_debt_listing() -> None:
    """The compiled plan's `# Book debt` comment tells an author to go add a `verify:` — the right instruction for a checkless `does:`, and the wrong one for a checkless `when:`, which is discharged by arrangement rather than by a check at all."""
    debt_oid = "okf:docs/features/demo/globex.md#post-things:does:2"
    when_oid = "okf:docs/features/demo/globex.md#submit-widget:when:1"
    compiled_oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(compiled_oid, checksDeclared=[_check()]),
        _obligation(debt_oid),
        _obligation(when_oid, kind="when"),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    assert debt_oid in source
    assert when_oid not in source
    assert _gap_kinds(gaps, debt_oid) == ["no-verify-declared"]
    assert _gap_kinds(gaps, when_oid) == ["precondition-discharged-by-arrangement"]



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
    """One `actsDeclared` row shaped the way `qa context` writes it: the canonical call text, its bound arguments, and the resolved book node each locator argument names."""
    call = f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
    return {"call": call, "name": name, "args": dict(args),
            "locates": {"locator": {"node": node, "locators": locators}}}


def _visible(locator: str) -> dict:
    return {"call": "it", "name": "visible", "args": {"locator": locator}}


def _navigation_context(*obligations: dict, navigation: dict,
                        screen_routes: dict[str, str] | None = None) -> dict:
    ctx = _context(*obligations)
    ctx["navigation"] = navigation
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
    """`empty-register-notice`/`policy-table` (real policy-desk bullets) must never land in the same compiled scenario — the amendment reads `exclusive-with:` as symmetric even though only one side of this real pair writes the bullet."""
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
    assert source is not None
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
    """A driver with no path grammar (`routes.is_path_addressed` says no) states no `rootPath` at all — `reach.root_path` now returns `(None, None)` for it rather than the app root."""
    oid = "okf:policy-list:policy-table:visible:1"
    node = f"{_SCREEN}#policy-table"
    nav = _arrival_navigation()
    nav["policy"]["rootPath"] = None
    context = _navigation_context(
        _page_obligation(oid, node, locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=nav,
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    detail = next(g.detail for g in result.gaps if g.obligation_id == oid)
    assert "states no root path" in detail


def test_an_unarranged_states_claim_produces_a_gap_not_a_scenario() -> None:
    """A `states:` bullet mints its own obligation (`kind == "states"`) separate from the node's `role:`/`name:` claim."""
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
    assert source is not None
    ast.parse(source)
    assert "combobox:Coverage type" in source
    assert _gap_kinds(gaps, oid) == []
    assert _gap_kinds(gaps, state_oid) == ["unarranged-state"]
    [gap] = [g for g in gaps if g.obligation_id == state_oid]
    assert "opens on `auto`." in gap.detail


def test_a_fully_arranged_states_claim_compiles_its_own_scenario() -> None:
    """A `states:` obligation that declares both a check and a fixture compiles into its own dedicated scenario, with `preconditions=[...]` quoting the arranging fixture's own words — it is not merged into the node's plain arrival scenario, and it is not gapped."""
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
    assert source is not None
    ast.parse(source)
    assert _gap_kinds(gaps, state_oid) == []
    assert "status:Loading" in source
    assert 'qa.fixture("seeded-loading")' in source
    assert '"the widget list is loading"' in source


def test_states_no_longer_withholds_exclusive_with_on_the_same_node() -> None:
    """`vehicle-vin-field` in the real `new-policy.md` fixture carries *both* `states:` and `exclusive-with:`."""
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
    assert source is not None
    ast.parse(source)
    assert "textbox:Vehicle VIN" in source
    assert "@scenario(" in source
    assert _gap_kinds(gaps, oid) == []
    assert _gap_kinds(gaps, state_oid) == ["unarranged-state"]


def test_unarranged_state_reaches_the_same_gap_on_every_driver() -> None:
    """A check-less `states:` obligation on a `component` node dispatches to a different builder per surface driver (D1: `component` x `driver`, `_OBSERVE_ROW`) — web to the page builder, cli and http to their own."""
    requirement = "opens on `auto`."

    node = f"{_SCREEN}#coverage-type-select"
    web_oid = "okf:new-policy:coverage-type-select:states:web"
    web_obligation = _page_obligation(web_oid, node, kind="states", requirement=requirement,
                                       locators={"role": ["combobox"], "name": ["Coverage type"]},
                                       checks=[])
    web_obligation["nodeType"] = "component"
    web_context = _navigation_context(web_obligation, navigation=_arrival_navigation())
    web_result = _compile_plan_gaps(web_context, story="demo-story")
    assert isinstance(web_result, Refusal)
    assert _gap_kinds(web_result.gaps, web_oid) == ["unarranged-state"]

    cli_oid = "okf:new-policy:coverage-type-select:states:cli"
    cli_context = _context(
        _obligation(cli_oid, nodeType="component", kind="states", requirement=requirement)
    )
    cli_context["navigation"][""]["driver"] = "cli"
    cli_result = _compile_plan_gaps(cli_context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(cli_result, Refusal)
    assert _gap_kinds(cli_result.gaps, cli_oid) == ["unarranged-state"]

    http_oid = "okf:new-policy:coverage-type-select:states:http"
    http_context = _context(
        _obligation(http_oid, nodeType="component", kind="states", requirement=requirement)
    )
    http_context["navigation"][""]["driver"] = "http"
    http_result = _compile_plan_gaps(http_context, story="demo-story", base_url=_BASE_URL)
    assert isinstance(http_result, Refusal)
    assert _gap_kinds(http_result.gaps, http_oid) == ["unarranged-state"]


def test_an_interactions_assertion_never_lands_on_the_arrival_scenario() -> None:
    """A `## Interactions` row's `visible(...)` asserts state *after* the interaction — it must never be emitted as an arrival assertion on the screen's own page-load scenario."""
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
    assert source is not None
    ast.parse(source)
    scenarios = source.split("@scenario(")[1:]
    arrival = [s for s in scenarios if "_arrival(" in s]
    interactions = [s for s in scenarios if "submit_new_policy(" in s]
    assert len(arrival) == 1
    assert "heading:Policy PN-1001" not in arrival[0]
    assert len(interactions) == 0
    assert sorted(_gap_kinds(gaps, interaction_oid)) == ["uncompilable-claim", "unresolved-precondition"]


def test_a_subject_only_verb_on_a_page_obligation_is_a_gap_not_a_silent_drop() -> None:
    """`unchanged` observes a subject (a before/after pair), not the rendered page — a Playwright driver cannot serve it."""
    node = f"{_SCREEN}#policy-table"
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  {"call": "the count", "name": "unchanged", "args": {"of": "policy.count"}}]),
        navigation=_arrival_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    kinds = _gap_kinds(result.gaps, oid)
    assert "uncompilable-claim" in kinds
    [gap] = [g for g in result.gaps if g.obligation_id == oid and g.kind == "uncompilable-claim"]
    assert "unchanged" in gap.detail
    assert "not observable from the playwright driver" in gap.detail


def test_a_body_observing_verb_on_a_page_obligation_names_driver_and_channel_differently() -> None:
    """`json_path` observes a `body` — a channel Playwright *can* see, unlike `unchanged`'s `subject`."""
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
    """Acceptance criterion 3: a driver declaring no capability at all must turn every claim shape routed through `_unobservable_gap` into a gap — never an exception, and never a silently compiled (falsely passing) assertion."""
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
    """Maestro is nameable from the compiler via its own capability declaration — it declares `page` and `subject`, not the HTTP channels Playwright can see, and not the same page/HTTP mix Playwright declares either."""
    assert PLAYWRIGHT.observes == frozenset({"page", "response", "body", "keyboard"})
    assert MAESTRO.observes == frozenset({"page", "subject"})
    assert PYTHON.observes == frozenset({"response", "body", "subject"})


def test_a_reachable_screen_with_no_declared_preconditions_is_undeclared_not_silent() -> None:
    """Amendment 2: reachable, but the screen's `requires:`/`params:` bullets are literally absent — a third outcome, distinct from `unreachable`, with its own gap kind, and emitted once per screen rather than once per obligation (a live-audit gate renders one line per gap; multiplying this by obligation count would not add information)."""
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
    assert undeclared_gaps[0].obligation_id == "okf:policy-list:policy-table:visible:1"


def test_an_unreachable_screen_is_a_finding_not_a_compile_target() -> None:
    """Correction 5': an unreachable screen is a finding, not a scenario."""
    node = f"{_SCREEN}#policy-table"
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(unreachable=[_SCREEN]),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    kinds = _gap_kinds(result.gaps, oid)
    assert kinds == ["unreachable-screen"]


def test_a_zero_screen_book_grows_no_playwright_target() -> None:
    """Condition 1: a book with no screen nodes on any surface never grows a `web` target, even if a stray page-checked obligation somehow reached the compiler."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)


def test_navigation_is_keyed_by_surface_even_for_a_single_surface_book() -> None:
    """Amendment 1: `navigation` is keyed by surface, no special-casing a one-surface book — pinned here with two surfaces so a screen on one never resolves against the other's route."""
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
    assert source is not None
    ast.parse(source)
    assert "table:Policies on file" in source
    assert "table:Claims on file" in source
    assert gaps == []



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
    """The attribute name of *call*'s callee, e.g."""
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
    """Five ways a compiled `by_role`/`by_css` call can be wrong and only fail at runtime, all pinned against one plan compiled from bullets that provoke each of them:"""
    screen = "docs/features/policy/gui/screens/policy-list.md"
    context = _navigation_context(
        _page_obligation("okf:policy-list:backticked:visible:1", f"{screen}#backticked",
                          locators={"role": ["`button`"], "name": ["`Cancel policy`"]},
                          checks=[_visible("button:Cancel policy")]),
        _page_obligation("okf:policy-list:bad-role:visible:1", f"{screen}#bad-role",
                          locators={"role": ["widget-nonexistent"], "name": ["Something"],
                                    "selector": ["`.something`"]},
                          checks=[_visible("something")]),
        _page_obligation("okf:policy-list:generic-role:visible:1", f"{screen}#generic-role",
                          locators={"role": ["generic"], "name": ["none"], "selector": ["dl"]},
                          checks=[_visible("generic")]),
        _page_obligation("okf:policy-list:role-only:visible:1", f"{screen}#role-only",
                          locators={"role": ["table"]},
                          checks=[_visible("table")]),
        navigation=_arrival_navigation(source=screen),
    )
    source, _gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)

    calls = _locator_calls(source)
    assert calls, "expected at least one by_role/by_css call to check"
    for call in calls:
        for value in _string_args(call):
            assert "`" not in value, f"a code-span backtick reached a compiled locator argument: {value!r}"
        kwargs = _call_kwargs(call)
        attr = _call_attr(call)
        role = kwargs.get("role") if attr == "by_role" else None
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


def test_a_bullet_value_wrapped_across_source_lines_still_compiles() -> None:
    """A long `name:` is prose an author wraps at the margin, and the reader hands back the newlines."""
    screen = "docs/features/policy/gui/screens/policy-list.md"
    context = _navigation_context(
        _page_obligation("okf:policy-list:wrapped:visible:1", f"{screen}#wrapped",
                          locators={"role": ["button"],
                                    "name": ["`Cancel the policy and\nrefund the remaining term`"]},
                          checks=[_visible("button:Cancel the policy")]),
        navigation=_arrival_navigation(source=screen),
    )
    source, _gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert '"Cancel the policy and refund the remaining term"' in source


def test_an_unavailable_role_set_degrades_to_a_selector_never_to_skipped_validation(monkeypatch) -> None:
    """Finding 9: when Playwright's `AriaRole` set cannot be derived (the `qa` extra missing, or a future playwright release moving the private module), `_MATCHABLE_ROLES` is `None` — and that must never be read as "validation is optional." `role: generic` must still not compile to `by_role("generic")`; it must fall through to `selector:` exactly as when the role set is known and `generic` is excluded from it."""
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
    assert source is not None
    ast.parse(source)
    assert 'by_role("generic"' not in source
    assert 'by_css("dl")' in source


def _located(locator: str, node: str, locators: dict) -> dict:
    """A `visible(locator=...)` row the packet already resolved to a declared component."""
    row = _visible(locator)
    row["locates"] = {"locator": {"node": node, "locators": locators}}
    return row


def test_a_check_is_pointed_at_the_component_its_locator_names() -> None:
    """The claim is the form's; the thing that shows the refusal is a span declared beside it."""
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
    assert source is not None
    ast.parse(source)
    assert "#name-error" in source
    assert 'name="New policy"' not in source
    assert 'locator="#name-error"' in source
    assert _gap_kinds(gaps, oid) == []


def test_a_check_locator_that_names_no_component_compiles_to_nothing() -> None:
    """`doctor` refuses this book; `compile_plan` is not `doctor`'s downstream and still sees it."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["undeclared-check-locator"]


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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]


def test_an_undetermined_claim_combiner_emits_no_code_at_all() -> None:
    """A claim whose siblings may be alternatives is undetermined, and undetermined never runs."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unstated-claim-combiner"]


def test_an_interactions_check_is_pointed_at_the_component_it_names() -> None:
    """An interaction's claim is observed by whatever the check names, not by the interaction."""
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
    assert source is not None
    ast.parse(source)
    interactions = [s for s in source.split("@scenario(")[1:] if "submit_new_policy(" in s]
    assert len(interactions) == 1
    assert 'qa.by_role("table", name="Policies on file")' in interactions[0]
    assert 'locator="#policy-table"' in interactions[0]
    assert _gap_kinds(gaps, interaction_oid) == ["unresolved-precondition"]
    assert interaction_oid in _covers(source)


def test_an_interaction_with_no_on_locator_emits_no_assertion() -> None:
    """A click with nowhere real to land is not a weaker version of the interaction — it is not the interaction at all, so nothing it would have proven is emitted."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, interaction_oid) == ["unresolved-precondition"]


def test_the_scaffold_click_gap_does_not_claim_does_is_unresolved() -> None:
    """The generic `unresolved-precondition` gap here only ever established one fact: the trigger compiles to a scaffold click, not a verified action."""
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
    """The `open-new-widget` shape: a real `covers=[...]` claim stands beside its own gap on purpose (`_ARRANGEMENT_GAPS`)."""
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
    """The mirror: a `submit-new-policy` with nowhere real to land compiles no assertion at all (`test_an_interaction_with_no_on_locator_emits_no_assertion`) — its whole gap is that the reference compiler produced no evidence for it, so it must be named as deferred."""
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
    """The producer half: the packet handed to `write_context` carries the reason inline, so a consumer (`validate_v2`) reads it off the obligation rather than recompiling."""
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
    """The real `globex` `new-widget.md` shape: a happy arm and its `extends:`-linked refusal arm share one resolved `on:` button and no fixture that fills the form either declares."""
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
    assert source is not None
    ast.parse(source)
    assert "#widget-table" not in source
    assert "#name-error" not in source
    assert submit_oid not in _covers(source)
    assert refuse_oid not in _covers(source)
    assert _gap_kinds(gaps, submit_oid) == ["unarranged-interaction-precondition"]
    assert _gap_kinds(gaps, refuse_oid) == ["unarranged-interaction-precondition"]


def test_an_arranged_interaction_arm_performs_its_acts_and_compiles_its_assertion() -> None:
    """The same two arms, with the happy one declaring the acts its `when:` needs."""
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
    assert source is not None
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
    assert fills[1] < clicks[0]
    assert "unarranged-interaction-precondition" not in _gap_kinds(gaps, submit_oid)
    assert submit_oid in _covers(source)
    assert "#saved-banner" in source
    assert "`name` non-empty and `quantity` a non-negative number" in source
    assert _gap_kinds(gaps, refuse_oid) == ["unarranged-interaction-precondition"]
    assert refuse_oid not in _covers(source)


def test_an_act_whose_subject_has_no_locator_withholds_the_whole_arrangement() -> None:
    """A `when:` is arranged by the whole sequence the book wrote, so half of it is not a weaker arrangement — it is a state no arm declares, neither the documented precondition nor the page's accidental default."""
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
    assert source is not None
    ast.parse(source)
    assert ".fill(" not in source
    assert _gap_kinds(gaps, submit_oid) == ["unarranged-interaction-precondition"]
    assert submit_oid not in _covers(source)


def test_an_arms_acts_reach_the_builder_from_the_bullet_that_declares_no_check() -> None:
    """The shape a real packet produces, and the one the two tests above do not write."""
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
    assert source is not None
    ast.parse(source)
    lines = source.splitlines()
    fills = [i for i, line in enumerate(lines) if ".fill(" in line]
    clicks = [i for i, line in enumerate(lines) if "# trigger:" in line]
    assert len(fills) == 2, source
    assert fills[1] < clicks[0]
    assert "unarranged-interaction-precondition" not in _gap_kinds(gaps, does_oid)
    assert does_oid in _covers(source)


def test_a_journey_step_performs_its_own_acts_before_it_triggers_it() -> None:
    """The performer of a step is the only actor that can establish state on the surface it performs on, and a journey performs this step itself — so the step's `arrange:` bullets are performed here, in the same window `_interaction_scenario` uses when it compiles the same interaction alone."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source), [g for g in gaps if g.obligation_id == oid]
    journey = source.split("@scenario(")[-1]
    first = journey.index('"#open-link"')
    fill = journey.index('.fill("Widget A")')
    second = journey.index('"#save-button"')
    assert first < fill < second


def test_a_wrapped_book_bullet_still_compiles_to_valid_python() -> None:
    """A `does:`/`trigger:` value that wrapped across lines in the book source is still just one string by the time `qa context` hands it here — nothing marks where the line broke."""
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
    assert source is not None
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
    """A compiled call the check vocabulary refuses is a plan `ostler qa validate` rejects."""
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
    assert source is not None
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
    """Presence is what a role locator proves; placement is what it cannot."""
    oid = "okf:new-policy:form:role:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#new-policy-form",
                          locators={"role": ["form"], "name": ["New policy"]},
                          checks=[_visible("form:New policy")]),
        navigation=_arrival_navigation(),
    )
    source, _ = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    assert _vetted(source) == [_SCREEN]


def test_an_interaction_photographs_the_screen_its_checks_name() -> None:
    """The state an interaction's claims are about is the one the trigger produced."""
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
        screen_routes={_SCREEN: "/new-policy", elsewhere: "/policies"},
    )
    source, _ = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    interactions = [s for s in source.split("@scenario(")[1:] if "submit_new_policy(" in s]
    assert len(interactions) == 1
    assert re.findall(r"qa\.vet\(\"(.+?)\"\)", interactions[0]) == [elsewhere]
    assert interactions[0].index(".click()") < interactions[0].index("qa.vet(")


def test_an_obligation_half_of_whose_checks_compile_is_claimed_by_nobody() -> None:
    """A claim whose refusal is visible on screen *and* leaves a stored count alone is one claim, and `unchanged` observes a `subject` no browser can see."""
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
    assert source is not None
    ast.parse(source)
    assert oid not in _covers(source)
    assert "#name-error" not in source
    assert "uncompilable-claim" in _gap_kinds(gaps, oid)




def test_a_two_surface_book_compiles_two_different_base_urls() -> None:
    """The `api` target's address comes from the http obligation's own surface, and the `web` target's from the page obligation's — a book with two services on two ports must not see either one's address bleed onto the other's target line."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert gaps == []
    assert 'api_service_api = target("api_service_api", driver="python", ' \
        'base_url="http://localhost:18101")' in source
    assert 'web_app_web = target("web_app_web", driver="playwright", ' \
        'base_url="http://localhost:18102")' in source


def test_two_surfaces_sharing_one_driver_kind_each_keep_their_own_address() -> None:
    """Two http surfaces — not one http surface and one page surface — land in the *same* `http_owed` partition (both are `_is_page_obligation` false), which is exactly the case the old `known[0]` alphabetic-first fallback used to collapse onto one address."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert gaps == []
    assert 'alpha_service_api = target("alpha_service_api", driver="python", ' \
        'base_url="http://localhost:18201")' in source
    assert 'zulu_service_api = target("zulu_service_api", driver="python", ' \
        'base_url="http://localhost:18202")' in source
    assert "    target=alpha_service_api,\n" in source
    assert "    target=zulu_service_api,\n" in source


def test_a_surface_with_no_entry_url_and_no_fallback_gaps_instead_of_guessing() -> None:
    """No `--base-url` and no book-stated `entry-url:` on this obligation's surface: the compiler drops it as `undeclared-entry-url` rather than compiling it against an address nobody wrote down — the failure mode Phase 2h exists to replace (one CLI default applied to every surface, right or wrong)."""
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
    context["navigation"] = {"api-service": {"driver": "http"}}
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["undeclared-entry-url"]


def test_a_checkless_obligation_on_a_surface_with_no_entry_url_is_book_debt_not_undeclared_entry_url() -> None:
    """A bucket that names a performer cannot also carry the things nothing performs: a check-less obligation has no claim for any driver to dispatch, so an unrelated surface with no `entry-url:` must not decide its gap kind."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    context = _context(
        _obligation(oid, surface="api-service"),
    )
    context["navigation"] = {"api-service": {"driver": "http"}}
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["no-verify-declared"]
    assert "undeclared-entry-url" not in {g.kind for g in result.gaps}


def _settled_origin_context(oid: str, entry_url: str) -> dict:
    """A surface whose address the engine settled on: several sources may have stated one, and `qa context` read them in §4.1 driver order and put the winner in `entryUrl`."""
    context = _context(
        _obligation(
            oid,
            surface="api-service",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
    )
    context["navigation"] = {"api-service": {"driver": "http", "entryUrl": entry_url}}
    return context


def test_an_address_the_book_states_outranks_the_operators_base_url() -> None:
    """`--base-url` answers a book that states no address."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    result = _compile_plan_gaps(_settled_origin_context(oid, "http://localhost:18101"),
                                story="demo-story", base_url="http://localhost:8000")
    assert isinstance(result, Plan)
    assert result.gaps == []
    assert 'base_url="http://localhost:18101"' in result.source
    assert "localhost:8000" not in result.source


def test_a_surface_stating_no_address_compiles_against_the_base_url() -> None:
    """Non-vacuity for the test above: the same obligation with the surface's own address removed — the only difference — takes the operator's flag rather than gapping, so the verdict there is a verdict on the book outranking the flag and not on the flag being unusable."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    context = _settled_origin_context(oid, "http://localhost:18101")
    del context["navigation"]["api-service"]["entryUrl"]
    result = _compile_plan_gaps(context, story="demo-story", base_url="http://localhost:8000")
    assert isinstance(result, Plan)
    assert result.gaps == []
    assert 'base_url="http://localhost:8000"' in result.source


def _driverless_context(oid: str) -> dict:
    """A surface no runbook states a `driver:` for: the engine reads every runbook covering the surface, so `driver` is `None` only when none of them states one at all."""
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
    context["navigation"] = {"api-service": {"driver": None}}
    return context


def test_a_surface_stating_no_driver_at_all_gaps_the_absence() -> None:
    """D1's dispatch table (§4.1) has nothing to look the performer up by, so the obligation cannot be compiled — and the message says the book states no `driver:`, which is the remedy: write one on a runbook covering the surface."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    result = _compile_plan_gaps(_driverless_context(oid), story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    assert "states no `driver:`" in result.gaps[0].detail


def test_a_surface_whose_runbooks_settled_on_a_driver_compiles_the_claim() -> None:
    """Non-vacuity for the test above: the same obligation with a settled `driver:` — the only difference — compiles, so the gap there is a verdict on the absence and not on the shape of the obligation."""
    oid = "okf:docs/features/acme/api.md#post-things:does:1"
    context = _driverless_context(oid)
    context["navigation"]["api-service"] = {"driver": "http", "entryUrl": "http://localhost:18101"}
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert result.gaps == []


def test_a_selector_the_census_cannot_read_still_compiles_one_whole_scenario() -> None:
    """Phase 3p': a compile-time gap is a statement about the plan being compiled, and vet's render census is a different observer."""
    oid = "okf:docs/features/policy/gui/screens/policy-list.md#seat-grid:verify:1"
    context = _navigation_context(
        _page_obligation(
            oid, "seat-grid",
            locators={"selector": ['[data-state="booked"]']},
            checks=[_visible('[data-state="booked"]')],
        ),
        navigation=_arrival_navigation(),
    )
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    assert r'locator="[data-state=\"booked\"]"' in source




def _scenarios(source: str) -> list[str]:
    return source.split("@scenario(")[1:]


def _http_status(code: int, path: str) -> dict[str, object]:
    return {"call": f'http_status(code={code}, path="{path}")', "name": "http_status",
            "args": {"code": code, "path": path}}


def test_a_page_claim_about_the_response_its_click_provoked_compiles_whole() -> None:
    """The globex shape: submitting the form is refused, the error span appears, and the page's own POST answered 400."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    assert "uncompilable-claim" not in _gap_kinds(gaps, oid)
    assert 'qa.verify("http_status", exchanges.response_for("/api/policies")' in source
    assert 'qa.verify("json_path", exchanges.response_for("/api/policies").json()' in source
    interactions = [s for s in _scenarios(source) if ".click()" in s]
    assert len(interactions) == 1
    assert interactions[0].index("qa.window()") < interactions[0].index(".click()")


def test_an_arrival_claim_about_a_response_opens_its_window_before_the_navigation() -> None:
    """An arrival scenario's action is `qa.goto`, so the same rule puts the window first — a response recorded before the page was asked for is not an observation of the arrival."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  _http_status(200, "/api/policies")]),
        navigation=_arrival_navigation(),
    )
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    [arrival] = [s for s in _scenarios(source) if "qa.goto(" in s]
    assert arrival.index("qa.window()") < arrival.index("qa.goto(")


def test_an_obligation_naming_two_routes_is_two_claims_and_emits_nothing_executable() -> None:
    """Undetermined ⇒ do not emit executable code."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file"),
                                  _http_status(200, "/api/policies"),
                                  _http_status(200, "/api/agents")]),
        navigation=_arrival_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert "uncompilable-claim" in _gap_kinds(result.gaps, oid)


def test_a_page_scenario_with_no_http_claim_binds_no_window() -> None:
    """The window is emitted because a row needs it, not because the scenario is a page one — a plan that reads no exchange should not carry a name nothing reads."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
    )
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    assert "qa.window()" not in _result.source


def test_a_node_nobody_performs_is_observed_by_the_driver_of_its_own_surface() -> None:
    """A `flow` orders steps that are performed; a `component`, a `screen`, and a `field` are places a claim is true."""
    for node_type in ("flow", "component", "screen", "field"):
        assert _dispatch_target(node_type, "web") == ("playwright", "", "")
        assert _dispatch_target(node_type, "http") == ("http", "", "")
        assert _dispatch_target(node_type, "cli") == ("cli", "", "")
        assert _dispatch_target(node_type, "mobile") == ("maestro", "", "")
    target, detail, kind = _dispatch_target("interaction", "http")
    assert target is None and "names no target" in detail
    assert kind == "uncompilable-claim"


def test_a_concept_node_gets_its_own_gap_message_not_a_generic_no_row_for() -> None:
    """`concept` names no row in `_OBSERVE_ROW` or `_DISPATCH_TABLE` either, exactly like an unrouted type — but it is unrouted for a different reason: a concept is a definition, not a place a claim is observed, so no row is owed and the generic "names no row for" phrasing would mislead an author into adding one."""
    target, detail, kind = _dispatch_target("concept", "web")
    assert target is None
    assert kind == "uncompilable-claim"
    assert "definition" in detail
    assert "names no row for" not in detail
    other_target, other_detail, other_kind = _dispatch_target("widget", "web")
    assert other_target is None
    assert other_kind == "uncompilable-claim"
    assert "names no row for" in other_detail
    assert "definition" not in other_detail


def test_a_field_claim_compiles_on_the_screen_it_sits_on() -> None:
    """A `field` node's own claim, on a `web`-driven surface, compiles to a real Playwright observation rather than to `uncompilable-claim` — the end-to-end counterpart of the dispatch-level assertion above, run through the page builder the way a `component`'s claim already is."""
    oid = "okf:policy-list:vin-field:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#vin-field",
                          locators={"role": ["textbox"], "name": ["Vehicle VIN"]},
                          checks=[_visible("textbox:Vehicle VIN")]),
        navigation=_arrival_navigation(),
    )
    context["obligations"][0]["nodeType"] = "field"
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert "textbox:Vehicle VIN" in source
    assert _gap_kinds(gaps, oid) == []


def test_a_field_claim_on_a_cli_surface_compiles_through_the_cli_builder() -> None:
    """The same claim, on a `cli`-driven surface: `field` reaches the cli builder through `_OBSERVE_ROW` exactly as `command` reaches it through `_DISPATCH_TABLE`'s invariant row."""
    oid = "okf:built-target-probe:field:exit-status:1"
    context = _context(
        _obligation(
            oid,
            nodeType="field",
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
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == []


def test_a_concept_claim_still_does_not_compile_with_the_new_message() -> None:
    """Even with a well-formed check declared, a `concept` claim still fails to compile — the change is the message, not the outcome."""
    oid = "okf:docs/features/demo/concepts/policy.md:contract:1"
    context = _context(
        _obligation(
            oid,
            nodeType="concept",
            checksDeclared=[
                {"call": "created", "name": "http_status", "args": {"code": 201, "path": "/api/x"}},
            ],
        )
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    (gap,) = [g for g in result.gaps if g.obligation_id == oid]
    assert "definition" in gap.detail


def _located_visible(node: str, locators: dict) -> dict:
    """A `visible(locator=…)` whose reference the packet already resolved to *node*."""
    row = _visible(node)
    row["locates"] = {"locator": {"node": node, "locators": locators}}
    return row


def _step(ref: str, node_type: str, surface: str) -> dict:
    return {"ref": ref, "href": ref.split("#")[-1], "nodeType": node_type, "surface": surface}


def _flow_obligation(oid: str, *, source: str, surface: str, steps: list[dict],
                     checks: list[dict], fixtures: list[dict] | None = None) -> dict:
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
    """A flow's claim is about what its `steps:` did, so a flow that names none states a claim about a journey nobody wrote down."""
    oid = "okf:docs/features/policy/flows/file-a-policy.md:end-state"
    context = _navigation_context(
        _obligation(oid, nodeType="flow", surface="policy",
                    source="docs/features/policy/flows/file-a-policy.md",
                    locators={}, checksDeclared=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "`steps:`" in gap.detail and "names no steps to walk" in gap.detail


def test_a_journeys_claim_is_observed_where_its_last_step_left_the_world() -> None:
    """The steps are performed in the order the book wrote them, and the flow's own `verify:` is asserted against the *last* step's response — the only world this scenario actually produced."""
    oid = f"okf:{_FLOW}:end-state"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api"),
                   _step(f"{_API}#get-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                                   "path": "/api/things"}}],
        ),
        _step_node(f"{_API}#post-things", {"route": ["DELETE /api/things"]}),
        _step_node(f"{_API}#get-things", {"route": ["GET /api/things"]}),
        navigation=_api_navigation(),
    )
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    post = source.index('observed_1 = qa.http.delete("/api/things"')
    get = source.index('observed_2 = qa.http.get("/api/things")')
    assert post < get
    assert 'qa.verify("http_status", observed_2' in source
    assert 'qa.verify("http_status", observed_1' not in source
    assert _gap_kinds(gaps, oid) == []


def test_a_journey_step_captures_a_field_its_own_verify_then_reads_back() -> None:
    """A `$.`-rooted capture on a step's node is a fact the *flow's own* `verify:` — running in this same scenario, after every step — is entitled to read back, the same way a strictly later obligation reads a `_scenario_body` capture back."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    post_node["actsDeclared"] = [_body_act("name", "Widget A")]
    post_node["capturesDeclared"] = [{"name": "widget_id", "from": "$.thing.id"}]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status",
                    "args": {"status": 201, "path": "/api/things", "detail": "$widget_id"}}],
        ),
        post_node,
        navigation=_api_navigation(),
    )
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    capture = source.index('qa.capture_field("widget_id", observed_1.json(), "thing.id")')
    verify = source.index('qa.verify("http_status"')
    assert capture < verify
    assert 'detail=qa.resolve("$widget_id")' in source
    assert _gap_kinds(gaps, oid) == []


def test_a_journeys_own_verify_referencing_nothing_captured_withdraws_it() -> None:
    """`$name` names a fact a `capture:` bullet must actually have produced in this same walk — a flow's own `verify:` that names one nothing captured is `unresolved-precondition`, the same as any other reference a `_scenario_body` obligation cannot resolve, and — because a `verify:` set is a conjunction — the whole obligation withdraws rather than emitting the rows that happened to resolve on their own."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    post_node["actsDeclared"] = [_body_act("name", "Widget A")]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status",
                    "args": {"status": 201, "path": "/api/things", "detail": "$widget_id"}}],
        ),
        post_node,
        navigation=_api_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unresolved-precondition"]


def test_a_journeys_own_verify_withdraws_wholesale_not_row_by_row() -> None:
    """Two rows on the same flow obligation, only one of which references a capture nothing produced: the conjunction rule withdraws both, not just the one that referenced it — the same `whole`-obligation rule `_scenario_body` applies to a row `_operand` cannot observe, carried here to a row a reference cannot resolve."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {"route": ["POST /api/things"]})
    post_node["actsDeclared"] = [_body_act("name", "Widget A")]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[
                {"call": "it", "name": "http_status",
                 "args": {"status": 201, "path": "/api/things", "detail": "$widget_id"}},
                {"call": "it", "name": "http_status",
                 "args": {"code": 201, "path": "/api/things"}},
            ],
        ),
        post_node,
        navigation=_api_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unresolved-precondition"]


def test_a_capture_on_a_step_the_journey_cannot_compile_is_still_declined() -> None:
    """A step whose node carries no `route:` withholds the whole journey (`uncompilable-claim`), exactly as `test_a_flow_that_names_no_steps_has_no_walk_to_compile`'s sibling cases do — and a `capture:` declared on that same node names a response this journey never holds either."""
    oid = f"okf:{_FLOW}:end-state"
    post_node = _step_node(f"{_API}#post-things", {})
    post_node["capturesDeclared"] = [{"name": "widget_id", "from": "$.thing.id"}]
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status",
                    "args": {"status": 201, "path": "/api/things"}}],
        ),
        post_node,
        navigation=_api_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    assert _gap_kinds(result.gaps, post_node["id"]) == ["uncaptured-declaration"]


def test_a_journey_step_sends_the_body_its_node_arranges() -> None:
    """Node-level, unlike the arm-level read in `_scenario_body`'s own tests: a journey step names a node, not an arm, so `_http_journey` reads `acts_by_node` the same way a step's `fill:` acts already are — merged across every obligation sharing that node."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    assert 'json_body={"name": "Widget A", "quantity": 3}' in source


def test_a_journey_step_with_a_contradictory_body_is_unarranged() -> None:
    """Phase 1's limitation, named explicitly: two arms of the same node stating different values for the same field merge to a contradiction, not a body any request could carry, so the step withholds the whole request exactly as a half-performable one already does."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-request-body"]


def test_a_journey_step_ignores_its_nodes_refusal_arm_arrangement() -> None:
    """A journey's steps causally chain, so it can only ever be walking the arm that leaves something for the next step to read back — never the refusal arm (`errors:`/`error:`, `registry.refusal_keys`)."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    assert _gap_kinds(gaps, oid) == []
    assert 'json_body={"name": "Widget A", "quantity": 3}' in source


def test_a_journey_step_whose_node_only_declares_a_refusal_arm_is_unarranged() -> None:
    """A node whose only declared arm is the refusal arm merges to no acts at all once that arm is excluded — not "nothing declared" the way a step that genuinely needs no body would read, so it withholds the request and gaps exactly as an unbuildable body already does, rather than silently sending `json_body={}`."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-request-body"]


def test_a_journey_step_with_an_unrecognized_method_is_an_invalid_http_method() -> None:
    """The node-level check mirrors `_scenario_body`'s: a step whose node states a `method:` that does not parse as an HTTP verb is undetermined, so `_http_journey` withholds the whole journey rather than falling through to `unarranged-request-body`."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["invalid-http-method"]


def test_a_check_naming_another_steps_path_is_not_about_this_journeys_end() -> None:
    """A journey's claim is about the world its last step left."""
    oid = f"okf:{_FLOW}:end-state"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api"),
                   _step(f"{_API}#get-health", "endpoint", "api")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 201,
                                                                   "path": "/api/things"}}],
        ),
        _step_node(f"{_API}#post-things", {"route": ["DELETE /api/things"]}),
        _step_node(f"{_API}#get-health", {"route": ["GET /healthz"]}),
        navigation=_api_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert "uncompilable-claim" in _gap_kinds(result.gaps, oid)
    [gap] = [g for g in result.gaps if g.obligation_id == oid and g.kind == "uncompilable-claim"]
    assert "/healthz" in gap.detail and "its last step left" in gap.detail


def test_a_journeys_json_path_check_is_not_about_a_route_at_all() -> None:
    """`json_path.path` is an identifier into the response *document*, not a route — unlike `http_status.path`, which the guard above this one withholds a journey's own `verify:` for."""
    oid = f"okf:{_FLOW}:end-state"
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="api",
            steps=[_step(f"{_API}#post-things", "endpoint", "api"),
                   _step(f"{_API}#get-things", "endpoint", "api")],
            checks=[{"call": "it", "name": "json_path",
                     "args": {"path": "$.widgets[0].status", "equals": "Draft"}}],
        ),
        _step_node(f"{_API}#post-things", {"route": ["DELETE /api/things"]}),
        _step_node(f"{_API}#get-things", {"route": ["GET /api/things"]}),
        navigation=_api_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    source, gaps = result.source, result.gaps
    ast.parse(source)
    assert oid in _covers(source)
    assert 'qa.verify("json_path", observed_2.json()' in source
    assert _gap_kinds(gaps, oid) == []


def test_two_surfaces_with_same_named_flows_compile_to_distinct_scenario_names() -> None:
    """`_slug` names a compiled scenario from its book's path, and a stem alone throws away the directory the surface lives in."""
    web_api = "web-app/http/api.md"
    mobile_api = "mobile-app/http/api.md"
    web_flow = "web-app/flows/browse-and-add-widget.md"
    mobile_flow = "mobile-app/flows/browse-and-add-widget.md"
    navigation = {
        "web_app": {"start": web_api, "surface": "web_app", "driver": "http",
                    "entryUrl": _BASE_URL, "counts": {}, "routes": {}, "unreachable": [],
                    "undeclared": []},
        "mobile_app": {"start": mobile_api, "surface": "mobile_app", "driver": "http",
                       "entryUrl": _BASE_URL, "counts": {}, "routes": {}, "unreachable": [],
                       "undeclared": []},
    }
    web_oid = f"okf:{web_flow}:end-state"
    mobile_oid = f"okf:{mobile_flow}:end-state"
    context = _navigation_context(
        _flow_obligation(
            web_oid, source=web_flow, surface="web_app",
            steps=[_step(f"{web_api}#post-things", "endpoint", "web_app")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                                    "path": "/api/things"}}],
        ),
        _flow_obligation(
            mobile_oid, source=mobile_flow, surface="mobile_app",
            steps=[_step(f"{mobile_api}#post-things", "endpoint", "mobile_app")],
            checks=[{"call": "it", "name": "http_status", "args": {"status": 200,
                                                                    "path": "/api/things"}}],
        ),
        _step_node(f"{web_api}#post-things", {"route": ["DELETE /api/things"]}),
        _step_node(f"{mobile_api}#post-things", {"route": ["DELETE /api/things"]}),
        navigation=navigation,
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    source, gaps = result.source, result.gaps
    ast.parse(source)
    names = re.findall(r"^def (\w+_journey)\(qa: Qa\) -> None:$", source, re.MULTILINE)
    assert len(names) == 2
    assert len(set(names)) == 2
    assert _gap_kinds(gaps, web_oid) == []
    assert _gap_kinds(gaps, mobile_oid) == []


def test_a_journey_across_two_targets_has_no_scenario_shape_to_fit_into() -> None:
    """A target is the pairing of a driver with a service, and `@scenario(target=...)` binds exactly one."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["needs-multi-target-runtime"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "binds one driver to one service" in gap.detail
    assert "http on 'api'" in gap.detail and "playwright on 'policy'" in gap.detail


def test_a_mobile_step_with_no_selector_is_the_books_to_finish_not_a_backend_gap() -> None:
    """D1's table names `maestro` for an interaction on a mobile surface, and this compiler now builds that path — so a mobile step whose own node states no `testID=` selector and no `name:` to fall back on gaps `uncompilable-claim`, the book's own gap, rather than `needs-target-backend`: the backend exists, and there is nothing wrong here a maestro builder could have compiled around."""
    oid = f"okf:{_SCREEN}#open-thing:does:1"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    navigation["policy"]["bundleId"] = "com.example.mobile-app"
    navigation["policy"]["launchScreen"] = _SCREEN
    context = _navigation_context(
        _obligation(oid, nodeType="interaction", source=_SCREEN, surface="policy",
                    checksDeclared=[_visible("table:Things on file")]),
        navigation=navigation,
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "testID" in gap.detail and "name:" in gap.detail


def test_a_step_whose_driver_the_book_never_states_is_still_the_books_to_fix() -> None:
    """The other side of the same branch, and the reason the two need different kinds: with no `driver:` on the surface the table cannot be read at all, and that *is* something an author goes and writes."""
    oid = f"okf:{_SCREEN}#open-thing:does:1"
    navigation = _arrival_navigation()
    del navigation["policy"]["driver"]
    context = _navigation_context(
        _obligation(oid, nodeType="interaction", source=_SCREEN, surface="policy",
                    checksDeclared=[_visible("table:Things on file")]),
        navigation=navigation,
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]


def test_a_mobile_journey_step_with_no_selector_gaps_uncompilable_claim() -> None:
    """Every step dispatches to one target, so there is no crossing to report — the single target is `maestro`, which this compiler now builds."""
    oid = f"okf:{_FLOW}:end-state"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    navigation["policy"]["bundleId"] = "com.example.mobile-app"
    navigation["policy"]["launchScreen"] = _SCREEN
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="policy",
            steps=[_step(f"{_SCREEN}#open-thing", "interaction", "policy")],
            checks=[_visible("table:Things on file")],
        ),
        navigation=navigation,
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]


def test_a_web_journey_arrives_then_clicks_every_step_in_order() -> None:
    """The journey walks to the screen its first step lives on and performs each `interaction` in document order; the flow's own `verify:` is observed after the last click, where the walk left the page."""
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
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert oid in _covers(source), [g for g in gaps if g.obligation_id == oid]
    goto = source.index("qa.goto(")
    first = source.index('"#open-link"')
    second = source.index('"#save-button"')
    assert goto < first < second
    assert second < source.rindex("#things-table")


def test_a_web_journey_with_no_root_path_gaps_uncompilable_claim_not_a_fabricated_root() -> None:
    """The journey side of the same catch-all removal: a driver with no path grammar states no `rootPath`, so the journey gaps `uncompilable-claim` naming the missing root instead of opening on a fabricated `qa.goto("/")` — no step is compiled and no claim is asserted in a world the walk never actually reached."""
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
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    detail = next(g.detail for g in result.gaps if g.obligation_id == oid)
    assert "root path a journey can open from" in detail


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
    """A journey's claims are about the world its steps left, and the world its steps left is the world they started in plus the walk."""
    oid, context = _unarranged_journey_context()
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unarranged-journey"]


def test_a_journey_that_says_it_needs_no_arrangement_compiles() -> None:
    """The author who decided the journey holds in whatever world it finds can say so, and that is a different packet from the author who never looked — which is the whole reason `arrangesNothing` is carried beside `fixturesDeclared` rather than folded into it."""
    oid, context = _unarranged_journey_context(arrangesNothing=True)
    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps
    ast.parse(source)
    assert _gap_kinds(gaps, oid) == []
    assert oid in _covers(source)
    assert "    preconditions=[\n    ],\n" in source


def test_a_scenario_ending_on_a_parameterised_route_vets_nothing() -> None:
    """A screen addressed by `/links/:id/edit` names a family of pages, not one page."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
        screen_routes={_SCREEN: "/policies/:id/edit"},
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    assert _vetted(source) == []
    unidentifiable = [gap for gap in gaps if gap.kind == "unidentifiable-screen"]
    assert [gap.obligation_id for gap in unidentifiable] == [oid]
    assert "/policies/:id/edit" in unidentifiable[0].detail
    assert f'covers=["{oid}"]' in source


def test_a_screen_the_book_states_no_route_for_vets_nothing() -> None:
    """Silence and ambiguity reach the compiler the same way: absent from the packet's map."""
    oid = "okf:policy-list:policy-table:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#policy-table",
                          locators={"role": ["table"], "name": ["Policies on file"]},
                          checks=[_visible("table:Policies on file")]),
        navigation=_arrival_navigation(),
        screen_routes={},
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    assert _vetted(source) == []
    detail = next(gap.detail for gap in gaps if gap.kind == "unidentifiable-screen")
    assert "no single `route:`" in detail


def test_a_route_that_is_not_a_path_is_reported_as_one_not_as_a_pattern() -> None:
    """A book reverse-engineered from a framework writes the route's *name* in this bullet."""
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
    """A rejected `fixture:` bullet and an absent one are not the same state of the book."""
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

    result = _compile_plan_gaps(context, story="demo-story")

    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unparsed-fixture"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "Seeded Ledger" in gap.detail and "is not a fixture name" in gap.detail
    assert "unarranged-journey" not in {g.kind for g in result.gaps}


def test_a_fixture_providing_a_fact_of_undetermined_source_compiles_nothing() -> None:
    """A `provides:` entry stating neither `from:`/`read:` nor `is:` is an undetermined arrangement."""
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

    result = _compile_plan_gaps(context, story="demo-story")

    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["undetermined-provided-fact"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "seeded-ledger" in gap.detail and "seeded-ledger.total" in gap.detail


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

    result = _compile_plan_gaps(context, story="demo-story")

    assert "undetermined-provided-fact" not in {g.kind for g in result.gaps}


def test_a_verify_bullet_the_parser_refused_is_not_a_node_that_declared_no_check() -> None:
    """The gap said the book declares no check, to an author who declared one and misspelled it."""
    oid = f"okf:{_SCREEN}#policy-table:contract"
    obligation = _page_obligation(oid, f"{_SCREEN}#policy-table",
                                  locators={"role": ["table"], "name": ["Policies on file"]},
                                  checks=[])
    obligation["checksUnparsed"] = [
        {"value": "visble(table:Policies on file)", "kind": "unknown-check",
         "problem": "names no check in the vocabulary"},
    ]
    context = _navigation_context(obligation, navigation=_arrival_navigation())

    result = _compile_plan_gaps(context, story="demo-story")

    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unparsed-check-bullet"]
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert "visble(table:Policies on file)" in gap.detail
    assert "names no check in the vocabulary" in gap.detail
    assert "no-verify-declared" not in {g.kind for g in result.gaps}


def test_a_capture_bullet_the_parser_refused_gaps_where_it_was_written() -> None:
    """A refused `capture:` costs this claim nothing and costs a later `$name` everything."""
    oid = f"okf:{_SCREEN}#policy-table:contract"
    obligation = _page_obligation(oid, f"{_SCREEN}#policy-table",
                                  locators={"role": ["table"], "name": ["Policies on file"]},
                                  checks=[_visible("table:Policies on file")])
    obligation["capturesUnparsed"] = [
        {"value": "claim_id $.id", "problem": "names no source"},
    ]
    context = _navigation_context(obligation, navigation=_arrival_navigation())

    _result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(_result, Plan)
    source, gaps = _result.source, _result.gaps

    ast.parse(source)
    [gap] = [g for g in gaps if g.kind == "unparsed-capture-bullet"]
    assert gap.obligation_id == oid
    assert "claim_id $.id" in gap.detail
    assert "names no source" in gap.detail
    assert oid in _covers(source)


def test_a_capture_no_builder_can_emit_stands_beside_the_claim_rather_than_against_it() -> None:
    """A UI-locator capture on a routed obligation: the assertion compiles, the binding does not."""
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
    result = _compile_plan_gaps(
        context, story="demo-story", base_url=_BASE_URL, covered_ids=covered)

    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == ["uncaptured-declaration"]
    assert oid in covered
    assert "qa.capture_field(" not in result.source
    assert "widget_id" in result.source


def test_a_declared_capture_that_no_builder_accounts_for_is_refused() -> None:
    """The guard, exercised by removing the thing it guards."""
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
    """One silence, reported once."""
    oid = "okf:docs/features/acme/api.md#get-things:does:1"
    context = _context(
        _obligation(oid, capturesDeclared=[{"name": "widget_id", "from": "#widget-id"}])
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == ["no-verify-declared"]



_ACKNOWLEDGED_UNBUILT_TARGETS: dict[str, str] = {}


def test_every_reachable_dispatch_target_is_built_or_named_as_an_exclusion() -> None:
    """Completeness: nothing D1's table can dispatch to falls through the floor."""
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
    """The smallest obligation D1 dispatches to `playwright`: an `interaction` on a `web`-driven surface, reachable from an arrival with nothing else to arrange."""
    oid = "okf:built-target-probe:playwright:visible:1"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#probe",
                          locators={"role": ["table"], "name": ["Things on file"]},
                          checks=[_visible("table:Things on file")]),
        navigation=_arrival_navigation(),
    )
    return context, oid


def _built_target_probe_http() -> tuple[dict, str]:
    """The smallest obligation D1 dispatches to `http`: an `endpoint` on the default `http`-driven surface, fully arranged so nothing else could withhold the scenario."""
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
    """The smallest obligation D1 dispatches to `cli`: a `command` on a `cli`-driven surface, with a real check (`exit_status`), a fixture arranged, and a `run:` (`ostler.acts`'s `invoke`) for the check to bind to — so nothing about this obligation is missing except a builder that reads it."""
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
    """`argv` names only the arguments — the executable is the owning `cli` file node's own `binary:` bullet, resolved from `context["cliBinaries"]` by the obligation's shared `source` path."""
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
    context["cliBinaries"] = {}

    _source, gaps = compile_plan_gaps(context, story="demo-story")

    assert _gap_kinds(gaps, oid) == ["uncompilable-claim"]
    (gap,) = [g for g in gaps if g.obligation_id == oid]
    assert "declares no `binary:`" in gap.detail
    assert "cannot name the executable this `run:` invokes" in gap.detail


def test_an_empty_argv_is_a_legal_bare_invocation() -> None:
    """`argv=[]` is a real, empty argument list — a bare invocation of the binary with no arguments — not indistinguishable from "no `run:` at all"."""
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
    assert source is not None

    assert _gap_kinds(gaps, oid) == []
    assert 'qa.tool("tally").run(cwd=qa.scenario_id)' in source


def test_an_invocation_on_a_cli_driven_surface_compiles_to_a_real_scenario() -> None:
    """`invocation` is one of `_OBSERVED_TYPES` — nobody performs it, the claim is observed through whatever drives its surface — so a `cli`-driven surface routes it through `_OBSERVE_ROW` to the same `cli` target `command` reaches through `_DISPATCH_TABLE`."""
    oid = "okf:built-target-probe:invocation:cli:exit-status:1"
    context = _context(
        _obligation(
            oid,
            nodeType="invocation",
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

    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None

    assert _gap_kinds(gaps, oid) == []
    assert "needs-target-backend" not in {g.kind for g in gaps}
    assert "uncompilable-claim" not in {g.kind for g in gaps}
    assert oid in _covers(source)
    assert 'qa.tool("tally").run("import", cwd=qa.scenario_id)' in source


def _built_target_probe_maestro() -> tuple[dict, str]:
    """The smallest obligation D1 dispatches to `maestro`: an `interaction` on a `mobile`-driven surface, its own node carrying a `testID=` selector so the check resolves a locator, and its screen's `route:` shaped as a navigator screen name so `qa.vet` has a document to compare against — nothing about this obligation is missing except a builder that reads it."""
    oid = "okf:built-target-probe:maestro:visible:1"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    navigation["policy"]["bundleId"] = "com.example.mobile-app"
    navigation["policy"]["launchScreen"] = _SCREEN
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#probe",
                          locators={"selector": ["testID=probe-widget"]},
                          checks=[_visible("table:Things on file")],
                          fixtures=[
                              {"name": "seeded-ledger", "args": [], "provides": "a ledger"},
                          ]),
        navigation=navigation,
        screen_routes={_SCREEN: "Probe"},
    )
    return context, oid


_BUILT_TARGET_PROBES = {
    "playwright": _built_target_probe_playwright,
    "http": _built_target_probe_http,
    "cli": _built_target_probe_cli,
    "maestro": _built_target_probe_maestro,
}

_KNOWN_BUILT_TARGET_GAPS: dict[str, str] = {}


def test_every_built_target_has_a_probe() -> None:
    """The probe table direction 2 drives must cover `_BUILT_TARGETS` exactly — a target added there with no probe written is untested, not passing, and this is where that shows up."""
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
    """Direction 2, behavioural: `_BUILT_TARGETS` says this compiler emits a scenario for an obligation dispatched to *target* — so drive the compiler with one and read the plan it hands back, rather than re-asserting a second hardcoded "targets that work" list beside the one under test."""
    context, oid = _BUILT_TARGET_PROBES[target]()
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert oid in _covers(source), (
        f"{target!r} is in _BUILT_TARGETS but the compiler emitted no scenario covering "
        f"{oid!r} — gaps recorded instead: {_gap_kinds(gaps, oid)}"
    )
    assert _gap_kinds(gaps, oid) == []


def test_a_generated_flow_matches_the_hand_written_reference_flows_shape() -> None:
    """Held against `browse-and-add-widget.flow.yaml`, a hand-written flow a fixture author wrote for globex's own mobile app, not against a second expected-text blob this file's author would write from the same belief as the generator itself."""
    reference_path = (
        Path(__file__).resolve().parents[2] / "paddock" / "data" / "apps" / "globex"
        / "app" / "mobile-app" / ".maestro" / "browse-and-add-widget.flow.yaml"
    )
    reference = yaml.safe_load_all(reference_path.read_text())
    reference_header, reference_commands = reference
    assert "appId" in reference_header
    assert reference_commands[0] == "launchApp"

    context, oid = _built_target_probe_maestro()
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert result.files, "expected a maestro obligation to write its own flow file"
    (flow_text,) = result.files.values()

    flow_header, flow_commands = yaml.safe_load_all(flow_text)
    assert "appId" in flow_header
    assert flow_commands[0] == "launchApp"


def test_the_compiled_maestro_target_and_flow_carry_the_books_own_bundle_id() -> None:
    """Both `appId:` sites — the flow YAML header and `target(..., app_id=...)` in the compiled plan — must thread the surface's *own* `bundleId`, not a fixed placeholder."""
    context, oid = _built_target_probe_maestro()
    context["navigation"]["policy"]["bundleId"] = "com.acme.groom"

    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == []
    assert 'app_id="com.acme.groom"' in result.source

    assert result.files, "expected a maestro obligation to write its own flow file"
    (flow_text,) = result.files.values()
    flow_header, _flow_commands = yaml.safe_load_all(flow_text)
    assert flow_header["appId"] == "com.acme.groom"


def test_a_surface_with_no_bundle_id_gaps_undeclared_bundle_id_and_emits_no_maestro() -> None:
    """A mobile obligation whose surface names no `bundle-id:` must not compile against `_MAESTRO_APP_ID`'s old placeholder — it gaps `undeclared-bundle-id` and the plan carries no scenario, no `target(driver=maestro, ...)`, and no flow file for it."""
    context, oid = _built_target_probe_maestro()
    context["navigation"]["policy"]["bundleId"] = None

    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["undeclared-bundle-id"]


def test_a_surface_with_no_launch_screen_gaps_undeclared_launch_screen_and_emits_no_maestro() -> None:
    """Mirrors `test_a_surface_with_no_bundle_id_gaps_undeclared_bundle_id_and_emits_no_maestro`: a settled `bundle-id:` is not enough on its own — a mobile obligation whose surface names no `launch-screen:` still compiles no flow, because the compiler has no way to know which screen a cold `- launchApp` opens on and refuses to guess one."""
    context, oid = _built_target_probe_maestro()
    context["navigation"]["policy"]["launchScreen"] = None

    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["undeclared-launch-screen"]


def test_an_obligation_off_the_launch_screen_gaps_unreachable_from_launch() -> None:
    """A settled `launch-screen:` does not make every mobile obligation reachable: this obligation's own page (`_SCREEN`, via `_built_target_probe_maestro`) is a *different* screen than the one the surface's `launch-screen:` now names, and the book states no way from the one to the other — so it gaps `unreachable-from-launch` rather than compiling a flow that opens on the wrong screen and asserts against it anyway."""
    context, oid = _built_target_probe_maestro()
    other_screen = "docs/features/policy/gui/screens/other.md"
    context["navigation"]["policy"]["launchScreen"] = other_screen

    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["unreachable-from-launch"]
    (gap,) = [g for g in result.gaps if g.obligation_id == oid]
    assert other_screen in gap.detail and _SCREEN in gap.detail


def test_a_mobile_journey_starting_on_the_launch_screen_compiles_end_to_end() -> None:
    """The globex shape, pinned directly: a journey whose *first* step's own page is the surface's settled `launch-screen:` still walks and compiles a flow — exercising `_maestro_journey`'s own first-step-only check, which the standalone obligation path `_built_target_probe_maestro` drives never reaches."""
    oid = f"okf:{_FLOW}:end-state"
    open_thing = f"{_SCREEN}#open-thing"
    save_thing = f"{_SCREEN}#save-thing"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    navigation["policy"]["bundleId"] = "com.example.mobile-app"
    navigation["policy"]["launchScreen"] = _SCREEN
    context = _navigation_context(
        _flow_obligation(
            oid, source=_FLOW, surface="policy",
            steps=[_step(open_thing, "interaction", "policy"),
                   _step(save_thing, "interaction", "policy")],
            checks=[_located_visible(f"{_SCREEN}#things-table",
                                     {"selector": ["testID=things-table"]})],
        ),
        _page_obligation(f"{open_thing}:carrier", open_thing,
                         locators={"on": ["[open-link](#open-link)"]}, checks=[])
            | {"required": False},
        _page_obligation(f"{save_thing}:carrier", save_thing,
                         locators={"on": ["[save-button](#save-button)"]}, checks=[])
            | {"required": False},
        _page_obligation(f"{_SCREEN}#open-link:carrier", f"{_SCREEN}#open-link",
                         locators={"selector": ["testID=open-link"]}, checks=[])
            | {"required": False},
        _page_obligation(f"{_SCREEN}#save-button:carrier", f"{_SCREEN}#save-button",
                         locators={"selector": ["testID=save-button"]}, checks=[])
            | {"required": False},
        navigation=navigation,
        screen_routes={_SCREEN: "Things"},
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == []
    assert oid in _covers(result.source)

    (flow_text,) = result.files.values()
    flow_header, flow_commands = yaml.safe_load_all(flow_text)
    assert flow_commands[0] == "launchApp"
    tap_ids = [c["tapOn"]["id"] for c in flow_commands
              if isinstance(c, dict) and "tapOn" in c]
    assert tap_ids == ["open-link", "save-button"]


def _maestro_press_probe(book_key: str) -> tuple[dict, str]:
    """`_built_target_probe_maestro`'s obligation, with a `press` act added on a control of its own — the smallest fixture that puts a book-stated `key=` through the mobile driver's own `pressKey` vocabulary rather than Playwright's."""
    oid = "okf:built-target-probe:maestro:press:1"
    navigation = _arrival_navigation()
    navigation["policy"]["driver"] = "mobile"
    navigation["policy"]["bundleId"] = "com.example.mobile-app"
    navigation["policy"]["launchScreen"] = _SCREEN
    press_node = f"{_SCREEN}#probe-field"
    context = _navigation_context(
        _page_obligation(oid, f"{_SCREEN}#probe",
                          locators={"selector": ["testID=probe-widget"]},
                          checks=[_visible("table:Things on file")],
                          fixtures=[
                              {"name": "seeded-ledger", "args": [], "provides": "a ledger"},
                          ],
                          acts=[_act("press", press_node,
                                     {"selector": ["testID=probe-field"]},
                                     locator="#probe-field", key=book_key)]),
        navigation=navigation,
        screen_routes={_SCREEN: "Probe"},
    )
    return context, oid


def test_a_documented_press_key_compiles_to_its_own_documented_spelling() -> None:
    """A book stated in ordinary title-case prose (`Enter`) is not the same string as Maestro's own lowercase `enter`, so the compiled flow must emit the documented spelling regardless of which casing the book happened to use — with no gap, since the physical key is real."""
    context, oid = _maestro_press_probe("Enter")
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == []
    (flow_text,) = result.files.values()
    assert '- pressKey: "enter"' in flow_text


def test_a_documented_multi_word_press_key_compiles_to_its_own_documented_spelling() -> None:
    """The same normalization holds for a two-word key: `Volume Up` in the book's own prose still resolves against Maestro's own `volume up` and is emitted spelled that way."""
    context, oid = _maestro_press_probe("Volume Up")
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == []
    (flow_text,) = result.files.values()
    assert '- pressKey: "volume up"' in flow_text


def test_an_already_canonical_press_key_round_trips_unchanged() -> None:
    """A book that already writes the documented spelling (`home`) is not a special case this canonicalization has to detour around — it normalizes to itself and compiles the same way."""
    context, oid = _maestro_press_probe("home")
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == []
    (flow_text,) = result.files.values()
    assert '- pressKey: "home"' in flow_text


def test_a_key_playwright_has_and_maestro_does_not_is_an_uncompilable_claim() -> None:
    """`Space` is a real Playwright key (several web books already state it) and is nowhere in Maestro's own `pressKey` table — the mobile driver cannot perform this claim, so it gaps `uncompilable-claim` naming the key, emits no `pressKey` line, and (the shared `whole = False`/`break` semantics the two neighbouring act gaps already use) withholds the rest of this obligation's flow rather than emitting a partial one."""
    context, oid = _maestro_press_probe("Space")
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    assert _gap_kinds(result.gaps, oid) == ["uncompilable-claim"]
    (gap,) = [g for g in result.gaps if g.obligation_id == oid]
    assert "Space" in gap.detail


def test_the_web_arm_still_compiles_a_press_space_key_unchanged() -> None:
    """The same `press(key="Space")` a mobile book cannot state is exactly what a web book already states and this repo's own Playwright arm has always compiled unchanged — proving this defect's fix is a fact about the *mobile* driver's own vocabulary, not a change to the `press` act itself, which both drivers still declare (`acts.py`)."""
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
                          acts=[_act("press", f"{_SCREEN}#name-field",
                                     {"selector": ["`input[name=\"name\"]`"]},
                                     locator="#name-field", key="Space")],
                          checks=[_located("#saved-banner", f"{_SCREEN}#saved-banner",
                                            {"selector": ["`#saved-banner`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert '.press("Space")' in source
    assert "unarranged-interaction-precondition" not in _gap_kinds(gaps, submit_oid)
    assert submit_oid in _covers(source)


def test_a_web_press_key_with_whitespace_is_uncompilable() -> None:
    """Playwright's own key vocabulary is open — any single character, a large named set, and `+`-joined modifier combos — so it cannot be checked against a closed table the way Maestro's `pressKey` is (`_maestro_press_key`'s 29-name table has no web counterpart on purpose)."""
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
                          acts=[_act("press", f"{_SCREEN}#name-field",
                                     {"selector": ["`input[name=\"name\"]`"]},
                                     locator="#name-field", key="volume up")],
                          checks=[_located("#saved-banner", f"{_SCREEN}#saved-banner",
                                            {"selector": ["`#saved-banner`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert ".press(" not in source
    uncompilable = [g for g in gaps if g.obligation_id == submit_oid
                    and g.kind == "uncompilable-claim"]
    assert len(uncompilable) == 1
    assert "volume up" in uncompilable[0].detail


def test_a_web_press_modifier_combo_key_compiles_unchanged() -> None:
    """A `+`-joined modifier combo (`Control+A`) is a real Playwright key with no whitespace in it anywhere, so the whitespace rule must not catch it — the rule is sound on exactly the fact that no single character, named key or combo ever contains a space, not on rejecting anything that looks unfamiliar."""
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
                          acts=[_act("press", f"{_SCREEN}#name-field",
                                     {"selector": ["`input[name=\"name\"]`"]},
                                     locator="#name-field", key="Control+A")],
                          checks=[_located("#saved-banner", f"{_SCREEN}#saved-banner",
                                            {"selector": ["`#saved-banner`"]})]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert source is not None
    ast.parse(source)
    assert '.press("Control+A")' in source
    assert "uncompilable-claim" not in _gap_kinds(gaps, submit_oid)
    assert submit_oid in _covers(source)


def test_the_mobile_arm_is_unaffected_by_the_web_whitespace_rule() -> None:
    """The whitespace rule is a fact about the *web* driver's own vocabulary — it must not leak into the mobile arm, which already has its own closed-vocabulary check (`_maestro_press_key`) and already accepts `volume up` as one of Maestro's own documented `pressKey` spellings."""
    context, oid = _maestro_press_probe("volume up")
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    assert _gap_kinds(result.gaps, oid) == []
    (flow_text,) = result.files.values()
    assert '- pressKey: "volume up"' in flow_text


def test_a_web_journey_step_with_a_whitespace_press_key_gaps_only_the_specific_claim() -> None:
    """A journey step whose `arrange:` names a `press` key with whitespace in it is refused for the same reason `_performed_lines` already refuses it standalone — the key names a Maestro spelling handed to the wrong driver."""
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
                         acts=[_act("press", f"{_SCREEN}#name-field",
                                    {"selector": ["#name-field"]},
                                    locator="#name-field", key="volume up")],
                         ) | {"required": False},
        _page_obligation(f"{_SCREEN}#open-link:carrier", f"{_SCREEN}#open-link",
                         locators={"selector": ["#open-link"]}, checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#save-button:carrier", f"{_SCREEN}#save-button",
                         locators={"selector": ["#save-button"]}, checks=[]) | {"required": False},
        _page_obligation(f"{_SCREEN}#name-field:carrier", f"{_SCREEN}#name-field",
                         locators={"selector": ["#name-field"]}, checks=[]) | {"required": False},
        navigation=_arrival_navigation(),
    )
    result = _compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal)
    uncompilable = [g for g in result.gaps if g.obligation_id == oid
                    and g.kind == "uncompilable-claim"]
    assert len(uncompilable) == 1
    assert "volume up" in uncompilable[0].detail
    assert "not a Playwright key" in uncompilable[0].detail
    assert "declares an arrangement this journey cannot make" not in uncompilable[0].detail
