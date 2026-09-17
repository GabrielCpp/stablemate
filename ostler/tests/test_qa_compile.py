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
    _unobservable_gap,
    cmd_compile_plan as _cmd_compile_plan,
    compile_plan as _compile_plan,
    compile_plan_gaps as _compile_plan_gaps,
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
    base = {
        "id": oid,
        "source": "docs/features/demo/api.md",
        "requirement": "writes the record and answers with it",
        "required": True,
        "locators": {"route": ["POST /api/things"]},
        "checksDeclared": [],
    }
    base.update(extra)
    return base


def _context(*obligations: dict) -> dict:
    return {"story": "demo-story", "obligations": list(obligations)}


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
    assert "qa.http.post" in source
    assert "expect_status=201" in source


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
        "code": "unresolved-precondition",
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


def test_a_missing_request_body_is_an_unresolved_precondition() -> None:
    oid = "okf:docs/features/demo/globex.md#post-things:does:1"
    context = _context(
        _obligation(
            oid,
            checksDeclared=[_check()],
            fixturesDeclared=[{"name": "seeded-ledger", "args": [], "provides": "a ledger"}],
        )
    )
    _source, gaps = compile_plan_gaps(context, story="demo-story")
    assert "unresolved-precondition" in _gap_kinds(gaps, oid)


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
                      checks: list[dict] | None = None) -> dict:
    return {
        "id": oid,
        "node": node,
        "source": source,
        "surface": surface,
        "requirement": "shows what the screen promises",
        "required": True,
        "locators": locators or {},
        "checksDeclared": checks if checks is not None else [
            {"call": "it", "name": "visible", "args": {"locator": "irrelevant"}},
        ],
    }


def _visible(locator: str) -> dict:
    return {"call": "it", "name": "visible", "args": {"locator": locator}}


def _navigation_context(*obligations: dict, navigation: dict) -> dict:
    ctx = _context(*obligations)
    ctx["navigation"] = navigation
    return ctx


def _arrival_navigation(source: str = _SCREEN, surface: str = "policy", *,
                         unreachable: list[str] | None = None,
                         undeclared: list[str] | None = None) -> dict:
    """One surface, one screen, reachable with an empty hop list (it is the route's own root)."""
    return {
        surface: {
            "start": source,
            "surface": surface,
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


def test_a_states_component_produces_a_gap_not_a_scenario() -> None:
    """A component naming `states:` compiles to nothing — no scenario, arrival or otherwise —
    only an `unresolved-precondition` gap quoting the `states:` text verbatim."""
    node = f"{_SCREEN}#coverage-type-select"
    oid = "okf:new-policy:coverage-type-select:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["combobox"], "name": ["Coverage type"],
                                    "states": ["opens on `auto`."]},
                          checks=[_visible("combobox:Coverage type")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "combobox:Coverage type" not in source
    kinds = _gap_kinds(gaps, oid)
    assert kinds == ["unresolved-precondition"]
    [gap] = [g for g in gaps if g.obligation_id == oid]
    assert "opens on `auto`." in gap.detail


def test_states_wins_over_exclusive_with_when_a_component_carries_both() -> None:
    """`vehicle-vin-field` in the real `new-policy.md` fixture carries *both* `states:` and
    `exclusive-with:` — a shape the ruling set's partition list did not anticipate as
    overlapping. This pins the resolution: `states:` is the stronger claim (it blocks compiling
    any scenario outright) and is checked first, so the component is gapped, never isolated into
    its own exclusive-with scenario."""
    node = f"{_SCREEN}#vehicle-vin-field"
    oid = "okf:new-policy:vehicle-vin-field:visible:1"
    context = _navigation_context(
        _page_obligation(oid, node,
                          locators={"role": ["textbox"], "name": ["Vehicle VIN"],
                                    "exclusiveWith": ["[property-address-field](#property-address-field)"],
                                    "states": ["present only while the coverage type is `auto`."]},
                          checks=[_visible("textbox:Vehicle VIN")]),
        navigation=_arrival_navigation(),
    )
    source, gaps = compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert "textbox:Vehicle VIN" not in source
    assert "@scenario(" not in source
    assert _gap_kinds(gaps, oid) == ["unresolved-precondition"]


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
    assert 'http_status(path="' in gap.detail


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
    same page/HTTP mix Playwright declares either."""
    assert PLAYWRIGHT.observes == frozenset({"page", "response", "body"})
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
                "start": "", "surface": "policy", "entryUrl": _BASE_URL,
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
            "api-service": {"entryUrl": "http://localhost:18101"},
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
            "alpha-service": {"entryUrl": "http://localhost:18201"},
            "zulu-service": {"entryUrl": "http://localhost:18202"},
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
    context["navigation"] = {}
    source, gaps = _compile_plan_gaps(context, story="demo-story")
    ast.parse(source)
    assert oid not in _covers(source)
    assert "qa.http.post" not in source
    assert _gap_kinds(gaps, oid) == ["undeclared-entry-url"]
    # The obligation was dropped before target emission, so nothing compiles a target for it.
    assert "target(" not in source


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
