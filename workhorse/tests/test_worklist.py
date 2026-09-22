"""Tests for the generic worklist primitive (workhorse/worklist.py)."""
from __future__ import annotations

import json
from pathlib import Path

from _fakes import present
from workhorse import worklist as wl


def _raw():
    return [
        {"id": "a", "status": "done", "order": 1, "payload": {"cat": "ui"}},
        {"id": "b", "status": "blocked", "order": 2, "payload": {"cat": "api"}},
        {"id": "c", "status": "pending", "order": 3, "payload": {"cat": "ui"}},
        {"id": "d", "status": "pending", "order": 4, "payload": {"cat": "api"}},
    ]


def _items():
    return [wl.WorkItem.model_validate(d) for d in _raw()]


def test_select_next_skips_done_and_blocked():
    got = present(wl.select_next(_items()))
    assert got.id == "c"


def test_active_item_is_preferred_for_crash_safe_repick():
    items = _items()
    items[3].status = "active"
    got = present(wl.select_next(items))
    assert got.id == "d", "an active item must be re-picked before a fresh pending one"


def test_skip_set_passes_over_an_item():
    got = present(wl.select_next(_items(), skip={"c"}))
    assert got.id == "d"


def test_drained_queue_returns_none():
    items = [wl.WorkItem(id="a", status="done"), wl.WorkItem(id="b", status="blocked")]
    assert wl.select_next(items) is None


def test_order_beats_list_order():
    items = [
        wl.WorkItem(id="late", status="pending", order=9),
        wl.WorkItem(id="early", status="pending", order=1),
    ]
    assert present(wl.select_next(items)).id == "early"


def test_custom_scheme_vocabulary():
    scheme = wl.Scheme(done=frozenset({"merged"}), blocked=frozenset({"held"}))
    items = [
        wl.WorkItem(id="a", status="merged"),
        wl.WorkItem(id="b", status="held"),
        wl.WorkItem(id="c", status="todo"),
    ]
    assert present(wl.select_next(items, scheme=scheme)).id == "c"


def test_counts_breakdown_and_composition():
    c = wl.counts(_items(), category_key="cat")
    assert c.total == 4
    assert c.done == 1 and c.blocked == 1 and c.pending == 2
    assert c.remaining == 3
    assert c.by_category == {"ui": 1, "api": 2}


def test_counts_without_category_key_has_empty_composition():
    c = wl.counts(_items())
    assert c.by_category == {}


def test_json_backend_roundtrip_mark_and_prune(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(_raw()))
    lst = wl.WorkList(wl.JsonBackend(path), category_key="cat")

    assert present(lst.select_next()).id == "c"
    assert lst.mark("c", "done") is True
    assert lst.mark("nonexistent", "done") is False
    assert present(lst.select_next()).id == "d"
    on_disk = json.loads(path.read_text())
    assert next(i for i in on_disk if i["id"] == "c")["status"] == "done"

    assert lst.prune("d") is True
    assert lst.select_next() is None


def test_json_backend_object_with_items_key(tmp_path):
    path = tmp_path / "board.json"
    path.write_text(json.dumps({"meta": {"v": 1}, "items": _raw()}))
    lst = wl.WorkList(wl.JsonBackend(path, items_key="items"))
    assert lst.mark("c", "done") is True
    saved = json.loads(path.read_text())
    assert saved["meta"] == {"v": 1}
    assert next(i for i in saved["items"] if i["id"] == "c")["status"] == "done"


def test_snapshot_is_label_ready(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(_raw()))
    lst = wl.WorkList(wl.JsonBackend(path), category_key="cat")
    snap = lst.snapshot(current="c")
    assert snap.current == "c"
    assert snap.progress == "1/4"
    assert snap.remaining == 3
    assert snap.composition == "2 api · 1 ui"


def test_missing_file_is_an_empty_queue(tmp_path):
    lst = wl.WorkList(wl.JsonBackend(tmp_path / "absent.json"))
    assert lst.items() == []
    assert lst.select_next() is None


def _mixed_raw():
    """One worklist holding three lists (epics, stories, fixes), the shape a run that tracks all its work in a single store would keep."""
    return [
        {"id": "E1", "kind": "epic", "status": "done", "order": 1},
        {"id": "E2", "kind": "epic", "status": "pending", "order": 2},
        {"id": "S1", "kind": "story", "status": "done", "order": 1},
        {"id": "S2", "kind": "story", "status": "pending", "order": 2},
        {"id": "S3", "kind": "story", "status": "pending", "order": 3},
        {"id": "F1", "kind": "fix", "status": "blocked", "order": 1},
    ]


def _mixed():
    return [wl.WorkItem.model_validate(d) for d in _mixed_raw()]


def test_select_next_scopes_to_a_kind():
    assert present(wl.select_next(_mixed())).id == "E2"
    assert present(wl.select_next(_mixed(), kind="story")).id == "S2"
    assert wl.select_next(_mixed(), kind="fix") is None


def test_counts_scope_by_kind_and_report_by_kind():
    cs = wl.counts(_mixed(), kind="story")
    assert cs.total == 3 and cs.done == 1 and cs.pending == 2
    call = wl.counts(_mixed())
    assert call.by_kind == {"epic": 1, "story": 2, "fix": 1}


def test_snapshot_scoped_to_a_kind_and_the_kinds_line():
    snap = wl.snapshot(_mixed(), current="S2", kind="story")
    assert snap.progress == "1/3"
    assert wl.snapshot(_mixed()).kinds == "1 epic · 1 fix · 2 story"


def test_mark_and_prune_disambiguate_by_kind(tmp_path):
    """An id that recurs across lists (an epic and a story both "A1") is marked/pruned on the right list when kind is given."""
    items = [
        {"id": "A1", "kind": "epic", "status": "pending"},
        {"id": "A1", "kind": "story", "status": "pending"},
    ]
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(items))
    lst = wl.WorkList(wl.JsonBackend(path))

    assert lst.mark("A1", "done", kind="story") is True
    on_disk = json.loads(path.read_text())
    story = next(i for i in on_disk if i["kind"] == "story")
    epic = next(i for i in on_disk if i["kind"] == "epic")
    assert story["status"] == "done" and epic["status"] == "pending"

    assert lst.prune("A1", kind="epic") is True
    remaining = json.loads(path.read_text())
    assert [i["kind"] for i in remaining] == ["story"]


def test_items_filter_by_kind(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(_mixed_raw()))
    lst = wl.WorkList(wl.JsonBackend(path))
    assert {i.id for i in lst.items(kind="epic")} == {"E1", "E2"}
    assert len(lst.items()) == 6


def test_a_round_trip_adds_no_key_the_workflow_never_wrote(tmp_path):
    """The file belongs to the workflow."""
    path = tmp_path / "units.json"
    path.write_text(json.dumps({"units": [
        {"id": "u1", "path": "src/a.py", "status": "pending"},
        {"id": "u2", "path": "src/b.py", "status": "pending"},
    ]}))
    lst = wl.WorkList(wl.JsonBackend(path, items_key="units"))
    assert lst.mark("u1", "assessed") is True

    saved = json.loads(path.read_text())["units"]
    assert saved == [
        {"id": "u1", "path": "src/a.py", "status": "assessed"},
        {"id": "u2", "path": "src/b.py", "status": "pending"},
    ], saved
    assert getattr(lst.items()[0], "path") == "src/a.py"


def test_stateless_snapshot_matches_the_worklist_method():
    """The module-level snapshot (for stores that aren't a Backend — coder hands items in directly) produces the same label-ready shape as WorkList.snapshot."""
    items = _items()
    snap = wl.snapshot(items, current="c", category_key="cat")
    assert snap.current == "c"
    assert snap.progress == "1/4"
    assert snap.remaining == 3
    assert snap.composition == "2 api · 1 ui"
    assert snap.counts.done == 1
    empty = wl.snapshot([])
    assert empty.progress == "0/0" and empty.remaining == 0


class CountingBackend:
    """A backend that remembers how many times a caller wrote it."""

    def __init__(self, items):
        self.items = items
        self.saves = 0

    def load(self):
        return [it.model_copy(deep=True) for it in self.items]

    def save(self, items):
        self.saves += 1
        self.items = [it.model_copy(deep=True) for it in items]


def _list(items=None):
    backend = CountingBackend(items if items is not None else _items())
    return wl.WorkList(backend=backend), backend


def test_claim_agrees_with_select_next_on_the_first_item():
    items = _items()
    assert [it.id for it in wl.claim(items, 2)] == ["c", "d"]
    assert present(wl.select_next(items)).id == "c"


def test_claim_takes_active_before_pending():
    items = _items()
    items[3].status = "active"
    assert [it.id for it in wl.claim(items, 2)] == ["d", "c"]


def test_claim_returns_fewer_than_asked_when_the_queue_is_shorter():
    assert [it.id for it in wl.claim(_items(), 9)] == ["c", "d"]


def test_claim_of_nothing_is_empty():
    assert wl.claim(_items(), 0) == []


def test_claim_honours_skip_and_kind():
    assert [it.id for it in wl.claim(_items(), 2, skip={"c"})] == ["d"]
    items = [
        wl.WorkItem(id="a", status="pending", kind="fix"),
        wl.WorkItem(id="b", status="pending", kind="audit"),
    ]
    assert [it.id for it in wl.claim(items, 2, kind="audit")] == ["b"]


def test_claim_marks_active_and_writes_once():
    work, backend = _list()
    taken = work.claim(2)
    assert [it.id for it in taken] == ["c", "d"]
    assert backend.saves == 1
    assert [it.status for it in work.items() if it.id in ("c", "d")] == [
        "active",
        "active",
    ]


def test_claim_on_a_drained_queue_writes_nothing():
    work, backend = _list([wl.WorkItem(id="a", status="done")])
    assert work.claim(3) == []
    assert backend.saves == 0


def test_a_crashed_claim_retakes_the_same_rows():
    work, backend = _list()
    first = [it.id for it in work.claim(2)]
    assert [it.id for it in work.claim(2)] == first


def test_settle_sets_every_named_row_in_one_write():
    work, backend = _list()
    assert work.settle(["c", "d"], "done") == 2
    assert backend.saves == 1
    assert {it.id for it in work.items() if it.status == "done"} == {"a", "c", "d"}


def test_settle_is_idempotent():
    work, backend = _list()
    assert work.settle(["c"], "done") == 1
    assert work.settle(["c"], "done") == 1


def test_settle_ignores_an_unknown_id_and_an_empty_list():
    work, backend = _list()
    assert work.settle(["nobody"], "done") == 0
    assert work.settle([], "done") == 0
    assert backend.saves == 0


def test_settle_scoped_by_kind_leaves_the_other_kind_alone():
    work, backend = _list([
        wl.WorkItem(id="a", status="pending", kind="fix"),
        wl.WorkItem(id="a", status="pending", kind="audit"),
    ])
    assert work.settle(["a"], "done", "audit") == 1
    assert [it.status for it in work.items("fix")] == ["pending"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            import inspect
            if "tmp_path" in inspect.signature(fn).parameters:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
