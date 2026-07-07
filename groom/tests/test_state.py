"""Tests for groom.state.prune_workflows — the reconciliation step that drops
workflows whose containers no longer exist (the deletion half of /refresh and
startup scan, which otherwise only ever add).

Run: uv run pytest tests/test_state.py
"""
from __future__ import annotations

from groom import state
from groom.models import WorkflowContainer


def _reset() -> None:
    state.WORKFLOWS.clear()
    state._gate_locks.clear()


def _wf(cid: str) -> None:
    state.WORKFLOWS[cid] = WorkflowContainer(container_id=cid, name=cid)


def test_prune_drops_absent_keeps_present():
    _reset()
    _wf("aaa")
    _wf("bbb")
    _wf("ccc")

    removed = state.prune_workflows({"aaa", "ccc"})

    assert removed == ["bbb"]
    assert set(state.WORKFLOWS) == {"aaa", "ccc"}


def test_prune_empty_present_removes_everything():
    _reset()
    _wf("aaa")
    removed = state.prune_workflows(set())
    assert removed == ["aaa"]
    assert state.WORKFLOWS == {}


def test_prune_also_forgets_gate_locks_of_removed():
    _reset()
    _wf("aaa")
    # Materialize a lock for a gate on the soon-to-be-removed container.
    state.gate_lock("aaa", "docs/gate.md")
    assert any(k.startswith("aaa::") for k in state._gate_locks)

    state.prune_workflows(set())

    assert not any(k.startswith("aaa::") for k in state._gate_locks)


def test_prune_is_noop_when_all_present():
    _reset()
    _wf("aaa")
    _wf("bbb")
    removed = state.prune_workflows({"aaa", "bbb"})
    assert removed == []
    assert set(state.WORKFLOWS) == {"aaa", "bbb"}


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
