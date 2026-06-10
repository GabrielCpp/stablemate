"""Tests for branch evaluation guardrails: an unresolvable branch path (the
producing step returned an unexpected shape, a null, or nothing — a common LLM
failure mode) routes to the node's `default` instead of crashing the run; a
branch with no `default` raises an actionable error rather than a raw KeyError.

Run: ./.venv/bin/python tests/test_branch_guardrail.py   (or via pytest)
"""
from __future__ import annotations

from workhorse.graph.context import WorkflowContext
from workhorse.graph.nodes import BranchCondition, BranchNode
from workhorse.runner import branch as b


def _node(**kw) -> BranchNode:
    return BranchNode(type="branch", id="decide_qa", path="qa_result.status", **kw)


def test_resolved_value_matches_case():
    node = _node(cases={"passed": "done", "failed": "fix"})
    ctx = WorkflowContext({"qa_result": {"status": "passed"}})
    assert b.evaluate(node, ctx) == ("done", "passed")


def test_missing_key_routes_to_default():
    # qa_result has no 'status' key.
    node = _node(cases={"passed": "done"}, default="fix")
    ctx = WorkflowContext({"qa_result": {"notes": "..."}})
    assert b.evaluate(node, ctx) == ("fix", None)


def test_non_dict_intermediate_routes_to_default():
    # qa_result is a bare string — can't traverse '.status' (the reported crash).
    node = _node(cases={"passed": "done"}, default="fix")
    ctx = WorkflowContext({"qa_result": "failed"})
    assert b.evaluate(node, ctx) == ("fix", None)


def test_missing_top_level_key_routes_to_default():
    node = _node(cases={"passed": "done"}, default="fix")
    ctx = WorkflowContext({})  # qa_result never produced
    assert b.evaluate(node, ctx) == ("fix", None)


def test_unresolvable_without_default_raises_actionable_error():
    node = _node(cases={"passed": "done"})  # no default
    ctx = WorkflowContext({"qa_result": "failed"})
    try:
        b.evaluate(node, ctx)
        raise AssertionError("expected RuntimeError when path unresolvable and no default")
    except RuntimeError as e:
        msg = str(e)
        assert "decide_qa" in msg and "qa_result.status" in msg and "default" in msg
        # Must NOT leak as a raw KeyError.
        assert not isinstance(e, KeyError)


def test_resolved_value_no_match_no_default_still_raises():
    # Existing behavior preserved: a *resolved* value that matches nothing and has
    # no default is an error (distinct from the unresolved-path guardrail).
    node = _node(cases={"passed": "done"})
    ctx = WorkflowContext({"qa_result": {"status": "weird"}})
    try:
        b.evaluate(node, ctx)
        raise AssertionError("expected RuntimeError for no-match-no-default")
    except RuntimeError:
        pass


def test_conditions_still_evaluated_for_resolved_value():
    node = BranchNode(
        type="branch",
        id="guard",
        path="count",
        conditions=[BranchCondition(op=">=", value="3", next="halt")],
        default="loop",
    )
    assert b.evaluate(node, WorkflowContext({"count": "5"})) == ("halt", "5")
    assert b.evaluate(node, WorkflowContext({"count": "1"})) == ("loop", "1")


def test_get_dotpath_default_vs_raise():
    ctx = WorkflowContext({"a": {"b": 1}})
    assert ctx.get_dotpath("a.b") == 1
    assert ctx.has_dotpath("a.b") is True
    assert ctx.has_dotpath("a.c") is False
    assert ctx.get_dotpath("a.c", default="x") == "x"
    assert ctx.get_dotpath("a.b.c", default="x") == "x"  # traverse into non-dict
    # Without a default, the original raising behavior is preserved.
    for bad in ("a.c", "a.b.c"):
        try:
            ctx.get_dotpath(bad)
            raise AssertionError(f"expected KeyError for {bad}")
        except KeyError:
            pass


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
