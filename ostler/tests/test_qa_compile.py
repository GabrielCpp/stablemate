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


def test_a_subject_check_wanting_a_before_after_pair_is_an_uncompilable_claim() -> None:
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
    assert "uncompilable-claim" in _gap_kinds(gaps, oid)


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
