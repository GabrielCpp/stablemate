"""What a plan compiled from the book alone may and may not claim.

A plan an author writes while reading the implementation tests what the code already does.
These pin the alternative: the book's own `verify:` grammar, compiled into assertions with
no source file opened — and, just as load-bearing, what the compiler refuses to invent when
the book is silent.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ostler.qa.compile import Gap, cmd_compile_plan, compile_plan, compile_plan_gaps


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
    source = compile_plan(context, story="demo-story")
    ast.parse(source)
    assert "TODO(arrange)" in source


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
    is book debt, filtered out before the body is ever asked to render one — so no gap, and no
    scenario, is emitted for it at all."""
    oid = "okf:docs/features/demo/globex.md#post-things:does:2"
    context = _context(_obligation(oid))
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert _gap_kinds(gaps, oid) == []
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
    as `uncompilable-claim` rather than silently asserting on `qa.page`/the document body."""
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
    assert len(interactions) == 1
    # No addressable subject for the interaction's own `visible(...)` claim, so it is a TODO
    # scaffold and a gap, never a compiled `qa.verify(...)` call against a guessed operand.
    assert "heading:Policy PN-1001" not in interactions[0]
    assert f"no addressable subject for {interaction_oid}" in interactions[0]
    assert "create-policy-button" in interactions[0] or "button:Create policy" not in interactions[0]
    assert "uncompilable-claim" in _gap_kinds(gaps, interaction_oid)


def test_a_subject_only_verb_on_a_page_obligation_is_a_gap_not_a_silent_drop() -> None:
    """`unchanged` observes a subject (a before/after pair), not the rendered page — a
    Playwright driver cannot serve it. Before the fix this row was dropped with a bare
    `continue`: no call, no gap, no note. It must now surface as a real `uncompilable-claim`
    gap naming the verb, while the obligation's own `visible(...)` row still compiles."""
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
    assert "table:Policies on file" in source
    kinds = _gap_kinds(gaps, oid)
    assert "uncompilable-claim" in kinds
    [gap] = [g for g in gaps if g.obligation_id == oid and g.kind == "uncompilable-claim"]
    assert "unchanged" in gap.detail
    assert "not observable from a Playwright driver" in gap.detail


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
                "start": "", "surface": "policy",
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
