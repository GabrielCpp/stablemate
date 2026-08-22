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

from ostler.qa.compile import cmd_compile_plan, compile_plan


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
